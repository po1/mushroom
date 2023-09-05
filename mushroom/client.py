import logging

from . import util
from .db import db
from .register import get_type
from .commands import BaseCommand
from .commands import add_answer_to, YesNoAnswer


class PlayCommand(BaseCommand):
    name = "play"
    help_text = (
        "syntax: play <name>\n"
        "Start playing as the given character. If the character is not\n"
        "found, the player will be invited to create a new one."
    )

    def create_character(self, caller, name):
        caller.add_cmd(self)
        char = get_type("player")(name)
        db.add(char)
        self.play(caller, char)

    def play(self, caller, char):
        if char.client is not None:
            caller.send(f"{char.name} is already online.")
            return
        caller.player = char
        char.client = caller
        caller.remove_cmd(self)
        caller.name = char.name
        caller.send("You are now playing as {}".format(char.name))
        caller.handler.broadcast_others(f"{char.name} logged in.")

    def run(self, caller, query):
        if query is None:
            caller.send("Play who?")
            return

        matchs = util.match_list(query, db.list_all(get_type("player")))
        if not matchs:
            caller.send(
                "Couldn't find a character named {}.\n" "Create it?".format(query)
            )
            caller.remove_cmd(self)
            add_answer_to(
                YesNoAnswer(
                    lambda x: self.create_character(x, query),
                    lambda _: caller.add_cmd(self),
                ),
                caller,
            )
            return
        self.play(caller, matchs[0])


class HelpCommand(BaseCommand):
    name = "help"
    help_text = "syntax: help <command>\n" "Displays help topics for the given command."

    def run(self, caller, query):
        caller = getattr(caller, "client", caller)
        commands = [x for x in caller.available_cmds() if hasattr(x, "name")]
        if query is None:
            visible_commands = [x.name for x in commands]
            caller.send("Available commands:")
            caller.send("  {}".format(", ".join(sorted(visible_commands))))
            return
        cmd_name = query.split()[0]
        matchs = [x for x in commands if cmd_name.lower() == x.name[: len(cmd_name)]]
        if not matchs:
            caller.send("Command {} was not found".format(cmd_name))
            return
        cmd = matchs[0]
        caller.send(f"{cmd.help_text}")


class Client:
    fw_cmds = [
        HelpCommand,
        PlayCommand,
    ]

    def __init__(self, handler, name):
        self.handler = handler
        self.name = name
        self.player = None
        self.cmds = [c() for c in self.fw_cmds]

    def reload(self):
        if self.player is None:
            return
        self.player = db.get(self.player.id)
        self.player.client = self

    def add_cmd(self, command):
        self.cmds.append(command)

    def remove_cmd(self, command):
        self.cmds.remove(command)

    def send(self, msg):
        try:
            self.handler.handler_write((msg + "\n"))
        except IOError:
            logging.error(f"Could not send to {self.name}")

    def broadcast(self, msg):
        self.handler.broadcast(f"{msg}\n")

    def available_cmds(self):
        cmds = list(self.cmds)
        # player will add other commands (e.g. powers, room, etc.)
        if self.player:
            cmds += self.player.cmds
        return cmds

    def handle_input(self, data):
        """
        Basic handler for commands
        """
        cmds = self.available_cmds()
        caller = self.player or self
        for cmd in cmds:
            if cmd.match(caller, data.strip()):
                return
        self.send("Huh?")

    def on_disconnect(self):
        if self.player is not None:
            self.player.client = None
