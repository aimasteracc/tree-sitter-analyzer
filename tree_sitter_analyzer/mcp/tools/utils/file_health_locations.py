"""Location helpers for actionable file-health smells."""

from __future__ import annotations

from typing import Any

from .element_extractor import get_functions


def deepest_nesting_location(lines: list[str]) -> tuple[int, int]:
    """Return the deepest indentation-derived nesting depth and its line."""
    max_indent = 0
    max_line = 0
    for line_number, line in enumerate(lines, start=1):
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if not counts_for_nesting(stripped):
            continue
        indent = len(line) - len(line.lstrip())
        if indent > max_indent:
            max_indent = indent
            max_line = line_number
    return max_indent // 4, max_line


def counts_for_nesting(stripped_line: str) -> bool:
    """Return whether an indented line is likely executable nesting signal."""
    stripped = stripped_line.lstrip()
    if stripped.startswith(("'", '"')):
        return False
    if stripped[0] in ")]}":
        return False
    return True


def largest_function(analysis: Any) -> dict[str, Any] | None:
    """Return the largest function-like element from analysis, if available."""
    if not analysis:
        return None
    functions = get_functions(analysis)
    if not functions:
        return None
    return max(functions, key=lambda func: func.get("lines", 0))


def first_control_flow_line(lines: list[str]) -> int:
    """Return the first likely decision branch line."""
    starters = (
        "if ",
        "if(",
        "elif ",
        "else if",
        "for ",
        "for(",
        "while ",
        "while(",
        "case ",
        "catch ",
        "except ",
        "switch ",
        "switch(",
        "try:",
    )
    for line_number, line in enumerate(lines, start=1):
        if line.strip().startswith(starters):
            return line_number
    return 0


def first_import_line(lines: list[str]) -> int:
    """Return the first likely import/dependency declaration line."""
    import_starters = ("import ", "from ", "#include", "use ", "package ")
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(import_starters) or "require(" in stripped:
            return line_number
    return 0
