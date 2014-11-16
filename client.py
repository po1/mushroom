## This client is based on console.py by James Thiele (27 April 2004)
## The original console.py file can be found at:
## http://www.eskimo.com/~jet/python/examples/cmd/ (Copyright (c) 2004, James Thiele)

import os
import cmd
import readline
import socket
import time

class Console(cmd.Cmd):

    def __init__(self):
        cmd.Cmd.__init__(self)
        self.prompt = "Mushroom > "
        self.intro  = (
                "Welcome to the Mushroom client!\n"
                "Connect to a server using the _connect command.\n"
                "Help is available with the _help command.")
        self.is_connected = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    ## Command definitions ##
    def do__hist(self, args):
        """Print a list of commands that have been entered"""
        print self._hist

    def do_exit(self, args):
        """Exits from the console"""
        return -1

    ## Command definitions to support Cmd object functionality ##
    def do_EOF(self, args):
        """Exit on system end of file character"""
        return self.do_exit(args)

    def do__help(self, args):
        """Get help on commands
           '_help' with no arguments prints a list of commands for which help is available
           '_help <command>' gives help on <command>"""
        ## The only reason to define this method is for the help text in the doc string
        cmd.Cmd.do_help(self, args)

    def do_help(self, args):
        """In-game help"""
        self.default("help")

    def do__connect(self, args):
        """Connects to the given server
           '_connect <server> <port>"""
        try:
            server, port = args.split()
            self.socket.connect((server, int(port)))
            self.is_connected = 1
            time.sleep(0.2)
            print self.socket.recv(4096)
        except ValueError:
            print "Too many arguments."
            print "Help for _connect:"
            cmd.Cmd.do_help(self, "_connect")
        except:
            print "Unable to connect, check the parameters and try again."

    ## Override methods in Cmd object ##
    def preloop(self):
        """Initialization before prompting user for commands.
           Despite the claims in the Cmd documentaion, Cmd.preloop() is not a stub.
        """
        cmd.Cmd.preloop(self)   ## sets up command completion
        self._hist    = []      ## No history yet
        self._locals  = {}      ## Initialize execution namespace for user
        self._globals = {}

    def postloop(self):
        """Take care of any unfinished business.
           Despite the claims in the Cmd documentaion, Cmd.postloop() is not a stub.
        """
        cmd.Cmd.postloop(self)   ## Clean up command completion
        print "Exiting..."

    def precmd(self, line):
        """ This method is called after the line has been input but before
            it has been interpreted. If you want to modify the input line
            before execution (for example, variable substitution) do it here.
        """
        self._hist += [ line.strip() ]
        return line

    def postcmd(self, stop, line):
        """If you want to stop the console, return something that evaluates to true.
           If you want to do some post command processing, do it here.
        """
        return stop

    def emptyline(self):    
        """Do nothing on empty input line"""
        pass

    def default(self, line):       
        """Called on an input line when the command prefix is not recognized.
           In that case we execute the line as Python code.
        """
        if not self.is_connected:
            print "The client is not connected. Please connect to a server using the '_connect' command."
        else:
            self.socket.send(line + "\n")
            time.sleep(0.2)
            print self.socket.recv(4096)

if __name__ == '__main__':
        console = Console()
        console.cmdloop() 
