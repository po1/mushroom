from . import util

from .db import db
from .interface import BaseObject
from .register import register


@register
class MRObject(BaseObject):
    """
    The base object class of the world.
    Every object belonging to the world
    must inherit from this class
    """
    pass


@register
class MRThing(MRObject):
    """
    Things that are not players or rooms.
    Usually common objects, usable or not.
    """

    fancy_name = "thing"

    def __init__(self, name):
        super(MRThing, self).__init__(name)
        self.description = "A boring non-descript thing."


@register
class MRRoom(MRObject):
    """
    The parent class for every room of
    the world. Any room should inherit
    from this class.
    """

    fancy_name = "room"
    fw_cmds = {
            "say"    : "cmd_say",
            "emit"   : "cmd_emit",
            "link"   : "cmd_link",
            "unlink" : "cmd_unlink"
    }

    def __init__(self, name):
        super(MRRoom, self).__init__(name)
        self.contents = []
        self.exits = []
        self.description = "A blank room."

    def emit(self, msg):
        for thing in filter(util.is_player, self.contents):
            thing.send(msg)

    def oemit(self, player, msg):
        for pl in filter(util.is_player, self.contents):
            if pl != player:
                pl.send(msg)

    def cmd_say(self, player, rest):
        self.emit(player.name + " says: " + rest)

    def cmd_emit(self, player, rest):
        self.emit(rest.replace('\\n', '\n').replace('\\t', '\t'))

    def cmd_link(self, player, rest):
        def doit(arg, _):
            self.exits.append(arg)
            self.emit("Linked {} and {}".format(arg.name, self.name))

        util.find_and_do(player, rest, doit,
                         db.list_all(MRRoom),
                         notfound="Don't know this place. Is it in Canada?")

    def cmd_unlink(self, player, rest):
        def doit(arg, _):
            self.exits.remove(arg)
            self.emit("Unlinked {} and {}".format(arg.name, self.name))

        util.find_and_do(player, rest, doit,
                         self.exits,
                         noarg="Unlink what?",
                         notfound="This room ain't connected to Canada.",
                         )


@register
class MRPlayer(MRObject):
    """
    Basic Player.
    Other player classes derive from this
    """

    fancy_name = "player"
    fw_cmds = {
            "look"     : "cmd_look",
            "go"       : "cmd_go",
            "describe" : "cmd_describe",
            "cmd"      : "cmd_cmd",
            "destroy"  : "cmd_destroy",
            "examine"  : "cmd_examine",
    }

    def __init__(self, name):
        super(MRPlayer, self).__init__(name)
        self.description = "A non-descript citizen."
        self.client = None
        self.room = None
        self.powers = []

    def __getstate__(self):
        odict = super(MRPlayer, self).__getstate__()
        del odict['client']
        return odict

    def __setstate__(self, dict):
        super(MRPlayer, self).__setstate__(dict)
        self.client = None

    def send(self, msg):
        if self.client is not None:
            self.client.send(msg)


    def reachable_objects(self):
        objs = []
        if self.room is not None:
            objs.extend(self.room.contents)
        return objs

    def find_doit(self, rest, dofun, **kwargs):
        util.find_and_do(self, rest, dofun,
                         self.reachable_objects(),
                         short_names=util.player_snames(self),
                         **kwargs)

    def cmd_describe(self, player, rest):
        def doit(thing, _):
            thing.description = (' '.join(rest.split()[1:])
                    .replace('\\n', '\n').replace('\\t', '\t'))
            self.send("Added description of {}".format(thing.name))

        self.find_doit(rest, doit, noarg="Describe what?")

    def cmd_cmd(self, player, rest):
        def doit(thing, _):
            if len(rest.split()) < 2:
                self.send("I need a command name.")
                return
            cmd = rest.split()[1]
            cmd_name = "cmd_" + cmd
            cmd_txt = (' '.join(rest.split()[2:])
                    .replace('\\n', '\n').replace('\\t', '\t'))
            try:
                thing.add_cmd(cmd, cmd_name, cmd_txt)
                self.send("Added command {} to {}".format(cmd_name, thing.name))
            except Exception:
                self.send("Something went wrong when adding the command.")

        self.find_doit(rest, doit, noarg="Add a command to what?")

    def cmd_go(self, player, rest):
        def doit(arg, _):
            if self.room is not None:
                self.room.contents.remove(self)
                self.room.emit(self.name + ' has gone to ' + arg.name)
                arg.emit(self.name + ' arrives from ' + self.room.name)
            else:
                arg.emit(self.name + ' pops into the room')
            self.room = arg
            self.room.contents.append(self)
            self.cmd_look(self, "here")

        util.find_and_do(player, rest, doit,
                         db.list_all(MRRoom),
                         noarg="Go where?",
                         notfound="Don't know this place. Is it in Canada?")

    def cmd_destroy(self, player, rest):
        def doit(thing, _):
            if self.room is not None:
                if util.is_room(thing):
                    self.room.emit(player.name + " blew up the place!")
                    self.room.emit("You fall into the void of nothingness.")
                    for p in filter(util.is_player, thing.contents):
                        p.room = None
                else:
                    self.room.emit(player.name + " violently destroyed " +
                                   thing.name + "!")
                    self.room.contents.remove(thing)
            db.remove(thing)
            if util.is_player(thing):
                if thing.client is not None:
                    thing.client.player = None
                    thing.send("Your character has been slain. You were kicked out of it")

        self.find_doit(rest, doit, noarg="Destroy what?")

    def cmd_look(self, player, rest):
        def doit(arg, _):
            if arg is None:
                self.send("You only see nothing. A lot of nothing.")
                return
            self.send(arg.name + ": " + arg.description)
            if util.is_room(arg):
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
        util.find_and_do(player, rest, doit,
                         self.reachable_objects(),
                         short_names=util.player_snames(self, allow_no_room=True),
                         arg_default="here",
                         notfound=notfound)

    def cmd_examine(self, player, rest):
        def doit(arg, rest):
            if rest:
                arg_name = '{}.{}'.format(arg.name, rest)
                arg_cmd = 'arg.{}'.format(rest) if rest.strip() else 'arg'
                try:
                    # XXX: security (who cares?)
                    arg = eval(arg_cmd)
                except AttributeError:
                    self.send("{} has no attribute {}".format(arg.name, rest))
                    return
                except Exception:
                    self.send("I don't know what just happened, "
                              "but don't do that again.")
                    return
            else:
                arg_name = arg.name
            self.send('{}: {}'.format(arg_name, util.myrepr(arg, db)))
            internals = {}
            for attr in dir(arg):
                if attr[0] == '_':
                    continue
                attr_val = getattr(arg, attr)
                if not isinstance(attr_val, util.member_types + (BaseObject,)):
                    continue
                internals[attr] = util.myrepr(attr_val, db)
            if internals:
                for k in sorted(internals):
                    self.send(" - {}: {}".format(k, internals[k]))

        dots = rest.split('.')
        rest = '{} {}'.format(dots[0], '.'.join(dots[1:]))
        util.find_and_do(player, rest, doit,
                         self.reachable_objects(),
                         short_names=util.player_snames(self),
                         arg_default="here")


@register
class MRPower(object):
    fw_cmds = {}

    @classmethod
    def cmdlist(cls):
        a = cls.fw_cmds
        for c in cls.__bases__:
            if issubclass(c, MRPower) and c is not MRPower:
                a.update(c.cmdlist())
        return a


@register
class MRArchi(MRPower):
    """
    Architect class
    Has extended powers
    """

    fw_cmds = {
        'eval':'cmd_eval',
        'exec':'cmd_exec',
    }

    def cmd_eval(self, rest):
        try:
            genv, lenv = self._safe_env()
            self.send(str(eval(rest, genv, lenv)))
        except Exception as pbm:
            self.send(str(pbm))

    def cmd_exec(self, rest):
        try:
            genv, lenv = self._safe_env()
            exec(rest.replace('\\n', '\n').replace('\\t', '\t'), genv, lenv)
        except Exception as pbm:
            self.send(str(pbm))


@register
class ArchiPlayer(MRPlayer):

    fancy_name = "archi"

    def __init__(self, name):
        MRPlayer.__init__(self, name)
        self.powers.append(MRArchi())

    def _safe_env(self):
        cl = self.client
        locd = {
            'client': cl,
            'db': db,
            'me': cl.player,
            'here': cl.player.room if cl.player is not None else None,
        }
        return globals(), locd
