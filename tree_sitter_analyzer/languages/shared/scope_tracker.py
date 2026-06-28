"""Shared scope-tracking utility for language plugins.

Provides ScopeStack, a lightweight stack that tracks nested scopes
(classes, methods, functions, namespaces) and builds qualified names.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _ScopeFrame:
    name: str
    kind: str  # e.g. "class", "method", "function", "namespace"


class ScopeStack:
    """Track nested lexical scopes and produce qualified names.

    Usage::

        stack = ScopeStack()
        stack.push("MyClass", "class")
        stack.push("my_method", "method")
        assert stack.current_qualified_name() == "MyClass.my_method"
        stack.pop()
        assert stack.current_qualified_name() == "MyClass"
        stack.pop()
        assert stack.current_qualified_name() == ""
    """

    def __init__(self) -> None:
        self._frames: list[_ScopeFrame] = []

    def push(self, name: str, kind: str) -> None:
        """Push a new scope frame.

        Args:
            name: The scope identifier (e.g. ``"MyClass"``).
            kind: The scope kind (e.g. ``"class"``, ``"method"``).
        """
        self._frames.append(_ScopeFrame(name=name, kind=kind))

    def pop(self) -> _ScopeFrame | None:
        """Pop the innermost scope frame. Returns None if the stack is empty."""
        if self._frames:
            return self._frames.pop()
        return None

    def current_qualified_name(self) -> str:
        """Return the dot-joined qualified name of all active frames.

        Returns:
            ``"OuterClass.InnerClass.method"`` style string,
            or ``""`` when the stack is empty.
        """
        return ".".join(f.name for f in self._frames)

    def depth(self) -> int:
        """Return the current nesting depth (number of frames on the stack)."""
        return len(self._frames)

    def is_empty(self) -> bool:
        """Return True when no scope frames are active."""
        return len(self._frames) == 0

    def current_kind(self) -> str | None:
        """Return the kind of the innermost scope, or None if empty."""
        if self._frames:
            return self._frames[-1].kind
        return None
