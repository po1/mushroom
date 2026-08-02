def serialize(val):
    from mushroom.db import BaseObject

    if isinstance(val, BaseObject):
        return {"kind": "DbRef", "spec": val.id}
    elif hasattr(val, "_serialize"):
        return val._serialize()
    elif val is None or isinstance(val, (str, int, float, bool)):
        return val
    elif isinstance(val, list):
        return [serialize(x) for x in val]
    elif isinstance(val, dict):
        return {k: serialize(v) for k, v in val.items()}
    return {"kind": "OpaqueObject", "spec": repr(val)}


class Serializable:
    def _serialize(self):
        return {
            "kind": self.__class__.__name__,
            "spec": {k: serialize(getattr(self, k)) for k in dir(self)},
        }

    @classmethod
    def _deserialize(cls, manifest):
        kind = manifest.get("kind", None)
        if cls.__name__ != kind:
            raise AttributeError(
                f"Wrong object type for class [{cls.__name__}]: [{kind}]"
            )
        spec = manifest.get("spec", {})
        name = spec.pop("name", None)
        obj = cls(name)
        obj.__dict__.update(spec)
        return obj
