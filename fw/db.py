import pickle

from . import util
from .interface import BaseObject


""" The database holding the world.  """
class Database:
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
            return self.ids[obj]

    def load(self, db_file):
        with open(db_file, 'rb') as f:
            self.objects = pickle.load(f)
            if self.objects:
                self.last_id = max(self.objects.keys()) + 1
                for k, v in self.objects.items():
                    self.ids[v] = k

    def dump(self, db_file):
        with self.lock.r:
            with open(db_file, 'wb') as f:
                pickle.dump(self.objects, f)

    def search(self, name, type=BaseObject):
        found = []
        with self.lock.r:
            for thing in self.objects.values():
                if util.match_name(name, thing.name):
                    if isinstance(thing, type):
                        found.append(thing)
        return found

    def list_all(self, type):
        with self.lock.r:
            return self.search("", type)

# global instance
db = Database()
