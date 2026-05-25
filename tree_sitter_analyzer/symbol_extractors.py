"""Top-level symbol-name extraction per source file.

Sister module to :mod:`tree_sitter_analyzer.import_extractors`. Where
``import_extractors`` answers *"what does this file import?"*, this module
answers *"what top-level definitions does this file export?"* — the
second half of the data needed by
:meth:`DependencyGraph.symbol_in_degree`.

Scope (PR-0.2): Python only. Other languages return an empty set as a
graceful no-op; per-language extractors land in follow-up PRs.

Anti-scope:
* Does NOT extract methods (top-level only — class members are
  per-definition resolved elsewhere).
* Does NOT track ``__all__``, visibility, or export signal — that is
  P4's scoring concern.
* Does NOT inspect aliases, wildcard re-exports, or conditional defs.
"""

from __future__ import annotations

import logging
from typing import Any

from .core.parser import Parser, ParseResult

logger = logging.getLogger(__name__)


# Tree-sitter Python node types — captured here as constants rather
# than imported from a generated grammar header so this module is
# resilient to grammar version churn (tree-sitter-python has been
# stable on these names since 0.20).
_PY_FUNCTION_DEF = "function_definition"
_PY_CLASS_DEF = "class_definition"
_PY_DECORATED_DEF = "decorated_definition"


def extract_top_level_defs_from_file(file_path: str, language: str) -> set[str]:
    """Return top-level function and class names defined in ``file_path``.

    For unsupported languages (anything but Python in PR-0.2), returns an
    empty set without raising — callers should treat empty as
    "language not supported", not as "file has no defs".

    The implementation walks ONLY the module root's direct children, so
    nested functions / functions inside ``if __name__ == "__main__"`` /
    methods inside classes are NOT counted. This matches the
    ``symbol_in_degree`` contract: we count things that other files can
    import, which means module-level top-line names.
    """

    if language != "python":
        return set()

    try:
        parser = Parser()
        result: ParseResult = parser.parse_file(file_path, language)
    except Exception:  # noqa: BLE001 — same failure-mode contract as extract_imports_from_file
        return set()

    if not result.success or result.tree is None:
        return set()

    root = result.tree.root_node
    return _python_top_level_names(root, result.source_code)


def _python_top_level_names(root_node: Any, source: bytes | str) -> set[str]:
    """Collect names of top-level ``def`` and ``class`` declarations.

    Handles three shapes:

    * Bare ``def foo(): ...`` / ``class Foo: ...`` directly under module.
    * Decorated ``@decorator\\ndef foo(): ...`` — wrapped in
      ``decorated_definition``; we unwrap one level.

    Decorators with arbitrary expressions inside (``@some.attr.lookup``)
    are not relevant — only the wrapped function/class name matters.
    """

    names: set[str] = set()

    children = getattr(root_node, "children", None) or ()
    for child in children:
        node_type = getattr(child, "type", None)
        if node_type in (_PY_FUNCTION_DEF, _PY_CLASS_DEF):
            name = _name_of_def(child, source)
            if name:
                names.add(name)
        elif node_type == _PY_DECORATED_DEF:
            inner = _decorated_inner_def(child)
            if inner is not None:
                name = _name_of_def(inner, source)
                if name:
                    names.add(name)

    return names


def _decorated_inner_def(decorated_node: Any) -> Any | None:
    """Return the wrapped ``function_definition`` / ``class_definition``.

    A ``decorated_definition`` node has one or more ``decorator`` children
    followed by exactly one definition child. Returns ``None`` if the
    expected definition child is missing (degenerate AST).
    """

    children = getattr(decorated_node, "children", None) or ()
    for child in children:
        if getattr(child, "type", None) in (_PY_FUNCTION_DEF, _PY_CLASS_DEF):
            return child
    return None


def _name_of_def(def_node: Any, source: bytes | str) -> str | None:
    """Extract the identifier name from a function/class definition node.

    Tree-sitter exposes the name child via the ``name`` field. We use the
    ``child_by_field_name`` API when available (libtree-sitter ≥0.20) and
    fall back to scanning children for an ``identifier`` node otherwise.
    """

    name_node = None
    if hasattr(def_node, "child_by_field_name"):
        try:
            name_node = def_node.child_by_field_name("name")
        except Exception:  # noqa: BLE001
            name_node = None

    if name_node is None:
        for child in getattr(def_node, "children", None) or ():
            if getattr(child, "type", None) == "identifier":
                name_node = child
                break

    if name_node is None:
        return None

    return _node_text(name_node, source)


def _node_text(node: Any, source: bytes | str) -> str | None:
    """Return the literal source text of a tree-sitter node."""

    start = getattr(node, "start_byte", None)
    end = getattr(node, "end_byte", None)
    if start is None or end is None or start >= end:
        return None

    if isinstance(source, str):
        # tree-sitter byte offsets are over the UTF-8 encoded source;
        # slicing a ``str`` by byte offsets is wrong for non-ASCII.
        # Re-encode once — this only happens for the small slice that
        # actually holds the identifier name, so the cost is negligible.
        encoded = source.encode("utf-8")
    else:
        encoded = source

    try:
        return encoded[start:end].decode("utf-8")
    except (UnicodeDecodeError, IndexError):
        return None


__all__ = ["extract_top_level_defs_from_file"]
