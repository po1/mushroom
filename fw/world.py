import re

from . import util
from .commands import CustomCommand
from .commands import WrapperCommand
from .db import db
from .object import BaseObject, proxify
from .register import register


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
        self.initcmds()

    def initcmds(self):
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
        self.initcmds()

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

    def __init__(self):
        super().__init__("config")
        self.default_room = None


@register
class MRThing(MRObject):
    """
    Things that are not players or rooms.
    Usually common objects, usable or not.
    """

    fancy_name = "thing"
    default_description = "A boring non-descript thing"


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
        "link": "cmd_link",
        "unlink": "cmd_unlink",
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

    def cmd_link(self, caller, query):
        """link [to] <place>: open an exit towards the place."""
        if query is None:
            return caller.send("Link what?")
        where = re.match(r"(?:to )?(.*)", query).group(1)

        def doit(arg):
            self.exits.append(arg)
            self.emit("Linked {} and {}".format(arg.name, self.name))

        util.find_and_do(
            caller,
            where,
            doit,
            db.list_all(MRRoom),
            notfound="Don't know this place. Is it in Canada?",
        )

    def cmd_unlink(self, player, rest):
        """unlink <place>: remove the exit to that place."""

        def doit(arg):
            self.exits.remove(arg)
            self.emit("Unlinked {} and {}".format(arg.name, self.name))

        util.find_and_do(
            player,
            rest,
            doit,
            self.exits,
            noarg="Unlink what?",
            notfound="This room ain't connected to Canada.",
        )

    def cmd_take(self, caller, query):
        def doit(obj):
            self.contents.remove(obj)
            caller.pockets.append(obj)
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
            caller.pockets.remove(obj)
            self.contents.append(obj)
            self.emit(
                f"{caller.name} takes {obj.name} out of their pocket and leaves it."
            )

        util.find_and_do(
            caller,
            query,
            doit,
            caller.pockets,
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
        self.room = None
        self.powers = []
        self.pockets = []
        super(MRPlayer, self).__init__(name)

        if not (confs := db.list_all(Config)):
            db.add(Config())
            # First player gets all powers. Dibs!
            self.powers += [Maker(), Engineer()]
        elif (default_room := confs[0].default_room) is not None:
            self.room = default_room
            self.room.contents.append(self)

    def __getstate__(self):
        odict = super().__getstate__()
        del odict["client"]
        return odict

    def __setstate__(self, odict):
        super().__setstate__(odict)
        self.client = None

    @property
    def cmds(self):
        c = super().cmds
        for p in self.powers:
            c += p.cmds
        for thing in self.pockets:
            if util.is_thing(thing):
                c += thing.cmds
        if self.room is not None:
            c += self.room.cmds
            for thing in self.room.contents:
                if util.is_thing(thing):
                    c += thing.cmds
        return c

    def send(self, msg):
        if self.client is not None:
            self.client.send(msg)

    def reachable_objects(self):
        objs = list(self.pockets)
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

    def cmd_describe(self, player, query):
        """describe <object> <description>: give a description to a room, player or thing."""
        if query is None:
            return self.send("Describe what?")
        what, description = re.match(r"(\w+) (.*)", query).groups()

        def doit(thing):
            thing.description = description.replace("\\n", "\n").replace("\\t", "\t")
            self.send("Added description of {}".format(thing.name))

        self.find_doit(what, doit)

    def cmd_go(self, player, query):
        """go [to] <place>: move to a different place."""
        if query is None:
            return self.send("Go where?")
        place = re.match(r"(?:to )?(.*)", query).group(1)

        def doit(arg):
            if self.room is not None:
                self.room.contents.remove(self)
                self.room.emit(self.name + " has gone to " + arg.name)
                arg.emit(self.name + " arrives from " + self.room.name)
            else:
                arg.emit(self.name + " pops into the room")
            self.room = arg
            self.room.contents.append(self)
            self.cmd_look(self, "here")

        util.find_and_do(
            player,
            place,
            doit,
            db.list_all(MRRoom),
            notfound="Don't know this place. Is it in Canada?",
        )

    def cmd_look(self, player, query):
        """look [object]: see descriptions of things, people or places."""

        def doit(arg):
            if arg is None:
                self.send("You only see nothing. A lot of nothing.")
                return
            self.send(f"\033[34m{arg.name}\033[0m: {arg.description}")
            if util.is_room(arg):
                self.send("")  # extra newline
                if len(arg.contents) == 0:
                    self.send("It is empty")
                else:
                    self.send("Contents:")
                for thing in arg.contents:
                    self.send(" - " + thing.name)
                if len(arg.exits) > 0:
                    self.send("Nearby places:")
                for room in arg.exits:
                    self.send(" - " + room.name)
                self.send("")

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
    }

    def exec_env(self, caller):
        locs = {
            "db": lambda x: proxify(db.get(x)),
            "me": proxify(caller),
        }
        if caller.room is not None:
            locs["here"] = proxify(caller.room)
        return locs

    def cmd_eval(self, caller, rest):
        """eval <string>: evaluate the string as raw code."""
        try:
            env = self.exec_env(caller)
            caller.send(repr(eval(rest, env)))
        except Exception as e:
            cls = e.__class__.__name__
            caller.send(f"{cls}: {e}")

    def cmd_exec(self, caller, rest):
        """exec <string>: execute raw code."""
        try:
            env = self.exec_env(caller)
            exec(util.unescape(rest), env)
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
            return doit(db.get(int(m.group(1))), None)

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
            return doit(db.get(int(m.group(1))), None)

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
            return doit(db.get(int(m.group(1))), None)

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

        def doit(thing, _):
            thing.add_cmd(CustomCommand(cmd, txt, thing))
            caller.send(f"Added command {cmd} to {thing.name}")

        if (m := re.match("#(\d+)", target)) is not None:
            doit(db.get(int(m.group(1))))
        else:
            caller.find_doit(target, doit)


class Maker(MRPower):
    fw_cmds = {
        "dig": "cmd_dig",
        "make": "cmd_make",
        "destroy": "cmd_destroy",
    }

    def cmd_dig(self, caller, query):
        """dig <room name>: make a new room."""
        room = MRRoom(query)
        db.add(room)
        if caller.room is None:
            caller.send("In a flash of darkness, a new place apepars around you.")
            caller.cmd_go(caller, query)
            return
        caller.room.emit(f"{caller.name} opens a new path towards {query}")
        caller.room.cmd_link(caller, query)

    def cmd_make(self, caller, query):
        """make <thing name>: make things. Just regular things."""
        if caller.room is None:
            return caller.send("There is nowehere to make things into.")
        name = query
        thing = MRThing(name)
        db.add(thing)
        thing.room = caller.room
        caller.room.contents.append(thing)
        caller.room.emit(f"{caller.name} makes {name} appear out of thin air.")

    def cmd_destroy(self, caller, query):
        """destroy <thing>: destroy things. Anything, really."""
        if query is None:
            return caller.send("Destroy what?")

        def doit(thing):
            if caller.room is not None:
                if util.is_room(thing):
                    caller.room.emit(f"{caller.name} blew up the place!")
                    caller.room.emit("You fall into the void of nothingness.")
                    for p in filter(util.is_player, thing.contents):
                        p.room = None
                else:
                    caller.room.emit(
                        caller.name + " violently destroyed " + thing.name + "!"
                    )
                    caller.room.contents.remove(thing)
            db.remove(thing)
            if util.is_player(thing):
                if thing.client is not None:
                    thing.client.player = None
                    thing.send(
                        "Your character has been slain. You were kicked out of it"
                    )

        caller.find_doit(query, doit)
