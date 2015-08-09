from .util import log_err


class BaseClient:
    """
    Base class for MUSHRoom clients
    """

    fw_cmds = {}

    def __init__(self, handler, name):
        self.handler = handler
        self.name = name
        self.cmds = {}
        for k, v in self.fw_cmds.items():
            self.add_cmd(k, v())

    def add_cmd(self, name, command):
        self.cmds[name] = command

    def remove_cmd(self, command):
        if type(command) is str and command in self.cmds:
            del self.cmds[command]
        else:
            for k in [x for x in self.cmds if self.cmds[x] == command]:
                del self.cmds[k]

    def send(self, msg):
        try:
            self.handler.handler_write((msg + "\n"))
        except IOError:
            log_err("Could not send to " + self.name)

    def handle_input(self, data):
        pass

    def on_disconnect(self):
        pass


class BaseObject(object):
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

    def __getstate__(self):
        odict = self.__dict__.copy()
        for cmd in self.custom_cmds:
            del odict[self.cmds[cmd]]
        return odict

    def __setstate__(self, mdict):
        self.__dict__.update(mdict)
        sample = self.__class__("sample")
        self.__dict__.update(dict([(k, sample.__dict__[k]) for k in
                                   [x for x in sample.__dict__
                                    if x not in mdict]]))
        for cmd in self.custom_cmds:
            mcmd = self.custom_cmds[cmd]
            self.add_cmd(cmd, mcmd[0], mcmd[1])

    def add_cmd(self, cmd, cmd_name, cmd_txt):
        self.custom_cmds[cmd] = (cmd_name, cmd_txt)
        self.cmds[cmd] = cmd_name
        locs = locals()
        locs[self.__class__.__name__] = self.__class__
        txt = cmd_txt.replace('\n', '\n\t\t')
        txt = ("def ___tmp(self, who, rest):\n"
               "\ttry:\n"
               "\t\t{}\n"
               "\texcept Exception as e:\n"
               "\t\twho.send('woops: {{}}'.format(e))\n\n"
               "self.{} = ___tmp.__get__(self, {})"
               .format(txt, cmd_name, self.__class__.__name__))
        exec(txt, globals(), locs)
