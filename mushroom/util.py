import re
import threading

from .commands import ActionFailed
from .register import get_type


def is_type(thing, type):
    return isinstance(thing, get_type(type))


def is_room(thing):
    return is_type(thing, "room")


def is_thing(thing):
    return is_type(thing, "thing")


def is_player(thing):
    return is_type(thing, "player")


def match_name(short, name):
    # allow matching individual words of the name
    for word in name.split():
        if short.lower() == word[: len(short)].lower():
            return True
    if short.lower() == name[: len(short)].lower():
        return True
    return False


def match_list(short, elts):
    return [x for x in elts if match_name(short, x.name)]


def player_snames(player, allow_no_room=False):
    sn = {"me": player}
    if player.location is not None or allow_no_room:
        sn["here"] = player.location
    return sn


def find(
    query="",
    objects=None,
    quiet=False,
    short_names=None,
    then=None,
    notfound=None,
):
    def found(results):
        if not quiet:
            if not results:
                raise ActionFailed(notfound or f"You see nothing like '{query}' here.")
            if len(results) > 1:
                raise ActionFailed(multiple_choice(results))
        if len(results) == 1 and then is not None:
            then(results[0])
        return results

    if objects is None:
        objects = []
    if short_names is None:
        short_names = {}
    if query in short_names:
        return found([short_names[query]])
    return found(match_list(query, objects))


def multiple_choice(choices):
    names = [x.name for x in choices]
    return "Which one?\nChoices are: " + ", ".join(names)


def moveto(obj, container):
    if not hasattr(obj, "location"):
        raise ActionFailed(f"{obj} cannot be moved.")
    if obj.location is not None:
        obj.location.contents.remove(obj)
    obj.location = container
    if container is not None:
        container.contents.append(obj)


class RWLock:
    """
    A read-write lock.
    Will allow concurrent reads but serialize all writes.
    Write operations have a higher priority.

    Example use:
        lock = RWLock()

        with lock.r:
            read_stuff()

        with lock.w:
            write_stuff()
    """

    class Selector:
        def __init__(self, rwlock, write):
            self.rwlock = rwlock
            self.write = write

        def __enter__(self):
            if self.write:
                self.rwlock.acquire_w()
            else:
                self.rwlock.acquire_r()

        def __exit__(self, exc_t, exc_v, trace):
            self.rwlock.release()

    def __init__(self):
        self.lock = threading.Lock()
        self.r_cv = threading.Condition(self.lock)
        self.w_cv = threading.Condition(self.lock)
        self.readers = 0
        self.writers = 0

        # 'public' members
        self.r = RWLock.Selector(self, write=False)
        self.w = RWLock.Selector(self, write=True)

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


def escape(input):
    def sub(match):
        return {
            "\n": "\\n",
            "\t": "\\t",
            "\\": "\\\\",
        }[match.group(1)]

    return re.sub(r"(\n|\t|\\)", sub, input)


def unescape(input):
    def sub(match):
        return {
            "\\": "\\",
            "n": "\n",
            "t": "\t",
        }[match.group(1)]

    return re.sub(r"\\(.)", sub, input)
