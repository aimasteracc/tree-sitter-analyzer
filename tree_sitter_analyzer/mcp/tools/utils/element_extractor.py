#!/usr/bin/env python3
"""
Cross-language element extraction via tree-sitter.

Replaces Python-AST-only analysis with the existing tree-sitter language
plugin system so that all 15 supported languages get full MCP tool value.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ....constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ....core.analysis_engine import AnalysisRequest, get_analysis_engine
from ....language_detector import detect_language_from_file
from ....models import AnalysisResult


def extract_elements(
    file_path: str, project_root: str | None = None
) -> AnalysisResult | None:
    """Analyze a file with tree-sitter and return structured elements.

    Returns None if the file cannot be parsed (unsupported language,
    binary file, etc.).
    """
    language = detect_language_from_file(file_path)
    if not language:
        return None

    engine = get_analysis_engine(project_root)
    request = AnalysisRequest(
        file_path=file_path,
        language=language,
        include_elements=True,
        include_complexity=True,
    )

    try:
        result = engine.analyze_sync(request)
        if result and result.elements:
            return result  # type: ignore[no-any-return]
    except Exception:  # nosec B110 — parse failure is non-critical
        pass

    return None


def get_functions(result: AnalysisResult) -> list[dict[str, Any]]:
    """Extract function/method elements from an AnalysisResult."""
    return [
        {
            "name": e.name,
            "kind": "function",
            "line": e.start_line,
            "end_line": e.end_line,
            "lines": e.end_line - e.start_line + 1,
            "parameters": getattr(e, "parameters", []),
            "is_static": getattr(e, "is_static", False),
            "visibility": getattr(e, "visibility", "public"),
            "parent": None,
        }
        for e in result.elements
        if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
    ]


def get_classes(result: AnalysisResult) -> list[dict[str, Any]]:
    """Extract class elements from an AnalysisResult."""
    # Get all functions to compute method counts by line range
    all_functions = get_functions(result)

    classes = []
    for e in result.elements:
        if not is_element_of_type(e, ELEMENT_TYPE_CLASS):
            continue
        methods = getattr(e, "methods", [])

        # If tree-sitter plugin didn't populate methods, compute from line ranges
        if not methods:
            class_funcs = [
                f
                for f in all_functions
                if f["line"] >= e.start_line and f["end_line"] <= e.end_line
            ]
            method_count = len(class_funcs)
            method_names = [f["name"] for f in class_funcs]
        else:
            method_count = len(methods)
            method_names = [m.name for m in methods]

        classes.append(
            {
                "name": e.name,
                "kind": "class",
                "line": e.start_line,
                "end_line": e.end_line,
                "method_count": method_count,
                "method_names": method_names,
            }
        )
    return classes


def get_imports(result: AnalysisResult) -> list[str]:
    """Extract import/module names from an AnalysisResult."""
    imports = []
    for e in result.elements:
        if is_element_of_type(e, ELEMENT_TYPE_IMPORT):
            imports.append(e.name)
    return imports


def get_all_exports(result: AnalysisResult) -> list[dict[str, Any]]:
    """Extract all exported symbols (classes, functions, constants, __all__).

    Recognises four export classes:
    - ``class`` — definitions
    - ``function`` — public (non-underscore-prefixed) definitions
    - ``constant`` — UPPER_CASE module-level variables
    - ``reexport`` — names listed in a module-level ``__all__`` list literal

    The ``reexport`` recognition is what makes ``__init__.py`` files report
    non-empty ``exports`` even when they only import + re-publish symbols.
    """
    exports: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for e in result.elements:
        if is_element_of_type(e, ELEMENT_TYPE_CLASS):
            methods = getattr(e, "methods", [])
            exports.append(
                {
                    "name": e.name,
                    "kind": "class",
                    "line": e.start_line,
                    "methods": len(methods),
                }
            )
            seen_names.add(e.name)
        elif is_element_of_type(e, ELEMENT_TYPE_FUNCTION):
            if not e.name.startswith("_"):
                exports.append(
                    {
                        "name": e.name,
                        "kind": "function",
                        "line": e.start_line,
                    }
                )
                seen_names.add(e.name)
        elif is_element_of_type(e, ELEMENT_TYPE_VARIABLE):
            if e.name.isupper():
                exports.append(
                    {
                        "name": e.name,
                        "kind": "constant",
                        "line": e.start_line,
                    }
                )
                seen_names.add(e.name)

    # Re-exports declared via ``__all__`` — parse the source so that
    # __init__.py files (which usually only import + republish) report
    # exports>0. Names already captured as class/function/constant above
    # are skipped to avoid double-counting.
    file_path = getattr(result, "file_path", None)
    if isinstance(file_path, str):
        for reexport in _extract_all_reexports(file_path):
            if reexport["name"] in seen_names:
                continue
            exports.append(reexport)
            seen_names.add(reexport["name"])

    return exports


def _extract_all_reexports(file_path: str) -> list[dict[str, Any]]:
    """Parse a module-level ``__all__`` list literal and return reexports.

    Only Python sources are considered. Failures (missing file, syntax
    error, non-list ``__all__``, non-string members) are swallowed — this
    is best-effort metadata, never a correctness gate.
    """
    if not file_path or not file_path.endswith(".py"):
        return []
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    for node in tree.body:
        names_line = _read_all_assignment(node)
        if names_line is None:
            continue
        names, lineno = names_line
        return [{"name": name, "kind": "reexport", "line": lineno} for name in names]
    return []


def _read_all_assignment(node: ast.stmt) -> tuple[list[str], int] | None:
    """Return ``(names, lineno)`` if ``node`` is ``__all__ = [...]``.

    Accepts list or tuple literals of string constants. Returns ``None``
    for anything else (other assignments, augmented assignments, dynamic
    forms like ``__all__ += [...]``).
    """
    if not isinstance(node, ast.Assign):
        return None
    if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
        return None
    value = node.value
    if not isinstance(value, ast.List | ast.Tuple):
        return None
    names: list[str] = []
    for elt in value.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            names.append(elt.value)
    if not names:
        return None
    return names, node.lineno


def get_structure(result: AnalysisResult) -> list[dict[str, str]]:
    """Extract a lightweight structure outline."""
    structure: list[dict[str, str]] = []
    for e in result.elements:
        if is_element_of_type(e, ELEMENT_TYPE_CLASS):
            structure.append(
                {
                    "name": e.name,
                    "kind": "class",
                    "lines": f"{e.start_line}-{e.end_line}",
                }
            )
        elif is_element_of_type(e, ELEMENT_TYPE_FUNCTION):
            structure.append(
                {
                    "name": e.name,
                    "kind": "function",
                    "lines": f"{e.start_line}-{e.end_line}",
                }
            )

    return structure[:30]


def get_functions_in_class(
    result: AnalysisResult, class_name: str
) -> list[dict[str, Any]]:
    """Get functions that belong to a specific class."""
    for e in result.elements:
        if is_element_of_type(e, ELEMENT_TYPE_CLASS) and e.name == class_name:
            methods = getattr(e, "methods", [])
            return [
                {
                    "name": m.name,
                    "line": m.start_line,
                    "end_line": m.end_line,
                    "lines": m.end_line - m.start_line + 1,
                    "is_static": getattr(m, "is_static", False),
                }
                for m in methods
            ]
    return []
