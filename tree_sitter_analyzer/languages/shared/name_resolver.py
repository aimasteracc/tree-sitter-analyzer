"""Shared qualified-name resolution utilities for language plugins.

Provides QualifiedNameBuilder, resolve_self_reference, and strip_type_params.
"""

from __future__ import annotations

import re


class QualifiedNameBuilder:
    """Build and manage qualified (dot-separated) names incrementally.

    Useful for constructing fully qualified symbol names while traversing
    nested class/method/namespace AST nodes.

    Usage::

        builder = QualifiedNameBuilder()
        builder.push("com.example")
        builder.push("MyClass")
        assert builder.build() == "com.example.MyClass"
        builder.pop()
        assert builder.build() == "com.example"
    """

    def __init__(self, separator: str = ".") -> None:
        self._parts: list[str] = []
        self._separator = separator

    def push(self, part: str) -> None:
        """Append *part* to the name chain."""
        if part:
            self._parts.append(part)

    def pop(self) -> str | None:
        """Remove and return the last name part, or None if empty."""
        if self._parts:
            return self._parts.pop()
        return None

    def build(self) -> str:
        """Return the current fully qualified name."""
        return self._separator.join(self._parts)

    def is_empty(self) -> bool:
        """Return True when no parts have been pushed."""
        return len(self._parts) == 0

    def depth(self) -> int:
        """Return the number of name parts currently accumulated."""
        return len(self._parts)


# Regex for generic/type-parameter stripping: captures content up to the
# first ``<``, ``[``, ``(``, or whitespace character.
_STRIP_GENERICS_RE = re.compile(r"^([^<\[\(\s]+)")

# Common self/this reference names across languages.
_SELF_ALIASES: frozenset[str] = frozenset(
    {
        "self",  # Python, Ruby, Swift
        "this",  # Java, C#, C++, JavaScript, TypeScript, Kotlin
        "me",  # Visual Basic / some DSLs
    }
)


def resolve_self_reference(name: str) -> bool:
    """Return True if *name* is a self/this reference for any supported language.

    Args:
        name: A raw identifier extracted from an AST node.

    Returns:
        True when *name* is ``"self"``, ``"this"``, or ``"me"``
        (case-sensitive, matching tree-sitter output directly).
    """
    return name in _SELF_ALIASES


def strip_type_params(type_name: str) -> str:
    """Return *type_name* with any generic type parameters stripped.

    Examples::

        strip_type_params("Container<T>")     == "Container"
        strip_type_params("List[String]")     == "List"
        strip_type_params("Map<K, V>")        == "Map"
        strip_type_params("Optional")         == "Optional"
        strip_type_params("")                 == ""

    Args:
        type_name: A raw type name string, possibly including ``<…>``,
                   ``[…]``, or ``(…)`` generic syntax.

    Returns:
        The bare type name before the first type-parameter delimiter,
        stripped of surrounding whitespace.
    """
    if not type_name:
        return ""
    match = _STRIP_GENERICS_RE.match(type_name.strip())
    if match:
        return match.group(1).strip()
    return type_name.strip()
