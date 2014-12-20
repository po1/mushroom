from . import util

from .db import db
from .register import get_type

class BaseCommand:
    hidden = False
    help_text = ""

    def call(self, caller, command, rest):
        pass


class HelpCommand(BaseCommand):
    help_text = ("syntax: help <command>\n"
                 "Displays help topics for the given command.")

    def call(self, caller, command, rest):
        if not rest.strip():
            visible_commands = [x for x in caller.available_cmds()
                                if not caller.available_cmds()[x].hidden]
            caller.send("Available commands:")
            caller.send("  {}".format(', '.join(sorted(visible_commands))))
            return
        cmd_name = rest.split()[0]
        matchs = [x for x in caller.available_cmds()
                  if cmd_name.lower() == x[:len(cmd_name)]]
        if not matchs:
            caller.send("Command {} was not found".format(cmd_name))
            return
        cmd = caller.available_cmds()[matchs[0]]
        caller.send("{}\n\n{}".format(matchs[0], cmd.help_text))


class WrapperCommand(BaseCommand):
    """ This is used to provide backwards compatibility with commands when
    they were just methods """

    help_text = "no help available"

    def __init__(self, func, who=None):
        self.func = func
        self.who = who

    def call(self, caller, command, rest):
        if self.func:
            self.func(self.who, rest)


class Answer(BaseCommand):
    hidden = True

    def __init__(self, answers):
        self.answers = answers

    def call(self, caller, command, rest):
        for k, v in self.answers.items():
            if command.lower() == k[:len(command)]:
                if v:
                    v(caller)
                break
        caller.remove_cmd(self)


class YesNoAnswer(Answer):
    def __init__(self, yes, no):
        Answer.__init__(self, answers={'yes': yes, 'no': no})


class PlayCommand(BaseCommand):
    command = "play"
    help_text = (
        "syntax: play <name>\n"
        "Start playing as the given character. If the character is not\n"
        "found, the player will be invited to create a new one."
    )

    def create_character(self, caller, name):
        char = get_type('player')(name)
        db.add(char)
        self.play(caller, char)

    def play(self, caller, char):
        caller.player = char
        char.client = caller
        caller.remove_cmd(self)
        caller.send("You are now playing as {}".format(char.name))

    def call(self, caller, command, rest):
        if not rest.strip():
            caller.send("Play who?")
            return

        matchs = util.match_list(rest, db.list_all(get_type('player')))
        if not matchs:
            caller.send("Couldn't find a character named {}.\n"
                        "Create it?".format(rest))
            yna = YesNoAnswer(lambda x: self.create_character(x, rest), None)
            caller.add_cmd('yes', yna)
            caller.add_cmd('no', yna)
            return
        self.play(caller, matchs[0])


