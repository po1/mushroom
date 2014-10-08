from .world import MRObject


class MRDB:
    """
    The class holding the world.
    This class shares an interface with the
    server and should inherit from such
    an interface...
    """

    #classes = [MRThing, MRRoom, MRPlayer]
    objects = []

    @staticmethod
    def search(name, type = MRObject):
        found = []
        for thing in MRDB.objects:
            if MRFW.match_name(name, thing.name):
                if isinstance(thing, type):
                    found.append(thing)
        return found

    @staticmethod
    def list_all(type):
        return MRDB.search("", type)
