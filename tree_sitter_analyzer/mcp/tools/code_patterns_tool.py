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
from .utils.element_extractor import extract_elements
from .utils.file_health_smells import detect_code_smells
from .utils.parse_validity import is_file_parse_broken

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
        file_path = arguments["file_path"]
        categories = arguments.get("categories", ["all"])
        severity_threshold = arguments.get("severity_threshold", "info")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved).is_file():
            raise ValueError(f"Not a file: {file_path}")

        # Pol2 (round-21): mirror ``file_health_tool`` and short-circuit on
        # empty / whitespace-only files. Running the smell + security passes
        # against zero bytes produces a true-but-misleading verdict=SAFE
        # — "you have 0 patterns" reads as "this file is clean to ship"
        # even though there is nothing to ship. ``file_health`` already
        # returns ``signal=empty_file``; aligning the two tools lets agents
        # branch on a single signal instead of reconciling cross-tool drift.
        empty_response = _empty_file_response(resolved, file_path, output_format)
        if empty_response is not None:
            return empty_response

        min_sev = _SEVERITY_ORDER.get(severity_threshold, 0)

        from ...language_detector import detect_language_from_file

        language = detect_language_from_file(resolved, project_root=self.project_root)

        # M3 (round-26 dogfood): a file containing only ``def broken(:`` used
        # to be graded ``SAFE``. tree-sitter is permissive — it sprinkles
        # ``ERROR`` nodes through the tree but still hands back a "result",
        # so every downstream detector ran against garbled output and
        # reported zero findings. An agent reading that envelope would
        # happily "proceed with planned change" on a broken file. The
        # syntax gate short-circuits before any smell/pattern/security
        # detector runs and pins ``verdict=ERROR signal=syntax_error`` so
        # all three syntax-gated tools (code_patterns, file_health,
        # safe_to_edit) agree on the same envelope.
        syntax_response = _syntax_error_response(
            resolved, file_path, language, output_format
        )
        if syntax_response is not None:
            return syntax_response

        all_patterns: list[dict[str, Any]] = []

        scan_all = "all" in categories

        if scan_all or "smells" in categories:
            all_patterns.extend(_detect_smells(resolved, language, self.project_root))

        if scan_all or "security" in categories:
            all_patterns.extend(_detect_security(resolved, language))

        if scan_all or "anti_patterns" in categories:
            all_patterns.extend(_detect_anti_patterns(resolved, language))

        # G4 dedup: ``_detect_smells`` already re-emits security issues via
        # ``_check_security_smells`` (so ``file_health`` users see them). When
        # ``_detect_security`` also runs, the same finding shows up twice —
        # once under ``smells`` with id ``security:<name>``, once under
        # ``security`` with id ``<name>``. Drop the ``smells`` mirror; keep
        # the ``security``-namespaced entry as the canonical record. This
        # only fires when the same ``(line, normalized_type)`` is present
        # under both categories, so non-security smells are unaffected.
        all_patterns = _dedup_security_mirror(all_patterns)

        filtered = [
            p
            for p in all_patterns
            if _SEVERITY_ORDER.get(p.get("severity"), 0) >= min_sev
        ]
        filtered.sort(
            key=lambda p: _SEVERITY_ORDER.get(p.get("severity"), 0), reverse=True
        )

        by_category: dict[str, list[dict[str, Any]]] = {}
        for p in filtered:
            cat = p["category"]
            by_category.setdefault(cat, []).append(p)

        critical_count = sum(1 for p in filtered if p.get("severity") == "critical")
        warning_count = sum(1 for p in filtered if p.get("severity") == "warning")

        # One-line headline an LLM (or grep) can read at a glance.
        # Pol1 (round-21): build via ``" ".join`` over a parts list so an
        # empty segment can never re-introduce the double-space we shipped
        # in round-20 (``"... patterns  critical=..."``). Any downstream
        # regex that splits on a single space stays correct.
        summary_line = " ".join(
            [
                file_path,
                f"{len(filtered)} patterns",
                f"critical={critical_count}",
                f"warning={warning_count}",
            ]
        )
        # Verdict mirrors the safety-tool vocabulary so callers can chain.
        if critical_count:
            verdict = "UNSAFE"
            next_step = "refactoring_suggestions for concrete fix recipes — start with critical findings"
        elif warning_count:
            verdict = "CAUTION"
            next_step = "refactoring_suggestions or address warnings before shipping"
        else:
            verdict = "SAFE"
            next_step = "no patterns flagged — proceed with planned change"

        response: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "language": language,
            "total_patterns": len(filtered),
            # ``count`` and ``results`` are cross-tool canonical aliases —
            # every search/scan tool emits a top-level ``count`` (int) and
            # a list under ``results``. Mirror the same names here so an
            # agent walking generic envelopes doesn't have to know each
            # tool's nickname.
            #
            # J13 (round-22): the legacy ``patterns`` key duplicated
            # ``results`` byte-for-byte (pure token waste in TOON output).
            # Removed in favour of the canonical ``results`` list. If a
            # caller still depends on ``patterns``, switch it to
            # ``results``.
            "count": len(filtered),
            "results": filtered[:50],
            "by_category": {k: len(v) for k, v in by_category.items()},
            "critical_count": critical_count,
            "warning_count": warning_count,
            "summary": _build_summary(filtered),
            "smart_workflow_hint": (
                f"Found {len(filtered)} pattern(s) in {file_path}. "
                + (
                    "Critical issues found — fix these first. "
                    if critical_count
                    else "Review warnings and decide which to address. "
                )
                + "Use refactoring_suggestions for concrete fix recipes."
            ),
            "summary_line": summary_line,
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": verdict,
            },
        }

        # M10 (round-26): mirror ``agent_summary.verdict`` to the top
        # level so chained agents reading either surface see the same
        # answer. code_patterns historically only set the agent-side
        # value; ``mirror_summary_line`` now copies it to the top.
        response = mirror_summary_line(response)
        return apply_toon_format_to_response(response, output_format)


def _dedup_security_mirror(
    patterns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate findings across smell / security / anti-pattern passes.

    Two dedup passes happen here, in this order:

    1) ``smells`` mirror of a security finding (original G4 behaviour).
       ``file_health_smells.detect_code_smells`` re-emits security issues
       under the smell namespace (id ``security:<name>``) so that
       file-health reports can surface them as a single signal. When
       ``code_patterns`` *also* runs the dedicated security pass, the
       same underlying finding appears twice: once with category
       ``smells`` and id ``security:sql_injection``, once with category
       ``security`` and id ``sql_injection``. The second one is the
       canonical record, so we drop the smell-namespaced mirror whenever
       a matching ``(line, security-name)`` exists under the
       ``security`` category.

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
            if pattern.get("category") == "smells":
                raw_type = str(pattern.get("type") or pattern.get("id") or "")
                if raw_type.startswith("security:"):
                    normalized = raw_type.split(":", 1)[1]
                    if (pattern.get("line"), normalized) in security_keys:
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
        patterns.append(
            {
                "id": smell_id,
                "category": "smells",
                "type": smell_id,
                "severity": sev,
                "message": message,
                "line": smell.get("line"),
            }
        )
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
    patterns: list[dict[str, Any]] = []

    try:
        content = Path(file_path).read_text(errors="replace")
    except Exception:
        return patterns

    lines = content.splitlines()

    if language == "python":
        _check_python_anti_patterns(lines, patterns)
    elif language in ("javascript", "typescript"):
        _check_js_anti_patterns(lines, patterns)
    elif language == "java":
        _check_java_anti_patterns(lines, patterns)

    return patterns


def _python_docstring_line_set(lines: list[str]) -> set[int]:
    # Return the 1-indexed line numbers that fall inside a Python triple-quoted
    # string. We skip these lines when checking anti-patterns so that docstring
    # examples (which often contain ``print()``, bare ``except:``, etc.) do not
    # produce false positives.
    #
    # Implementation is intentionally line-based (not AST-based) because the
    # caller only has access to the raw text. It handles single-line triple
    # quotes and multi-line blocks but does not track nested strings or
    # escapes — sufficient for anti-pattern muting.
    inside = False
    delim: str | None = None
    docstring_lines: set[int] = set()
    for i, line in enumerate(lines, 1):
        if inside:
            docstring_lines.add(i)
            # Closing delim found — exit (assume single closing per line).
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
                # Opens here but does not close on the same line.
                inside = True
                delim = d
            break
    return docstring_lines


def _check_python_anti_patterns(
    lines: list[str], patterns: list[dict[str, Any]]
) -> None:
    docstring_lines = _python_docstring_line_set(lines)
    for i, line in enumerate(lines, 1):
        if i in docstring_lines:
            continue
        stripped = line.strip()

        if "=" in stripped and any(
            f"={t}" in stripped for t in ("[]", "{},", "set()", "[],")
        ):
            if "def " in lines[max(0, i - 5) : i][-1] or any(
                "def " in ln for ln in lines[max(0, i - 10) : i]
            ):
                patterns.append(
                    {
                        "id": "AP001",
                        "category": "anti_patterns",
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
                    "category": "anti_patterns",
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
                        "category": "anti_patterns",
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
                    "category": "anti_patterns",
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
                        "category": "anti_patterns",
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
                    "category": "anti_patterns",
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
                    "category": "anti_patterns",
                    "type": "print_stacktrace",
                    "severity": "warning",
                    "message": "Use proper logging instead of printStackTrace()",
                    "line": i,
                }
            )


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
