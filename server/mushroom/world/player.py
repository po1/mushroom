import itertools
import logging
import re

import frozendict

from mushroom import util
from mushroom.util import ActionFailed, regexp_command
from mushroom.world.objects import Config, StuffBase, Thing
from mushroom.world.room import Room

logger = logging.getLogger(__name__)


class Player(StuffBase):
    """
    Basic Player.
    Other player classes derive from this
    """

    fancy_name = "player"
    fw_cmds = frozendict.frozendict(
        {
            "look": "cmd_look",
            "describe": "cmd_describe",
        }
    )
    fw_event_handlers = frozendict.frozendict(
        {
            "connect": "on_connect",
            "emit": "on_emit",
            **StuffBase.fw_event_handlers,
        }
    )
    default_description = "A non-descript citizen."

    def __init__(self, name):
        self._client = None
        self._game = None
        self.powers = []
        super().__init__(name)

    def play(self, client, game):
        self._client = client
        self._game = game

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
            if not isinstance(thing, Thing):
                continue
            pows.extend(thing.powers)
        return pows

    @property
    def client(self):
        return self._client

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
                if isinstance(thing, Thing):
                    fw_cmds.extend(onlyflag(flag, thing._fwcmds))
                    custom_cmds.extend(onlyflag(flag, thing.commands))

        addthingcmds(self, "o")
        if self.location is not None:
            addthingcmds(self.location, "p")
            room_flag = "" if isinstance(self.location, Room) else "i"
            fw_cmds += onlyflag(room_flag, self.location._fwcmds)
            custom_cmds += onlyflag(room_flag, self.location.commands)

        if (master_room := Config.get_entry("master_room")) is not None:
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
        if not isinstance(object, Thing):
            raise ActionFailed(f"Can not move {object.name}.")
        if not hasattr(destination, "contents"):
            raise ActionFailed(f"{destination.name} has no room for {object.name}")
        if object.has_flag("big"):
            raise ActionFailed(f"{object.name} is too big.")
        if object is destination:
            raise ActionFailed("Can not move into itself.")
        util.moveto(object, destination)

    def send(self, msg):
        if self._client is not None:
            self._client.send(msg)

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
        caller.send(f"Added description of {thing.name}")

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
