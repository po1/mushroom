from __future__ import annotations

import logging
import re
import types

from mushroom.db import proxify
from mushroom.util import ActionFailed, escape

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
        exec(code, code_env(caller, owner=owner, **kwargs))  # noqa: S102
    except ActionFailed:
        raise
    except Exception as e:  # noqa: BLE001
        caller.send(f"exec error: ({e.__class__.__name__}) {e}")


def eval_code(code, caller, owner=None, **kwargs):
    try:
        return eval(code, code_env(caller, owner=owner, **kwargs))
    except ActionFailed:
        raise
    except Exception as e:  # noqa: BLE001
        caller.send(f"eval error: ({e.__class__.__name__}) {e}")


class BoundCode:
    def __init__(self, code, owner):
        self.code = code
        self.owner = owner

    def __repr__(self):
        return repr(self.code).replace("<", "<bound ")

    def __getattr__(self, attr):
        if "code" not in self.__dict__:
            raise AttributeError()
        child_attr = getattr(self.code, attr)
        if type(child_attr) is types.MethodType:
            child_attr = child_attr.__func__.__get__(self)
        return child_attr

    def bind(self, owner):
        return self.code.bind(owner)

    def run(self, caller=None, **kwargs):
        return self.code.run(self.owner, caller=caller, **kwargs)

    __call__ = run


class Code:
    fancy_name = "code"

    def __init__(self, code):
        self.code = code

    def bind(self, owner):
        return BoundCode(self, owner)

    def __repr__(self):
        txt = escape(self.code)
        return f"<{self.fancy_name}: {txt}>"

    def __dir__(self):
        return [k for k in self.__dict__ if not k.startswith("_")]

    def run(self, owner, caller=None, **kwargs):
        caller = caller or owner
        exec_code(self.code, caller, owner=owner, **kwargs)


class Caller:
    def send(self, text):
        pass


class Action:
    def match(self, caller: Caller, query: str) -> bool:
        """Run the action if the query matches.

        Returns True if there was a match, False otherwise.
        """
        return False


class RegexpAction(Action, Code):
    def __init__(self, regexp, code, name=None, flags=None):
        self.regexp = re.compile(regexp, re.IGNORECASE)
        Code.__init__(self, code)
        self.name = name or re.match(r"\w+", regexp).group()
        self.help_text = regexp
        self.flags = flags or DEFAULT_FLAGS

    def __repr__(self) -> str:
        txt = escape(self.code)
        return f"<match {self.name}[{self.flags}]: {self.regexp.pattern!r} -> {txt}>"

    def match(self, caller, query):
        if (m := self.regexp.match(query)) is not None:
            self.run(caller, groups=m.groups())
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

        self.run(caller, query=args)
        return True

    def run(self, caller, query):
        raise NotImplementedError("Subclasses must implement run")


class WrapperCommand(BaseCommand):
    """This is used to provide backwards compatibility with commands when
    they were just methods"""

    help_text = "No help available"

    def __init__(self, cmd, func, flags=None):
        self.name = cmd
        self.func = func
        self.help_text = func.__doc__ or self.help_text
        self.flags = flags or DEFAULT_FLAGS

    def run(self, caller, query):
        if self.func:
            self.func(caller, query)


class CustomCommand(BaseCommand, Code):
    """For user-supplied scripts."""

    help_text = "No help available"

    def __init__(self, name, code, flags=None):
        self.name = name
        Code.__init__(self, code)
        self.flags = flags or DEFAULT_FLAGS

    def __repr__(self):
        txt = escape(self.code)
        return f"<cmd {self.name}[{self.flags}]: {txt}>"

    run = Code.run


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
        super().__init__(answers)


def add_answer_to(answer, target):
    """Add and register cleanup."""
    answer.cleanup = lambda: target.remove_cmd(answer)
    target.add_cmd(answer)


class EventHandler(Code):
    fancy_name = "event handler"


class Lambda(Code):
    fancy_name = "lambda"

    def __repr__(self):
        return f"<lambda: {self.code}>"

    def run(self, owner, caller=None, **kwargs):
        caller = caller or owner
        return eval_code(self.code, caller, owner=owner, **kwargs)
