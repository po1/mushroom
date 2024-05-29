import argparse
import importlib
import logging
import socket
import socketserver
import sys
import threading
import time
import traceback
from typing import Any

import tomli

from .client import Client
from .config import Config


class LogFile:
    def __init__(self, log_file) -> None:
        self.log_file = open(log_file, "a")

    def __call__(self, msg) -> Any:
        now = time.time()
        self.log_file.write(f"[{now}] {msg}\n")


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
        for c, i in self.idmap.items():
            if i == cid:
                return c
        return None

    def add(self, client):
        self.clients.append(client)
        self.idmap[client] = self.get_uid()

    def delete(self, client):
        del self.idmap[client]
        self.clients.remove(client)


class ThreadedTCPRequestHandler(socketserver.StreamRequestHandler):
    """
    Basic handler for TCP input
    Interfaces with the FW client class
    Also handles the operator commands,
    which are FW-independant
    """

    scmds = {
        "help": "scmd_help",
        "reload": "scmd_reload",
        "login": "scmd_login",
        "users": "scmd_users",
        "kick": "scmd_kick",
        "save": "scmd_save",
        "shutdown": "scmd_shutdown",
        "load": "scmd_load",
    }
    op_scmds = ["users", "kick", "save", "load", "shutdown", "reload"]

    def handler_write(self, msg):
        self.wfile.write(msg.encode("utf8"))

    def broadcast(self, msg):
        self.server.cr.broadcast(msg)

    def broadcast_others(self, msg):
        self.server.cr.broadcast_except(self.cl, msg)

    def handle(self):
        ip = self.request.getpeername()[0]
        self.cl = Client(self, ip)
        self.server.cr.add(self.cl)
        self.silent = False
        self.op = False

        logging.info(f"New client: {ip}")
        try:
            with open(self.server.cfg.motd_file, "r") as f:
                self.handler_write(f.read())
        except OSError:
            self.handler_write("Welcome!\n")
        for data in self.rfile:
            try:
                data = data.decode("utf8")
                if self.server.cfg.debug:
                    self.server.log(f"data from {self.cl.name}: {repr(data)}")
                if not self.handle_scommands(data):
                    self.cl.handle_input(data)
            except Exception as e:
                traceback.print_exc()
                if self.server.cfg.debug:
                    self.handler_write(f"{repr(e)}")
                    continue
                self.handler_write("An error occured. Please reconnect...\n")
                break
        logging.info(f"Client disconnected: {ip}")
        self.cl.on_disconnect()
        self.server.cr.delete(self.cl)
        if not self.silent:
            self.server.cr.broadcast(self.cl.name + " has quit.")

    def handle_scommands(self, data):
        op_command_prefix = self.server.cfg.op_command_prefix
        words = data.split()
        if len(words) < 1:
            return True  # no need to parse that further
        if words[0][0] != op_command_prefix:
            return False
        cmd = words[0].lstrip(op_command_prefix)
        if cmd not in self.scmds:
            return False
        if cmd in self.op_scmds and not self.op:
            return False
        return getattr(self, self.scmds[cmd])(" ".join(words[1:]))

    def scmd_help(self, rest):
        self.handler_write("List of available server commands:\n")
        cmds = list(self.scmds.keys())
        if not self.op:
            cmds = [x for x in cmds if x not in self.op_scmds]
        self.handler_write("  {}\n".format(", ".join(cmds)))
        return True

    def scmd_login(self, rest):
        if rest == self.server.cfg.op_password:
            self.op = True
            self.handler_write("Successflly logged as operator\n")
            return True
        return False

    def scmd_reload(self, rest):
        if rest:
            try:
                self.scmd_save("")
                importlib.reload(sys.modules[rest])
                self.scmd_load("")
                for client in self.server.cr.clients:
                    client.reload()
                self.handler_write("Done!\n")
            except Exception as e:
                self.handler_write(f"woops: {e}")
            return True
        return False

    def scmd_shutdown(self, rest):
        logging.info(f"Shutdown request by {self.cl.name}")
        self.handler_write("Shutting down\n")
        self.server.running = False
        return True

    def scmd_users(self, rest):
        self.handler_write("Users listing:\n")
        for c in self.server.cr.clients:
            cid = self.server.cr.idmap[c]
            try:
                self.handler_write(
                    "{}\t{}\t{}\n".format(
                        cid, c.name, c.handler.request.getpeername()[0]
                    )
                )
            except socket.error:
                traceback.print_exc()
                self.handler_write("{}\t{}\tSOCK_ERR\n".format(cid, c.name))
        return True

    def scmd_save(self, rest):
        self.server.save_db()
        self.handler_write("Database saved\n")
        return True

    def scmd_load(self, rest):
        try:
            self.server.db.load(self.server.cfg.db_file)
            self.handler_write("Database loaded\n")
        except IOError:
            self.handler_write("Could not load: database not found.\n")
        except Exception:
            self.handler_write("Load failed. Check server log.\n")
            traceback.print_exc()
        return True

    def scmd_kick(self, rest):
        try:
            cid = int(rest)
        except ValueError:
            self.handler_write("Error: not a valid id\n")
        else:
            clnt = self.server.cr.get_client(cid)
            if clnt is not None:
                clnt.handler.handler_write("You have been kicked! (ouch...)\n")
                clnt.handler.silent = True
                clnt.handler.request.shutdown(socket.SHUT_RD)
                self.server.cr.broadcast_except(clnt, clnt.name + " has been kicked!")
            else:
                self.handler_write("Error: not a valid id\n")
        return True


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


class Server:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.start()

    def start(self):
        HOST = self.config.listen_address
        PORT = self.config.listen_port

        self.server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)

        # Start a thread with the server -- that thread will then start one
        # more thread for each request
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        # Exit the server thread when the main thread terminates
        self.server_thread.Daemon = True
        self.server.running = True
        self.server.cr = ClientRegister()
        self.server.log = LogFile(self.config.log_file)
        self.server.db = self.db
        self.server.cfg = self.config
        self.autosave_thread = threading.Thread(target=self.autosave, daemon=True)

        self.server_thread.start()
        self.autosave_thread.start()

        logging.info("Server started and ready to accept connections")
        logging.info("Loading database...")

    def save_db(self):
        self.db.dump(self.config.db_file)

    def autosave(self):
        while True:
            time.sleep(self.config.autosave_period)
            self.save_db()
            if self.server_thread.is_alive():
                self.server.cr.broadcast("Saving the world...")

    def serve_forever(self):
        # Wait for a user shutdown
        try:
            while self.server.running:
                self.server_thread.join(1)
        except KeyboardInterrupt:
            logging.info("Got SIGINT, closing the server...")
        self.server.cr.broadcast("Shutting down...")
        self.server.cr.shutdown()
        self.server.shutdown()
        self.save_db()


def parse_args():
    parser = argparse.ArgumentParser(description="Launch a mushroom server.")
    parser.add_argument("--config", "-c", help="path to a config.toml")

    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO)

    from .db import db as global_db

    db = global_db  # XXX: switch to a non-local DB eventually

    args = parse_args()
    cfg_override = {}
    if args.config is not None:
        with open(args.config, "rb") as file:
            cfg_override = tomli.load(file)
    cfg = Config(**cfg_override)
    try:
        db.load(cfg.db_file)
        logging.info("Database successfully loaded.")
    except IOError:
        logging.info("Database not found, starting fresh.")

    logging.info(f"Starting server on {cfg.listen_address}:{cfg.listen_port}")
    server = Server(cfg, db)
    server.serve_forever()


if __name__ == "__main__":
    main()
