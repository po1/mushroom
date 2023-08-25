from __future__ import annotations

import re

from .object import proxify


class Caller:
    def send(self, text):
        pass


class Action:
    def match(self, caller: Caller, query: str) -> bool:
        """Run the action if the query matches.

        Returns True if there was a match, False otherwise.
        """
        return False


class BaseCommand(Action):
    help_text = ""
    name = ""

    command_regex = re.compile(r"([^ ]+)(?: (.*))?")

    def __repr__(self):
        return f"<built-in command {self.name}>"

    def match(self, caller: Caller, query: str) -> bool:
        m = self.command_regex.match(query)
        if m is None:
            return False
        command, args = m.groups()
        if command.lower() != self.name:
            return False

        self.run(caller, args)
        return True


class WrapperCommand(BaseCommand):
    """This is used to provide backwards compatibility with commands when
    they were just methods"""

    help_text = "No help available"

    def __init__(self, cmd, func):
        self.name = cmd
        self.func = func
        self.help_text = func.__doc__ or self.help_text

    def run(self, caller, query):
        if self.func:
            self.func(caller, query)


class CustomCommand(BaseCommand):
    """For user-supplied scripts."""

    help_text = "No help available"

    def __init__(self, name, txt, owner):
        self.name = name
        self.txt = txt
        self.owner = owner

    def __repr__(self):
        txt = self.txt.replace("\\", "\\\\").replace("\n", "\\n")
        return f"<code: {txt}>"

    def run(self, caller, query):
        locs = {
            "send": caller.send,
            "self": proxify(self.owner),
            "caller": proxify(caller),
            "here": proxify(caller.room),
            "query": query,
            **caller.exec_env(),
        }
        try:
            exec(self.txt, locs)
        except Exception as e:
            caller.send(f"command {self.name} failed: ({e.__class__.__name__}) {e}")


class Answer(Action):
    def __init__(self, answers: list[tuple[str, callable[Caller]]]):
        self.answers = answers
        self.cleanup = None

    def match(self, caller, query):
        q = query.lower()
        for a, c in self.answers:
            if q == a:
                if self.cleanup:
                    self.cleanup()
                if c:
                    c(caller)
                return True
        return False


class YesNoAnswer(Answer):
    def __init__(self, yes_action, no_action):
        yes_answers = ["yes", "sure", "yup", "ok", "aye"]
        no_answers = ["no", "nope", "nah", "nay"]
        answers = [(x, yes_action) for x in yes_answers] + [
            (x, no_action) for x in no_answers
        ]
        super(YesNoAnswer, self).__init__(answers)


def add_answer_to(answer, target):
    """Add and register cleanup."""
    answer.cleanup = lambda: target.remove_cmd(answer)
    target.add_cmd(answer)
