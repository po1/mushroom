import bisect
from collections.abc import Iterable
import queue
import logging
import re
import threading
import time

from . import util
from .commands import CustomCommand
from .commands import WrapperCommand
from .db import db, DbProxy
from .object import BaseObject, proxify
from .register import register


class Game:
    def __init__(self) -> None:
        self._timers = []  # ordered by increasing expiration time
        self._event_queue = queue.SimpleQueue()
        self._loop_thread = threading.Thread(target=self._loop)
        self._loop_thread.daemon = True
        self._loop_thread.start()

    def __reduce__(self):
        return "game"  # name of the global instance for pickling

    def __dir__(self) -> Iterable[str]:
        return [
            x
            for x in list(self.__dict__) + list(self.__class__.__dict__)
            if not x.startswith("_")
        ]

    def schedule(self, when, event):
        """Schedules an event to happen in <when> seconds."""
        bisect.insort(self._timers, (time.time() + when, event))
        self._event_queue.put(None)  # wake up

    def _next_timeout(self):
        # wake up the thread every second, just, you know, for fun.
        if not self._timers:
            return 1.0
        return min(self._timers[0][0] - time.time(), 1.0)

    def _loop(self):
        while True:
            try:
                event = self._event_queue.get(timeout=self._next_timeout())
            except queue.Empty:
                pass
            else:
                self._run_event(event)

            self._handle_timers()

    def _run_event(self, event):
        if event is not None:
            try:
                event()  # self-dispatching events are tight
            except Exception as e:
                logging.warning(
                    "exception in event callback: %s", repr(event), exc_info=e
                )

    def _handle_timers(self):
        now = time.time()
        while self._timers:
            when, evt = self._timers[0]
            if when > now:
                return
            del self._timers[0]
            self._run_event(evt)


game = Game()


class MRObject(BaseObject):
    """
    Base database object.
    """

    fancy_name = "object"
    fw_cmds = {}
    default_description = "An abstract object."

    def __init__(self, name):
        super().__init__(name)
        self.description = self.default_description
        self.custom_cmds = {}
        self._initcmds()
        self.flags = []

    def _initcmds(self):
        self.fwcmds = [
            WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()
        ]

    def __dir__(self):
        return [k for k in self.__dict__ if not k.startswith("_")]

    def __repr__(self):
        return f"<#{self.id} {self.fancy_name} {self.name}>"

    def add_cmd(self, cmd):
        self.custom_cmds[cmd.name] = cmd

    def __getstate__(self):
        odict = dict(self.__dict__)
        del odict["fwcmds"]
        return odict

    def __setstate__(self, odict):
        self.__dict__.update(odict)
        self._initcmds()
        self._checkfields()

    @classmethod
    def _get_dummy(cls):
        return cls(None)

    def _checkfields(self):
        dummy = self._get_dummy()
        for d in dummy.__dict__:
            if d not in self.__dict__:
                setattr(self, d, getattr(dummy, d))

    @property
    def id(self):
        return db.get_id(self)

    @property
    def cmds(self):
        return self.fwcmds + list(self.custom_cmds.values())


@register
class Config(MRObject):
    fancy_name = "config"
    default_description = "The main game config object. No big deal."

    def __init__(self, name="config"):
        super().__init__(name)
        self.default_room = None


@register
class MRThing(MRObject):
    """
    Things that are not players or rooms.
    Usually common objects, usable or not.
    """

    fancy_name = "thing"
    default_description = "A boring non-descript thing"

    def __init__(self, name):
        self.powers = []
        super().__init__(name)


@register
class MRRoom(MRObject):
    """
    The parent class for every room of
    the world. Any room should inherit
    from this class.
    """

    fancy_name = "room"
    fw_cmds = {
        "say": "cmd_say",
        "emit": "cmd_emit",
        "take": "cmd_take",
        "drop": "cmd_drop",
    }
    default_description = "A blank room."

    def __init__(self, name):
        self.contents = []
        self.exits = []
        super(MRRoom, self).__init__(name)

    def emit(self, msg):
        for thing in filter(util.is_player, self.contents):
            thing.send(msg)

    def oemit(self, player, msg):
        for pl in filter(util.is_player, self.contents):
            if pl != player:
                pl.send(msg)

    def cmd_say(self, player, rest):
        """say <stuff>: say something out loud where you are."""
        self.emit(player.name + " says: " + rest)

    def cmd_emit(self, player, rest):
        """emit <stuff>: broadcast text in the current room."""
        self.emit(rest.replace("\\n", "\n").replace("\\t", "\t"))

    def cmd_take(self, caller, query):
        def doit(obj):
            if obj is caller:
                return caller.emit(
                    f"{caller.name} tries to fold themselves into their own pocket, but fails."
                )
            if "big" in obj.flags:
                return caller.emit(f"{obj.name} is too big.")
            util.moveto(obj, caller)
            self.emit(f"{caller.name} puts {obj.name} in their pocket.")

        util.find_and_do(
            caller,
            query,
            doit,
            self.contents,
            noarg="Take what?",
            notfound="Can't see a thing named that here",
        )

    def cmd_drop(self, caller, query):
        def doit(obj):
            util.moveto(obj, caller.room)
            self.emit(
                f"{caller.name} takes {obj.name} out of their pocket and leaves it."
            )

        util.find_and_do(
            caller,
            query,
            doit,
            caller.contents,
            noarg="Take what?",
            notfound="You don't have that in your pockets.",
        )


@register
class MRPlayer(MRObject):
    """
    Basic Player.
    Other player classes derive from this
    """

    fancy_name = "player"
    fw_cmds = {
        "look": "cmd_look",
        "go": "cmd_go",
        "describe": "cmd_describe",
    }
    default_description = "A non-descript citizen."

    def __init__(self, name):
        self.client = None
        self._parent = None
        self.powers = []
        self.contents = []
        super(MRPlayer, self).__init__(name)

        if not (confs := db.list_all(Config)):
            db.add(Config())
            # First player gets all powers. Dibs!
            self.powers.append(God())
        elif (default_room := confs[0].default_room) is not None:
            util.moveto(self, default_room)

    def __getstate__(self):
        odict = super().__getstate__()
        del odict["client"]
        return odict

    def __setstate__(self, odict):
        super().__setstate__(odict)
        self.client = None

    @property
    def room(self):
        return getattr(self, "_parent", None)

    @property
    def cmds(self):
        c = super().cmds
        for p in self.powers:
            c += p.cmds
        for thing in self.contents:
            if util.is_thing(thing):
                c += thing.cmds
                for p in getattr(thing, "powers", []):
                    c += p.cmds
        if self.room is not None and util.is_room(self.room):
            c += self.room.cmds
            for thing in self.room.contents:
                if util.is_thing(thing):
                    c += thing.cmds
        return c

    def send(self, msg):
        if self.client is not None:
            self.client.send(msg)

    def emit(self, msg):
        if self.room is not None:
            self.room.emit(msg)

    def reachable_objects(self):
        objs = list(self.contents)
        if self.room is not None:
            objs += [self.room] + self.room.contents
        return objs

    def find_doit(self, rest, dofun, **kwargs):
        util.find_and_do(
            self,
            rest,
            dofun,
            self.reachable_objects(),
            short_names=util.player_snames(self),
            **kwargs,
        )

    def exec_env(self):
        import mushroom

        return {
            "game": game,
            "db": DbProxy(db),
            # "unsafe" useful stuff (nothing is really safe)
            "world": mushroom.world,
            "util": mushroom.util,
            "re": re,
        }

    def cmd_describe(self, player, query):
        """describe <object> <description>: give a description to a room, player or thing."""
        if query is None:
            return self.send("Describe what?")
        what, description = re.match(r"(\w+) (.*)", query).groups()

        def doit(thing):
            thing.description = description.replace("\\n", "\n").replace("\\t", "\t")
            self.send("Added description of {}".format(thing.name))

        self.find_doit(what, doit)

    def cmd_go(self, caller, query):
        """go [to] <place>: move to a different place."""
        if query is None:
            return self.send("Go where?")
        place = re.match(r"(?:to )?(.*)", query).group(1)

        if caller.room is None:
            self.send("You're nowhere. And can't go anywhere :'(")
            return

        def doit(arg):
            self.room.emit(self.name + " has gone to " + arg.name)
            arg.emit(self.name + " arrives from " + self.room.name)
            util.moveto(self, arg)
            self.cmd_look(self, "here")

        util.find_and_do(
            caller,
            place,
            doit,
            caller.room.exits,
            notfound="Don't know this place. Is it in Canada?",
        )

    def cmd_look(self, player, query):
        """look [object]: see descriptions of things, people or places."""

        def doit(arg):
            if arg is None:
                self.send("You only see nothing. A lot of nothing.")
                return
            self.send(f"\033[34m{arg.name}\033[0m: {arg.description}")
            if hasattr(arg, "contents") and "opaque" not in arg.flags:
                self.send("")  # extra newline
                if arg.contents:
                    self.send("Contents:")
                for thing in arg.contents:
                    self.send(" - " + thing.name)
            if hasattr(arg, "exits") and "opaque" not in arg.flags:
                self.send("")  # extra newline
                if arg.exits:
                    self.send("Nearby places:")
                for room in arg.exits:
                    self.send(" - " + room.name)

        if self.room is None:
            notfound = "You see nothing but you."
        else:
            notfound = "You see nothing like '{}' here."
        util.find_and_do(
            player,
            query,
            doit,
            self.reachable_objects(),
            short_names=util.player_snames(self, allow_no_room=True),
            arg_default="here",
            notfound=notfound,
        )


class MRPower:
    fw_cmds = {}

    def __init__(self):
        self.initcommands()

    def __repr__(self):
        return f"<power {self.__class__.__name__}>"

    def __setstate__(self, odict):
        self.initcommands()

    def __getstate__(self):
        odict = dict(self.__dict__)
        del odict["fwcmds"]
        return odict

    def initcommands(self):
        self.fwcmds = [
            WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()
        ]

    @property
    def cmds(self):
        return self.fwcmds


class Engineer(MRPower):
    fw_cmds = {
        "eval": "cmd_eval",
        "exec": "cmd_exec",
        "examine": "cmd_examine",
        "setattr": "cmd_setattr",
        "delattr": "cmd_delattr",
        "cmd": "cmd_cmd",
        "setflag": "cmd_setflag",
        "resetflag": "cmd_resetflag",
    }

    def _exec_env(self, caller):
        return {
            "self": proxify(caller),
            "find": lambda w: proxify(
                util.match_list(w, caller.reachable_objects())[0]
            ),
            **caller.exec_env(),
        }

    def cmd_eval(self, caller, rest):
        """eval <string>: evaluate the string as raw code."""
        try:
            caller.send(repr(eval(rest, self._exec_env(caller))))
        except Exception as e:
            cls = e.__class__.__name__
            caller.send(f"{cls}: {e}")

    def cmd_exec(self, caller, rest):
        """exec <string>: execute raw code."""
        try:
            exec(util.unescape(rest), self._exec_env(caller))
        except Exception as e:
            cls = e.__class__.__name__
            caller.send(f"{cls}: {e}")

    def cmd_examine(self, caller, query):
        """examine <object>: display commands and attributes of an object.
        <object> can be a # database ID."""
        if query is None:
            return caller.send("Examine what?")

        def doit(obj):
            what = proxify(obj)
            caller.send(f"{what}:")
            caller.send(
                "\n".join(f"  {k}: {repr(getattr(what, k))}" for k in dir(what))
            )

        if (m := re.match(r"#(\d+)", query)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find_doit(query, doit)

    def cmd_setattr(self, caller, query):
        """setattr <object> <attribute> <value>: set an attribute on an object.
        <object> can be a # database ID.
        <value> can be a # database ID, otherwise it is a string."""
        if (
            query is None
            or (match := re.match(r"(#\d+|\w+) ([^ ]+) (.*)", query)) is None
        ):
            return caller.send("Try help setattr")

        target, attr, value = match.groups()
        if (match := re.match(r"#(\d+)", value)) is not None:
            value = db.get(int(match.group(1)))

        def doit(obj):
            setattr(obj, attr, value)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find_doit(target, doit)

    def cmd_delattr(self, caller, query):
        """delattr <object> <attribute>: delete an attribute on an object.
        <object> can be a # database ID."""
        if query is None or (match := re.match(r"(#\d+|\w+) ([^ ]+)", query)) is None:
            return caller.send("Try help delattr")

        target, attr = match.groups()

        def doit(obj):
            delattr(obj, attr)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find_doit(target, doit)

    def cmd_cmd(self, caller, query):
        """cmd <object> <cmd> <code>: add a command to an object."""
        if (
            query is None
            or (match := re.match(r"((?:\w+)|(?:#\d+)) ([^ ]+) (.*)", query)) is None
        ):
            caller.send("Try 'help cmd'. Haha.")
            return
        target, cmd, txt = match.groups()
        txt = re.sub(r"\\.", lambda x: {"\\n": "\n", "\\\\": "\\"}[x.group(0)], txt)

        def doit(thing):
            thing.add_cmd(CustomCommand(cmd, txt, thing))
            caller.send(f"Added command {cmd} to {thing.name}")

        if (m := re.match("#(\d+)", target)) is not None:
            doit(db.get(int(m.group(1))))
        else:
            caller.find_doit(target, doit)

    def cmd_setflag(self, caller, query):
        """setflag <object> <flag>: set a flag on an object.
        <object> can be a # database ID."""
        if query is None or (match := re.match(r"(#\d+|\w+) (.*)", query)) is None:
            return caller.send("Try help setflag")

        target, flag = match.groups()

        def doit(obj):
            if not flag in obj.flags:
                obj.flags.append(flag)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find_doit(target, doit)

    def cmd_resetflag(self, caller, query):
        """resetflag <object> <flag>: reset a flag on an object.
        <object> can be a # database ID."""
        if query is None or (match := re.match(r"(#\d+|\w+) (.*)", query)) is None:
            return caller.send("Try help setflag")

        target, flag = match.groups()

        def doit(obj):
            if flag in obj.flags:
                obj.flags.remove(flag)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find_doit(target, doit)


class Digger(MRPower):
    fw_cmds = {
        "dig": "cmd_dig",
    }

    def cmd_dig(self, caller, query):
        """dig <room name>: make a new room."""
        if not query:
            return caller.send("Dig what? Try help dig")
        room = MRRoom(query)
        db.add(room)
        if caller.room is None:
            caller.send("In a flash of darkness, a new place appears around you.")
            caller.cmd_teleport(caller, query)
            return
        room.exits.append(caller.room)
        caller.room.exits.append(room)
        caller.room.emit(f"{caller.name} digs a hole that leads to {room.name}")


class SuperDigger(Digger):
    fw_cmds = {
        "link": "cmd_link",
        "unlink": "cmd_unlink",
        "teleport": "cmd_teleport",
        **Digger.fw_cmds,
    }

    def cmd_link(self, caller, query):
        """link [to] <place>: open an exit towards the place."""
        if caller.room is None:
            return caller.send("Bawoops, you're nowhere.")
        if query is None:
            return caller.send("Link what?")
        where = re.match(r"(?:to )?(.*)", query).group(1)

        def doit(arg):
            caller.room.exits.append(arg)
            caller.room.emit(f"{caller.name} opens a new path towards {arg.name}")

        util.find_and_do(
            caller,
            where,
            doit,
            db.list_all(MRRoom),
            notfound="Don't know this place. Is it in Canada?",
        )

    def cmd_unlink(self, caller, rest):
        """unlink <place>: remove the exit to that place."""
        if caller.room is None:
            return caller.send("There's nothing here.")

        def doit(arg):
            caller.room.exits.remove(arg)
            caller.room.emit(f"{caller.name} removed the exit to {arg.name}")

        util.find_and_do(
            caller,
            rest,
            doit,
            caller.room.exits,
            noarg="Unlink what?",
            notfound="This room ain't connected to Canada.",
        )

    # it makes sense to keep this with link, since it can open an exit to anywhere anyway
    def cmd_teleport(self, caller, query):
        """teleport [to] <place>: place can be a # database ID"""
        if query is None:
            return caller.send("To where?")
        place = re.match(r"(?:to )?(.*)", query).group(1)

        def doit(room):
            caller.emit(f"{caller.name} vanishes. Gone.")
            util.moveto(caller, room)
            caller.cmd_look(caller, "here")
            room.emit(f"{caller.name} pops into the room. Poof.")

        if (m := re.match(r"#(\d+)", place)) is not None:
            room = db.get(int(m.group(1)))
            if not util.is_room(room):
                return caller.send(f"{room} is not a room!")
            return doit(room)

        util.find_and_do(
            caller,
            place,
            doit,
            db.list_all(MRRoom),
            notfound="Don't know this place. Is it in Canada?",
        )


class Maker(MRPower):
    fw_cmds = {
        "make": "cmd_make",
        "destroy": "cmd_destroy",
    }

    def cmd_make(self, caller, query):
        """make <thing name>: make things. Just regular things."""
        if caller.room is None:
            return caller.send("There is nowehere to make things into.")
        name = query
        thing = MRThing(name)
        db.add(thing)
        util.moveto(thing, caller.room)
        caller.room.emit(f"{caller.name} makes {name} appear out of thin air.")

    def cmd_destroy(self, caller, query):
        """destroy <thing>: destroy things. Anything, really."""
        if query is None:
            return caller.send("Destroy what?")

        def doit(thing):
            if util.is_room(thing):
                thing.emit(f"{caller.name} blew up the place!")
                for p in filter(util.is_player, thing.contents):
                    p.send("You fall into the void of nothingness.")
                    util.moveto(p, None)
            else:
                caller.emit(caller.name + " violently destroyed " + thing.name + "!")
                util.moveto(thing, None)
            db.remove(thing)
            if util.is_player(thing):
                if thing.client is not None:
                    thing.client.player = None
                    thing.send(
                        "Your character has been slain. You were kicked out of it"
                    )

        caller.find(query, then=doit)


class God(Engineer, Maker, SuperDigger):
    fw_cmds = {
        **Engineer.fw_cmds,
        **Maker.fw_cmds,
        **SuperDigger.fw_cmds,
    }
