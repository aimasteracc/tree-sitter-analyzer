"""Language-aware anti-pattern detection.

Shared by ``code_patterns_tool`` (top-level ``category=anti_patterns``
results) and ``file_health_smells.detect_code_smells`` (so file-health
sees the same findings code_patterns does — N7).

Each detector emits dicts with ``id`` / ``type`` / ``severity`` / ``line``
/ ``message`` keys; callers wrap them in their preferred envelope shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_anti_patterns(file_path: str, language: str | None) -> list[dict[str, Any]]:
    """Return anti-pattern findings for ``file_path`` in ``language``.

    Returns an empty list for unsupported languages, unreadable files, or
    files that produce no findings — never raises.
    """
    if not language:
        return []
    patterns: list[dict[str, Any]] = []
    try:
        content = Path(file_path).read_text(errors="replace")
    except Exception:  # nosec B110 — unreadable file is non-fatal here.
        return patterns

    lines = content.splitlines()
    if language == "python":
        _check_python_anti_patterns(lines, patterns)
    elif language in ("javascript", "typescript"):
        _check_js_anti_patterns(lines, patterns)
    elif language == "java":
        _check_java_anti_patterns(lines, patterns)
    return patterns


def python_docstring_line_set(lines: list[str]) -> set[int]:
    """Return 1-indexed line numbers inside Python triple-quoted strings.

    Callers skip these lines so anti-pattern detectors don't fire on
    docstring examples (which often contain ``print()``, bare ``except:``,
    etc.). Implementation is line-based, not AST-based; it handles
    single-line triple quotes and multi-line blocks but does not track
    nested strings or escapes — sufficient for muting false positives.
    """
    inside = False
    delim: str | None = None
    docstring_lines: set[int] = set()
    for i, line in enumerate(lines, 1):
        if inside:
            docstring_lines.add(i)
            if delim and delim in line:
                inside = False
                delim = None
            continue
        for d in ('"""', "'''"):
            idx = line.find(d)
            if idx == -1:
                continue
            docstring_lines.add(i)
            rest = line[idx + 3 :]
            if d not in rest:
                inside = True
                delim = d
            break
    return docstring_lines


def _check_python_anti_patterns(
    lines: list[str], patterns: list[dict[str, Any]]
) -> None:
    docstring_lines = python_docstring_line_set(lines)
    for i, line in enumerate(lines, 1):
        if i in docstring_lines:
            continue
        stripped = line.strip()
        # r37as (dogfood): AP001/AP002 used to fire on `#`-comment lines
        # that contained example snippets (e.g. ``# ``def f(x=[])`` ``).
        # AP003 already skipped ``stripped.startswith("#")``; mirror the
        # same guard onto the structural anti-patterns so docstring +
        # comment false-positives are caught by a single rule.
        if stripped.startswith("#"):
            continue

        if "=" in stripped and any(
            f"={t}" in stripped for t in ("[]", "{},", "set()", "[],")
        ):
            if "def " in lines[max(0, i - 5) : i][-1] or any(
                "def " in ln for ln in lines[max(0, i - 10) : i]
            ):
                patterns.append(
                    {
                        "id": "AP001",
                        "type": "mutable_default_argument",
                        "severity": "critical",
                        "message": "Mutable default argument — shared across calls",
                        "line": i,
                    }
                )

        if stripped.startswith("except:") and "except:" == stripped:
            patterns.append(
                {
                    "id": "AP002",
                    "type": "bare_except",
                    "severity": "warning",
                    "message": "Bare except catches everything including KeyboardInterrupt",
                    "line": i,
                }
            )

        if "print(" in stripped and not stripped.startswith("#"):
            in_def = any("def " in ln for ln in lines[max(0, i - 30) : i])
            if in_def:
                patterns.append(
                    {
                        "id": "AP003",
                        "type": "print_in_production",
                        "severity": "info",
                        "message": "Use logging instead of print()",
                        "line": i,
                    }
                )


def _check_js_anti_patterns(lines: list[str], patterns: list[dict[str, Any]]) -> None:
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "var " in stripped and not stripped.startswith("//"):
            patterns.append(
                {
                    "id": "AP010",
                    "type": "var_usage",
                    "severity": "info",
                    "message": "Use const/let instead of var",
                    "line": i,
                }
            )
        if "== " in stripped or " !=" in stripped:
            if "===" not in stripped and "!==" not in stripped:
                patterns.append(
                    {
                        "id": "AP011",
                        "type": "loose_equality",
                        "severity": "warning",
                        "message": "Use === instead of == for strict comparison",
                        "line": i,
                    }
                )


def _check_java_anti_patterns(lines: list[str], patterns: list[dict[str, Any]]) -> None:
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "System.out.println" in stripped and not stripped.startswith("//"):
            patterns.append(
                {
                    "id": "AP020",
                    "type": "system_out_println",
                    "severity": "info",
                    "message": "Use a logging framework instead of System.out",
                    "line": i,
                }
            )
        if "e.printStackTrace()" in stripped:
            patterns.append(
                {
                    "id": "AP021",
                    "type": "print_stacktrace",
                    "severity": "warning",
                    "message": "Use proper logging instead of printStackTrace()",
                    "line": i,
                }
            )


__all__ = ["detect_anti_patterns", "python_docstring_line_set"]
