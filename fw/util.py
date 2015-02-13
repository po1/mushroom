from .register import get_type

import sys
import threading

member_types = (
    bool,
    dict,
    float,
    int,
    list,
    type(None),
    bytes,
    tuple,
    str,
)

def log_err(msg):
    print(msg, file=sys.stderr)


def is_type(thing, type):
    return isinstance(thing, get_type(type))


def is_room(thing):
    return is_type(thing, "room")


def is_thing(thing):
    return is_type(thing, "thing")


def is_player(thing):
    return is_type(thing, "player")


def match_name(short, name):
    if short == name[:len(short)]:
        return True
    return False


def match_list(short, elts):
    return [x for x in elts if match_name(short, x.name)]


def player_snames(player, allow_no_room=False):
    sn = {'me': player}
    if player.room is not None or allow_no_room:
        sn['here'] = player.room
    return sn


def find_and_do(player, rest, dofun, search_list,
                arg_default=None,
                short_names=None,
                noarg="Pardon?",
                notfound="You see nothing like '{}' here.",
                ):
    try:
        what = rest.split()[0]
        rest = ' '.join(rest.split()[1:])
    except IndexError:
        if arg_default is None:
            player.send(noarg)
            return
        what = arg_default
    found = match_list(what, search_list)
    if short_names is None:
        short_names = player_snames(player)
    if what in short_names:
        dofun(short_names[what], rest)
    elif len(found) < 1:
        player.send(notfound.format(what))
    elif len(found) > 1:
        player.send(multiple_choice(found))
    else:
        dofun(found[0], rest)


def multiple_choice(choices):
    names = [x.name for x in choices]
    return "Which one?\nChoices are: " + ', '.join(names)


def myrepr(obj, db=None):
    if type(obj) in (str, int, float, bool):
        return repr(obj)
    elif isinstance(obj, list):
        return '[{}]'.format(', '.join([myrepr(x, db) for x in obj]))
    elif isinstance(obj, tuple):
        return '({})'.format(', '.join([myrepr(x, db) for x in obj]))
    elif isinstance(obj, dict):
        return '{{{}}}'.format(', '.join(['{}: {}'.format(myrepr(k, db),
                                                          myrepr(v, db))
                                            for k, v in list(obj.items())]))
    elif obj is None:
        return 'None'
    else:
        ret = '<{}>'.format(obj.__class__.__name__)
        if db is not None:
            try:
                ret += '#{}'.format(db.get_id(obj))
            except Exception:
                pass
        return ret


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
                self.rwlock.aquire_w()
            else:
                self.rwlock.aquire_r()

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

    def aquire_r(self):
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
