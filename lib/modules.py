"""Loading a Python file by its path, so one script can use another folder's module without
putting that folder on sys.path, where its module names would shadow the caller's own."""
import importlib.util
import os
import sys


def load(path, name):
    """The module in the file at `path`, registered in sys.modules as `name`; sys.path is left as it is.

    A second call with the same `name` gives the module already loaded. Pick a `name` no import
    statement uses (`<folder>_<module>`), so it never shadows a module found through sys.path."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.realpath(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s as %s" % (path, name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module
