"""
pygeoweaver — Python and CLI wrapper for Geoweaver.

Public functions (``start``, ``list_processes``, ``run_workflow`` ...) are loaded on
first access so ``import pygeoweaver`` and the ``gw`` CLI stay fast; the AI-agent
client lives in :mod:`pygeoweaver.agent`.
"""
from pygeoweaver.pgw_log_config import setup_logging


setup_logging()


def _interface():
    from pygeoweaver.commands import pgw_interface

    return pgw_interface


def __getattr__(name):
    if name == "__all__":
        return [n for n in dir(_interface()) if not n.startswith("_")]
    if name.startswith("__"):
        raise AttributeError(name)
    interface = _interface()
    if name in globals():  # a submodule imported as a side effect, e.g. pygeoweaver.server
        return globals()[name]
    try:
        return getattr(interface, name)
    except AttributeError:
        raise AttributeError(f"module 'pygeoweaver' has no attribute {name!r}") from None


def __dir__():
    return sorted(set(globals()) | set(__getattr__("__all__")))
