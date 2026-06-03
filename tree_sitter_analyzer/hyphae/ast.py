"""Hyphae AST node types (immutable).

Mirrors mycelium-hyphae/src/ast.rs. All nodes are frozen dataclasses so a
parsed selector is a hashable, side-effect-free value.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttributeSelector:
    """An ``[name=value]`` filter, e.g. ``[file=src/lib.rs]``."""

    name: str
    value: str


@dataclass(frozen=True)
class PseudoClass:
    """A pseudo-class filter such as ``:calls(#x)``, ``:not(.struct)``, ``:in(src/)``.

    ``arg`` is one of: a nested :class:`SelectorList` (for ``:calls`` / ``:has`` /
    ``:not`` / ``:callers`` / ``:imports`` / ``:implements``), an ``int`` (for
    ``:nth-child``), a ``str`` path (for ``:in``), or ``None`` (for argument-less
    pseudo-classes like ``:first-child``).
    """

    name: str
    arg: SelectorList | int | str | None = None


@dataclass(frozen=True)
class SimpleSelector:
    """A single selector unit: a base plus attribute and pseudo-class filters.

    ``base`` is a ``(kind, value)`` pair where kind is one of:
    ``"name"`` (``#Foo``), ``"kind"`` (``.method``), ``"universal"`` (``*``).
    """

    base: tuple[str, str]
    attributes: tuple[AttributeSelector, ...] = ()
    pseudo_classes: tuple[PseudoClass, ...] = ()


@dataclass(frozen=True)
class Combined:
    """Two selectors joined by a combinator (``>`` child, ``~`` sibling, descendant)."""

    left: Selector
    combinator: str  # ">" | "~" | " "
    right: Selector


Selector = SimpleSelector | Combined


@dataclass(frozen=True)
class SelectorList:
    """A comma-separated list of selectors; results are the union."""

    selectors: tuple[Selector, ...] = field(default_factory=tuple)
