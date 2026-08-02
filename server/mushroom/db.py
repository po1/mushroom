import os
import pickle
import re

from mushroom import util


def compat_fw():
    # register all classes

    # old _objects have fw.world.* classes
    import sys

    for module in list(sys.modules):
        if module.startswith("mushroom"):
            oldmodule = module.replace("mushroom", "fw")
            sys.modules[oldmodule] = sys.modules[module]


def proxify(object):
    return object


class BaseObject:
    """
    The base building block of a MUSHRoom world
    """

    def __init__(self, name):
        self.name = name


class Database:
    """The database holding the world."""

    def __init__(self):
        self._objects = {}
        self._ids = {}  # use a reverse map
        self._next_id = 0
        self._lock = util.RWLock()

    def add(self, obj):
        if not isinstance(obj, BaseObject):
            raise TypeError("Trying to add random trash to the DB!")
        with self._lock.r:
            self._objects[self._next_id] = obj
            self._ids[obj] = self._next_id
            self._next_id += 1
        return obj

    def remove(self, obj):
        with self._lock.w:
            if type(obj) is int:
                del self._ids[self._objects[obj]]
                del self._objects[obj]
            else:
                del self._objects[self._ids[obj]]
                del self._ids[obj]

    def get(self, obj_id):
        with self._lock.r:
            return self._objects.get(obj_id, None)

    def get_id(self, obj):
        with self._lock.r:
            return self._ids.get(obj, None)

    def load(self, db_file):
        compat_fw()
        with open(db_file, "rb") as f:
            self._objects = pickle.load(f)
            if self._objects:
                self._next_id = max(self._objects.keys()) + 1
                self._ids = {v: k for k, v in self._objects.items()}

    def dump(self, db_file):
        with self._lock.r:
            tempfile = f"{db_file}.tmp"
            with open(tempfile, "wb") as f:
                pickle.dump(self._objects, f)
            os.replace(tempfile, db_file)

    def search(self, name="", type=BaseObject):
        found = []
        with self._lock.r:
            for thing in self._objects.values():
                if util.match_name(name, thing.name) and isinstance(thing, type):
                    found.append(thing)
        return found

    def list_all(self, type=BaseObject):
        with self._lock.r:
            return self.search("", type)

    def dbref(self, query):
        if (m := re.match(r"#(\d+)", query)) is None:
            return None
        return self.get(int(m.group(1)))


def _prox(f):
    def __fun(self, *args, **kwargs):
        return proxify(f.__get__(self.db)(*args, **kwargs))

    return __fun


class DbProxy:
    """A version of the database that's somewhat safer to use for in-game scripting."""

    def __init__(self, db) -> None:
        self.db = db

    def __repr__(self):
        return "<Database db>"

    def __call__(self, obj_id):
        return self.get(obj_id)

    @classmethod
    def __dir__(cls):
        return [x for x in cls.__dict__ if not x.startswith("_")]

    get = _prox(Database.get)
    add = _prox(Database.add)
    remove = _prox(Database.remove)
    search = _prox(Database.search)
