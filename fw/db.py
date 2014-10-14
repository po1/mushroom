import pickle

from . import util
from .interface import BaseObject


""" The database holding the world.  """
objects = []


def load(db_file):
    global objects
    with open(db_file, 'rb') as f:
        objects = pickle.load(f)


def dump(db_file):
    with open(db_file, 'wb') as f:
        pickle.dump(objects, f)


def search(name, type=BaseObject):
    found = []
    for thing in objects:
        if util.match_name(name, thing.name):
            if isinstance(thing, type):
                found.append(thing)
    return found


def list_all(type):
    return search("", type)
