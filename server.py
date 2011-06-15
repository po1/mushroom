import threading
import SocketServer

class ClientRegister:
    pass

class MRClient:
    def handle_input(self, data):
        pass

class ThreadedTCPRequestHandler(SocketServer.StreamRequestHandler):
    """
    Basic handler for TCP input
    """
    scommand_letter = '@'

    def handle(self):
        self.cl = MRClient()

        while 1:
            data = self.rfile.readline().strip()
            words = data.split()
            if self.handle_scommands(words) < 1:
                self.cl.handle_input(data);

    def handle_scommands(self, words):
        if len(words) < 1:
            return 0

        if words[0][0] == self.scommand_letter:
            if words[0].lstrip('@') == "help":
                self.request.send("No help for now\n")
                return 1
            elif words[0].lstrip('@') == "shutdown":
                self.request.send("Shutting down...\n")
                print("dodo")
                self.server.shutdown()
                return 1

        return 0

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

if __name__ == "__main__":
    # Port 0 means to select an arbitrary unused port
    HOST, PORT = "localhost", 1337

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    server.daemon_threads = True

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
#    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
#    server_thread.setDaemon(True)
#    server_thread.start()
#    print "Server loop running in thread:", server_thread.getName()

#    raw_input()

    server.serve_forever()
