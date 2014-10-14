from . import util
from . import db

from .register import get_type
from .interface import BaseClient


class MRClient(BaseClient):
    """
    This class is one of the only interfaces
    between the FW and the server.
    """

    cmds = {
            'chat'   : 'cmd_chat',
            'name'   : 'cmd_name',
            'help'   : 'cmd_help',
            'create' : 'cmd_create',
            'play'   : 'cmd_play',
    }


    def __init__(self, handler, name):
        BaseClient.__init__(self, handler, name)
        self.player = None

    def cmd_chat(self, rest):
        self.handler.server.cr.broadcast("[global] " + self.name +
                " says: " + rest)

    def cmd_name(self, rest):
        words = rest.split()
        if len(words) < 1:
            self.send("Again?")
        else:
            self.name = words[0]

    def cmd_help(self, rest):
        if not rest:
            self.send("Contextual commands:")
            self.send("  {}".format(', '.join(sorted(self.available_cmds()))))
        return
        # TODO: add help topics for each command
        self.send("chat <text>           global chat\n"
                  "name <name>           change your client name\n"
                  "exec <command>        execute python command\n"
                  "eval <expression>     evaluate python expression\n"
                  "create <type> <name>  thing, player, or room\n"
                  "play <name>           go in the shoes of a player\n"
                  "go <place>            move to a room\n"
                  "look                  in a room, look around")

    def cmd_create(self, rest):
        words = rest.split()
        if len(words) < 2:
            self.send("Cannot create a nameless thing...")
            return
        cls = get_type(words[0])
        if cls is None:
            self.send("Create a what?")
        else:
            if len(db.search(words[1])) > 0:
                self.send("Uhm... something by that name already exists...")
                return
            thing = cls(' '.join(words[1:]))
            db.objects.append(thing)
            if util.is_thing(thing) and self.player is not None:
                if self.player.room is not None:
                    self.player.room.contents.append(thing)

    def cmd_play(self, rest):
        def doit(arg, _):
            if self.player is not None:
                self.player.client = None
            self.player = arg
            arg.client = self

        util.find_and_do(self, rest, doit,
                         db.list_all(get_type('player')),
                         short_names=[],
                         noarg="Play who?",
                         notfound="Couldn't find the guy.")

    def available_cmds(self):
        """
        Looks for commands in (in this order):
        - client
        - player
        - room
        """

        def clientcmd(fun):
            def r(pl, rest):
                return fun(rest)
            return r

        cmds = {}
        for k, c in self.cmds.items():
            cmds[k] = clientcmd(getattr(self, c))
        if self.player is not None:
            for k, c in self.player.cmds.items():
                cmds[k] = getattr(self.player, c)
            for p in self.player.powers:
                for k, c in p.cmdlist().items():
                    cmds[k] = getattr(p, c).im_func
            if self.player.room is not None:
                for k, c in self.player.room.cmds.items():
                    cmds[k] = getattr(self.player.room, c)
        return cmds


    def handle_input(self, data):
        """
        Basic handler for commands
        """
        cmds = self.available_cmds()
        words = data.split()
        match = filter(lambda x:util.match_name(words[0], x), cmds.keys())
        if len(match) != 1:
            self.send("Huh?")
            return
        cmd = cmds[match[0]]
        cmd(self.player, ' '.join(words[1:]))

    def on_disconnect(self):
        if self.player is not None:
            self.player.client = None

