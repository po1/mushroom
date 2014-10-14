from .world import MRObject
from . import util

class MRDB:
    """
    The class holding the world.
    This class shares an interface with the
    server and should inherit from such
    an interface...
    """

    objects = []

    @staticmethod
    def search(name, type = MRObject):
        found = []
        for thing in MRDB.objects:
            if util.match_name(name, thing.name):
                if isinstance(thing, type):
                    found.append(thing)
        return found

    @staticmethod
    def list_all(type):
        return MRDB.search("", type)
