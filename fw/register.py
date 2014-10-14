registry = {}


def register(cls):
    registry[cls.__name__] = cls
    return cls


def get_class(name):
    return registry.get(name)


def get_type(fancy_name):
    for c in registry.itervalues():
        if getattr(c, 'fancy_name', None) == fancy_name:
            return c
    return None


def get_types():
    fn = []
    for c in registry.itervalues():
        f = getattr(c, 'fancy_name', None)
        if f is not None and f not in fn:
            fn.append(f)
    return fn
