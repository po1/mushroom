import pickle

from . import util
from .interface import BaseObject


""" The database holding the world.  """
class Database:
    def __init__(self):
        self.objects = {}
        self.last_id = 0

    def add(self, obj):
        self.objects[self.last_id] = obj
        self.last_id += 1

    def remove(self, obj_id):
        if type(obj_id) is not int:
            obj_id = self.get_id(obj_id)
        del self.objects[obj_id]

    def get(self, obj_id):
        return self.objects.get(obj_id, None)

    # slow, do not use
    def get_id(self, obj):
        for i, o in self.objects.items():
            if o is obj:
                return i
        raise Exception("Object '{}' <{}> not in the database"
                .format(obj.name, obj.__class__.__name__))

    def load(self, db_file):
        with open(db_file, 'rb') as f:
            self.objects = pickle.load(f)
            if self.objects:
                self.last_id = max(self.objects.keys()) + 1

    def dump(self, db_file):
        with open(db_file, 'wb') as f:
            pickle.dump(self.objects, f)

    def search(self, name, type=BaseObject):
        found = []
        for tid, thing in self.objects.items():
            if util.match_name(name, thing.name):
                if isinstance(thing, type):
                    found.append(thing)
        return found

    def list_all(self, type):
        return self.search("", type)

# global instance
db = Database()
