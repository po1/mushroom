import re

from mushroom import util
from mushroom.util import ActionFailed
from mushroom.world.objects import Object


class Room(Object):
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
            if not isinstance(obj, Object) and not caller.has_flag("big"):
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
