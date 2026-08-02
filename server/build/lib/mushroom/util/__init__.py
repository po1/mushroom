import re

from mushroom.util import template
from mushroom.util.cipher import cipher, decipher
from mushroom.util.format import format
from mushroom.util.format import format_object as pretty_format
from mushroom.util.rwlock import RWLock

__all__ = [
    "RWLock",
    "cipher",
    "decipher",
    "format",
    "pretty_format",
    "template",
]


class ActionFailed(Exception):
    pass


def match_name(short, name):
    # allow matching individual words of the name
    for word in name.split():
        if short.lower() == word[: len(short)].lower():
            return True
    return short.lower() == name[: len(short)].lower()


def match_list(short, elts):
    exact_matches = [x for x in elts if x.name.lower() == short.lower()]
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


def get_db():
    from mushroom.game import Game

    return Game.get_instance().db


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
