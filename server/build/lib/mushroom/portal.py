import asyncio
import json
import logging
import threading

import websockets.server

# might be useful to remove those and provide a mushroom-agnostic interface
import mushroom.client
from mushroom.util import ActionFailed

DEFAULT_IP = "0.0.0.0"
DEFAULT_PORT = 1339

logger = logging.getLogger(__name__)
portals = {}


class Server:
    def __init__(self, ip=None, port=None):
        self.ip = ip or DEFAULT_IP
        self.port = port or DEFAULT_PORT
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.listen, daemon=True)

    def start(self):
        if self.thread.is_alive():
            return
        self.thread.start()

    def listen(self):
        asyncio.set_event_loop(self.loop)
        # will run until websocket server crashes
        self.loop.run_until_complete(self.serve())

    async def new_client(self, websocket):
        from mushroom.db import db

        handler = Handler(db, websocket)
        # returns when connection with client closes
        await handler.process()

    async def serve(self):
        async with websockets.server.serve(self.new_client, self.ip, self.port):
            await asyncio.Future()  # run forever


class PortalClient(mushroom.client.Client):
    fw_cmds = (mushroom.client.HelpCommand,)

    def __init__(self, player_id, handler):
        self.player_id = player_id
        self.handler = handler
        self.player = None
        self.cmds = [c() for c in self.fw_cmds]

    def send(self, text):
        self.handler.call_soon(
            self.handler.send("player-output", player_id=self.player_id, text=text)
        )


def portalify(obj):
    def _field(o):
        if isinstance(o, (int, float, str)):
            return o
        if isinstance(o, list):
            return [_field(x) for x in o]
        if isinstance(o, dict):
            return {k: _field(v) for k, v in o.items()}
        if hasattr(o, "__dict__") and hasattr(o, "id"):
            return _field({"id": o.id})
        return repr(o)

    return {k: _field(getattr(obj, k)) for k in dir(obj)}


class Portal:
    def __init__(self, name, world_object=None):
        """A Portal is a 2-way channel between 2 worlds.

        Arguments:
            name: the name of the portal
            world_object: the MRObject instance that receives portal events
        """
        self.name = name
        self.world_object = world_object
        self.handler = None
        self.client_thread = None
        self.object_requests = {}
        self.local_players = {}
        self.remote_players = {}

    @classmethod
    def register(cls, name, world_object=None):
        portals[name] = cls(name, world_object)
        return portals[name]

    @property
    def connected(self):
        return self.handler is not None and self.handler.websocket.open

    # calls from world (i.e. without a running loop)
    def open(self, uri):
        if self.connected:
            raise ActionFailed("Portal is already open.")
        from mushroom.db import db

        async def _connection():
            ws = await websockets.connect(uri)
            self.handler = Handler(db, ws, portal=self)
            await self.handler.send("hello", name=self.name)
            if self.world_object is not None:
                self.world_object.dispatch("portal-connect", portal=self)
            await self.handler.process()  # loop forever

        self.client_thread = threading.Thread(
            target=lambda: asyncio.run(_connection()), daemon=True
        )
        self.client_thread.start()

    def close(self):
        if self.handler is not None:
            self.handler.call_soon(self.handler.close())

    def local_enter(self, player_id, player):
        if self.handler is None:
            raise ActionFailed("Portal leads nowhere.")
        self.local_players[player_id] = player
        self.handler.call_soon(self.handler.send("player-enter", player_id=player_id))

    def local_leave(self, player_id):
        del self.local_players[player_id]
        self.handler.call_soon(self.handler.send("player-leave", player_id=player_id))

    def local_input(self, player_id, text):
        self.handler.call_soon(
            self.handler.send("player-input", player_id=player_id, text=text)
        )

    def get_object(self, object_id, cb):
        self.object_requests[object_id] = cb
        self.handler.call_soon(self.handler.send("object-get", object_id=object_id))

    # from handler
    async def object_info(self, object_id, obj):
        if not object_id in self.object_requests:
            await self.handler.error(
                f"received spurious object data for object #{object_id}"
            )
            return
        self.object_requests.pop(object_id)(obj)

    async def player_output(self, player_id, text):
        if not player_id in self.local_players:
            await self.handler.error(
                f"received spurious player output for player #{player_id}"
            )
            return
        self.local_players[player_id].send(text)

    async def remote_connect(self, handler):
        self.handler = handler
        if self.world_object is not None:
            self.world_object.dispatch("portal-connect", portal=self)

    async def remote_enter(self, player_id):
        if player_id in self.remote_players:
            await self.handler.error(f"player #{player_id} enter while already in")
            return
        client = PortalClient(player_id, self.handler)
        self.remote_players[player_id] = client
        if self.world_object is not None:
            self.world_object.dispatch("portal-visitor", portal=self, visitor=client)

    async def remote_leave(self, player_id):
        if player_id not in self.remote_players:
            await self.handler.error(f"player #{player_id} left but was unknown")
            return
        if self.remote_players[player_id].player is not None:
            self.remote_players[player_id].player.dispatch("portal-leave")
        del self.remote_players[player_id]

    async def remote_input(self, player_id, text):
        if player_id not in self.remote_players:
            await self.handler.error(f"player #{player_id} input but was unknown")
            return
        client = self.remote_players[player_id]
        client.handle_input(text)

    def error(self, message):
        logger.error(f"error from portal {self.name}: {message}")

    def on_close(self):
        if self.world_object is not None:
            self.world_object.dispatch("portal-disconnect", portal=self)
            for player in self.local_players.values():
                self.world_object.dispatch("portal-return", player=player)
        for remote_player in self.remote_players.values():
            if remote_player.player is not None:
                remote_player.player.dispatch("portal-leave")
        self.remote_players = {}
        self.object_requests = {}


class Handler:
    def __init__(self, db, websocket, portal=None):
        self.db = db
        self.websocket = websocket
        self.portal = portal
        self.loop = asyncio.get_running_loop()

    def call_soon(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def get_handler(self, type):
        handlers = {
            "hello": self.handle_hello,
            "error": self.handle_error,
            "player-input": self.handle_player_input,
            "player-output": self.handle_player_output,
            "player-leave": self.handle_player_leave,
            "player-enter": self.handle_player_enter,
            "object-get": self.handle_object_get,
            "object-info": self.handle_object_info,
        }
        return handlers.get(type, lambda _: self.error(f"unknown message type {type}"))

    async def error(self, message):
        await self.send("error", message=message)

    async def send(self, type, **payload):
        msg = json.dumps({"type": type, **payload})
        await self.websocket.send(msg)

    async def close(self):
        await self.websocket.close()

    # sync method, the connection is gone already
    def on_close(self):
        if self.portal is not None:
            self.portal.on_close()

    async def process(self):
        """Processes all incoming messages. Returns when connection closes."""
        try:
            async for message in self.websocket:
                try:
                    # it's all json
                    msg = json.loads(message)
                except ValueError:
                    logger.warn(f"failed to decode message: {message}")
                    continue
                await self.handle(msg)
        finally:
            self.on_close()

    async def handle(self, msg):
        if not "type" in msg:
            await self.error("Bad message")
            return
        try:
            await self.get_handler(msg["type"])(msg)
        except AttributeError:
            if self.portal is None:
                await self.error(
                    f"Got message type: {msg['type']} when portal was closed"
                )
            else:
                raise

    async def handle_hello(self, msg):
        name = msg["name"]
        self.portal = portals.get(name, None)
        if self.portal is None:
            await self.error(f"portal '{name}' does not exist or isn't ready")
            return
        await self.portal.remote_connect(self)

    async def handle_error(self, msg):
        if self.portal is not None:
            self.portal.error(msg)
        else:
            logger.warn("Got a portal error before hello: %s", msg)

    async def handle_player_input(self, msg):
        await self.portal.remote_input(msg["player_id"], msg["text"])

    async def handle_player_output(self, msg):
        await self.portal.player_output(msg["player_id"], msg["text"])

    async def handle_player_leave(self, msg):
        await self.portal.remote_leave(msg["player_id"])

    async def handle_player_enter(self, msg):
        await self.portal.remote_enter(msg["player_id"])

    async def handle_object_get(self, msg):
        await self.send(
            "object-info",
            object_id=msg["object_id"],
            info=portalify(self.db.get(msg["object_id"])),
        )

    async def handle_object_info(self, msg):
        await self.portal.object_info(msg["object_id"], msg["info"])
