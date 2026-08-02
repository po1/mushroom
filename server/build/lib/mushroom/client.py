import logging
import time

from mushroom import util
from mushroom.commands import ActionFailed, BaseCommand, YesNoAnswer, add_answer_to


class PlayCommand(BaseCommand):
    name = "play"
    help_text = (
        "syntax: play <name>\n"
        "Start playing as the given character. If the character is not\n"
        "found, the player will be invited to create a new one."
    )

    def create_character(self, caller, name):
        caller.add_cmd(self)
        char = caller.game.make_player(name, self)
        self.play(caller, char)

    def play(self, caller, char):
        if char._client is not None:
            caller.send(f"{char.name} is already online.")
            return
        caller.player = char
        char.play(caller, caller.game)
        caller.remove_cmd(self)
        caller.name = char.name
        caller.send(f"You are now playing as {char.name}")
        caller.handler.broadcast_others(f"{char.name} logged in.")
        caller.player.dispatch("connect")

    def run(self, caller, query):
        if query is None:
            caller.send("Play who?")
            return

        matchs = util.match_list(query, caller.game.get_players())
        if not matchs:
            caller.send(f"Couldn't find a character named {query}.\nCreate it?")
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
    help_text = "syntax: help <command>\nDisplays help topics for the given command."

    def run(self, caller, query):
        caller = getattr(caller, "_client", caller)
        commands = [x for x in caller.available_cmds() if hasattr(x, "name")]
        if query is None:
            visible_commands = [x.name for x in commands]
            caller.send("Available commands:")
            caller.send("  {}".format(", ".join(sorted(visible_commands))))
            return
        cmd_name = query.split()[0]
        matchs = [x for x in commands if cmd_name.lower() == x.name[: len(cmd_name)]]
        if not matchs:
            caller.send(f"Command {cmd_name} was not found")
            return
        if len(matchs) > 1:
            caller.send("Multiple commands were found:")
        caller.send("\n".join(cmd.help_text for cmd in matchs))


class Client:
    fw_cmds = [
        HelpCommand,
        PlayCommand,
    ]

    def __init__(self, handler, name, game):
        self.handler = handler
        self.name = name
        self.game = game
        self.player = None
        self.cmds = [c() for c in self.fw_cmds]

    def reload(self):
        if self.player is None:
            return
        self.player = self.game.db.get(self.player.id)
        self.player._client = self

    def add_cmd(self, command):
        self.cmds.append(command)

    def remove_cmd(self, command):
        self.cmds.remove(command)

    def send(self, msg):
        try:
            self.handler.send(msg + "\n")
        except OSError:
            logging.error(f"Could not send to {self.name}")

    def broadcast(self, msg):
        self.handler.broadcast(f"{msg}")

    def available_cmds(self):
        cmds = []
        # player will add other commands (e.g. powers, room, etc.)
        if self.player:
            cmds += self.player.cmds
        cmds += self.cmds
        return cmds

    def handle_input(self, data):
        """
        Basic handler for commands
        """
        cmds = self.available_cmds()
        caller = self.player or self
        if self.player is not None:
            self.player.last_activity = time.time()
        for cmd in cmds:
            try:
                if cmd.match(caller, data.strip()):
                    return
            except ActionFailed as e:
                # permit silent failures
                if e.args:
                    self.send(str(e))
                return
        self.send("Huh?")

    def on_disconnect(self):
        if self.player is not None:
            self.player._client = None
            self.player.dispatch("disconnect")
