from .util import MRFW
from .util import NotFoundException, AmbiguousException, EmptyArgException

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
    cmds = {"say":"cmd_say"}

    def __init__(self, name):
        super(MRRoom, self).__init__(name)
        self.contents = []
        self.description = "A blank room."

    def cmd_say(self, player, rest):
        self.broadcast(player.name + " says: " + rest)

    def broadcast(self, msg):
        for thing in filter(MRFW.is_player, self.contents):
            thing.send(msg)


class MRPlayer(MRObject):
    fancy_name = "player"
    cmds = {"look":"cmd_look",
            "go":"cmd_go",
            'describe':'cmd_describe',
            "destroy":"cmd_destroy"}

    def __init__(self, name):
        super(MRPlayer, self).__init__(name)
        self.description = "A non-descript citizen."
        self.client = None
        self.room = None

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['client']
        return odict

    def __setstate__(self, dict):
        self.__dict__.update(dict)
        self.client = None

    def send(self, msg):
        if self.client != None:
            self.client.send(msg)

    def find_thing(self, name):
        if name == "me" or name == self.name:
            return self
        if self.room == None:
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
            thing.description = ' '.join(rest.split()[1:])

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
            if self.room != None:
                self.room.contents.remove(self)
                self.room.broadcast(self.name + ' has gone to ' + found[0].name)
                found[0].broadcast(self.name + ' arrives from ' + self.room.name)
            else:
                found[0].broadcast(self.name + ' pops into the room')
            self.room = found[0]
            self.room.contents.append(self)

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
            if self.room != None:
                self.room.broadcast(self.name + " violently destroyed " + thing.name + "!")
                if MRFW.is_room(thing):
                    self.room.broadcast("You are expulsed into the void of nothingness.")
                    for p in filter(MRFW.is_player, thing.contents):
                        p.room = None
                else:
                    self.room.contents.remove(thing)
            MRDB.objects.remove(thing)
            if MRFW.is_player(thing):
                if thing.client != None:
                    thing.client.player = None
                    thing.send("Your player has been slain. You were kicked out of it")


    def cmd_look(self, player, rest):
        try:
            what = MRFW.get_first_arg(rest)
        except EmptyArgException:
            what = "here"
        if what == "here":
            if self.room == None:
                self.send("You only see nothing. A lot of nothing.")
            else:
                self.send(self.room.name + ": " + self.room.description)
                if len(self.room.contents) == 0:
                    self.send("It is empty")
                else:
                    self.send("Contents:")
                for thing in self.room.contents:
                    self.send(" - " + thing.name)
        elif what == "me" or what==self.name:
                self.send(self.name + ": " + self.description)
        else:
            if self.room == None:
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

