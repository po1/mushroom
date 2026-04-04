import argparse
import asyncio
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

from mushroom.client import Client
from mushroom.game import Game
from mushroom.config import Config
from mushroom.portal import Server as PortalServer


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

    def find_client(self, handler):
        for client in self.clients:
            if client.handler is handler:
                return client
        raise RuntimeError("Could not find a client for handler")

    def broadcast_except(self, client, msg):
        if isinstance(client, ClientHandler):
            client = self.find_client(handler=client)
        for c in self.clients:
            if c is not client:
                c.send(msg)

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


class ClientHandler():
    def __init__(self, server, writer):
        self.server = server
        self.writer = writer
        self.name = writer.get_extra_info('peername')
        self.silent = False
        self.op = False

    def broadcast(self, msg):
        self.server.broadcast(msg)

    def broadcast_others(self, msg):
        self.server.broadcast_except(self, msg)

    def send(self, msg):
        self.writer.write(msg.encode("utf8"))
        asyncio.create_task(self.writer.drain())

    def shutdown(self):
        asyncio.create_task(self.writer.close())


class ServerCommandHandler:
    scmds = {
        "help": "scmd_help",
        "login": "scmd_login",
        "users": "scmd_users",
        "kick": "scmd_kick",
        "save": "scmd_save",
        "shutdown": "scmd_shutdown",
        "load": "scmd_load",
    }
    op_scmds = ["users", "kick", "save", "load", "shutdown"]

    def __init__(self, server, client):
        self.server = server
        self.client = client
        self.op = False

    def handle_input(self, data):
        op_command_prefix = self.server.config.op_command_prefix
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
        self.client.send("List of available server commands:\n")
        cmds = list(self.scmds.keys())
        if not self.op:
            cmds = [x for x in cmds if x not in self.op_scmds]
        self.client.send("  {}\n".format(", ".join(cmds)))
        return True

    def scmd_login(self, rest):
        if rest == self.server.config.op_password:
            self.op = True
            self.client.send("Successflly logged as operator\n")
            return True
        return False

    def scmd_shutdown(self, rest):
        logging.info(f"Shutdown request by {self.client.name}")
        self.client.send("Shutting down\n")
        self.server.running = False
        return True

    def scmd_users(self, rest):
        self.client.send("Users listing:\n")
        for c in self.server.client_register.clients:
            cid = self.server.client_register.idmap[c]
            try:
                self.client.send(
                    "{}\t{}\t{}\n".format(
                        cid, c.name, c.handler.request.getpeername()[0]
                    )
                )
            except socket.error:
                traceback.print_exc()
                self.client.send("{}\t{}\tSOCK_ERR\n".format(cid, c.name))
        return True

    def scmd_save(self, rest):
        self.server.save_db()
        self.client.send("Database saved\n")
        return True

    def scmd_load(self, rest):
        try:
            self.server.db.load(self.server.config.db_file)
            self.client.send("Database loaded\n")
        except IOError:
            self.client.send("Could not load: database not found.\n")
        except Exception:
            self.client.send("Load failed. Check server log.\n")
            traceback.print_exc()
        return True

    def scmd_kick(self, rest):
        try:
            cid = int(rest)
        except ValueError:
            self.client.send("Error: not a valid id\n")
        else:
            clnt = self.server.client_register.get_client(cid)
            if clnt is not None:
                clnt.send("You have been kicked! (ouch...)\n")
                clnt.handler.silent = True
                clnt.handler.shutdown()
                self.server.broadcast_except(clnt, clnt.name + " has been kicked!")
            else:
                self.client.send("Error: not a valid id\n")
        return True


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


class Server:
    def __init__(self, config, game):
        self.config = config
        self.game = game
        self.client_register = ClientRegister()
        self.log = LogFile(self.config.log_file)
        self.dirty = False
        self.running = False

    async def start(self):
        self.running = True
        self.server = await asyncio.start_server(self._on_client_connect, self.config.listen_address, self.config.listen_port)
        logging.info("Server started and ready to accept connections.")

    def greet_client(self, client):
        try:
            with open(self.config.motd_file, "r") as f:
                client.send(f.read())
        except OSError:
            client.send("Welcome!\n")

    async def _on_client_connect(self, reader, writer):
        handler = ClientHandler(self, writer)
        client = Client(handler, handler.name, self.game)
        scommand_handler = ServerCommandHandler(self, client)
        self.client_register.add(client)

        logging.info(f"New client: {client.name}")
        self.greet_client(client)

        while self.running:
            data = await reader.readline()
            if not data:
                break
            self.dirty = True
            try:
                data = data.decode("utf8")
                self.dirty = True
                if self.config.debug:
                    self.log(f"data from {client.name}: {repr(data)}")
                if not scommand_handler.handle_input(data):
                    client.handle_input(data)
            except Exception as e:
                traceback.print_exc()
                if self.config.debug:
                    client.send(f"{repr(e)}\n")
                    continue
                client.send("An error occured. Please reconnect...\n")
                break

        logging.info(f"Client disconnected: {client.name}")
        client.on_disconnect()
        client.handler.shutdown()
        self.client_register.delete(self.cl)
        if not self.silent:
            self.client_register.broadcast(client.name + " has quit.")

    def save_db(self):
        logging.info("Saving database.")
        self.game.dump_db(self.config.db_file)

    async def autosave(self):
        while self.running:
            await asyncio.sleep(self.config.autosave_period)
            if not server.dirty:
                continue
            self.save_db()
            self.server.cr.broadcast("Saving the world...")

    def broadcast(self, msg):
        self.client_register.broadcast(msg)

    def broadcast_except(self, client, msg):
        self.client_register.broadcast_except(client, msg)

    async def serve_forever(self):
        asyncio.create_task(self.autosave())
        try:
            await self.server.serve_forever()
        finally:
            self.client_register.broadcast("Shutting down...")
            self.save_db()


def parse_args():
    parser = argparse.ArgumentParser(description="Launch a mushroom server.")
    parser.add_argument("--config", "-c", help="path to a config.toml")

    return parser.parse_args()


async def amain():
    logging.basicConfig(level=logging.INFO)

    game = Game()

    args = parse_args()
    cfg_override = {}
    if args.config is not None:
        with open(args.config, "rb") as file:
            cfg_override = tomli.load(file)
    config = Config(**cfg_override)

    try:
        game.load_db(config.db_file)
        logging.info("Database successfully loaded.")
    except IOError:
        logging.info("Database not found, starting fresh.")

    if config.portal_enabled:
        logging.info(f"Starting portal server")
        portal_server = PortalServer(ip=config.portal_ip, port=config.portal_port)
        await portal_server.start()

    logging.info(f"Starting server on {config.listen_address}:{config.listen_port}")
    server = Server(config, game)
    await server.start()
    
    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        logging.info("Got SIGINT, closing the server...")


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    asyncio.run(amain())
