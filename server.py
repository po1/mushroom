import threading
import SocketServer
import socket
import string
import pickle

from config import MRConfig as cfg
from fw import get_class


class ClientRegister:
    """
    Nothing more than a list of clients, with
    some sugar added
    """

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

    def shutdown(self):
        for c in self.clients:
            c.handler.request.shutdown(socket.SHUT_WR)

    def get_uid(self):
        self.lastid += 1
        return self.lastid

    def get_client(self, cid):
        for c, i in self.idmap.iteritems():
            if i == cid:
                return c
        return None

    def add(self, client):
        self.clients.append(client)
        self.idmap[client] = self.get_uid()

    def delete(self, client):
        del self.idmap[client]
        self.clients.remove(client)


class ThreadedTCPRequestHandler(SocketServer.StreamRequestHandler):
    """
    Basic handler for TCP input
    Interfaces with the FW client class
    Also handles the operator commands,
    which are FW-independant
    """
    scommand_letter = cfg.op_command_prefix
    sc_password = cfg.op_password

    scmds = {'help':'scmd_help',
             'login':'scmd_login',
             'users':'scmd_users',
             'kick':'scmd_kick',
             'save':'scmd_save',
             'shutdown':'scmd_shutdown',
             'load':'scmd_load'}
    op_scmds = ['users', 'kick', 'save', 'load', 'shutdown']

    def handle(self):
        client_class = get_class(cfg.client_class)

        ip = self.request.getpeername()[0]
        self.cl = client_class(self, ip)
        self.server.cr.add(self.cl)
        self.silent = False
        self.op = False

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
        op_command_prefix = cfg.op_command_prefix
        words = data.split()
        if len(words) < 1:
            return True # no need to parse that further
        if words[0][0] != op_command_prefix:
            return False
        cmd = words[0].lstrip(op_command_prefix)
        if cmd not in self.scmds:
            return False
        if cmd in self.op_scmds and not self.op:
            return False
        return getattr(self, self.scmds[cmd])(string.join(words[1:]))

    def scmd_help(self, rest):
        self.wfile.write("List of available server commands:\n")
        self.wfile.write("  {}\n".format(', '.join(self.scmds)))
        return True

    def scmd_login(self, rest):
        if rest == cfg.op_password:
            self.op = True
            return True
        return False

    def scmd_shutdown(self, rest):
        print("Shutdown request by " + self.cl.name)
        self.server.running = False
        return True

    def scmd_users(self, rest):
        for c in self.server.cr.clients:
            cid = self.server.cr.idmap[c]
            try:
                self.wfile.write("{}\t{}\t{}\n".format(cid, c.name,
                    c.handler.request.getpeername()[0]))
            except:
                self.wfile.write("{}\t{}\tSOCK_ERR\n".format(cid, c.name))
        return True

    def scmd_save(self, rest):
        db_class = get_class(cfg.db_class)

        pickle.dump(db_class.objects, open(cfg.db_file, 'wb'))
        return True

    def scmd_load(self, rest):
        db_class = get_class(cfg.db_class)

        try:
            db_class.objects = pickle.load(open(cfg.db_file, 'rb'))
        except Exception, e:
            self.wfile.write("Load failed. Check server log.\n")
            print e
        return True

    def scmd_kick(self, rest):
        try:
            cid = int(rest)
        except ValueError:
            self.wfile.write("Error: not a valid id\n")
        else:
            clnt = self.server.cr.get_client(cid)
            if clnt is not None:
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
    HOST, PORT = cfg.listen_address, cfg.listen_port

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    server_thread.setDaemon(True)
    server.running = True
    server.cr = ClientRegister()
    server_thread.start()

    print "Server started and ready to accept connections"

    # Wait for a user shutdown
    try:
        while server.running:
            server_thread.join(1)
    except KeyboardInterrupt:
        print "\nGot SIGINT, closing the server..."

    server.cr.broadcast("Shutting down...")
    server.cr.shutdown()
    server.shutdown()
