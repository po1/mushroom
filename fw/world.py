from .util import MRFW
from .util import NotFoundException, AmbiguousException, EmptyArgException


def get_type(fancy_name):
    for c in globals().itervalues():
        if getattr(c, 'fancy_name', None) == fancy_name:
            return c
    return None


class MRObject(object):
    """
    The base object class of the world.
    Every object belonging to the world
    should inherit from this class
    """

    fancy_name = "object"
    cmds = {}

    def __init__(self, name):
        self.name = name
        self.custom_cmds = {}

    def __getstate__(self):
        odict = self.__dict__.copy()
        for cmd in self.custom_cmds:
            del odict[self.cmds[cmd]]
        return odict

    def __setstate__(self, mdict):
        self.__dict__.update(mdict)
        sample = self.__class__("sample")
        self.__dict__.update(dict([(k, sample.__dict__[k]) for k in
                                   [x for x in sample.__dict__
                                    if x not in mdict]]))
        for cmd in self.custom_cmds:
            mcmd = self.custom_cmds[cmd]
            self.add_cmd(cmd, mcmd[0], mcmd[1])

    def add_cmd(self, cmd, cmd_name, cmd_txt):
        self.cmds[cmd] = cmd_name
        txt = cmd_txt.replace('\n', '\n\t')
        txt = ("def ___tmp(self, player, rest):\n"
               "\t{}\n\n"
               "self.{} = ___tmp.__get__(self, {})
               .format(txt, cmd_name, self.__class__.name))
        exec(txt)



class MRThing(MRObject):
    """
    Things that are not players or rooms.
    Usually common objects, usable or not.
    """

    fancy_name = "thing"

    def __init__(self, name):
        super(MRThing, self).__init__(name)
        self.description = "A boring non-descript thing."


class MRRoom(MRObject):
    """
    The parent class for every room of
    the world. Any room should inherit
    from this class.
    """

    fancy_name = "room"
    cmds = {"say":"cmd_say",
            "emit":"cmd_emit",
            "link":"cmd_link",
            "unlink":"cmd_unlink"}
    }

    def __init__(self, name):
        super(MRRoom, self).__init__(name)
        self.contents = []
        self.exits = []
        self.description = "A blank room."

    def emit(self, msg):
        for thing in filter(MRFW.is_player, self.contents):
            thing.send(msg)

    def oemit(self, player, emit):
        for pl in filter(MRFW.is_player, self.contents):
            if pl != player:
                pl.send(msg)

    def cmd_say(self, player, rest):
        self.emit(player.name + " says: " + rest)

    def cmd_emit(self, player, rest):
        self.emit(rest.replace('\\n','\n').replace('\\t','\t'))

    def cmd_link(self, player, rest):
        try:
            what = MRFW.get_first_arg(rest)
        except EmptyArgException:
            player.send("Link to where?")
            return
        found = MRDB.search(what, MRRoom)
        if len(found) < 1:
            player.send("Don't know this place. Is it in Canada?")
        elif len(found) > 1:
            player.send(MRFW.multiple_choice(found))
        else:
            self.exits.append(found[0])

    def cmd_unlink(self, player, rest):
        try:
            what = MRFW.get_first_arg(rest)
        except EmptyArgException:
            player.send("Unlink what?")
            return
        match = filter(lambda x:MRFW.match_name(rest, x.name), self.exits)
        if len(match) < 1:
            player.send("This room ain't connected to Canada.")
        elif len(match) > 1:
            player.send(MRFW.multiple_choice(match))
        else:
            self.exits.remove(match[0])


class MRPlayer(MRObject):
    """
    Basic Player.
    Other player classes derive from this
    """

    fancy_name = "player"
    cmds = {
            "look"     : "cmd_look",
            "go"       : "cmd_go",
            "describe" : "cmd_describe",
            "cmd"      : "cmd_cmd",
            "destroy"  : "cmd_destroy",
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

    def find_thing(self, name):
        if name == "me" or name == self.name:
            return self
        if self.room is None:
            raise NotFoundException()
        if name == "here":
            return self.room
        match = filter(lambda x:MRFW.match_name(name, x.name), self.room.contents)
        if len(match) > 1:
            raise AmbiguousException(match)
        if len(match) < 1:
            raise NotFoundException()
        return match[0]

    def cmd_describe(self, player, rest):
        try:
            what = MRFW.get_first_arg(rest)
            thing = self.find_thing(what)
        except AmbiguousException, ex:
            self.send(MRFW.multiple_choice(ex.choices))
        except NotFoundException:
            self.send("You see nothing like '" + what + "' here.")
        except EmptyArgException:
            self.send("Describe what?")
        else:
            thing.description = (' '.join(rest.split()[1:])
                                 .replace('\\n','\n').replace('\\t','\t'))


    def cmd_cmd(self, player, rest):
        try:
            what = MRFW.get_first_arg(rest)
            thing = self.find_thing(what)
        except AmbiguousException, ex:
            self.send(MRFW.multiple_choice(ex.choices))
        except NotFoundException:
            self.send("You see nothing like '" + what + "' here.")
        except EmptyArgException:
            self.send("What do you want to add a command to?")
        else:
            if len(rest.split()) < 2:
                self.send("I need a command name.")
                return
            cmd = rest.split()[1]
            cmd_name = "cmd_" + cmd
            cmd_txt = string.join(rest.split()[2:]).replace('\\n','\n').replace('\\t','\t')
            thing.custom_cmds[cmd] = (cmd_name, cmd_txt)
            thing.add_cmd(cmd, cmd_name, cmd_txt)

    def cmd_go(self, player, rest):
        from .db import MRDB

        try:
            what = MRFW.get_first_arg(rest)
        except EmptyArgException:
            self.send("Go where?")
            return
        found = MRDB.search(what, MRRoom)
        if len(found) < 1:
            self.send("Don't know this place. Is it in Canada?")
        elif len(found) > 1:
            self.send(MRFW.multiple_choice(found))
        else:
            if self.room is not None:
                self.room.contents.remove(self)
                self.room.emit(self.name + ' has gone to ' + found[0].name)
                found[0].emit(self.name + ' arrives from ' + self.room.name)
            else:
                found[0].emit(self.name + ' pops into the room')
            self.room = found[0]
            self.room.contents.append(self)
            self.cmd_look(self, "here")

    def cmd_destroy(self, player, rest):
        from .db import MRDB

        try:
            what = MRFW.get_first_arg(rest)
            thing = self.find_thing(what)
        except AmbiguousException, ex:
            self.send(MRFW.multiple_choice(ex.choices))
        except NotFoundException:
            self.send("You see nothing like '" + what + "' here.")
        except EmptyArgException:
            self.send("Destroy what?")
        else:
            if self.room is not None:
                self.room.emit(self.name + " violently destroyed " + thing.name + "!")
                if MRFW.is_room(thing):
                    self.room.emit("You are expulsed into the void of nothingness.")
                    for p in filter(MRFW.is_player, thing.contents):
                        p.room = None
                else:
                    self.room.contents.remove(thing)
            MRDB.objects.remove(thing)
            if MRFW.is_player(thing):
                if thing.client is not None:
                    thing.client.player = None
                    thing.send("Your player has been slain. You were kicked out of it")


    def cmd_look(self, player, rest):
        try:
            what = MRFW.get_first_arg(rest)
        except EmptyArgException:
            what = "here"
        if what == "here":
            if self.room is None:
                self.send("You only see nothing. A lot of nothing.")
            else:
                self.send(self.room.name + ": " + self.room.description)
                if len(self.room.contents) == 0:
                    self.send("It is empty")
                else:
                    self.send("Contents:")
                for thing in self.room.contents:
                    self.send(" - " + thing.name)
                if len(self.room.exits) > 0:
                    self.send("Nearby places:")
                for room in self.room.exits:
                    self.send(" - " + room.name)
                self.send("")
        elif what == "me" or what==self.name:
                self.send(self.name + ": " + self.description)
                self.send("")
        else:
            if self.room is None:
                self.send("You see nothing but you.")
            else:
                try:
                    thing = self.find_thing(what)
                except AmbiguousException, ex:
                    self.send(MRFW.multiple_choice(ex))
                except NotFoundException:
                    self.send("You see nothing like '" + what + "' here.")
                else:
                    self.send(thing.name + ": " + thing.description)


class MRPower(object):
    cmds = {}

    @classmethod
    def cmdlist(cls):
        a = cls.cmds
        for c in cls.__bases__:
            if issubclass(c, MRPower) and c is not MRPower:
                a.update(c.cmdlist())
        return a


class MRArchi(MRPower):
    """
    Architect class
    Has extended powers
    """

    cmds = {'eval':'cmd_eval',
            'exec':'cmd_exec'}

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


class ArchiPlayer(MRPlayer):

    fancy_name = "archi"

    def __init__(self, name):
        MRPlayer.__init__(self, name)
        self.powers.append(MRArchi())

    def _safe_env(self):
        cl = self.client
        locd = {
            'client': cl,
            'me': cl.player,
            'here': cl.player.room if cl.player is not None else None,
        }
        return globals(), locd
