from __future__ import annotations

import logging
import re

from .object import proxify
from .util import ActionFailed, Updatable, escape

logger = logging.getLogger(__name__)
DEFAULT_FLAGS = "o"  # (o)wner (p)eer (i)nterior


def code_env(caller, owner=None, **kwargs):
    return {
        "self": proxify(owner),
        "caller": proxify(caller),
        "ActionFailed": ActionFailed,
        **caller.exec_env(),
        **kwargs,
    }


def exec_code(code, caller, owner=None, **kwargs):
    try:
        exec(code, code_env(caller, owner=owner, **kwargs))
    except ActionFailed as e:
        raise
    except Exception as e:
        caller.send(f"exec error: ({e.__class__.__name__}) {e}")


def eval_code(code, caller, owner=None, **kwargs):
    try:
        return eval(code, code_env(caller, owner=owner, **kwargs))
    except ActionFailed as e:
        raise
    except Exception as e:
        caller.send(f"eval error: ({e.__class__.__name__}) {e}")


class Caller:
    def send(self, text):
        pass


class Action:
    def match(self, caller: Caller, query: str) -> bool:
        """Run the action if the query matches.

        Returns True if there was a match, False otherwise.
        """
        return False


class RegexpAction(Action, Updatable):
    def __init__(self, regexp, code, name=None, owner=None, flags=None):
        self.regexp = re.compile(regexp)
        self.code = code
        self.owner = owner
        self.name = name or re.match(r"\w+", regexp).group()
        self.help_text = regexp
        self.flags = flags or DEFAULT_FLAGS

    # for Updatable
    @classmethod
    def _get_dummy(cls):
        return cls("dummy", None)

    def __repr__(self) -> str:
        txt = escape(self.code)
        return (
            f"<match {self.name}[{self.flags}]: {repr(self.regexp.pattern)} -> {txt}>"
        )

    def match(self, caller, query):
        if (m := self.regexp.match(query)) is not None:
            exec_code(self.code, caller, owner=self.owner, groups=m.groups())
            return True
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

    def __init__(self, cmd, func, flags=None):
        self.name = cmd
        self.func = func
        self.help_text = func.__doc__ or self.help_text
        self.flags = flags or DEFAULT_FLAGS

    def __repr__(self):
        return f"<built-in command {self.name}>"

    def run(self, caller, query):
        if self.func:
            self.func(caller, query)


class CustomCommand(BaseCommand, Updatable):
    """For user-supplied scripts."""

    help_text = "No help available"

    def __init__(self, name, code, owner, flags=None):
        self.name = name
        self.code = code
        self.owner = owner
        self.flags = flags or DEFAULT_FLAGS

    # for Updatable
    @classmethod
    def _get_dummy(cls):
        return cls(None, None, None)

    def __setstate__(self, odict):
        if 'txt' in odict:
            odict['code'] = odict.pop('txt')
        super().__setstate__(odict)

    def __repr__(self):
        txt = escape(self.txt)
        return f"<cmd {self.name}[{self.flags}]: {txt}>"

    def run(self, caller, query):
        exec_code(self.code, caller, owner=self.owner, query=query)


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


class EventHandler:
    def __init__(self, code, owner):
        self.code = code
        self.owner = owner

    def __repr__(self):
        txt = escape(self.code)
        return f"<event handler: {txt}>"

    def run(self, caller=None, **kwargs):
        caller = caller or self.owner
        exec_code(self.code, caller, owner=self.owner, **kwargs)


class Lambda:
    def __init__(self, code, owner):
        self.code = code
        self.owner = owner

    def __repr__(self):
        return f"<lambda: {self.code}>"

    def __call__(self, caller=None, **kwargs):
        caller = caller or self.owner
        return eval_code(self.code, caller, owner=self.owner, **kwargs)
