import threading
import SocketServer
import time
import socket 
import string
import pickle

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
                self.room.broadcast(self.name + ' has gone to ' + found[0].name) 
                found[0].broadcast(self.name + ' arrives from ' + self.room.name) 
            else:
                found[0].broadcast(self.name + ' pops into the room')
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
            if len(MRDB.search(words[1])) > 0:
                self.send("Uhm... something by that name already exists...")
                return
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
            self.handler.wfile.write(msg + "\n")
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
    
    scmds = {'help':'scmd_help',
             'login':'scmd_login',
             'users':'scmd_users',
             'kick':'scmd_kick',
             'save':'scmd_save',
             'load':'scmd_load'}
    op_scmds = ['users', 'kick', 'save', 'load']

    def handle(self):
        ip = self.request.getpeername()[0]
        self.cl = MRClient(self, ip)
        self.server.cr.add(self.cl)
        self.silent = False

        print("New client: " + ip)
        self.wfile.write("Welcome!\n")
        for data in self.rfile:
            try:
                if not self.handle_scommands(data):
                    self.cl.handle_input(data);
            except Exception, e:
                print e
                self.wfile.write("An error occured. Please reconnect...\n")
                break
        print("Client disconnected: " + ip)
        self.cl.on_disconnect()
        self.server.cr.delete(self.cl)
        if not self.silent:
            self.server.cr.broadcast(self.cl.name + " has quit")

    def handle_scommands(self, data):
        words = data.split()
        if len(words) < 1:
            return True # no need to parse that further
        if words[0][0] != self.scommand_letter:
            return False
        cmd = words[0].lstrip('@') 
        if cmd not in self.scmds:
            return False
        if cmd in self.op_scmds and not self.cl.is_op():
            return False
        return getattr(self, self.scmds[cmd])(string.join(words[1:]))

    def scmd_help(self, rest):
        self.wfile.write("No help for now\n")
        return True

    def scmd_login(self, rest):
        if rest == self.sc_password:
            self.cl.op = True
            return True
        return False

    def scmd_shutdown(self, rest):
        print("Shutdown request by " + self.cl.name)
        self.server.running = False
        return True

    def scmd_users(self, rest):
        for c in self.server.cr.clients:
            try:
                self.wfile.write(`c.id` + "\t" + c.name + "\t" 
                    + c.handler.request.getpeername()[0] + "\n")
            except:
                self.wfile.write(`c.id` + "\t" + c.name + "\t" 
                    + "SOCK_ERR\n")
        return True

    def scmd_save(self, rest):
        pickle.dump(MRDB.objects, open('world.sav', 'wb'))
        return True

    def scmd_load(self, rest):
        try:
            MRDB.objects = pickle.load(open('world.sav', 'rb'))
        except Exception, e:
            self.wfile.write("Load failed. Check server log.\n")
            print e
        return True

    def scmd_kick(self, rest):
        try:
            id = int(rest)
        except ValueError:
            self.wfile.write("Error: not a valid id\n")
        else:
            if id in self.server.cr.idmap:
                clnt = self.server.cr.idmap[id]
                req = clnt.handler.wfile
                req.write("You have been kicked! (ouch...)\n")
                clnt.handler.silent = True
                clnt.handler.request.shutdown(socket.SHUT_RD)
                self.server.cr.broadcast_except(clnt, clnt.name + 
                    " has been kicked!")
            else:
                self.wfile.write("Error: not a valid id\n")
        return True

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    HOST, PORT = "localhost", 1337

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    server_thread.setDaemon(True)
    server.running = True
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
#     for c in server.cr.clients:
#         c.handler.request.shutdown(socket.SHUT_RD)
#     server.server_close()
