"""Bounded projection, paging and continuation handles (RFC-0041 §4).

The default (``detail="compact"``) is the smallest sufficient answer: one
string per row, per-stage counts and coverage, and — only for inputs whose
coverage was not ``complete`` — a ready-to-call ``nav`` request that drills
into the producer's full evidence. ``detail="full"`` returns structured rows
with provenance and every examined input.

Rows are paged across groups in output order. A cursor is stateless: it pins
the query text and the source generation, and the next page re-executes the
query (no server-side result retention). A cursor from another query is
rejected; one from another generation is stale.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from .coverage import (
    CURSOR_GENERATION_UNVERIFIED,
    INCOMPLETE,
    UPSTREAM_INCOMPLETE,
    UPSTREAM_UNKNOWN,
    Coverage,
    gap,
    with_upstream,
)
from .engine import Execution, Group
from .errors import INVALID_CURSOR, STALE_CURSOR, Err, Ok, QueryError, Result
from .relations import Row

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
_EVIDENCE_HANDLES = 3
_CURSOR_PREFIX = "uql1:"


@dataclass(frozen=True)
class PageRequest:
    offset: int = 0
    generation: str | None = None
    cursor_given: bool = False


def canonical(query: Any) -> str:
    """查询身份：解析后 IR 的规范形式（与答案缓存键一致，Codex #1801）。

    同一 IR 的两种写法共享缓存条目，因此游标也必须按 IR 而非原文绑定，否则
    命中缓存的另一写法续页会被判为“别的查询”。
    """
    return repr(query.stages)


def query_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _generation_tag(generation: str | None) -> str | None:
    if generation is None:
        return None
    return hashlib.sha256(generation.encode("utf-8")).hexdigest()[:16]


def encode_cursor(text: str, offset: int, generation: str | None) -> str:
    payload = {"q": query_digest(text), "o": offset, "g": _generation_tag(generation)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return _CURSOR_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: Any, text: str) -> Result[PageRequest]:
    bad = QueryError(
        INVALID_CURSOR,
        "cursor is malformed or belongs to a different query",
        suggestion="Resend the same query with the next_cursor it returned, or omit cursor.",
    )
    if not isinstance(cursor, str) or not cursor.startswith(_CURSOR_PREFIX):
        return Err(bad)
    body = cursor[len(_CURSOR_PREFIX) :]
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return Err(bad)
    if not isinstance(payload, dict) or payload.get("q") != query_digest(text):
        return Err(bad)
    offset = payload.get("o")
    generation = payload.get("g")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        return Err(bad)
    if generation is not None and not isinstance(generation, str):
        return Err(bad)
    return Ok(PageRequest(offset, generation, True))


def check_generation(
    request: PageRequest, current: str | None
) -> Result[Coverage | None]:
    """Stale cursor -> error; unverifiable continuation -> a coverage gap."""
    if not request.cursor_given:
        return Ok(None)
    if request.generation is not None and current is not None:
        if request.generation != _generation_tag(current):
            return Err(
                QueryError(
                    STALE_CURSOR,
                    "the source changed since this cursor was issued",
                    suggestion="Re-run the query without cursor to page a consistent answer.",
                )
            )
        return Ok(None)
    return Ok(gap(INCOMPLETE, CURSOR_GENERATION_UNVERIFIED))


def _label(row: Row) -> str:
    name = f"{row.cls}.{row.name}" if row.cls else row.name
    where = f"{row.file}:{row.line}" if row.line else row.file
    text = f"{where} {name}"
    return text + " ?" if row.membership == "unknown" else text


def _full(row: Row) -> dict[str, Any]:
    out = {k: v for k, v in row.__dict__.items() if v is not None}
    if "cls" in out:
        out["class"] = out.pop("cls")
    return out


def _output_groups(execution: Execution) -> list[tuple[str, list[Row]]]:
    out: list[tuple[str, list[Row]]] = []
    for group in execution.groups:
        if group.files is not None:  # impact: callers, tests
            out.append((group.name, [r for r in group.rows if r.role != "test"]))
            out.append(
                (f"{group.name}.tests", [r for r in group.rows if r.role == "test"])
            )
        else:
            out.append((group.name, group.rows))
    return out


def _reasons(execution: Execution) -> list[str]:
    reasons: list[str] = []
    for report in execution.stages:
        for code in report.own.reasons:
            item = f"{report.op}:{code}"
            if item not in reasons:
                reasons.append(item)
    return reasons


def project(
    execution: Execution,
    *,
    limit: int,
    page: PageRequest,
    generation: str | None,
    extra_gap: Coverage | None,
    detail: str,
) -> dict[str, Any]:
    groups = _output_groups(execution)
    flat = [(name, row) for name, rows in groups for row in rows]
    total = len(flat)
    window = flat[page.offset : page.offset + limit]
    results: dict[str, list[Any]] = {name: [] for name, _ in groups}
    for name, row in window:
        results[name].append(_full(row) if detail == "full" else _label(row))
    next_offset = page.offset + len(window)
    next_cursor = (
        encode_cursor(canonical(execution.query), next_offset, generation)
        if next_offset < total
        else None
    )
    coverage = execution.total
    if extra_gap is not None:
        coverage = with_upstream(extra_gap, coverage)
    reasons = _reasons(execution)
    if extra_gap is not None:
        reasons += [f"page:{r}" for r in extra_gap.reasons]
    payload: dict[str, Any] = {
        "success": True,
        "verdict": "INFO" if total else "NOT_FOUND",
        "query": execution.query.text,
        "completeness": coverage.status,
        "completeness_reasons": reasons,
        "stages": [_stage(r, detail) for r in execution.stages],
        "results": results,
        "page": {
            "offset": page.offset,
            "returned": len(window),
            "total": total,
            "next_cursor": next_cursor,
        },
    }
    files = [g for g in execution.groups if g.files is not None]
    if files:
        payload["files"] = files[-1].files
    handles = _handles(execution)
    if handles and detail != "full":
        payload["evidence"] = handles
    if detail == "full":
        payload["indexed_files"] = execution.indexed_files
    payload["agent_summary"] = _summary(
        execution, coverage, total, next_cursor, handles
    )
    return payload


def _stage(report: Any, detail: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "op": report.op,
        "n": report.count,
        "c": report.effective.status,
    }
    own = [
        r
        for r in report.effective.reasons
        if r not in (UPSTREAM_INCOMPLETE, UPSTREAM_UNKNOWN)
    ]
    if own:
        out["r"] = own
    if report.note:
        out["note"] = report.note
    if detail == "full" and report.evidence:
        out["inputs"] = report.evidence
    return out


def _handles(execution: Execution) -> list[dict[str, Any]]:
    """Ready-to-call drill-downs for the first non-complete examined inputs."""
    out: list[dict[str, Any]] = []
    for report in execution.stages:
        for item in report.evidence:
            if item.get("completeness") != "complete":
                out.append(
                    {"stage": report.op, "nav": item["nav"], "r": item.get("reasons")}
                )
                if len(out) >= _EVIDENCE_HANDLES:
                    return out
    return out


def _summary(
    execution: Execution,
    coverage: Coverage,
    total: int,
    next_cursor: str | None,
    handles: list[dict[str, Any]],
) -> dict[str, Any]:
    parts = [
        f"{r.op} {r.count}" for r in execution.stages if r.op not in ("take", "sort")
    ]
    line = f"uql: {' -> '.join(parts)} ({coverage.status})"
    if coverage.complete:
        step = "Answer is complete for every stage."
    else:
        gap_stage = next(
            (r for r in execution.stages if not r.own.complete), execution.stages[-1]
        )
        first = (
            gap_stage.own.reasons[0] if gap_stage.own.reasons else coverage.reasons[0]
        )
        step = (
            f"Not a census: stage {gap_stage.op} reports {first}. Treat counts as "
            "lower bounds (incomplete) or unproven (unknown)."
        )
        if handles:
            step += " Drill in with the nav request under evidence[], or detail='full'."
    if next_cursor:
        step += " More rows: resend the same query with cursor=page.next_cursor."
    verdict = "INFO" if total else "NOT_FOUND"
    return {"summary_line": line, "verdict": verdict, "next_step": step}


def error_payload(error: QueryError, query: Any) -> dict[str, Any]:
    detail = error.to_dict()
    next_step = error.suggestion or "Fix the query and retry."
    if error.fixed_query:
        next_step += f" Corrected query: {error.fixed_query}"
    return {
        "success": False,
        "verdict": "ERROR",
        "error_code": error.code,
        "error": error.message,
        "error_detail": detail,
        "query": query if isinstance(query, str) else None,
        "completeness": "unknown",
        "agent_summary": {
            "summary_line": f"uql: {error.code}",
            "verdict": "ERROR",
            "next_step": next_step,
        },
    }


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "Group",
    "PageRequest",
    "check_generation",
    "decode_cursor",
    "encode_cursor",
    "error_payload",
    "project",
    "replace",
]
