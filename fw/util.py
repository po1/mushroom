from .register import get_type

import sys

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


def myrepr(obj):
    if type(obj) in (str, int, float, bool):
        return repr(obj)
    elif isinstance(obj, list):
        return '[{}]'.format(', '.join([myrepr(x) for x in obj]))
    elif isinstance(obj, tuple):
        return '({})'.format(', '.join([myrepr(x) for x in obj]))
    elif isinstance(obj, dict):
        return '{{{}}}'.format(', '.join(['{}: {}'.format(myrepr(k), myrepr(v))
                                            for k, v in list(obj.items())]))
    elif obj is None:
        return 'None'
    else:
        return '<{}>'.format(obj.__class__.__name__)
