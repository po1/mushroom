from collections.abc import Iterable
from typing import Any


class ObjectProxy:
    def __init__(self, obj):
        """An object proxy for in-game scripting.

        This hides all the internal plumbing and allows filtering of user commands.
        """
        self.obj = obj

    def __getattribute__(self, __name: str) -> Any:
        obj = object.__getattribute__(self, "obj")
        if __name not in obj.cmds:
            raise AttributeError
        return obj.cmds[__name]

    def __dir__(self) -> Iterable[str]:
        obj = object.__getattribute__(self, "obj")
        return obj.cmds() + obj.attrs()


class BaseObject:
    """
    The base building block of a MUSHRoom world
    MUSHRoom will only save children of this object
    """

    fancy_name = "object"
    fw_cmds = {}

    def __init__(self, name):
        self.name = name
        self.custom_cmds = {}
        self.cmds = self.fw_cmds.copy()
        self.attrs = {
            'name': lambda: self.name,
            'description': lambda: self.description,
        }

    def __getstate__(self):
        odict = self.__dict__.copy()
        for cmd in self.custom_cmds:
            del odict[self.cmds[cmd]]
        return odict

    def __setstate__(self, mdict):
        self.__dict__.update(mdict)
        sample = self.__class__("sample")
        self.__dict__.update(
            dict(
                [
                    (k, sample.__dict__[k])
                    for k in [x for x in sample.__dict__ if x not in mdict]
                ]
            )
        )
        for cmd in self.custom_cmds:
            mcmd = self.custom_cmds[cmd]
            self.add_cmd(cmd, mcmd[0], mcmd[1])

    def add_cmd(self, cmd, cmd_name, cmd_txt):
        self.custom_cmds[cmd] = (cmd_name, cmd_txt)
        self.cmds[cmd] = cmd_name
        locs = locals()
        locs[self.__class__.__name__] = self.__class__
        txt = cmd_txt.replace("\n", "\n\t\t")
        txt = (
            "def ___tmp(self, who, rest):\n"
            "\ttry:\n"
            "\t\t{}\n"
            "\texcept Exception as e:\n"
            "\t\twho.send('woops: {{}}'.format(e))\n\n"
            "self.{} = ___tmp.__get__(self, {})".format(
                txt, cmd_name, self.__class__.__name__
            )
        )
        exec(txt, globals(), locs)
