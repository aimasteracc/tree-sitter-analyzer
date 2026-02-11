"""
Shared decorator extraction logic — single source of truth.

Both scanner.py (main-thread) and parallel.py (worker-thread) use this
module to extract decorated function/method names. Eliminates the code
duplication flagged by Martin Fowler (F-1).
"""

from __future__ import annotations

import logging
from typing import Any

from tree_sitter_analyzer_v2.core.code_map.constants import FRAMEWORK_DECORATORS

logger = logging.getLogger(__name__)


def extract_decorated_entries(
    functions: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    ast_node: Any = None,
) -> set[str]:
    """Extract names of functions/methods that have framework decorators.

    This is the **single source of truth** for decorator extraction,
    used by both the parallel parsing path and the single-thread path.

    Args:
        functions: Parsed function dicts from a language parser.
        classes: Parsed class dicts from a language parser.
        ast_node: Optional AST root for fallback decorator scanning.

    Returns:
        Set of function/method names considered "framework-registered"
        (exempt from dead code detection).
    """
    decorated: set[str] = set()
    decorator_names_used: set[str] = set()

    def _check_decos(decos: list[str], func_name: str) -> None:
        for dec in decos:
            root_name = dec.replace("@", "").split("(")[0].split(".")[0]
            if root_name:
                decorator_names_used.add(root_name)
            parts = dec.replace("@", "").split("(")[0].split(".")
            if any(p in FRAMEWORK_DECORATORS for p in parts):
                if func_name:
                    decorated.add(func_name)

    for func in functions:
        _check_decos(func.get("decorators", []), func.get("name", ""))

    for cls in classes:
        for method in cls.get("methods", []):
            _check_decos(method.get("decorators", []), method.get("name", ""))

    # Decorator factories themselves are also alive
    decorated |= decorator_names_used

    # AST fallback: if no decorated entries found from parser metadata,
    # walk the AST tree to find decorated_definition nodes
    if ast_node and not decorated:
        decorated |= _scan_ast_for_decorators(ast_node)

    return decorated


def _scan_ast_for_decorators(
    node: Any, *, _depth: int = 0, _max_depth: int = 50
) -> set[str]:
    """Walk AST to find decorated function/class definitions (Python-specific)."""
    decorated: set[str] = set()
    if not node or not hasattr(node, "type") or _depth > _max_depth:
        return decorated

    if node.type == "decorated_definition":
        func_name = _get_decorated_func_name(node)
        dec_name = _get_decorator_name(node)
        if func_name and dec_name:
            parts = dec_name.split(".")
            if any(p in FRAMEWORK_DECORATORS for p in parts):
                decorated.add(func_name)

    if hasattr(node, "children"):
        for child in node.children:
            decorated |= _scan_ast_for_decorators(
                child, _depth=_depth + 1, _max_depth=_max_depth
            )

    return decorated


def _get_decorated_func_name(node: Any) -> str:
    """Extract function/class name from a decorated_definition node."""
    if not hasattr(node, "children"):
        return ""
    for child in node.children:
        if child.type in ("function_definition", "class_definition"):
            for sub in child.children:
                if sub.type == "identifier":
                    text = getattr(sub, "text", b"")
                    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
    return ""


def _get_decorator_name(node: Any) -> str:
    """Extract decorator name from a decorated_definition node."""
    if not hasattr(node, "children"):
        return ""
    for child in node.children:
        if child.type == "decorator":
            for sub in child.children:
                if sub.type == "identifier":
                    text = getattr(sub, "text", b"")
                    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
                if sub.type in ("attribute", "call"):
                    text = getattr(sub, "text", b"")
                    raw = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    return raw.split("(")[0]
    return ""
