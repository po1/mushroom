import bisect
from collections.abc import Iterable
import copy
import queue
import itertools
import logging
import re
import threading
import time

from . import util
from .commands import (
    CustomCommand,
    RegexpAction,
    WrapperCommand,
    ActionFailed,
    EventHandler,
    Lambda,
    Code,
)
from .db import db, DbProxy
from .object import BaseObject, proxify
from .register import register
from .util import regexp_command

logger = logging.getLogger(__name__)


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
    fw_event_handlers = {}
    default_description = "An abstract object."

    def __init__(self, name):
        super().__init__(name)
        self.description = self.default_description
        self.custom_cmds = {}
        self.custom_event_handlers = {}
        self._initcmds()
        self.flags = []
        self.parent = None

    def has_flag(self, flag):
        """Return True if flag is set.
        Note: there is no way to reset an inherited flag."""
        if self.parent is not None and self.parent.has_flag(flag):
            return True
        return flag in self.flags

    @property
    def event_handlers(self):
        """Return all soft-code event handlers, including those of a parent."""
        handlers = {}
        if self.parent is not None:
            handlers.update(self.parent.event_handlers)
        handlers.update(self.custom_event_handlers)
        return handlers

    @property
    def commands(self):
        """Return all soft-code commands, including those of a parent."""
        cmds = list(self.custom_cmds.values())
        if self.parent is not None:
            cmds += [c.bind(self) for c in self.parent.commands]
        return cmds

    def dispatch(self, event, **kwargs):
        if event in self.event_handlers:
            # raise ActionFailed to interrupt
            handler = self.event_handlers[event].bind(self)
            handler(**kwargs)
        if event in self.fw_event_handlers:
            handler = getattr(self, self.fw_event_handlers[event])
            handler(**kwargs)

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

    def __getattr__(self, attr):
        if attr.startswith("_"):
            return object.__getattribute__(self, attr)
        if self.parent is None or not hasattr(self.parent, attr):
            return object.__getattribute__(self, attr)
        return getattr(self.parent, attr)

    def __getstate__(self):
        odict = dict(self.__dict__)
        del odict["_fwcmds"]
        return odict

    def __setstate__(self, odict):
        self.__dict__.update(odict)
        self._initcmds()
        self._checkfields()

    def exec_env(self):
        import math
        import random

        import mushroom

        return {
            "game": game,
            "db": DbProxy(db),
            "util": mushroom.util,
            "world": mushroom.world,
            "mushroom": mushroom,
            "itertools": itertools,
            "math": math,
            "random": random,
            "time": time,
        }

    def clone(self):
        obj = self.__class__(self.name)

        def _copy(item):
            if isinstance(item, list):
                return [_copy(x) for x in item]
            if isinstance(item, dict):
                return {k: _copy(v) for k, v in item.items()}
            if isinstance(item, Code):
                return item.bind(obj)
            return item

        for attr, value in self.__dict__.items():
            if attr.startswith("_"):
                continue
            if attr == "contents":
                obj.contents = []
            setattr(obj, attr, _copy(value))
        obj._initcmds()
        return obj

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
        self.master_room = None


class MRStuff(MRObject):
    """
    Stuff that can be in rooms. Things or players.
    """

    fw_event_handlers = {
        "look": "on_look",
    }

    def __init__(self, name):
        self.location = None
        self.contents = []
        super().__init__(name)

    def exec_env(self):
        return {
            "send": self.send,
            "here": self.location,
            **super().exec_env(),
        }

    def emit(self, msg):
        if self.location is not None:
            self.location.emit(msg)

    def oemit(self, msg):
        if self.location is None:
            return
        for obj in self.location.contents:
            if obj != self:
                obj.dispatch("emit", text=msg)

    def clone(self):
        obj = super().clone()
        obj.contents = []
        obj.location = None
        return obj

    def on_look(self, caller):
        colordesc = util.format(self.description, self=self)
        caller.send(f"\033[34m{self}\033[0m: {colordesc}")
        if self.has_flag("opaque"):
            return
        contents = [
            x for x in getattr(self, "contents", []) if not x.has_flag("invisible")
        ]
        if contents:
            caller.send("\nContents:")
            caller.send("\n".join(f" - {thing}" for thing in contents))


@register
class MRThing(MRStuff):
    """
    Things that are not players or rooms.
    Usually common objects, usable or not.
    """

    fancy_name = "thing"
    default_description = "A boring non-descript thing"

    def __init__(self, name):
        self.powers = []
        super().__init__(name)

    # need this as a /dev/null sink for event handlers
    def send(self, msg):
        logger.warn(f"{repr(self)} was sent: {msg}")


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
        "go": "cmd_go",
    }
    fw_event_handlers = {
        "look": "on_look",
    }
    default_description = "A blank room."

    def __init__(self, name):
        self.contents = []
        self.exits = []
        super().__init__(name)

    def emit(self, msg):
        """emit <stuff>: display text to all connected players in the room."""
        for thing in self.contents:
            thing.dispatch("emit", text=util.format(msg))

    def cmd_say(self, caller, rest):
        """say <stuff>: say something out loud where you are."""
        self.emit(caller.name + " says: " + rest)

    def cmd_emit(self, caller, rest):
        """emit <stuff>: broadcast text in the current room."""
        if not rest:
            raise ActionFailed("Emit what?")
        self.emit(rest.replace("\\n", "\n").replace("\\t", "\t"))

    def cmd_take(self, caller, query):
        """take <thing>: move a thing into your pocket."""
        if query is None:
            raise ActionFailed("Take what?")

        def doit(obj):
            if obj is caller:
                return caller.emit(
                    f"{caller.name} tries to fold themselves into their own pocket, but fails."
                )
            if obj.has_flag("big"):
                raise ActionFailed(f"{obj} is too big.")
            if not util.is_thing(obj) and not caller.has_flag("big"):
                raise ActionFailed(f"{obj} won't fit in your pocket.")

            # last chance to raise an ActionFailed
            obj.dispatch("taken", caller=caller)

            util.moveto(obj, caller)
            self.emit(f"{caller.name} puts {obj.name} in their pocket.")

        util.find(query, objects=caller.location.contents, then=doit)

    def cmd_drop(self, caller, query):
        """drop <thing>: move a thing out of your pocket."""
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

    def cmd_go(self, caller, query):
        """go [to] <place>: move to a different place."""
        m = re.match(r"(?:to )?(.*)", query or "")
        if m is None:
            raise ActionFailed("Go where?")
        place = m.group(1)

        def doit(arg):
            caller.location.emit(caller.name + " has gone to " + arg.name)
            arg.emit(caller.name + " arrives from " + caller.location.name)
            util.moveto(caller, arg)
            caller.cmd_look(caller, "here")

        util.find(
            place,
            objects=caller.location.exits,
            notfound=f"There doesn't seem to be a place named '{place}' nearby.",
            then=doit,
        )

    def on_look(self, caller):
        colordesc = util.format(self.description, self=self)
        caller.send(f"\033[34m{self}\033[0m: {colordesc}")
        if self.has_flag("opaque"):
            return
        contents = [x for x in self.contents if not x.has_flag("invisible")]
        if contents:
            caller.send("\nContents:")
            caller.send("\n".join(f" - {thing}" for thing in contents))
        if self.exits:
            caller.send("\nNearby places:")
            caller.send("\n".join(f" - {room}" for room in self.exits))


@register
class MRPlayer(MRStuff):
    """
    Basic Player.
    Other player classes derive from this
    """

    fancy_name = "player"
    fw_cmds = {
        "look": "cmd_look",
        "describe": "cmd_describe",
    }
    fw_event_handlers = {
        "connect": "on_connect",
        "emit": "on_emit",
        **MRStuff.fw_event_handlers,
    }
    default_description = "A non-descript citizen."

    def __init__(self, name):
        self.client = None
        self.powers = []
        super().__init__(name)

        if not (confs := db.list_all(Config)):
            db.add(Config())
            # First player gets all powers. Dibs!
            self.powers.append(God())
        elif (default_room := confs[0].default_room) is not None:
            default_room.emit(f"{self} materializes into the room.")
            util.moveto(self, default_room)

    def __getstate__(self):
        odict = super().__getstate__()
        del odict["client"]
        return odict

    def __setstate__(self, odict):
        super().__setstate__(odict)
        self.client = None

    def has_flag(self, flag):
        powerflags = itertools.chain(*(p.flags for p in self.get_powers()))
        if flag in powerflags:
            return True
        return super().has_flag(flag)

    def get_powers(self):
        pows = list(self.powers)
        if self.parent is not None and hasattr(self.parent, "get_powers"):
            pows.extend(self.parent.get_powers())
        for thing in self.contents:
            if not util.is_thing(thing):
                continue
            pows.extend(thing.powers)
        return pows

    @property
    def cmds(self):
        fw_cmds = list(self._fwcmds)
        custom_cmds = self.commands
        for p in self.get_powers():
            fw_cmds += p._fwcmds  # no custom commands on powers yet

        def onlyflag(flag, cmds):
            return [c for c in cmds if flag in c.flags]

        def addthingcmds(container, flag=""):
            for thing in container.contents:
                if util.is_thing(thing):
                    fw_cmds.extend(onlyflag(flag, thing._fwcmds))
                    custom_cmds.extend(onlyflag(flag, thing.commands))

        addthingcmds(self, "o")
        if self.location is not None:
            addthingcmds(self.location, "p")
            room_flag = "" if util.is_room(self.location) else "i"
            fw_cmds += onlyflag(room_flag, self.location._fwcmds)
            custom_cmds += onlyflag(room_flag, self.location.commands)

        config = db.search(type=Config)[0]
        if (master_room := getattr(config, "master_room", None)) is not None:
            addthingcmds(master_room)

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

    def reachable_objects(self):
        objs = list(self.contents)
        if self.location is not None:
            objs += [self.location]
            objs += getattr(self.location, "contents", [])
            objs += getattr(self.location, "exits", [])
        return objs

    @regexp_command("describe", r"(#\d+|\w+) (.*)")
    def cmd_describe(self, caller, thing, description):
        """describe <object> <description>: give a description to a room, player or thing."""
        if thing is None:
            raise ActionFailed("There is nothing to describe.")
        thing.description = description.replace("\\n", "\n").replace("\\t", "\t")
        caller.send("Added description of {}".format(thing.name))

    def cmd_look(self, caller, query):
        """look [at] [object]: see descriptions of things, people or places."""
        if (m := re.match(r"(?:at )?(.*)", query or "")) is not None:
            query = m.group(1)

        def doit(arg):
            if arg is None:
                caller.send("You only see nothing. A lot of nothing.")
                return
            arg.dispatch("look", caller=caller)

        if caller.location is None:
            notfound = "You see nothing but you."
        else:
            notfound = f"You see nothing like '{query}' here."
        caller.find(query or "here", then=doit, notfound=notfound)

    def on_emit(self, text):
        self.send(text)

    def on_connect(self):
        self.cmd_look(self, "here")


class MRPower:
    fw_cmds = {}
    flags = []

    def __init__(self, name=None):
        self.initcommands()
        self.name = name or self.__class__.__name__

    def __dir__(self):
        return [x for x in self.__dict__ if not x.startswith("_")]

    def __repr__(self):
        return f"<power {self.name}>"

    def __setstate__(self, odict):
        if not "name" in odict:
            odict["name"] = self.__class__.__name__
        self.__dict__.update(odict)
        self.initcommands()

    def __getstate__(self):
        odict = dict(self.__dict__)
        del odict["_fwcmds"]
        return odict

    def initcommands(self):
        self._fwcmds = [
            WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()
        ]


class Examiner(MRPower):
    fw_cmds = {
        "examine": "cmd_examine",
    }

    @regexp_command("examine", r"(#\d+|[^#].*)")
    def cmd_examine(self, caller, obj):
        """examine <object>: display commands and attributes of an object.
        <object> can be a # database ID."""
        caller.send(util.pretty_format(obj))


class Tinkerer(Examiner):
    fw_cmds = {
        "setattr": "cmd_setattr",
        "delattr": "cmd_delattr",
        "setflag": "cmd_setflag",
        "resetflag": "cmd_resetflag",
        **Examiner.fw_cmds,
    }

    @regexp_command("setattr", r"(#\d+|\w+) ([^ ]+) (lambda:\s*)?(.*)")
    def cmd_setattr(self, caller, obj, attr, lbd, value):
        """setattr <object> <attribute> <value>: set an attribute on an object.
        <object> can be a # database ID.
        <value> can be a # database ID, otherwise it is a string."""
        value = db.dbref(value) or value
        if lbd is not None:
            value = Lambda(value, obj)
        setattr(obj, attr, value)
        caller.send(f"Set attribute '{attr}' on {obj}")

    @regexp_command("delattr", r"(#\d+|\w+) ([^ ]+)")
    def cmd_delattr(self, caller, obj, attr):
        """delattr <object> <attribute>: delete an attribute on an object.
        <object> can be a # database ID."""
        if not hasattr(obj, attr):
            raise ActionFailed(f"No attribute '{attr}' on {obj}")
        delattr(obj, attr)
        caller.send(f"Deleted attribute '{attr}' on {obj}")

    @regexp_command("setflag", r"(#\d+|\w+) (\w+)")
    def cmd_setflag(self, caller, obj, flag):
        """setflag <object> <flag>: set a flag on an object.
        <object> can be a # database ID."""
        if not flag in obj.flags:
            obj.flags.append(flag)
        caller.send(f"Set flag '{flag}' on {obj}")

    @regexp_command("resetflag", r"(#\d+|\w+) (\w+)")
    def cmd_resetflag(self, caller, obj, flag):
        """resetflag <object> <flag>: reset a flag on an object.
        <object> can be a # database ID."""
        if flag in obj.flags:
            obj.flags.remove(flag)
        caller.send(f"Reset flag '{flag}' on {obj}")


class Engineer(Tinkerer):
    fw_cmds = {
        "eval": "cmd_eval",
        "exec": "cmd_exec",
        "cmd": "cmd_cmd",
        "match": "cmd_match",
        "delcmd": "cmd_delcmd",
        "setevent": "cmd_setevent",
        "delevent": "cmd_delevent",
        **Tinkerer.fw_cmds,
    }

    def _exec_env(self, caller):
        return {
            "caller": proxify(caller),
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

    @regexp_command("cmd", r"(#\d+|\w+) ([^ :]+)(?::([opi]+))? (.*)")
    def cmd_cmd(self, caller, thing, cmd, flags, txt):
        """cmd <object> <cmd>[:<flags>] <code>: add a command to an object.
        <flags> can be one or more of (o)wner, (p)eer, (i)interior."""
        thing.custom_cmds[cmd] = CustomCommand(
            cmd, util.unescape(txt), thing, flags=flags
        )
        caller.send(f"Added command '{cmd}' to {thing}")

    @regexp_command(
        "match",
        r"(#\d+|\w+) (?:(\w+)(?::([opi]+))?:)?(\"(?:[^\"]*)\"|'(?:[^']*)') (.*)",
    )
    def cmd_match(self, caller, target, name, flags, regex, code):
        """match <object> [<name>[:<flags>]:]<match regexp> <code>: add a matcher to an object.
        <object> can be a # database ID.
        <flags> can be one or more of (o)wner, (p)eer, (i)interior."""
        action = RegexpAction(
            regex[1:-1], util.unescape(code), owner=target, name=name, flags=flags
        )
        target.custom_cmds[action.name] = action
        caller.send(f"Added match command '{action.name}' to {target}")

    @regexp_command("delcmd", r"(#\d+|\w+) ([^ ]+)")
    def cmd_delcmd(self, caller, obj, cmd):
        """delcmd <object> <cmd>: delete a command or match.
        <object> can be a # database ID."""
        if cmd not in obj.custom_cmds:
            raise ActionFailed(f"{obj} does not have command {cmd}")
        del obj.custom_cmds[cmd]
        caller.send(f"Deleted command '{cmd}' on {obj}")

    @regexp_command("setevent", r"(#\d+|\w+) ([^ ]+) (.*)")
    def cmd_setevent(self, caller, obj, event, code):
        """setevent <object> <event> <code>: set an event handler on an object.
        <object> can be a # database ID."""
        code = util.unescape(code)
        obj.custom_event_handlers[event] = EventHandler(code, owner=obj)
        caller.send(f"Set event handler '{event}' on {obj}")

    @regexp_command("delevent", r"(#\d+|\w+) ([^ ]+)")
    def cmd_delevent(self, caller, obj, event):
        """delevent <object> <event>: delete an event handler on an object.
        <object> can be a # database ID."""
        if event not in getattr(obj, "custom_event_handlers", {}):
            raise ActionFailed(f"{obj} does not have event handler {event}")
        del obj.custom_event_handlers[event]
        caller.send(f"Deleted event handler '{event}' on {obj}")


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
            util.moveto(caller, room)
            return
        room.exits.append(caller.location)
        caller.location.exits.append(room)
        caller.location.emit(f"{caller.name} digs a hole that leads to {room.name}")


class Demolisher(MRPower):
    fw_cmds = {
        "demolish": "cmd_demolish",
    }

    def cmd_demolish(self, caller, query):
        """demolish <room>: demolish a room."""
        if query is None:
            raise ActionFailed("Demolish what?")

        def doit(room):
            room.emit(f"{caller.name} blew up the place!")
            room.emit(f"The explosion blows you towards {caller.location.name}")
            caller.location.emit(f"{caller.name} demolished {room.name}!")
            caller.location.exits.remove(room)
            for o in room.contents:
                util.moveto(o, caller.location)
            db.remove(room)

        if caller.location is None or not hasattr(caller.location, "exits"):
            raise ActionFailed("There are no rooms to demolish around here.")
        util.find(query, objects=caller.location.exits, then=doit)


class SuperDigger(Demolisher, Digger):
    fw_cmds = {
        "link": "cmd_link",
        "unlink": "cmd_unlink",
        "teleport": "cmd_teleport",
        **Demolisher.fw_cmds,
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

    @regexp_command("destroy", r"(#\d+|\w+)")
    def cmd_destroy(self, caller, thing):
        """destroy <thing>: destroy things."""
        if not util.is_thing(thing):
            raise ActionFailed("You can't destroy that.")
        caller.emit(caller.name + " violently destroyed " + thing.name + "!")
        util.moveto(thing, None)
        db.remove(thing)


class God(Engineer, Maker, SuperDigger):
    fw_cmds = {
        **Engineer.fw_cmds,
        **Maker.fw_cmds,
        **SuperDigger.fw_cmds,
    }
