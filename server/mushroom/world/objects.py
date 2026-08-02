import logging
from functools import cached_property

import frozendict

from mushroom import util
from mushroom.commands import BoundCode, Code, Lambda, WrapperCommand
from mushroom.db import BaseObject
from mushroom.game import Game

logger = logging.getLogger(__name__)


class Object(BaseObject):
    """
    Base database object.
    """

    fancy_name = "object"
    fw_cmds = frozendict.frozendict()
    fw_event_handlers = frozendict.frozendict()
    default_description = "An abstract object."

    def __init__(self, name):
        super().__init__(name)
        self.description = self.default_description
        self.custom_cmds = {}
        self.custom_event_handlers = {}
        self.flags = []
        self.parent = None

    def has_flag(self, flag):
        """Return True if flag is set.
        Note: there is no way to reset an inherited flag."""
        if self.parent is not None and self.parent.has_flag(flag):
            return True
        return flag in self.flags

    @property
    def event_handlers(self):
        """Return all soft-code event handlers, including those of a parent."""
        handlers = {}
        if self.parent is not None:
            handlers.update(self.parent.event_handlers)
        handlers.update(
            {e: h.bind(self) for e, h in self.custom_event_handlers.items()}
        )
        return handlers

    @property
    def commands(self):
        """Return all soft-code commands, including those of a parent."""
        cmds = [c.bind(self) for c in self.custom_cmds.values()]
        if self.parent is not None:
            cmds += [c.bind(self) for c in self.parent.commands]
        return cmds

    def dispatch(self, event, **kwargs):
        if event in self.event_handlers:
            # raise ActionFailed to interrupt
            handler = self.event_handlers[event].bind(self)
            handler(**kwargs)
        if event in self.fw_event_handlers:
            handler = getattr(self, self.fw_event_handlers[event])
            handler(**kwargs)

    @cached_property
    def _fwcmds(self):
        return [WrapperCommand(k, getattr(self, v)) for k, v in self.fw_cmds.items()]

    def __dir__(self):
        return [k for k in self.__dict__ if not k.startswith("_")]

    def __repr__(self):
        return f"<#{self.id} {self.fancy_name} {self.name}>"

    def __str__(self):
        return self.name

    def __getattr__(self, attr):
        if attr.startswith("_"):
            return object.__getattribute__(self, attr)
        if self.parent is None or not hasattr(self.parent, attr):
            return object.__getattribute__(self, attr)
        return getattr(self.parent, attr)

    def __getstate__(self):
        return {k: getattr(self, k) for k in dir(self)}

    def __setstate__(self, odict):
        self.__dict__.update(odict)
        self._add_missing_fields()
        self._bind_all_lambdas()

    def clone(self):
        obj = self.__class__(self.name)

        def _copy(item):
            if isinstance(item, list):
                return [_copy(x) for x in item]
            if isinstance(item, dict):
                return {k: _copy(v) for k, v in item.items()}
            if isinstance(item, (Code, BoundCode)):
                return item.bind(obj)
            return item

        for attr, value in self.__dict__.items():
            if attr.startswith("_"):
                continue
            if attr == "contents":
                obj.contents = []
            setattr(obj, attr, _copy(value))
        return obj

    @classmethod
    def _get_dummy(cls):
        return cls(None)

    def _add_missing_fields(self):
        dummy = self._get_dummy()
        for d in dummy.__dict__:
            if d not in self.__dict__:
                setattr(self, d, getattr(dummy, d))

    def _bind_all_lambdas(self):
        for k, v in self.__dict__.items():
            if isinstance(v, Lambda):
                setattr(self, k, v.bind(self))

    @property
    def id(self):
        return Game.get_instance().db.get_id(self)

    def exec_env(self):
        return Game.get_instance().exec_env()


class Config(Object):
    fancy_name = "config"
    default_description = "The main game config object. No big deal."

    def __init__(self, name="config"):
        super().__init__(name)
        self.default_room = None
        self.master_room = None

    @classmethod
    def get_world_config(cls):
        db = Game.get_instance().db
        configs = db.search(type=cls)
        if not configs:
            db.add(config := cls())
            return config
        return configs[0]

    @classmethod
    def get_entry(cls, key):
        """
        Returns: None if the entry is not found.
        """
        return getattr(cls.get_world_config(), key, None)


class StuffBase(Object):
    """
    Stuff that can be in rooms. Things or players.
    """

    fw_event_handlers = frozendict.frozendict(
        {
            "look": "on_look",
        }
    )

    def __init__(self, name):
        self.location = None
        self.contents = []
        super().__init__(name)

    def exec_env(self):
        return {
            "send": self.send,
            "here": self.location,
            **super().exec_env(),
        }

    def emit(self, msg):
        if self.location is not None:
            self.location.emit(msg)

    def oemit(self, msg):
        if self.location is None:
            return
        for obj in self.location.contents:
            if obj != self:
                obj.dispatch("emit", text=msg)

    def clone(self):
        obj = super().clone()
        obj.contents = []
        obj.location = None
        return obj

    def on_look(self, caller):
        colordesc = util.format(self.description, self=self)
        caller.send(f"\033[34m{self}\033[0m: {colordesc}")
        if self.has_flag("opaque"):
            return
        contents = [
            x for x in getattr(self, "contents", []) if not x.has_flag("invisible")
        ]
        if contents:
            caller.send("\nContents:")
            caller.send("\n".join(f" - {thing}" for thing in contents))


class Thing(StuffBase):
    """
    Things that are not players or rooms.
    Usually common objects, usable or not.
    """

    fancy_name = "thing"
    default_description = "A boring non-descript thing"

    def __init__(self, name):
        self.powers = []
        super().__init__(name)

    # need this as a /dev/null sink for event handlers
    def send(self, msg):
        logger.warning(f"{self!r} was sent: {msg}")
