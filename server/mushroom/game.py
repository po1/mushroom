import functools
import queue
import threading
import time

from mushroom.db import Database
from mushroom.db import DbProxy


class Game:
    _instance = None

    def __init__(self) -> None:
        self._timers = []  # ordered by increasing expiration time
        self._event_queue = queue.SimpleQueue()
        self._loop_thread = threading.Thread(target=self._loop)
        self._loop_thread.daemon = True
        self._loop_thread.start()
        self._db = Database()

    def __reduce__(self):
        return "game"  # name of the global instance for pickling

    def __dir__(self) -> list[str]:
        return [
            x
            for x in list(self.__dict__) + list(self.__class__.__dict__)
            if not x.startswith("_")
        ]

    @property
    def db(self):
        return self._db

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def make_player(self, name, client):
        from mushroom.world import MRPlayer, God, Config

        player = MRPlayer(name)

        if not self.get_players():
            # First player gets all powers. Dibs!
            player.powers.append(God())

        if (default_room := Config.get_entry("default_room")) is not None:
            default_room.emit(f"{self} materializes into the room.")
            util.moveto(player, default_room)

        self._db.add(player)
        return player

    def get_players(self):
        from mushroom.world import Player

        return self._db.search(type=Player)

    def load_db(self, file):
        self._db.load(file)

    def dump_db(self, file):
        self._db.dump(file)

    def schedule(self, when, event):
        """Schedules an event to happen in <when> seconds."""
        bisect.insort(self._timers, (time.time() + when, event))
        self._event_queue.put(None)  # wake up

    def _next_timeout(self):
        # wake up the thread every second, just, you know, for fun.
        if not self._timers:
            return 1.0
        return min(self._timers[0][0] - time.time(), 1.0)

    def _loop(self):
        while True:
            try:
                event = self._event_queue.get(timeout=self._next_timeout())
            except queue.Empty:
                pass
            else:
                self._run_event(event)

            self._handle_timers()

    def _run_event(self, event):
        if event is not None:
            try:
                event()  # self-dispatching events are tight
            except Exception as e:
                logging.warning(
                    "exception in event callback: %s", repr(event), exc_info=e
                )

    def _handle_timers(self):
        now = time.time()
        while self._timers:
            when, evt = self._timers[0]
            if when > now:
                return
            del self._timers[0]
            self._run_event(evt)

    def exec_env(self):
        import itertools
        import math
        import random
        import time

        import mushroom

        return {
            "game": self,
            "db": DbProxy(self._db),
            "util": mushroom.util,
            "world": mushroom.world,
            "mushroom": mushroom,
            "itertools": itertools,
            "math": math,
            "random": random,
            "time": time,
        }
