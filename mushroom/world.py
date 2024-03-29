import bisect
from collections.abc import Iterable
import queue
import itertools
import logging
import re
import threading
import time

from . import util
from .commands import CustomCommand, RegexpAction, WrapperCommand, ActionFailed
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

    def has_flag(self, flag):
        return flag in self.flags

    def _initcmds(self):
        self._fwcmds = [
            WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()
        ]

    def __dir__(self):
        return [k for k in self.__dict__ if not k.startswith("_")]

    def __repr__(self):
        return f"<#{self.id} {self.fancy_name} {self.name}>"

    def __str__(self):
        return self.name

    def __getstate__(self):
        odict = dict(self.__dict__)
        del odict["_fwcmds"]
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
        self.location = None
        self.powers = []
        super().__init__(name)

    def __setstate__(self, odict):
        if "location" not in odict:
            odict["location"] = odict.pop("_parent", None)
        super().__setstate__(odict)


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
        super().__init__(name)

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
        if query is None:
            raise ActionFailed("Take what?")

        def doit(obj):
            if obj is caller:
                return caller.emit(
                    f"{caller.name} tries to fold themselves into their own pocket, but fails."
                )
            if "big" in obj.flags:
                raise ActionFailed(f"{obj} is too big.")

            util.moveto(obj, caller)
            self.emit(f"{caller.name} puts {obj.name} in their pocket.")

        util.find(query, objects=caller.location.contents, then=doit)

    def cmd_drop(self, caller, query):
        if query is None:
            raise ActionFailed("Drop what?")

        def doit(obj):
            util.moveto(obj, caller.location)
            self.emit(
                f"{caller.name} takes {obj.name} out of their pocket and leaves it."
            )

        util.find(
            query,
            objects=caller.contents,
            notfound=f"There's nothing like '{query}' in your pockets.",
            then=doit,
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
        self.location = None
        self.powers = []
        self.contents = []
        super().__init__(name)

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
        if "location" not in odict:
            odict["location"] = odict.pop("_parent", None)
        super().__setstate__(odict)
        self.client = None

    def has_flag(self, flag):
        powerflags = itertools.chain(*(p.flags for p in self.get_powers()))
        return flag in self.flags or flag in powerflags

    def get_powers(self):
        pows = list(self.powers)
        for thing in self.contents:
            if not util.is_thing(thing):
                continue
            pows.extend(thing.powers)
        return pows

    @property
    def room(self):
        return getattr(self, "location", None)

    @property
    def cmds(self):
        fw_cmds = list(self._fwcmds)
        custom_cmds = list(self.custom_cmds.values())
        for p in self.get_powers():
            fw_cmds += p._fwcmds  # no custom commands on powers yet

        def addthingcmds(container):
            for thing in container.contents:
                if util.is_thing(thing):
                    fw_cmds.extend(thing._fwcmds)
                    custom_cmds.extend(thing.custom_cmds.values())

        addthingcmds(self)
        if self.location is not None:
            addthingcmds(self.location)
            fw_cmds.extend(self.location._fwcmds)
            custom_cmds.extend(self.location.custom_cmds.values())

        return custom_cmds + fw_cmds

    def find(
        self,
        query="",
        objects=None,
        **kwargs,
    ):
        if objects is None:
            objects = self.reachable_objects()
        short_names = {"me": self, "here": self.location}
        return util.find(query, objects=objects, short_names=short_names, **kwargs)

    def move(self, object, destination):
        if not util.is_thing(object):
            raise ActionFailed(f"Can not move {object.name}.")
        if not hasattr(destination, "contents"):
            raise ActionFailed(f"{destination.name} has no room for {object.name}")
        if object.has_flag("big"):
            raise ActionFailed(f"{object.name} is too big.")
        if object is destination:
            raise ActionFailed(f"Can not move into itself.")
        util.moveto(object, destination)

    def send(self, msg):
        if self.client is not None:
            self.client.send(msg)

    def emit(self, msg):
        if self.location is not None:
            self.location.emit(msg)

    def reachable_objects(self):
        objs = list(self.contents)
        if self.location is not None:
            objs += [self.location] + self.location.contents + self.location.exits
        return objs

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

    def cmd_describe(self, caller, query):
        """describe <object> <description>: give a description to a room, player or thing."""
        m = re.match(r"(\w+) (.*)", query or "")
        if m is None:
            raise ActionFailed("Try help describe.")
        what, description = m.groups()

        def doit(thing):
            thing.description = description.replace("\\n", "\n").replace("\\t", "\t")
            caller.send("Added description of {}".format(thing.name))

        self.find(what, then=doit)

    def cmd_go(self, caller, query):
        """go [to] <place>: move to a different place."""
        if self.location is None:
            raise ActionFailed("You're nowhere. And can't go anywhere :'(")
        m = re.match(r"(?:to )?(.*)", query or "")
        if m is None:
            raise ActionFailed("Go where?")
        place = m.group(1)

        def doit(arg):
            self.location.emit(self.name + " has gone to " + arg.name)
            arg.emit(self.name + " arrives from " + self.location.name)
            util.moveto(self, arg)
            self.cmd_look(self, "here")

        util.find(
            place,
            objects=self.location.exits,
            notfound=f"There doesn't seem to be a place named '{place}' nearby.",
            then=doit,
        )

    def cmd_look(self, player, query):
        """look [object]: see descriptions of things, people or places."""

        def doit(arg):
            if arg is None:
                self.send("You only see nothing. A lot of nothing.")
                return
            self.send(f"\033[34m{arg.name}\033[0m: {arg.description}")
            if hasattr(arg, "contents") and not arg.has_flag("opaque"):
                self.send("")  # extra newline
                if arg.contents:
                    self.send("Contents:")
                for thing in arg.contents:
                    self.send(" - " + thing.name)
            if hasattr(arg, "exits") and not arg.has_flag("opaque"):
                self.send("")  # extra newline
                if arg.exits:
                    self.send("Nearby places:")
                for room in arg.exits:
                    self.send(" - " + room.name)

        if self.location is None:
            notfound = "You see nothing but you."
        else:
            notfound = "You see nothing like '{}' here."
        self.find(query or "here", then=doit, notfound=notfound)


class MRPower:
    fw_cmds = {}
    flags = []

    def __init__(self):
        self.initcommands()

    def __repr__(self):
        return f"<power {self.__class__.__name__}>"

    def __setstate__(self, odict):
        self.initcommands()

    def __getstate__(self):
        odict = dict(self.__dict__)
        del odict["_fwcmds"]
        return odict

    def initcommands(self):
        self._fwcmds = [
            WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()
        ]


class Engineer(MRPower):
    fw_cmds = {
        "eval": "cmd_eval",
        "exec": "cmd_exec",
        "examine": "cmd_examine",
        "setattr": "cmd_setattr",
        "delattr": "cmd_delattr",
        "cmd": "cmd_cmd",
        "match": "cmd_match",
        "setflag": "cmd_setflag",
        "resetflag": "cmd_resetflag",
    }

    def _exec_env(self, caller):
        return {
            "self": proxify(caller),
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
            raise ActionFailed("Examine what?")

        def doit(obj):
            what = proxify(obj)
            caller.send(f"{repr(what)}:")
            caller.send(
                "\n".join(f"  {k}: {repr(getattr(what, k))}" for k in dir(what))
            )

        if (m := re.match(r"#(\d+)", query)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find(query, then=doit)

    def cmd_setattr(self, caller, query):
        """setattr <object> <attribute> <value>: set an attribute on an object.
        <object> can be a # database ID.
        <value> can be a # database ID, otherwise it is a string."""
        if (match := re.match(r"(#\d+|\w+) ([^ ]+) (.*)", query or "")) is None:
            raise ActionFailed("Try help setattr")

        target, attr, value = match.groups()
        if (match := re.match(r"#(\d+)", value)) is not None:
            value = db.get(int(match.group(1)))

        def doit(obj):
            setattr(obj, attr, value)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find(target, then=doit)

    def cmd_delattr(self, caller, query):
        """delattr <object> <attribute>: delete an attribute on an object.
        <object> can be a # database ID."""
        if (match := re.match(r"(#\d+|\w+) ([^ ]+)", query or "")) is None:
            raise ActionFailed("Try help delattr")

        target, attr = match.groups()

        def doit(obj):
            delattr(obj, attr)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find(target, then=doit)

    def cmd_cmd(self, caller, query):
        """cmd <object> <cmd> <code>: add a command to an object."""
        if (match := re.match(r"((?:\w+)|(?:#\d+)) ([^ ]+) (.*)", query or "")) is None:
            raise ActionFailed("Try 'help cmd'.")
        target, cmd, txt = match.groups()
        txt = re.sub(r"\\.", lambda x: {"\\n": "\n", "\\\\": "\\"}[x.group(0)], txt)

        def doit(thing):
            thing.custom_cmds[cmd] = CustomCommand(cmd, txt, thing)
            caller.send(f"Added command {cmd} to {thing.name}")

        if (m := re.match("#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find(target, then=doit)

    def cmd_match(self, caller, query):
        """match <object> [<name>:]<match regexp> <code>: add a matcher to an object.
        <object> can be a # database ID."""
        m = re.match("(.*) (?:(\w+):)?(\"(?:[^\"]*)\"|'(?:[^']*)') (.*)", query or "")
        if m is None:
            raise ActionFailed("Try help match")
        target, name, regex, code = m.groups()

        def doit(target):
            action = RegexpAction(regex[1:-1], code, owner=target, name=name)
            target.custom_cmds[action.name] = action
            caller.send(f"Added match command {action.name} to {target.name}")

        if (m := re.match("#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))
        return caller.find(target, then=doit)

    def cmd_setflag(self, caller, query):
        """setflag <object> <flag>: set a flag on an object.
        <object> can be a # database ID."""
        if (match := re.match(r"(#\d+|\w+) (.*)", query or "")) is None:
            raise ActionFailed("Try help setflag")

        target, flag = match.groups()

        def doit(obj):
            if not flag in obj.flags:
                obj.flags.append(flag)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find(target, then=doit)

    def cmd_resetflag(self, caller, query):
        """resetflag <object> <flag>: reset a flag on an object.
        <object> can be a # database ID."""
        if (match := re.match(r"(#\d+|\w+) (.*)", query or "")) is None:
            raise ActionFailed("Try help resetflag")

        target, flag = match.groups()

        def doit(obj):
            if flag in obj.flags:
                obj.flags.remove(flag)

        if (m := re.match(r"#(\d+)", target)) is not None:
            return doit(db.get(int(m.group(1))))

        caller.find(target, then=doit)


class Digger(MRPower):
    fw_cmds = {
        "dig": "cmd_dig",
    }

    def cmd_dig(self, caller, query):
        """dig <room name>: make a new room."""
        if not query:
            raise ActionFailed("Dig what? Try help dig")
        room = MRRoom(query)
        db.add(room)
        if caller.location is None:
            caller.send("In a flash of darkness, a new place appears around you.")
            caller.cmd_teleport(caller, query)
            return
        room.exits.append(caller.location)
        caller.location.exits.append(room)
        caller.location.emit(f"{caller.name} digs a hole that leads to {room.name}")


class SuperDigger(Digger):
    fw_cmds = {
        "link": "cmd_link",
        "unlink": "cmd_unlink",
        "teleport": "cmd_teleport",
        **Digger.fw_cmds,
    }

    def cmd_link(self, caller, query):
        """link [to] <place>: open an exit towards the place."""
        if caller.location is None:
            raise ActionFailed("Bawoops, you're nowhere.")
        if (match := re.match(r"(?:to )?(.*)", query or "")) is None:
            raise ActionFailed("Link what?")
        where = match.group(1)

        def doit(arg):
            caller.location.exits.append(arg)
            caller.location.emit(f"{caller.name} opens a new path towards {arg.name}")

        util.find(where, objects=db.list_all(MRRoom), then=doit)

    def cmd_unlink(self, caller, query):
        """unlink <place>: remove the exit to that place."""
        if caller.location is None:
            raise ActionFailed("There's nothing here.")
        if query is None:
            raise ActionFailed("Unlink what?")

        def doit(arg):
            caller.location.exits.remove(arg)
            caller.location.emit(f"{caller.name} removed the exit to {arg.name}")

        util.find(query, objects=caller.location.exits, then=doit)

    # it makes sense to keep this with link, since it can open an exit to anywhere anyway
    def cmd_teleport(self, caller, query):
        """teleport [to] <place>: place can be a # database ID"""
        place = re.match(r"(?:to )?(.*)", query or "").group(1)
        if place is None:
            raise ActionFailed("Teleport to where?")

        def doit(room):
            caller.emit(f"{caller.name} vanishes. Gone.")
            util.moveto(caller, room)
            caller.cmd_look(caller, "here")
            room.emit(f"{caller.name} pops into the room. Poof.")

        if (m := re.match(r"#(\d+)", place)) is not None:
            room = db.get(int(m.group(1)))
            if not util.is_room(room):
                raise ActionFailed(f"{room} is not a room!")
            return doit(room)

        util.find(place, objects=db.list_all(MRRoom), then=doit)


class Maker(MRPower):
    fw_cmds = {
        "make": "cmd_make",
        "destroy": "cmd_destroy",
    }

    def cmd_make(self, caller, query):
        """make <thing name>: make things. Just regular things."""
        if caller.location is None:
            raise ActionFailed("There is nowehere to make things into.")
        name = query
        thing = MRThing(name)
        db.add(thing)
        util.moveto(thing, caller.location)
        caller.location.emit(f"{caller.name} makes {name} appear out of thin air.")

    def cmd_destroy(self, caller, query):
        """destroy <thing>: destroy things. Anything, really."""
        if query is None:
            raise ActionFailed("Destroy what?")

        def doit(thing):
            if util.is_room(thing):
                thing.emit(f"{caller.name} blew up the place!")
                for o in thing.contents:
                    if util.is_player(o):
                        o.send("You fall into the void of nothingness.")
                    util.moveto(o, None)
            else:
                caller.emit(caller.name + " violently destroyed " + thing.name + "!")
                util.moveto(thing, None)
            db.remove(thing)
            if util.is_player(thing):
                if thing.client is not None:
                    thing.client.player = None
                    thing.send(
                        "Your character has been slain. You were kicked out of it."
                    )

        caller.find(query, then=doit)


class God(Engineer, Maker, SuperDigger):
    fw_cmds = {
        **Engineer.fw_cmds,
        **Maker.fw_cmds,
        **SuperDigger.fw_cmds,
    }
