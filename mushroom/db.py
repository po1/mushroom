import os
import pickle
import re

from . import util
from .object import BaseObject, proxify


def compat_fw():
    # register all classes
    from . import world

    # old objects have fw.world.* classes
    import sys

    for module in list(sys.modules):
        if module.startswith("mushroom"):
            oldmodule = module.replace("mushroom", "fw")
            sys.modules[oldmodule] = sys.modules[module]


class Database:
    """The database holding the world."""

    def __init__(self):
        self.objects = {}
        self.ids = {}  # use a reverse map
        self.last_id = 0
        self.lock = util.RWLock()

    def add(self, obj):
        if not isinstance(obj, BaseObject):
            raise Exception("Trying to add random trash to the DB!")
        with self.lock.r:
            self.objects[self.last_id] = obj
            self.ids[obj] = self.last_id
            self.last_id += 1

    def remove(self, obj):
        with self.lock.w:
            if type(obj) is int:
                del self.ids[self.objects[obj]]
                del self.objects[obj]
            else:
                del self.objects[self.ids[obj]]
                del self.ids[obj]

    def get(self, obj_id):
        with self.lock.r:
            return self.objects.get(obj_id, None)

    def get_id(self, obj):
        with self.lock.r:
            return self.ids.get(obj, None)

    def load(self, db_file):
        compat_fw()
        with open(db_file, "rb") as f:
            self.objects = pickle.load(f)
            if self.objects:
                self.last_id = max(self.objects.keys()) + 1
                for k, v in self.objects.items():
                    self.ids[v] = k

    def dump(self, db_file):
        with self.lock.r:
            tempfile = f"{db_file}.tmp"
            with open(tempfile, "wb") as f:
                pickle.dump(self.objects, f)
            os.replace(tempfile, db_file)

    def search(self, name="", type=BaseObject):
        found = []
        with self.lock.r:
            for thing in self.objects.values():
                if util.match_name(name, thing.name):
                    if isinstance(thing, type):
                        found.append(thing)
        return found

    def list_all(self, type=BaseObject):
        with self.lock.r:
            return self.search("", type)

    def dbref(self, query):
        if (m := re.match(r"#(\d+)", query)) is None:
            return None
        return self.get(int(m.group(1)))


# global instance
db = Database()


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
