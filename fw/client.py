from .util import MRFW
from .util import EmptyArgException
from .util import log_err

from .world import get_type
from .db import MRDB


class BaseClient:
    """
    Base class for MUSHRoom clients
    """
    def __init__(self, handler, name):
        self.handler = handler
        self.name = name
        self.op = False

    def send(self, msg):
        try:
            self.handler.wfile.write(msg + "\n")
        except:
            log_err("Could not send to " + self.name)

    def handle_input(self, data):
        pass

    def on_disconnect(self):
        pass


class MRClient(BaseClient):
    """
    This class is one of the only interfaces
    between the FW and the server.
    """

    cmds = {'chat':'cmd_chat',
            'name':'cmd_name',
            'help':'cmd_help',
            'create':'cmd_create',
            'play':'cmd_play',
            'eval':'cmd_eval',
            'exec':'cmd_exec'}


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
            if len(MRDB.search(words[1])) > 0:
                self.send("Uhm... something by that name already exists...")
                return
            thing = cls(' '.join(words[1:]))
            MRDB.objects.append(thing)
            if MRFW.is_thing(thing) and self.player != None:
                if self.player.room != None:
                    self.player.room.contents.append(thing)

    def cmd_play(self, rest):
        try:
            who = MRFW.get_first_arg(rest)
        except EmptyArgException:
            self.send("Play who?")
            return
        found = MRDB.search(who, get_type('player'))
        if len(found) < 1:
            self.send("Couldn't find the guy.")
        elif len(found) > 1:
            self.send(MRFW.multiple_choice(found))
        else:
            if self.player != None:
                self.player.client = None
            self.player = found[0]
            found[0].client = self

    def _safe_env(self):
        locd = {
            'me': self.player,
            'here': self.player.room,
        }
        return globals(), locd

    def cmd_eval(self, rest):
        try:
            genv, lenv = self._safe_env()
            self.send(str(eval(rest, genv, lenv)))
        except Exception, pbm:
            self.send(str(pbm))

    def cmd_exec(self, rest):
        try:
            genv, lenv = self._safe_env()
            exec(rest.replace('\\n','\n').replace('\\t','\t'), genv, lenv)
        except Exception, pbm:
            self.send(str(pbm))

    def handle_input(self, data):
        cmds = {}
        for k in self.cmds.keys():
            cmds[k] = self
        if self.player != None:
            for k in self.player.cmds.keys():
                cmds[k] = self.player
            if self.player.room != None:
                for k in self.player.room.cmds.keys():
                    cmds[k] = self.player.room
        words = data.split()
        match = filter(lambda x:MRFW.match_name(words[0], x), cmds.keys())
        if len(match) != 1:
            self.send("Huh?")
            return
        if cmds[match[0]] == self:
            cmd = getattr(self, self.cmds[match[0]])
            cmd(' '.join(words[1:]))
        else:
            t = cmds[match[0]]
            cmd = getattr(t, t.cmds[match[0]])
            cmd(self.player, ' '.join(words[1:]))

    def on_disconnect(self):
        if self.player != None:
            self.player.client = None

