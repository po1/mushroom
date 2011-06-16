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
                return 1
        except:
            pass
        return 0

    @staticmethod
    def is_player(thing):
        return MRFW.is_type(thing, "player")


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
        for thing in self.contents:
            if MRFW.is_player(thing):
                thing.send(player.name + " says: " + rest)


class MRPlayer(MRObject):
    fancy_name = "player"
    cmds = {"look":"cmd_look", "go":"cmd_go"}

    def __init__(self, name):
        super(MRPlayer,self).__init__(name)
        self.client = None
        self.room = None
        self.description = "A non-descript citizen."

    def send(self, msg):
    	self.client.send(msg)

    def cmd_go(self, player, rest):
        words = rest.split()
        if len(words) < 1:
            self.send("Go where?")
            return 
        found = MRDB.search(words[0], "room")
        if len(found) < 1:
            self.send("Don't know this place. Is it in Canada?")
        else:
            if self.room != None:
                self.room.contents.remove(self)
            self.room = found[0]
            self.room.contents.append(self)

    def cmd_look(self, player, rest):
        what = None
        if len(rest.split()) < 1:
            what = "here"
        else:
            what = rest.split()[0]

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
                found = None
                for thing in self.room.contents:
                    if thing.name == what:
                        self.send(thing.name + ": " + thing.description)
                        found = 1
                        break
                if found == None:
                    self.send("You see nothing like '" + what + "' here.")

    def handle_input(self, data):
        self.handle_local_cmd(data)

    def handle_local_cmd(self, data):
        words = data.split()
        where2look = [self]
        if self.room != None:
            where2look.append(self.room)

        found = 0
        for p in where2look:
            if words[0] in p.cmds:
                cmd = getattr(p, p.cmds[words[0]])
                cmd(self, string.join(words[1:]))
                found = 1
        if found == 0:
            self.send("Huh?")


class MRDB:
    classes = [MRObject, MRRoom, MRPlayer]
    objects = []

    @staticmethod
    def search(name, type = "thing"):
        found = []
        for thing in MRDB.objects:
            if thing.name == name:
                if thing.__class__.fancy_name == type:
                    found.append(thing)

        return found


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


class MRClient:
    def __init__(self, handler, name):
        self.handler = handler
        self.name = name
        self.op = 0
        handler.server.cr.broadcast(name + " connected!")
        self.id = handler.server.cr.get_uid()
        self.player = []

    def handle_input(self, data):
        words = data.split()
        if words[0] == "chat":
                self.handler.server.cr.broadcast("[global] " + self.name + 
                        " says: " + string.join(words[1:]))
        elif words[0] == "name":
            self.name = words[1]
        elif words[0] == "help":
            self.send("chat <text>           global chat\n"
                      "name <name>           change your client name\n"
                      "exec <command>        execute python command\n"
                      "create <type> <name>  thing, player, or room\n"
                      "play <name>           go in the shoes of a player\n"
                      "go <place>            move to a room\n"
                      "look                  in a room, look around")
        elif words[0] == "create":
            if len(words) < 3:
                self.send("Cannot create a nameless thing...")
                return
            found = 0
            for cl in MRDB.classes:
                if words[1] == cl.fancy_name:
                    thing = cl(words[2])
                    MRDB.objects.append(thing)
                    found = 1
                    break
            if found == 0:
                self.send("Don't know what a '" + words[1] + "' is...")
        elif words[0] == "play":
            if len(words) < 2:
                self.send("Play who?")
                return
            found = MRDB.search(words[1], "player")
            if len(found) == 0:
                self.send("Couldn't find the guy.")
            else:
                self.player = found[0]
                found[0].client = self
        elif words[0] == "exec":
            try:
                self.send(str(eval(string.join(words[1:]))))
            except Exception, pbm:
                self.send(str(pbm))
        elif self.player != []:
            self.player.handle_input(data)
        else:
            self.send("Huh?")

    def is_op(self):
        return self.op

    def send(self, msg):
        try:
            self.handler.request.send(msg + "\n")
        except:
            print "Could not send to " + self.name


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
