"""Code smell detection helpers for file health reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..security_scanner import detect_security_issues
from .anti_patterns import detect_anti_patterns
from .element_extractor import get_classes, get_functions
from .file_health_blocks import find_long_blocks_heuristic
from .file_health_locations import (
    deepest_nesting_location,
    first_control_flow_line,
    first_import_line,
    largest_function,
)

# N7 (round-28): canonical smell-type normalization. ``code_patterns``
# emits security findings as bare names (e.g. ``eval_usage``) while
# ``file_health`` used to prefix them with ``security:``. Same rule,
# different ``type`` string — agents that chained the two tools had to
# branch on both. Strip the prefix here so both surfaces agree on the
# canonical name. The ``category`` / ``smell_kind`` flag below is the
# load-bearing distinguisher between a smell-mirror of a security
# finding and the dedicated security pass.
_SECURITY_SMELL_PREFIX = "security:"


def canonical_smell_type(smell: dict[str, Any]) -> str:
    """Return the canonical type name for a smell.

    Strips the legacy ``security:`` prefix so cross-tool consumers see the
    same string regardless of whether the smell came from ``file_health``
    (which used to prefix) or ``code_patterns`` (which never did). Falls
    through ``smell`` → ``type`` → ``id`` → ``"unknown"`` so the helper
    works on every shape the codebase emits.
    """
    raw = smell.get("smell") or smell.get("type") or smell.get("id") or "unknown"
    if isinstance(raw, str) and raw.startswith(_SECURITY_SMELL_PREFIX):
        return raw[len(_SECURITY_SMELL_PREFIX) :]
    return str(raw)


TECH_DEBT_MARKERS = ("TODO", "FIXME", "HACK", "XXX")
COMMENT_DELIMITERS = ("#", "//", "/*", "*", "<!--", "--")

# K9: long-line / single-line-file thresholds. 200 chars per line is the
# de-facto industry ceiling for code review readability (PEP-8 = 79/99,
# Black = 88, Google style = 80, Java/JS modern = 120, hard upper for
# "still readable in a side-by-side diff" = ~200). Picking 200 keeps
# normal 80-120 char code clean while still flagging minified / bundled
# / single-statement-per-file emissions where humans can no longer
# scan the file. SINGLE_LINE_FILE_THRESHOLD = 200 bytes prevents
# false-positives on trivial files (1-line modules, ``__init__.py`` with
# only an import) while still catching the 3.5KB bundled-on-one-line
# case reported in K9.
LONG_LINE_THRESHOLD = 200
SINGLE_LINE_FILE_THRESHOLD = 200
LONG_LINE_REPORT_LIMIT = 5


def detect_code_smells(
    file_path: str,
    dimensions: dict[str, float],
    analysis: Any,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Detect specific code smells using tree-sitter elements."""
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines = source.splitlines()
    line_count = len(lines)
    smells: list[dict[str, Any]] = []

    _check_oversized_file(smells, line_count)
    _check_deep_nesting(smells, lines)
    _check_dimension_smells(smells, dimensions, lines, analysis)
    _check_element_smells(smells, lines, line_count, analysis)
    _check_technical_debt(smells, lines)
    _check_security_smells(smells, source, language, file_path)
    # N7 (round-28): file_health was missing anti-pattern coverage that
    # ``code_patterns`` already had — ``mutable_default_argument``,
    # ``bare_except``, ``print_in_production`` (Python), and similar
    # JS/Java rules. Sharing ``detect_anti_patterns`` means the two
    # tools surface the same set of findings on the same file, which is
    # what an agent walking either response shape expects.
    _check_anti_pattern_smells(smells, file_path, language)
    # K9: catch files that the tree-sitter element pass never sees as
    # problematic — a 3.5KB minified/bundled blob on one physical line
    # used to score grade A because no smell detector covered it. Run
    # AFTER the dimension/element checks so the long-line smells don't
    # crowd out the more actionable signals when both fire.
    _check_long_lines(smells, lines)
    _check_single_line_file(smells, source)

    return smells


def _check_anti_pattern_smells(
    smells: list[dict[str, Any]],
    file_path: str,
    language: str | None,
) -> None:
    """Emit anti-pattern findings (mutable_default_argument, bare_except, …).

    Mirrors what ``code_patterns._detect_anti_patterns`` does — they share
    ``detect_anti_patterns`` under the hood — and reshapes each finding to
    the smell envelope ``detect_code_smells`` returns. ``smell_kind`` is
    set to ``anti_pattern`` so downstream dedup logic can distinguish
    these from the smell-mirror of a security finding.
    """
    issues = detect_anti_patterns(file_path, language)
    for issue in issues:
        smells.append(
            {
                "smell": issue.get("type") or issue.get("id") or "unknown",
                "smell_kind": "anti_pattern",
                "detail": issue.get("message", ""),
                "severity": issue.get("severity", "info"),
                "line": issue.get("line"),
                "fix": _anti_pattern_fix_hint(issue.get("type")),
            }
        )


_ANTI_PATTERN_FIX_HINTS: dict[str, str] = {
    "mutable_default_argument": (
        "Use ``None`` as the default and create the mutable inside the function"
    ),
    "bare_except": "Catch a specific exception type, or use ``except Exception:``",
    "print_in_production": "Use the project logger instead of ``print()``",
    "var_usage": "Use ``const`` (or ``let``) instead of ``var``",
    "loose_equality": "Use ``===`` / ``!==`` instead of ``==`` / ``!=``",
    "system_out_println": "Use a logging framework instead of ``System.out``",
    "print_stacktrace": "Use proper logging instead of ``printStackTrace()``",
}


def _anti_pattern_fix_hint(anti_type: str | None) -> str:
    """Return a one-line fix hint for an anti-pattern smell."""
    if not anti_type:
        return ""
    return _ANTI_PATTERN_FIX_HINTS.get(anti_type, "")


def _check_long_lines(smells: list[dict[str, Any]], lines: list[str]) -> None:
    """Flag individual lines that exceed ``LONG_LINE_THRESHOLD``.

    Caps reported lines at ``LONG_LINE_REPORT_LIMIT`` to avoid drowning
    the smell list when an entire file is minified — the headline
    ``single_line_file`` smell already covers the worst case. We report
    by descending length so the most egregious offenders surface first.
    """
    if not lines:
        return
    candidates: list[tuple[int, int]] = []
    for line_no, line in enumerate(lines, start=1):
        length = len(line)
        if length > LONG_LINE_THRESHOLD:
            candidates.append((line_no, length))
    if not candidates:
        return
    # Report the longest lines first, up to the cap. Tie-break by line
    # number so output is deterministic.
    candidates.sort(key=lambda pair: (-pair[1], pair[0]))
    for line_no, length in candidates[:LONG_LINE_REPORT_LIMIT]:
        smells.append(
            {
                "smell": "long_line",
                "detail": (
                    f"Line {line_no} is {length} chars "
                    f"(recommended <= {LONG_LINE_THRESHOLD})"
                ),
                "severity": "critical" if length > 500 else "warning",
                "line": line_no,
                "fix": (
                    "Break the line at logical boundaries — extract sub-"
                    "expressions, use line continuations, or split the "
                    "statement across multiple lines"
                ),
            }
        )


def _check_single_line_file(smells: list[dict[str, Any]], source: str) -> None:
    """Flag files that have no newlines but substantial content.

    Bundled JS, minified output, and one-liner Python scripts that grew
    too big all share this shape — the file is ``substantial`` bytes
    long but tree-sitter element extraction reports 1 line of code.
    Without this check those files score grade A because the long_method
    / oversized_file / deep_nesting checks all rely on line counts.
    """
    if not source or "\n" in source:
        return
    if len(source) < SINGLE_LINE_FILE_THRESHOLD:
        return
    smells.append(
        {
            "smell": "single_line_file",
            "detail": (
                f"File has no newlines but {len(source)} chars — "
                "likely minified / bundled / accidentally inlined"
            ),
            "severity": "critical",
            "line": 1,
            "fix": (
                "Re-format the file with line breaks at logical "
                "statements; if the source is generated, regenerate "
                "from the original."
            ),
        }
    )


def _check_oversized_file(smells: list[dict[str, Any]], line_count: int) -> None:
    """Flag files exceeding recommended line count."""
    if line_count <= 500:
        return
    smells.append(
        {
            "smell": "oversized_file",
            "detail": f"{line_count} lines (recommended < 300)",
            "severity": "critical" if line_count > 1000 else "warning",
            "fix": "Split into smaller, focused modules",
        }
    )


def _check_deep_nesting(smells: list[dict[str, Any]], lines: list[str]) -> None:
    """Detect deep nesting based on indentation levels."""
    max_nesting, max_line = deepest_nesting_location(lines)
    if max_nesting <= 4:
        return
    smells.append(
        {
            "smell": "deep_nesting",
            "detail": f"Max nesting depth: {max_nesting} at L{max_line} (recommended < 4)",
            "severity": "critical" if max_nesting > 6 else "warning",
            "line": max_line,
            "fix": "Extract nested logic into helper functions or use early returns",
        }
    )


def _check_dimension_smells(
    smells: list[dict[str, Any]],
    dimensions: dict[str, float],
    lines: list[str],
    analysis: Any,
) -> None:
    """Flag low scores in structure, complexity, and dependency dimensions."""
    _add_low_structure_smell(smells, dimensions, lines)
    _add_low_complexity_smell(smells, dimensions, lines, analysis)
    _add_high_coupling_smell(smells, dimensions, lines)


def _add_low_structure_smell(
    smells: list[dict[str, Any]], dimensions: dict[str, float], lines: list[str]
) -> None:
    """Add a smell for very low structure scores."""
    if dimensions.get("structure", 100) >= 30:
        return
    if any(smell["smell"] == "deep_nesting" for smell in smells):
        return
    max_nesting, max_line = deepest_nesting_location(lines)
    smell = {
        "smell": "deep_nesting",
        "detail": f"Structure score: {dimensions.get('structure', 0):.0f}/100 - deep nesting detected",
        "severity": "warning",
        "fix": "Flatten nesting with early returns, guard clauses, or extract helper functions",
    }
    if max_line:
        smell["detail"] += f" near L{max_line}"
        smell["line"] = max_line
        smell["nesting_depth"] = max_nesting
    smells.append(smell)


def _add_low_complexity_smell(
    smells: list[dict[str, Any]],
    dimensions: dict[str, float],
    lines: list[str],
    analysis: Any,
) -> None:
    """Add a smell for very low complexity scores."""
    complexity = dimensions.get("complexity", 100)
    if complexity >= 30:
        return
    smell = _base_complexity_smell(complexity)
    _annotate_complexity_smell(smell, lines, analysis)
    smells.append(smell)


def _base_complexity_smell(complexity: float) -> dict[str, Any]:
    """Build the generic high-complexity smell payload."""
    return {
        "smell": "high_complexity",
        "detail": f"Complexity score: {complexity:.0f}/100",
        "severity": "critical" if complexity < 10 else "warning",
        "fix": "Break complex functions into smaller, focused ones",
    }


def _annotate_complexity_smell(
    smell: dict[str, Any], lines: list[str], analysis: Any
) -> None:
    """Attach the best available location evidence to a complexity smell."""
    target = largest_function(analysis)
    if target:
        smell["detail"] += f"; inspect '{target['name']}' at L{target['line']}"
        smell["line"] = target["line"]
        smell["symbol"] = target["name"]
        return

    control_line = first_control_flow_line(lines)
    if control_line:
        smell["detail"] += f"; first control-flow branch at L{control_line}"
        smell["line"] = control_line


def _add_high_coupling_smell(
    smells: list[dict[str, Any]], dimensions: dict[str, float], lines: list[str]
) -> None:
    """Add a smell for very low dependency scores."""
    deps = dimensions.get("dependencies", 100)
    if deps >= 30:
        return
    smell = {
        "smell": "high_coupling",
        "detail": f"Dependency score: {deps:.0f}/100",
        "severity": "warning",
        "fix": "Reduce imports - consider dependency injection or facade pattern",
    }
    import_line = first_import_line(lines)
    if import_line:
        smell["detail"] += f"; import cluster starts near L{import_line}"
        smell["line"] = import_line
    smells.append(smell)


def _check_element_smells(
    smells: list[dict[str, Any]],
    lines: list[str],
    line_count: int,
    analysis: Any,
) -> None:
    """Detect god_class and long_method smells from tree-sitter elements."""
    if not analysis:
        _check_heuristic_long_methods(smells, lines)
        return

    classes = get_classes(analysis)
    functions = get_functions(analysis)
    _check_god_class(smells, line_count, classes)
    _check_long_functions(smells, functions)


def _check_god_class(
    smells: list[dict[str, Any]], line_count: int, classes: list[dict[str, Any]]
) -> None:
    """Flag files that look like a single oversized class/module."""
    if len(classes) != 1:
        return

    class_info = classes[0]
    class_lines = class_info["end_line"] - class_info["line"] + 1
    if class_lines <= 300:
        return
    smells.append(
        {
            "smell": "god_class",
            "detail": f"Single class '{class_info['name']}' spans {class_lines} lines",
            "severity": "critical" if class_lines > 500 else "warning",
            "line": class_info["line"],
            "symbol": class_info["name"],
            "fix": "Extract responsibilities into separate classes (Single Responsibility Principle)",
        }
    )


def _check_long_functions(
    smells: list[dict[str, Any]], functions: list[dict[str, Any]]
) -> None:
    """Flag tree-sitter functions longer than the recommended limit."""
    for func in functions:
        if func["lines"] <= 50:
            continue
        smells.append(
            {
                "smell": "long_method",
                "detail": f"'{func['name']}' is {func['lines']} lines (L{func['line']})",
                "severity": "critical" if func["lines"] > 100 else "warning",
                "line": func["line"],
                "symbol": func["name"],
                "fix": "Extract logical sections into separate helper methods",
            }
        )


def _check_heuristic_long_methods(
    smells: list[dict[str, Any]], lines: list[str]
) -> None:
    """Flag long methods when tree-sitter analysis is unavailable."""
    long_methods = find_long_blocks_heuristic(lines, threshold=50)
    for method_name, start, length in long_methods[:3]:
        smells.append(
            {
                "smell": "long_method",
                "detail": f"'{method_name}' is ~{length} lines (L{start})",
                "severity": "critical" if length > 100 else "warning",
                "line": start,
                "symbol": method_name,
                "fix": "Extract logical sections into separate helper methods",
            }
        )


def _check_technical_debt(smells: list[dict[str, Any]], lines: list[str]) -> None:
    """Count TODO/FIXME/HACK markers as technical debt."""
    todo_lines = [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if _has_technical_debt_marker(line)
    ]
    todo_count = len(todo_lines)
    if todo_count <= 5:
        return
    smells.append(
        {
            "smell": "technical_debt",
            "detail": f"{todo_count} TODO/FIXME/HACK markers",
            "severity": "info",
            "line": todo_lines[0],
            "fix": "Resolve or create issues for outstanding TODOs",
        }
    )


def _has_technical_debt_marker(line: str) -> bool:
    """Return whether a line has a TODO-like marker in comment text."""
    stripped = line.strip()
    if stripped.startswith(("#!", "# type:")):
        return False

    if stripped.upper().startswith(TECH_DEBT_MARKERS):
        return True

    comment_text = _comment_text(line)
    return any(marker in comment_text.upper() for marker in TECH_DEBT_MARKERS)


def _comment_text(line: str) -> str:
    """Return probable comment text while avoiding string literals."""
    delimiter_positions = [
        line.find(delimiter) for delimiter in COMMENT_DELIMITERS if delimiter in line
    ]
    if not delimiter_positions:
        return ""

    return line[min(delimiter_positions) :]


def _check_security_smells(
    smells: list[dict[str, Any]],
    source: str,
    language: str | None,
    file_path: str,
) -> None:
    """Add security scanner issues as file-health smells.

    N7 (round-28): emit the bare smell name (``eval_usage``) without the
    legacy ``security:`` prefix so ``file_health.code_smells[].type``
    matches the string ``code_patterns.results[].type`` emits for the
    same finding. ``smell_kind="security"`` carries the same information
    the prefix used to, but in a structured field downstream dedup logic
    can still read.
    """
    if not language:
        return
    sec_issues = detect_security_issues(source, language, file_path=file_path)
    for issue in sec_issues[:10]:
        smells.append(
            {
                "smell": issue["issue"],
                "smell_kind": "security",
                "detail": f"{issue['description']} (line {issue['lines'][0]})",
                "severity": issue["severity"],
                "line": issue["lines"][0],
                "fix": "Move secrets to env vars / use parameterized queries / avoid eval()",
            }
        )
