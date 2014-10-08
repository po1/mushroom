from __future__ import print_function

import sys

def log_err(msg):
    print(msg, file=sys.stderr)


class MRFW:
    """
    A toolbox of useful functions for the FW.
    Should probably be more structured, or not
    set as a bunch of static methods...
    """

    @staticmethod
    def is_type(thing, type):
        try:
            if thing.__class__.fancy_name == type:
                return True
        except:
            pass
        return False

    @staticmethod
    def is_room(thing):
        return MRFW.is_type(thing, "room")

    @staticmethod
    def is_thing(thing):
        return MRFW.is_type(thing, "thing")

    @staticmethod
    def is_player(thing):
        return MRFW.is_type(thing, "player")

    @staticmethod
    def match_name(short, name):
        if short == name[:len(short)]:
            return True
        return False

    @staticmethod
    def get_first_arg(data):
        words = data.split()
        if len(words) < 1:
            raise EmptyArgException()
        return words[0]

    @staticmethod
    def multiple_choice(choices):
        names = map(lambda x:x.name, choices)
        return "Which one?\nChoices are: " + ', '.join(names)


# A bunch of exceptions... quite handy
class AmbiguousException(Exception):
    def __init__(self, choices):
        self.choices = choices

class NotFoundException(Exception):
    pass

class EmptyArgException(Exception):
    pass

