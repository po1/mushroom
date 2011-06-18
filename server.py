import threading
import SocketServer
import time
import socket 
import string

class MRFW:
    @staticmethod
    def is_type(thing, type):
        try:
            if thing.__class__.fancy_name == type:
                return True
        except:
            pass
        return False

    @staticmethod
    def is_room(thing):
        return MRFW.is_type(thing, "room")

    @staticmethod
    def is_thing(thing):
        return MRFW.is_type(thing, "thing")

    @staticmethod
    def is_player(thing):
        return MRFW.is_type(thing, "player")

    @staticmethod
    def match_name(short, name):
        if short == name[:len(short)]:
            return True
        return False

    @staticmethod
    def get_first_arg(data):
        words = data.split()
        if len(words) < 1:
            raise EmptyArgException()
        return words[0]

    @staticmethod
    def multiple_choice(choices):
        names = map(lambda x:x.name, choices)
        return "Which one?\nChoices are: " + string.join(names, ', ')


class MRObject(object):
    fancy_name = "thing"
    cmds = {}

    def __init__(self, name):
        self.name = name

class MRRoom(MRObject):
    fancy_name = "room"
    cmds = {"say":"cmd_say"}

    def __init__(self, name):
        super(MRRoom,self).__init__(name)
        self.description = "A blank room."
        self.contents = []

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
        super(MRPlayer,self).__init__(name)
        self.client = None
        self.room = None
        self.description = "A non-descript citizen."

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['client']
        return odict

    def __setstate__(self, dict):
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
            thing.description = string.join(rest.split()[1:])

    def cmd_go(self, player, rest):
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
            self.room = found[0]
            self.room.contents.append(self)

    def cmd_destroy(self, player, rest):
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


class MRDB:
    classes = [MRObject, MRRoom, MRPlayer]
    objects = []

    @staticmethod
    def search(name, type = MRObject):
        found = []
        for thing in MRDB.objects:
            if MRFW.match_name(name, thing.name):
                if isinstance(thing, type):
                    found.append(thing)
        return found

    @staticmethod
    def list_all(type):
        return MRDB.search("", type)



class ClientRegister:    
    clients = []
    idmap = {}
    lastid = 0
    def broadcast(self, msg):
        for c in self.clients:
            c.send(msg)

    def broadcast_except(self, client, msg):
        for c in self.clients:
            if c is not client:
                c.send(msg)

    def get_uid(self):
        self.lastid += 1
        return self.lastid

    def add(self, client):
        self.clients.append(client)
        self.idmap[client.id] = client

    def delete(self, client):
        del self.idmap[client.id]
        self.clients.remove(client)

class AmbiguousException(Exception):
    def __init__(self, choices):
        self.choices = choices

class NotFoundException(Exception):
    pass

class EmptyArgException(Exception):
    pass

class MRClient:
    cmds = {'chat':'cmd_chat', 
            'name':'cmd_name',
            'help':'cmd_help',
            'create':'cmd_create',
            'play':'cmd_play',
            'eval':'cmd_eval',
            'exec':'cmd_exec'}
          
    def __init__(self, handler, name):
        self.handler = handler
        self.name = name
        self.op = 0
        handler.server.cr.broadcast(name + " connected!")
        self.id = handler.server.cr.get_uid()
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
                  "create <type> <name>  thing, player, or room\n"
                  "play <name>           go in the shoes of a player\n"
                  "go <place>            move to a room\n"
                  "look                  in a room, look around")

    def cmd_create(self, rest):
        words = rest.split()
        if len(words) < 2:
            self.send("Cannot create a nameless thing...")
            return
        cls = filter(lambda x:MRFW.match_name(words[0], x.fancy_name), MRDB.classes)
        if len(cls) != 1:
            self.send("Create a what?")
        else:
            thing = cls[0](words[1])
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
        found = MRDB.search(who, MRPlayer)
        if len(found) < 1:
            self.send("Couldn't find the guy.")
        elif len(found) > 1:
            self.send(MRFW.multiple_choice(found))
        else:
            if self.player != None:
                self.player.client = None
            self.player = found[0]
            found[0].client = self

    def cmd_eval(self, rest):
        try:
            self.send(str(eval(rest)))
        except Exception, pbm:
            self.send(str(pbm))

    def cmd_exec(self, rest):
        try:
            exec(rest.replace('\\n','\n').replace('\\t','\t'))
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
            cmd(string.join(words[1:]))
        else:
            t = cmds[match[0]]
            cmd = getattr(t, t.cmds[match[0]])
            cmd(self.player, string.join(words[1:]))

    def is_op(self):
        return self.op

    def send(self, msg):
        try:
            self.handler.request.send(msg + "\n")
        except:
            print "Could not send to " + self.name

    def on_disconnect(self):
        if self.player != None:
            self.player.client = None


class ThreadedTCPRequestHandler(SocketServer.StreamRequestHandler):
    """
    Basic handler for TCP input
    """
    scommand_letter = '@'
    sc_password = 'lol'

    def handle(self):
        ip = self.request.getpeername()[0]
        self.cl = MRClient(self, ip)
        self.server.cr.add(self.cl)
        self.silent = 0

        print("New client: " + ip)
        while True:
            data = self.rfile.readline()
            if len(data) < 1:
                print("Client disconnected: " + ip)
                self.cl.on_disconnect()
                self.server.cr.delete(self.cl)
                if not self.silent:
                    self.server.cr.broadcast(self.cl.name + " has quit")
                break
            data = data.strip() 
            words = data.split()
            if len(words) < 1:
                continue
            if self.handle_scommands(words) < 1:
                self.cl.handle_input(data);

    def handle_scommands(self, words):
        if len(words) < 1:
            return 0

        if words[0][0] == self.scommand_letter:
            cmd = words[0].lstrip('@') 
            if cmd == "help":
                self.request.send("No help for now\n")
                return 1
            elif cmd == "login":
                if len(words) > 1:
                    if words[1] == self.sc_password:
                        self.cl.op = 1
                        return 1
            elif cmd == "shutdown":
                if self.cl.is_op():
                    print("Shutdown request by " + self.cl.name)
                    self.server.running = 0
                    return 1
            elif cmd == "users":
                if self.cl.is_op():
                    for c in self.server.cr.clients:
                        self.request.send(`c.id` + "\t" + c.name + "\t" 
                                + c.handler.request.getpeername()[0] + "\n")
                    return 1
            elif cmd == "kick":
                if self.cl.is_op():
                    try:
                        id = int(words[1])
                    except ValueError:
                        self.request.send("Error: not a valid id\n")
                    else:
                        if id in self.server.cr.idmap:
                            clnt = self.server.cr.idmap[id]
                            req = clnt.handler.request
                            req.send("You have been kicked! (ouch...)\n")
                            clnt.handler.silent = 1
                            clnt.handler.request.shutdown(socket.SHUT_RDWR)
                            self.server.cr.broadcast_except(clnt, clnt.name + 
                            	" has been kicked!")
                        else:
                            self.request.send("Error: not a valid id\n")
                    return 1
        return 0

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

if __name__ == "__main__":
    HOST, PORT = "localhost", 1337

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    server_thread.setDaemon(True)
    server.running = 1
    server.cr = ClientRegister()
    server_thread.start()

    print "Server loop running in thread:", server_thread.getName()

	# Wait for a user shutdown
    while server.running:
        try:
            time.sleep(0.5)
        except KeyboardInterrupt:
            print "\nGot ^C, closing the server..."
            break

    server.cr.broadcast("Shutting down...")
