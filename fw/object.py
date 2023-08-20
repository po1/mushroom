from collections.abc import Iterable
from typing import Any


def proxify(obj):
    proxy = lambda x: x
    if isinstance(obj, BaseObject):
        return proxy(obj)
    if isinstance(obj, list):
        return [proxify(x) for x in obj]
    return obj


class ObjectProxy:
    def __init__(self, obj):
        """An object proxy for in-game scripting.

        This hides all the internal plumbing and allows filtering of user commands.
        """
        object.__setattr__(self, "obj", obj)

    def __repr__(self):
        return str(object.__getattribute__(self, "obj"))

    def __getattribute__(self, __name: str) -> Any:
        obj = object.__getattribute__(self, "obj")
        if __name not in obj.attrs:
            raise AttributeError(
                f"'{obj.fancy_name}' object has no attribute '{__name}'"
            )
        attr = obj.attrs[__name]
        return proxify(attr)

    def __setattr__(self, __name: str, __value: Any) -> None:
        obj = object.__getattribute__(self, "obj")
        obj._attrs[__name] = __value

    def __detattr__(self, __name: str) -> None:
        obj = object.__getattribute__(self, "obj")
        del obj._attrs[__name]

    def __dir__(self) -> Iterable[str]:
        obj = object.__getattribute__(self, "obj")
        return obj.attrs


class BaseObject:
    """
    The base building block of a MUSHRoom world
    """

    def __init__(self, name):
        self.name = name
