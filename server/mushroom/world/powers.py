import logging
import re
from functools import cached_property

import frozendict

from mushroom import util
from mushroom.commands import (
    CustomCommand,
    EventHandler,
    Lambda,
    RegexpAction,
    WrapperCommand,
)
from mushroom.db import proxify
from mushroom.game import Game
from mushroom.util import ActionFailed, regexp_command
from mushroom.world.objects import Thing
from mushroom.world.room import Room

logger = logging.getLogger(__name__)


class Power:
    fw_cmds = frozendict.frozendict({})
    flags = frozenset()

    def __init__(self, name=None):
        self.name = name or self.__class__.__name__

    def __dir__(self):
        return [x for x in self.__dict__ if not x.startswith("_")]

    def __repr__(self):
        return f"<power {self.name}>"

    def __getstate__(self):
        return {k: getattr(self, k) for k in dir(self)}

    def __setstate__(self, odict):
        if not "name" in odict:
            odict["name"] = self.__class__.__name__
        self.__dict__.update(odict)

    @cached_property
    def _fwcmds(self):
        return [WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()]


class Examiner(Power):
    fw_cmds = frozendict.frozendict(
        {
            "examine": "cmd_examine",
        }
    )

    @regexp_command("examine", r"(#\d+|[^#].*)")
    def cmd_examine(self, caller, obj):
        """examine <object>: display commands and attributes of an object.
        <object> can be a # database ID."""
        caller.send(util.pretty_format(obj))


class Tinkerer(Examiner):
    fw_cmds = frozendict.frozendict(
        {
            "setattr": "cmd_setattr",
            "delattr": "cmd_delattr",
            "setflag": "cmd_setflag",
            "resetflag": "cmd_resetflag",
            **Examiner.fw_cmds,
        }
    )

    @regexp_command("setattr", r"(#\d+|\w+) ([^ ]+) (lambda:\s*)?(.*)")
    def cmd_setattr(self, caller, obj, attr, lbd, value):
        """setattr <object> <attribute> <value>: set an attribute on an object.
        <object> can be a # database ID.
        <value> can be a # database ID, otherwise it is a string."""
        value = Game.get_instance().db.get(value) or value
        if lbd is not None:
            value = Lambda(value).bind(obj)
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
    fw_cmds = frozendict.frozendict(
        {
            "eval": "cmd_eval",
            "exec": "cmd_exec",
            "cmd": "cmd_cmd",
            "match": "cmd_match",
            "delcmd": "cmd_delcmd",
            "setevent": "cmd_setevent",
            "delevent": "cmd_delevent",
            **Tinkerer.fw_cmds,
        }
    )

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
        except Exception as e:  # noqa: BLE001
            cls = e.__class__.__name__
            caller.send(f"{cls}: {e}")

    def cmd_exec(self, caller, rest):
        """exec <string>: execute raw code."""
        try:
            exec(util.unescape(rest), self._exec_env(caller))  # noqa: S102
        except Exception as e:  # noqa: BLE001
            cls = e.__class__.__name__
            caller.send(f"{cls}: {e}")

    @regexp_command("cmd", r"(#\d+|\w+) ([^ :]+)(?::([opi]+))? (.*)")
    def cmd_cmd(self, caller, thing, cmd, flags, txt):
        """cmd <object> <cmd>[:<flags>] <code>: add a command to an object.
        <flags> can be one or more of (o)wner, (p)eer, (i)interior."""
        thing.custom_cmds[cmd] = CustomCommand(cmd, util.unescape(txt), flags=flags)
        caller.send(f"Added command '{cmd}' to {thing}")

    @regexp_command(
        "match",
        r"(#\d+|\w+) (?:(\w+)(?::([opi]+))?:)?(\"(?:[^\"]*)\"|'(?:[^']*)') (.*)",
    )
    def cmd_match(self, caller, target, name, flags, regex, code):
        """match <object> [<name>[:<flags>]:]<match regexp> <code>: add a matcher to an object.
        <object> can be a # database ID.
        <flags> can be one or more of (o)wner, (p)eer, (i)interior."""
        action = RegexpAction(regex[1:-1], util.unescape(code), name=name, flags=flags)
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
        obj.custom_event_handlers[event] = EventHandler(code)
        caller.send(f"Set event handler '{event}' on {obj}")

    @regexp_command("delevent", r"(#\d+|\w+) ([^ ]+)")
    def cmd_delevent(self, caller, obj, event):
        """delevent <object> <event>: delete an event handler on an object.
        <object> can be a # database ID."""
        if event not in getattr(obj, "custom_event_handlers", {}):
            raise ActionFailed(f"{obj} does not have event handler {event}")
        del obj.custom_event_handlers[event]
        caller.send(f"Deleted event handler '{event}' on {obj}")


class Digger(Power):
    fw_cmds = frozendict.frozendict(
        {
            "dig": "cmd_dig",
        }
    )

    def cmd_dig(self, caller, query):
        """dig <room name>: make a new room."""
        if not query:
            raise ActionFailed("Dig what? Try help dig")
        room = Room(query)
        Game.get_instance().db.add(room)
        if caller.location is None:
            caller.send("In a flash of darkness, a new place appears around you.")
            util.moveto(caller, room)
            return
        room.exits.append(caller.location)
        caller.location.exits.append(room)
        caller.location.emit(f"{caller.name} digs a hole that leads to {room.name}")


class Demolisher(Power):
    fw_cmds = frozendict.frozendict(
        {
            "demolish": "cmd_demolish",
        }
    )

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
            Game.get_instance().db.remove(room)

        if caller.location is None or not hasattr(caller.location, "exits"):
            raise ActionFailed("There are no rooms to demolish around here.")
        util.find(query, objects=caller.location.exits, then=doit)


class SuperDigger(Demolisher, Digger):
    fw_cmds = frozendict.frozendict(
        {
            "link": "cmd_link",
            "unlink": "cmd_unlink",
            "teleport": "cmd_teleport",
            **Demolisher.fw_cmds,
            **Digger.fw_cmds,
        }
    )

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

        util.find(where, objects=Game.get_instance().db.search(type=Room), then=doit)

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
            room = Game.get_instance().db.get(int(m.group(1)))
            if not isinstance(room, Room):
                raise ActionFailed(f"{room} is not a room!")
            return doit(room)

        util.find(place, objects=Game.get_instance().db.search(type=Room), then=doit)


class Maker(Power):
    fw_cmds = frozendict.frozendict(
        {
            "make": "cmd_make",
            "destroy": "cmd_destroy",
        }
    )

    def cmd_make(self, caller, query):
        """make <thing name>: make things. Just regular things."""
        if caller.location is None:
            raise ActionFailed("There is nowehere to make things into.")
        name = query
        thing = Thing(name)
        Game.get_instance().db.add(thing)
        util.moveto(thing, caller.location)
        caller.location.emit(f"{caller.name} makes {name} appear out of thin air.")

    @regexp_command("destroy", r"(#\d+|\w+)")
    def cmd_destroy(self, caller, thing):
        """destroy <thing>: destroy things."""
        if not isinstance(thing, Thing):
            raise ActionFailed("You can't destroy that.")
        caller.emit(caller.name + " violently destroyed " + thing.name + "!")
        util.moveto(thing, None)
        Game.get_instance().db.remove(thing)


class God(Engineer, Maker, SuperDigger):
    fw_cmds = frozendict.frozendict(
        {
            **Engineer.fw_cmds,
            **Maker.fw_cmds,
            **SuperDigger.fw_cmds,
        }
    )
