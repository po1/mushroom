from . import util

from .register import get_type

from .commands import HelpCommand
from .commands import PlayCommand
from .commands import WrapperCommand


class MRClient:
    """
    This class is one of the only interfaces
    between the FW and the server.
    """

    fw_cmds = {
            'help'   : HelpCommand,
            'play'   : PlayCommand,
    }

    def __init__(self, handler, name):
        self.handler = handler
        self.name = name
        self.cmds = {}
        for k, v in self.fw_cmds.items():
            self.add_cmd(k, v())
        self.player = None

    def add_cmd(self, name, command):
        self.cmds[name] = command

    def remove_cmd(self, command):
        if type(command) is str and command in self.cmds:
            del self.cmds[command]
        else:
            for k in [x for x in self.cmds if self.cmds[x] == command]:
                del self.cmds[k]

    def send(self, msg):
        try:
            self.handler.handler_write((msg + "\n"))
        except IOError:
            util.log_err(f"Could not send to {self.name}")


    def available_cmds(self):
        """
        Looks for commands in (in this order):
        - client
        - player
        - room
        - room contents
        """

        def add_cmds(cmds, obj):
            for k, v in obj.cmds.items():
                cmds[k] = WrapperCommand(getattr(obj, v, None), self.player)

        def add_power_cmds(cmds, power):
            for k, v in power.fw_cmds.items():
                cmd = getattr(power.__class__, v).__get__(self.player,
                                                          get_type('player'))
                cmds[k] = WrapperCommand(lambda _, x: cmd(x))

        cmds = self.cmds.copy()
        if self.player:
            add_cmds(cmds, self.player)
            for p in self.player.powers:
                add_power_cmds(cmds, p)
            if self.player.room:
                add_cmds(cmds, self.player.room)
                for o in self.player.room.contents:
                    if isinstance(o, get_type('thing')):
                        add_cmds(cmds, o)
        return cmds


    def handle_input(self, data):
        """
        Basic handler for commands
        """
        cmds = self.available_cmds()
        words = data.split()
        match = [x for x in list(cmds.keys()) if util.match_name(words[0], x)]
        if len(match) != 1:
            self.send("Huh?")
            return
        cmd = cmds[match[0]]
        cmd.call(self, words[0], ' '.join(words[1:]))

    def on_disconnect(self):
        if self.player is not None:
            self.player.client = None