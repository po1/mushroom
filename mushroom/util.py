import logging
import re
import threading

from .register import get_type

logger = logging.getLogger(__name__)


class ActionFailed(Exception):
    pass


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
    exact_matches = [x for x in elts if x.name.lower() == short.lower ()]
    if exact_matches:
        return [exact_matches[0]]  # the user can't be more specific anyway
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


# a bit of a circular import, so import at runtime
def get_db():
    from .db import db

    return db


def regexp_command(name, regexp):
    """Used for standard actions on nearby objects."""

    def _decorator(f):
        def _out(self, caller, query):
            if (m := re.match(regexp, query or "")) is None:
                raise ActionFailed(f"Try 'help {name}'.")
            target, *args = m.groups()

            if (ref := get_db().dbref(target)) is not None:
                return f(self, caller, ref, *args)
            caller.find(target, then=lambda o: f(self, caller, o, *args))

        _out.__doc__ = f.__doc__
        return _out

    return _decorator


class Updatable:
    def __setstate__(self, odict):
        self.__dict__.update(odict)
        self._checkfields()

    @classmethod
    def _get_dummy(cls):
        return cls()  # this will fail if the constructor is not trivial

    def _checkfields(self):
        dummy = self._get_dummy()
        for d in dummy.__dict__:
            if d not in self.__dict__:
                setattr(self, d, getattr(dummy, d))
