#!/usr/bin/env python3
"""
Code Patterns / Anti-Pattern Detection MCP Tool.

Unified pattern detection combining code smells, security issues, refactoring
patterns, and LLM anti-patterns into a single agent-friendly API.

Tells AI agents: "Here are the problems in this file and how to fix them."
"""

from pathlib import Path
from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool, mirror_summary_line
from .security_scanner import detect_security_issues
from .utils.anti_patterns import (
    _check_java_anti_patterns,
    _check_js_anti_patterns,
    _check_python_anti_patterns,
    detect_anti_patterns,
)
from .utils.anti_patterns import (
    python_docstring_line_set as _python_docstring_line_set,
)
from .utils.element_extractor import extract_elements
from .utils.file_health_smells import canonical_smell_type, detect_code_smells
from .utils.parse_validity import is_file_parse_broken

# Backwards-compatible aliases for the previously-private helpers that
# unit tests imported by name. The implementations now live in
# ``utils.anti_patterns`` so file_health and code_patterns share the
# same code (N7); we keep these symbols at the module level so older
# call sites and tests continue to work.
__all__ = [
    "CodePatternsTool",
    "_check_java_anti_patterns",
    "_check_js_anti_patterns",
    "_check_python_anti_patterns",
    "_detect_anti_patterns",
    "_detect_security",
    "_detect_smells",
    "_python_docstring_line_set",
]

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "File to scan for patterns",
        },
        "categories": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["smells", "security", "anti_patterns", "all"],
            },
            "default": ["all"],
            "description": "Pattern categories to detect",
        },
        "severity_threshold": {
            "type": "string",
            "enum": ["info", "warning", "critical"],
            "default": "info",
            "description": "Minimum severity to report",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    "required": ["file_path"],
    "additionalProperties": False,
}

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class CodePatternsTool(BaseMCPTool):
    """Detect code patterns, anti-patterns, and security issues in a file."""

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "code_patterns",
            "description": (
                "Detect anti-patterns, code smells, and security issues in a file. "
                "Categories: smells (god_class, long_method, deep_nesting), "
                "security (sql_injection, hardcoded_secret, eval_usage), "
                "anti_patterns (mutable_defaults, bare_except, print_statements). "
                "Use BEFORE editing to know what to fix."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("file_path"):
            raise ValueError("file_path is required")
        cats = arguments.get("categories", ["all"])
        valid = {"smells", "security", "anti_patterns", "all"}
        for c in cats:
            if c not in valid:
                raise ValueError(f"Unknown category: {c}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Scan a file for code-quality patterns.

        r37bm (dogfood): tool flagged this at 152 lines. Split into
        early-exit guards + detection scatter + envelope assembly.
        Pol2 / M3 / G4 / Pol1 / M10 contracts preserved exactly.
        """
        file_path = arguments["file_path"]
        categories = arguments.get("categories", ["all"])
        severity_threshold = arguments.get("severity_threshold", "info")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).is_file():
            raise ValueError(f"Not a file: {file_path}")

        # Pol2: short-circuit empty / whitespace-only files so the agent
        # gets the same ``signal=empty_file`` envelope file_health emits.
        empty_response = _empty_file_response(resolved, file_path, output_format)
        if empty_response is not None:
            return empty_response

        from ...language_detector import detect_language_from_file

        language = detect_language_from_file(resolved, project_root=self.project_root)

        # M3: short-circuit on parse errors so we don't grade garbled output.
        syntax_response = _syntax_error_response(
            resolved, file_path, language, output_format
        )
        if syntax_response is not None:
            return syntax_response

        all_patterns = self._collect_patterns(resolved, language, categories)
        min_sev = _SEVERITY_ORDER.get(severity_threshold, 0)
        filtered = _filter_and_sort_patterns(all_patterns, min_sev)

        response = _build_code_patterns_response(
            file_path=file_path,
            language=language,
            filtered=filtered,
        )
        # M10: mirror agent_summary.verdict to top level.
        response = mirror_summary_line(response)
        return apply_toon_format_to_response(response, output_format)

    def _collect_patterns(
        self,
        resolved: str,
        language: str | None,
        categories: list[str],
    ) -> list[dict[str, Any]]:
        """Run the 3 category detectors per ``categories``, then G4-dedup."""
        all_patterns: list[dict[str, Any]] = []
        scan_all = "all" in categories
        if scan_all or "smells" in categories:
            all_patterns.extend(_detect_smells(resolved, language, self.project_root))
        if scan_all or "security" in categories:
            all_patterns.extend(_detect_security(resolved, language))
        if scan_all or "anti_patterns" in categories:
            all_patterns.extend(_detect_anti_patterns(resolved, language))
        # G4: drop the smells-namespaced duplicate of a security finding.
        return _dedup_security_mirror(all_patterns)


def _filter_and_sort_patterns(
    patterns: list[dict[str, Any]], min_sev: int
) -> list[dict[str, Any]]:
    """Drop patterns below ``min_sev`` and sort the rest by severity descending."""
    filtered = [
        p for p in patterns if _SEVERITY_ORDER.get(p.get("severity"), 0) >= min_sev
    ]
    filtered.sort(key=lambda p: _SEVERITY_ORDER.get(p.get("severity"), 0), reverse=True)
    return filtered


def _build_code_patterns_response(
    *,
    file_path: str,
    language: str | None,
    filtered: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the canonical code_patterns envelope from a filtered findings list.

    r37bm: extracted from ``execute`` so the 30-line envelope literal +
    verdict/next_step dispatch live in one focused function. Pol1
    summary_line formatting + count/results cross-tool aliases preserved.
    """
    by_category: dict[str, list[dict[str, Any]]] = {}
    for p in filtered:
        by_category.setdefault(p["category"], []).append(p)

    critical_count = sum(1 for p in filtered if p.get("severity") == "critical")
    warning_count = sum(1 for p in filtered if p.get("severity") == "warning")

    # Pol1: " ".join keeps the headline well-formed even if a part is empty.
    summary_line = " ".join(
        [
            file_path,
            f"{len(filtered)} patterns",
            f"critical={critical_count}",
            f"warning={warning_count}",
        ]
    )

    if critical_count:
        verdict = "UNSAFE"
        next_step = (
            "refactoring_suggestions for concrete fix recipes — start with "
            "critical findings"
        )
    elif warning_count:
        verdict = "CAUTION"
        next_step = "refactoring_suggestions or address warnings before shipping"
    else:
        verdict = "SAFE"
        next_step = "no patterns flagged — proceed with planned change"

    hint_critical = (
        "Critical issues found — fix these first. "
        if critical_count
        else "Review warnings and decide which to address. "
    )

    return {
        "success": True,
        "file_path": file_path,
        "language": language,
        "total_patterns": len(filtered),
        # ``count`` + ``results`` are cross-tool canonical aliases.
        "count": len(filtered),
        "results": filtered[:50],
        "by_category": {k: len(v) for k, v in by_category.items()},
        "critical_count": critical_count,
        "warning_count": warning_count,
        "summary": _build_summary(filtered),
        "smart_workflow_hint": (
            f"Found {len(filtered)} pattern(s) in {file_path}. "
            + hint_critical
            + "Use refactoring_suggestions for concrete fix recipes."
        ),
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": verdict,
        },
    }


def _dedup_security_mirror(
    patterns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate findings across smell / security / anti-pattern passes.

    Two dedup passes happen here, in this order:

    1) ``smells`` mirror of a security finding (original G4 behaviour).
       ``file_health_smells.detect_code_smells`` re-emits security issues
       under the smell namespace so file-health reports can surface them
       as a single signal. When ``code_patterns`` *also* runs the
       dedicated security pass, the same underlying finding appears
       twice: once with ``category=smells smell_kind=security
       type=sql_injection``, once with ``category=security
       type=sql_injection``. The second one is the canonical record,
       so we drop the smell-namespaced mirror whenever a matching
       ``(line, type)`` exists under the ``security`` category.

       N7 (round-28): the smell mirror now emits the bare type
       (``sql_injection``) instead of the prefixed ``security:sql_injection``,
       so the dedup uses the smell's ``smell_kind`` flag — set by
       ``_check_security_smells`` — to identify a mirror. Direct ``type``
       comparison would also work but the flag makes the intent explicit.

    2) ``anti_patterns`` vs ``security`` cross-category mirror (J10,
       round-22). ``_detect_security`` and ``_detect_anti_patterns``
       independently flag the same constructs — ``bare_except`` shows
       up as ``('bare_except', 'security')`` AND ``('AP002',
       'anti_patterns', 'bare_except')`` on the same line. Keep the
       ``security`` namespace as canonical (matches the G4 convention)
       and drop the ``anti_patterns`` duplicate whenever a matching
       ``(line, normalized_type)`` exists under ``security``.
    """
    # --- Pass 1 (G4): drop the ``smells`` mirror of a security finding ---
    security_keys: set[tuple[int | None, str]] = {
        (p.get("line"), str(p.get("type") or p.get("id") or ""))
        for p in patterns
        if p.get("category") == "security"
    }

    pass1: list[dict[str, Any]] = []
    if security_keys:
        for pattern in patterns:
            if pattern.get("category") == "smells" and _is_security_mirror_smell(
                pattern, security_keys
            ):
                continue
            pass1.append(pattern)
    else:
        pass1 = list(patterns)

    # --- Pass 2 (J10): drop anti_patterns mirror of a security finding ---
    # ``security_keys`` is reused intentionally: pass1 only drops smell
    # mirrors, so the set of canonical security findings is unchanged.
    if not security_keys:
        return pass1

    pass2: list[dict[str, Any]] = []
    for pattern in pass1:
        if pattern.get("category") == "anti_patterns":
            # The anti-pattern entries carry the human-readable
            # ``type`` (e.g. ``bare_except``) — that is what matches
            # the security ``type`` key. Compare against ``type`` only;
            # the AP*** ``id`` would never collide and the security
            # detector itself already normalises on ``type``.
            anti_type = str(pattern.get("type") or "")
            if anti_type and (pattern.get("line"), anti_type) in security_keys:
                continue
        pass2.append(pattern)
    return pass2


def _is_security_mirror_smell(
    pattern: dict[str, Any],
    security_keys: set[tuple[int | None, str]],
) -> bool:
    """Return True when ``pattern`` is the smell-side mirror of a security finding.

    Two ways to tell:
    * The smell carries ``smell_kind="security"`` (set by
      ``_check_security_smells`` once N7 stripped the ``security:``
      prefix from ``type``).
    * The ``type`` still uses the legacy ``security:<name>`` prefix
      — kept as a fallback in case a downstream caller injects smells
      via the old shape.

    Either way we then verify ``(line, normalized_type)`` exists in
    ``security_keys`` so we never drop an unrelated smell that happens
    to share a name.
    """
    raw_type = str(pattern.get("type") or pattern.get("id") or "")
    normalized = canonical_smell_type(pattern)
    if pattern.get("smell_kind") == "security":
        return (pattern.get("line"), normalized) in security_keys
    if raw_type.startswith("security:"):
        return (pattern.get("line"), normalized) in security_keys
    return False


def _detect_smells(
    file_path: str, language: str, project_root: str | None = None
) -> list[dict[str, Any]]:
    # ``detect_code_smells`` signature is (file_path, dimensions, analysis,
    # language=None). Build the same tree-sitter analysis that
    # ``file_health_tool`` uses so the AST-driven detectors (long_method,
    # god_class) work for every supported language. Without ``analysis`` the
    # detector falls back to ``find_long_blocks_heuristic`` in
    # ``file_health_blocks`` — which matches only ``def`` / ``async def``
    # prefixes and is therefore Python-only. (Bugs H1 + M5.)
    try:
        analysis = extract_elements(file_path, project_root)
    except Exception:  # nosec B110 — parse failure is non-critical, fall back to heuristic
        analysis = None
    try:
        smells = detect_code_smells(file_path, {}, analysis, language=language)
    except Exception:
        return []

    patterns: list[dict[str, Any]] = []
    for smell in smells:
        # ``detect_code_smells`` emits ``smell``/``detail``/``severity``;
        # also accept the older ``type``/``message`` shape for forward
        # compatibility.
        smell_id = smell.get("smell") or smell.get("type") or smell.get("id", "unknown")
        # N7 (round-28): normalize the canonical type so security mirrors
        # come through as ``eval_usage`` rather than ``security:eval_usage``.
        # That matches the bare name ``_detect_security`` emits and lets
        # cross-tool consumers branch on a single string.
        canonical = canonical_smell_type(smell)
        # N7 (round-28): file_health's ``detect_code_smells`` now emits
        # anti-pattern findings as smells so ``code_smells`` matches what
        # code_patterns sees. Inside code_patterns the dedicated
        # ``_detect_anti_patterns`` pass produces the same findings under
        # the canonical ``category=anti_patterns`` namespace — keeping
        # the smell mirror as well would double-count every
        # ``mutable_default_argument`` / ``bare_except`` /
        # ``print_in_production`` line. Drop the smell mirror here; the
        # anti_patterns pass remains the canonical surface.
        if smell.get("smell_kind") == "anti_pattern":
            continue
        detail = smell.get("detail") or smell.get("message", "")
        fix_hint = smell.get("fix", "")
        message = (
            f"{detail} ({fix_hint})" if fix_hint and detail else (detail or fix_hint)
        )
        sev_raw = smell.get("severity", "info")
        sev = (
            "critical"
            if sev_raw == "critical" or smell.get("critical")
            else ("warning" if sev_raw in ("warning", "major") else "info")
        )
        emitted: dict[str, Any] = {
            "id": smell_id,
            "category": "smells",
            "type": canonical,
            "severity": sev,
            "message": message,
            "line": smell.get("line"),
        }
        # Forward the smell_kind so ``_dedup_security_mirror`` knows
        # this entry came from the security pass even though the name
        # no longer carries the legacy prefix.
        smell_kind = smell.get("smell_kind")
        if smell_kind:
            emitted["smell_kind"] = smell_kind
        patterns.append(emitted)
    return patterns


def _detect_security(file_path: str, language: str) -> list[dict[str, Any]]:
    # ``detect_security_issues`` wants the file *content* as ``source``;
    # passing the path string would silently match nothing. Read with
    # ``errors="replace"`` so binary noise can't crash the call.
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    try:
        issues = detect_security_issues(source, language, file_path=file_path)
    except Exception:
        return []

    patterns: list[dict[str, Any]] = []
    for issue in issues:
        # ``detect_security_issues`` returns ``issue``/``description``/``lines``;
        # normalize to the same shape the rest of code_patterns emits.
        issue_name = (
            issue.get("issue") or issue.get("type") or issue.get("id", "unknown")
        )
        lines = issue.get("lines") or []
        first_line = lines[0] if lines else issue.get("line")
        severity_raw = issue.get("severity", "warning")
        severity = "critical" if severity_raw == "critical" else "warning"
        patterns.append(
            {
                "id": issue_name,
                "category": "security",
                "type": issue_name,
                "severity": severity,
                "message": issue.get("description", issue.get("message", "")),
                "line": first_line,
            }
        )
    return patterns


def _detect_anti_patterns(file_path: str, language: str) -> list[dict[str, Any]]:
    """Wrap shared ``detect_anti_patterns`` and stamp ``category=anti_patterns``.

    N7 (round-28): the actual detection lives in
    ``tree_sitter_analyzer.mcp.tools.utils.anti_patterns`` so both
    ``code_patterns`` and ``file_health`` produce the same findings on
    the same file. We only wrap the bare results with the category
    tag the rest of ``code_patterns`` expects.
    """
    return [
        {**issue, "category": "anti_patterns"}
        for issue in detect_anti_patterns(file_path, language)
    ]


def _build_summary(patterns: list[dict[str, Any]]) -> str:
    if not patterns:
        return "No patterns detected."

    critical = sum(1 for p in patterns if p["severity"] == "critical")
    warning = sum(1 for p in patterns if p["severity"] == "warning")
    info = sum(1 for p in patterns if p["severity"] == "info")

    parts: list[str] = []
    if critical:
        parts.append(f"{critical} critical")
    if warning:
        parts.append(f"{warning} warning")
    if info:
        parts.append(f"{info} info")

    return f"Patterns: {', '.join(parts)}. Total: {len(patterns)}."


def _empty_file_response(
    resolved: str, file_path: str, output_format: str
) -> dict[str, Any] | None:
    """Pol2 (round-21): mirror ``file_health_tool._empty_file_response``.

    Returns ``None`` when the caller should continue with normal scanning;
    otherwise returns a fully-formatted n/a envelope (already passed
    through the TOON formatter).

    Empty / whitespace-only files have no signal for any of the smell,
    security, or anti-pattern detectors. Reporting ``verdict=SAFE`` on
    such a file is true-but-misleading: callers chain ``verdict`` with
    ``file_health.signal`` to decide whether to edit, and the two tools
    were disagreeing about the same input. Aligning on
    ``signal=empty_file`` + ``verdict=N/A`` lets agents take one branch.
    """
    detail = "empty (0 bytes)"
    try:
        size = Path(resolved).stat().st_size
    except OSError:
        return None
    if size == 0:
        pass  # fall through to the n/a envelope below
    else:
        # Match the H9 widening: whitespace-only files behave like empty.
        try:
            text = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if text.strip():
            return None
        detail = f"whitespace-only ({size} bytes)"

    summary_line = " ".join(
        [
            file_path,
            "0 patterns",
            "critical=0",
            "warning=0",
            "signal=empty_file",
        ]
    )
    response: dict[str, Any] = {
        "success": True,
        "file_path": file_path,
        "language": None,
        "verdict": "N/A",
        "signal": "empty_file",
        "total_patterns": 0,
        # J13 (round-22): ``patterns`` removed as a duplicate of
        # ``results``. Empty file gives an empty list under the
        # canonical key.
        "count": 0,
        "results": [],
        "by_category": {},
        "critical_count": 0,
        "warning_count": 0,
        "summary": f"File is {detail}; nothing to detect.",
        "smart_workflow_hint": (
            f"File is {detail}; no patterns can be detected. Skip."
        ),
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": "skip",
            "verdict": "N/A",
        },
    }
    return apply_toon_format_to_response(response, output_format)


def _syntax_error_response(
    resolved: str,
    file_path: str,
    language: str | None,
    output_format: str,
) -> dict[str, Any] | None:
    """M3 (round-26): short-circuit when tree-sitter reports a syntax error.

    Returns ``None`` when the file parses cleanly (caller continues with
    normal smell / security / anti-pattern detection). Otherwise returns
    a fully-formatted envelope that mirrors the empty/whitespace
    branches in structure but uses ``verdict=ERROR signal=syntax_error``
    so cross-tool consumers can distinguish "couldn't analyse" from
    "analysed and clean".
    """
    # No language → either non-code or unknown extension; the existing
    # caller handles those via downstream detectors (which mostly return
    # empty lists). We don't claim "syntax error" without a known
    # grammar to check against.
    if not language or language == "unknown":
        return None
    if not is_file_parse_broken(resolved, language):
        return None
    summary_line = f"{file_path} signal=syntax_error verdict=ERROR"
    response: dict[str, Any] = {
        "success": True,
        "file_path": file_path,
        "language": language,
        "verdict": "ERROR",
        "signal": "syntax_error",
        "total_patterns": 0,
        "count": 0,
        "results": [],
        "by_category": {},
        "critical_count": 0,
        "warning_count": 0,
        "summary": (
            "File fails to parse — tree-sitter reported syntax errors. "
            "Fix syntax before running pattern detection."
        ),
        "smart_workflow_hint": (
            "Fix syntax errors first; pattern detection is meaningless on a broken AST."
        ),
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": ("file fails to parse — fix syntax before further analysis"),
            "verdict": "ERROR",
            "risk": "high",
        },
    }
    return apply_toon_format_to_response(response, output_format)
