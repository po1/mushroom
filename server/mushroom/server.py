import argparse
import asyncio
import logging
import socketserver
import time
import traceback
from typing import Any

import frozendict
import tomli

from mushroom.client import Client
from mushroom.config import Config
from mushroom.game import Game
from mushroom.portal import Server as PortalServer

logger = logging.getLogger(__name__)


class LogFile:
    def __init__(self, log_file) -> None:
        self.log_file = open(log_file, "a")  # noqa: SIM115

    def __call__(self, msg) -> Any:
        now = time.time()
        self.log_file.write(f"[{now}] {msg}\n")


class ClientRegister:
    """
    Nothing more than a list of clients, with
    some sugar added
    """

    def __init__(self):
        self.clients = []
        self.idmap = {}
        self.lastid = 0

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


class ClientHandler:
    def __init__(self, server, writer):
        self.server = server
        self.writer = writer
        self.name = self.ip
        self.op = False

    @property
    def ip(self):
        return self.writer.get_extra_info("peername")[0]

    def broadcast(self, msg):
        self.server.broadcast(msg)

    def broadcast_others(self, msg):
        self.server.broadcast_except(self, msg)

    def send(self, msg):
        self.writer.write(msg.encode("utf8"))

    #        asyncio.create_task(self.writer.drain())

    def shutdown(self):
        self.writer.close()


class ServerCommandHandler:
    scmds = frozendict.frozendict(
        {
            "help": "scmd_help",
            "login": "scmd_login",
            "users": "scmd_users",
            "kick": "scmd_kick",
            "save": "scmd_save",
            "shutdown": "scmd_shutdown",
            "load": "scmd_load",
        }
    )
    op_scmds = ("users", "kick", "save", "load", "shutdown")

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
        logger.info(f"Shutdown request by {self.client.name}")
        self.client.send("Shutting down\n")
        self.server.running = False
        self.server.server.close()
        return True

    def scmd_users(self, rest):
        self.client.send("Users listing:\n")
        for c in self.server.client_register.clients:
            cid = self.server.client_register.idmap[c]
            try:
                self.client.send(f"{cid}\t{c.name}\t{c.handler.ip}\n")
            except OSError:
                traceback.print_exc()
                self.client.send(f"{cid}\t{c.name}\tSOCK_ERR\n")
        return True

    def scmd_save(self, rest):
        self.server.save_db()
        self.client.send("Database saved\n")
        return True

    def scmd_load(self, rest):
        try:
            self.server.db.load(self.server.config.db_file)
            self.client.send("Database loaded\n")
        except OSError:
            self.client.send("Could not load: database not found.\n")
        except Exception:  # noqa: BLE001
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
        self.load_db()

    async def start(self):
        self.running = True
        self.server = await asyncio.start_server(
            self._on_client_connect, self.config.listen_address, self.config.listen_port
        )
        logger.info("Server started and ready to accept connections.")

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

        logger.info(f"New client: {client.name}")
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
                    self.log(f"data from {client.name}: {data!r}")
                if not scommand_handler.handle_input(data):
                    client.handle_input(data)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                if self.config.debug:
                    client.send(f"{e!r}\n")
                    continue
                client.send("An error occured. Please reconnect...\n")
                break

        logger.info(f"Client disconnected: {client.name}")
        client.on_disconnect()
        client.handler.shutdown()
        self.client_register.delete(client)
        self.client_register.broadcast(client.name + " has quit.")

    def load_db(self):
        try:
            self.game.load_db(self.config.db_file)
            logger.info("Database successfully loaded.")
        except OSError:
            logger.info("Database not found, starting fresh.")

    def save_db(self):
        logger.info("Saving database.")
        self.game.dump_db(self.config.db_file)

    async def autosave(self):
        while self.running:
            await asyncio.sleep(self.config.autosave_period)
            if not self.dirty:
                continue
            self.save_db()
            self.client_register.broadcast("Saving the world...")

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
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="enable verbose logging"
    )
    return parser.parse_args()


async def amain():
    args = parse_args()

    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level)

    game = Game.get_instance()

    cfg_override = {}
    if args.config is not None:
        with open(args.config, "rb") as file:  # noqa: ASYNC230
            cfg_override = tomli.load(file)
    config = Config(**cfg_override)

    if config.portal_enabled:
        logger.info("Starting portal server")
        portal_server = PortalServer(ip=config.portal_ip, port=config.portal_port)
        await portal_server.start()

    logger.info(f"Starting server on {config.listen_address}:{config.listen_port}")
    server = Server(config, game)
    await server.start()

    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        logger.info("Closing the server...")


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        logger.info("Got SIGINT")


if __name__ == "__main__":
    main()
