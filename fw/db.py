import pickle
import threading

from . import util
from .interface import BaseObject


""" The database holding the world.  """
class Database:
    def __init__(self):
        self.objects = {}
        self.ids = {}  # use a reverse map
        self.last_id = 0
        self.readers = 0
        self.writers = 0
        self.lock = threading.Lock()
        self.r_cv = threading.Condition(self.lock)
        self.w_cv = threading.Condition(self.lock)

    def acquire_r(self):
        with self.lock:
            while self.readers < 0 or self.writers:
                self.r_cv.wait()
            self.readers += 1

    def acquire_w(self):
        with self.lock:
            while self.readers != 0:
                self.writers += 1
                self.w_cv.wait()
                self.writers -= 1
            self.readers = -1

    def release(self):
        with self.lock:
            if self.readers < 0:
                self.readers = 0
            else:
                self.readers -= 1
            if self.writers and self.readers == 0:
                self.w_cv.notify()
            elif self.writers == 0:
                self.r_cv.notifyAll()

    def add(self, obj):
        if not isinstance(obj, BaseObject):
            raise Exception("Trying to add random trash to the DB!")
        self.acquire_w()
        self.objects[self.last_id] = obj
        self.ids[obj] = self.last_id
        self.last_id += 1
        self.release()

    def remove(self, obj):
        self.acquire_w()
        if type(obj) is int:
            del self.ids[self.objects[obj]]
            del self.objects[obj]
        else:
            del self.objects[self.ids[obj]]
            del self.ids[obj]
        self.release()

    def get(self, obj_id):
        self.acquire_r()
        obj = self.objects.get(obj_id, None)
        self.release()
        return obj

    def get_id(self, obj):
        self.acquire_r()
        obj_id = self.ids[obj]
        self.release()
        return obj_id

    def load(self, db_file):
        with open(db_file, 'rb') as f:
            self.objects = pickle.load(f)
            if self.objects:
                self.last_id = max(self.objects.keys()) + 1
                for k, v in self.objects.items():
                    self.ids[v] = k

    def dump(self, db_file):
        self.acquire_r()
        with open(db_file, 'wb') as f:
            pickle.dump(self.objects, f)
        self.release()

    def search(self, name, type=BaseObject):
        found = []
        self.acquire_r()
        for thing in self.objects.values():
            if util.match_name(name, thing.name):
                if isinstance(thing, type):
                    found.append(thing)
        self.release()
        return found

    def list_all(self, type):
        self.acquire_r()
        obj_list = self.search("", type)
        self.release()
        return obj_list

# global instance
db = Database()
