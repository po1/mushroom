import random

from mushroom.util import template


def color(fg, bg=None):
    bg = f";{bg+10}" if bg else ""
    return f"\033[{fg}{bg}m"


class Color:
    normal = 0

    black = 30
    red = 31
    green = 32
    yellow = 33
    blue = 34
    magenta = 35
    cyan = 36
    white = 37

    bright_black = gray = 90
    bright_red = 91
    bright_green = 92
    bright_yellow = 93
    bright_blue = 94
    bright_magenta = 95
    bright_cyan = 96
    bright_white = 97


def color_eval_env():
    return {c: color(getattr(Color, c)) for c in dir(Color) if not c.startswith("_")}


def format(s, **context):
    return template.parse(s, context={**color_eval_env(), **context})


def _pf(obj, indent=2, width=80, newl=False):
    def _val(k, newl=False):
        ind = indent * " "
        return _pf(k, indent=indent, width=width - indent, newl=newl).replace(
            "\n", f"\n{ind}"
        )

    # only supports lists and dicts
    if len(r := repr(obj)) < width - indent:
        return r
    if isinstance(obj, list):
        ind = " " * (indent - 2) + "- "
        newl = "\n" if newl else ""
        return newl + "\n".join(f"{ind}{_val(k)}" for k in obj)
    if isinstance(obj, dict):
        ind = " " * indent
        newl = f"\n" if newl else ""
        keycolor = color(random.randint(31, 36))

        def _keyval(k, v):
            return f"{keycolor}{k}{color(0)}: {_val(v, newl=True)}"

        return newl + "\n".join(f"{ind}{_keyval(k, v)}" for k, v in obj.items())
    return repr(obj)


def format_object(obj, indent=2):
    """A super-prettiajin-blue.

    Formats to colorful yaml-like syntax with a few niceties."""
    dirstuff = {k: getattr(obj, k) for k in dir(obj)}
    return repr(obj) + "\n" + _pf(dirstuff, indent=indent)
