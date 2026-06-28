"""Lineage formatter helpers — Phase 3 REQ-CLEAN-001.

Contains response formatting, risk assessment, definition classification,
and scope filtering for SymbolLineageTool.

Functions:
    _build_truncations_and_summary_line
    _build_agent_summary_block
    _verdict_and_next_step
    _is_definition_like
    _line_looks_like_definition
    _reclassify_definition_like
    _assess_risk
    _normalize_scope_file_paths
    _filter_references_to_scope
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Response envelope caps (G6 truncation transparency).
_DEF_LIMIT = 20
_REF_LIMIT = 30
_DOWNSTREAM_LIMIT = 50
_UPSTREAM_LIMIT = 20
_TEST_LIMIT = 20
_HIER_LIMIT = 50

# Risk level → verdict mapping (canonical vocab per CLAUDE.md).
_RISK_TO_VERDICT: dict[str, str] = {
    "high": "CAUTION",
    "medium": "REVIEW",
    "low": "INFO",
    "unknown": "NOT_FOUND",
}

# H12: element_type values that mean "this hit IS the symbol's definition site".
_DEFINITION_LIKE_TYPES: tuple[str, ...] = (
    "function",
    "method",
    "constructor",
    "decorated_definition",
    "arrow_function",
    "function_declaration",
    "method_declaration",
    "function_definition",
    "method_definition",
    "class",
    "class_declaration",
    "class_definition",
    "struct",
    "struct_declaration",
    "interface",
    "interface_declaration",
    "enum",
    "enum_declaration",
    "definition",
    "declaration",
    "trait",
    "impl_item",
)

# Source-line prefixes that indicate a definition site.
_DEFINITION_LINE_PREFIXES: tuple[str, ...] = (
    "def ",
    "async def ",
    "class ",
    "function ",
    "function* ",
    "async function ",
    "func ",
    "fn ",
    "struct ",
    "interface ",
    "trait ",
    "enum ",
    "type ",
    "public ",
    "private ",
    "protected ",
    "static ",
    "abstract ",
    "@",
)


def _build_truncations_and_summary_line(
    symbol: str,
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    downstream_files: set[str],
    risk: dict[str, Any],
) -> tuple[list[str], str]:
    """G6: compose the truncation list + the headline summary_line."""
    truncations: list[str] = []
    if len(references) > _REF_LIMIT:
        truncations.append("references")
    if len(downstream_files) > _DOWNSTREAM_LIMIT:
        truncations.append("downstream_files")
    summary_line = (
        f"{symbol} defs={len(definitions)} refs={len(references)} "
        f"downstream={len(downstream_files)} risk={risk['level']}"
    )
    if truncations:
        summary_line += f" truncated={'+'.join(truncations)}"
    return truncations, summary_line


def _verdict_and_next_step(risk_level: str) -> tuple[str, str]:
    """Map a risk level to (verdict, next_step) per the lineage contract."""
    verdict = _RISK_TO_VERDICT.get(risk_level, "NOT_FOUND")
    if risk_level == "high":
        next_step = "trace_impact and run listed test files before changing signature"
    elif risk_level == "medium":
        next_step = "review callers in listed files, then run downstream tests"
    elif risk_level == "low":
        next_step = "proceed with edit, run nearest test file"
    else:
        next_step = "verify symbol name — no definitions found"
    return verdict, next_step


def _normalize_scope_file_paths(project_root: str, file_paths: list[Any]) -> set[str]:
    root = Path(project_root).resolve()
    normalized: set[str] = set()
    for raw_path in file_paths:
        if not raw_path:
            continue
        path = Path(str(raw_path))
        try:
            rel = path.resolve().relative_to(root) if path.is_absolute() else path
        except ValueError:
            rel = path
        rel_text = str(rel).replace("\\", "/")
        normalized.add(rel_text[2:] if rel_text.startswith("./") else rel_text)
    return normalized


def _filter_references_to_scope(
    references: list[dict[str, Any]],
    scope_files: set[str],
) -> list[dict[str, Any]]:
    if not scope_files:
        return references
    return [
        ref
        for ref in references
        if str(ref.get("file", "")).replace("\\", "/") in scope_files
    ]


def _build_agent_summary_block(
    summary_line: str,
    next_step: str,
    verdict: str,
    truncations: list[str],
) -> dict[str, Any]:
    """Canonical agent_summary block with optional ``truncations`` echo."""
    block: dict[str, Any] = {
        "summary_line": summary_line,
        "next_step": next_step,
        "verdict": verdict,
    }
    if truncations:
        block["truncations"] = truncations
    return block


def _is_definition_like(element_type: str) -> bool:
    """Return ``True`` when ``element_type`` denotes a definition site."""
    if not element_type:
        return False
    lowered = element_type.lower()
    return any(kind in lowered for kind in _DEFINITION_LIKE_TYPES)


def _line_looks_like_definition(
    project_root: str,
    file_rel: str,
    line_no: int,
    symbol: str,
) -> bool:
    """Return ``True`` when the source line at ``line_no`` is a def site."""
    if not file_rel or line_no < 1 or not symbol:
        return False
    try:
        path = Path(project_root) / file_rel
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = text.splitlines()
    if line_no > len(lines):
        return False
    line = lines[line_no - 1]
    stripped = line.lstrip()
    if symbol not in stripped:
        return False
    if any(stripped.startswith(prefix) for prefix in _DEFINITION_LINE_PREFIXES):
        return True
    return False


def _reclassify_definition_like(
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    project_root: str | None = None,
    symbol: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """H12 fix: promote definition-like references into ``definitions``."""
    if not references:
        return definitions, references

    promoted: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    seen_def_keys: set[tuple[str, int]] = {
        (d.get("file", ""), d.get("start_line", 0)) for d in definitions
    }

    for entry in references:
        role = entry.get("role")
        etype = entry.get("type", "")
        if role == "related":
            remaining.append(entry)
            continue
        if not _is_definition_like(etype):
            remaining.append(entry)
            continue
        if project_root and symbol:
            file_rel = entry.get("file", "")
            line_no = entry.get("start_line", 0)
            if not _line_looks_like_definition(project_root, file_rel, line_no, symbol):
                remaining.append(entry)
                continue
        key = (entry.get("file", ""), entry.get("start_line", 0))
        if key in seen_def_keys:
            remaining.append(entry)
            continue
        seen_def_keys.add(key)
        promoted.append(entry)

    new_definitions = list(definitions) + promoted
    return new_definitions, remaining


def _assess_risk(
    def_count: int, ref_count: int, downstream_count: int
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    if def_count == 0:
        return {"level": "unknown", "score": 0, "reasons": ["Symbol not found"]}

    if def_count > 1:
        score += 1
        reasons.append(f"Multiple definitions ({def_count})")

    if ref_count > 20:
        score += 3
        reasons.append(f"Many references ({ref_count})")
    elif ref_count > 5:
        score += 2
        reasons.append(f"Moderate references ({ref_count})")
    elif ref_count > 0:
        score += 1
        reasons.append(f"Few references ({ref_count})")

    if downstream_count > 10:
        score += 3
        reasons.append(f"Wide blast radius ({downstream_count} downstream files)")
    elif downstream_count > 3:
        score += 2
        reasons.append(f"Moderate blast radius ({downstream_count} downstream files)")
    elif downstream_count > 0:
        score += 1
        reasons.append(f"Small blast radius ({downstream_count} downstream files)")

    if score <= 2:
        level = "low"
    elif score <= 5:
        level = "medium"
    else:
        level = "high"

    return {"level": level, "score": score, "reasons": reasons}
