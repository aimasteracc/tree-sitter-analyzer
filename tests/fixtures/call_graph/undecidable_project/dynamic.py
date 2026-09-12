"""Computed-attribute and reflection dispatch, invisible to a text search.

Each target below is genuinely reachable, and no line names it at a call site.
"""

from __future__ import annotations

import importlib


class Service:
    """Attribute dispatch through a computed name."""

    def method_one(self) -> int:
        return 1

    def method_two(self) -> int:
        return 2

    def run_named(self, name: str) -> int:
        """Call a method chosen at runtime."""
        return getattr(self, name)()


def module_level_target() -> int:
    return 3


def call_through_globals(name: str) -> int:
    """Reach a module-level function by name."""
    return globals()[name]()


def call_through_import(module_name: str, attr: str) -> int:
    """Reach an attribute of a dynamically imported module."""
    module = importlib.import_module(module_name)
    return getattr(module, attr)()
