#!/usr/bin/env python3
"""Shared symbol-body inlining — coordinates -> content + deterrent (P2).

``call_path`` proved the turn-saving trade-off: inlining the *verbatim source
body* next to a symbol's coordinates eliminates the follow-up ``Read`` per
``file:line`` that an agent would otherwise issue.  An agent's real cost is
``turns x tokens-per-turn``; paying once for a (bigger) inlined response is
cheaper than N downstream Read turns.

P2 generalises that mechanism to the tools agents actually reach for first when
exploring an unfamiliar codebase:

  - ``nav navigate``  — inline the definition body (full tier).
  - ``nav callers`` / ``nav callees`` — inline each neighbour's body (neighbour
    tier, capped to the top-N neighbours so a 1000-caller fan-out can't blow up
    the response).
  - ``search symbol`` — inline a short body summary for each top match (summary
    tier) so the agent judges relevance from content, not coordinates.

Three cap tiers keep big-Java responses bounded.  Long bodies are truncated and
flagged with ``full_at`` ``file:line`` so the agent can still Read on demand.

The low-level ``_build_def_index`` / ``_resolve_def`` / ``_read_body``
primitives are reused from :mod:`call_path_enrich` so there is a single
implementation of the def-index scan and the verbatim-read-with-caps logic.
"""

from __future__ import annotations

from typing import Any

from .call_path_enrich import _build_def_index, _read_body, _resolve_def

# ---------------------------------------------------------------------------
# Cap tiers — bound the single (intentionally larger) response per use-case.
# ---------------------------------------------------------------------------

#: Max source lines for a single go-to-definition body (nav navigate).
MAX_DEFINITION_LINES = 80
#: Max source lines per caller/callee body (nav callers / nav callees).
MAX_NEIGHBOR_LINES = 40
#: Max source lines per search-match body summary (search symbol).
MAX_SUMMARY_LINES = 30

#: Max neighbours that get an inlined body before falling back to coordinates.
MAX_NEIGHBOR_BODIES = 12
#: Max search matches that get an inlined body summary.
MAX_SUMMARY_BODIES = 8

#: Total source-line budget shared across all bodies in one response.
MAX_TOTAL_DEFINITION_LINES = 160
MAX_TOTAL_NEIGHBOR_LINES = 320
MAX_TOTAL_SUMMARY_LINES = 200


# ---------------------------------------------------------------------------
# Span resolution — prefer the record's own end_line, else def-index lookup.
# ---------------------------------------------------------------------------


def _record_span(
    record: dict[str, Any],
    cache: Any,
) -> dict[str, Any] | None:
    """Return a ``{name,file,line,end_line,class}`` def-span for ``record``.

    Records from navigate definitions / search results already carry
    ``end_line``; caller/callee records carry only ``name``/``file``/``line``,
    so their span is resolved through the AST-index def-index (targeted scan,
    name-filtered — never materialises the full symbol set).  Returns ``None``
    when neither path yields a usable span.
    """
    name = record.get("name") or ""
    file_hint = record.get("file") or None
    line = int(record.get("line", 0) or 0)
    if not name or line < 1:
        return None

    end_line = int(record.get("end_line", 0) or 0)
    if end_line >= line:
        return {
            "name": name,
            "file": record.get("file", ""),
            "line": line,
            "end_line": end_line,
            "class": record.get("class"),
        }

    # No usable end_line — resolve via the def-index (cap to this one name).
    index = _build_def_index(cache, {name})
    defn = _resolve_def(index, name, file_hint)
    if defn is None:
        return None
    return {**defn, "name": name}


def _body_for_record(
    project_root: str,
    cache: Any,
    record: dict[str, Any],
    per_body_cap: int,
    budget: list[int],
) -> dict[str, Any] | None:
    """Read one verbatim body for ``record`` honouring per-body + total caps."""
    span = _record_span(record, cache)
    if span is None:
        return None
    return _read_body(project_root, span, budget, max_body_lines=per_body_cap)


# ---------------------------------------------------------------------------
# Public API — one helper per tool surface
# ---------------------------------------------------------------------------


def inline_symbol_body(
    project_root: str,
    cache: Any,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    """Inline a single definition body (full tier) for ``nav navigate``.

    Returns a body block ``{name,file,start_line,end_line,content,...}`` or
    ``None`` when the body can't be read.  Long bodies are truncated and
    flagged with ``full_at`` so the agent can Read the remainder on demand.
    """
    budget = [MAX_TOTAL_DEFINITION_LINES]
    return _body_for_record(project_root, cache, record, MAX_DEFINITION_LINES, budget)


def inline_neighbor_bodies(
    project_root: str,
    cache: Any,
    neighbors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach a body (neighbour tier) to the top-N caller/callee records.

    Each record is returned as a *new* dict (immutable — never mutates the
    input) with a ``body`` key for the first ``MAX_NEIGHBOR_BODIES`` entries
    that resolve; the remaining entries pass through coordinate-only.  The
    total-line budget is shared so a deep fan-out still can't blow the cap.
    """
    budget = [MAX_TOTAL_NEIGHBOR_LINES]
    out: list[dict[str, Any]] = []
    bodied = 0
    for record in neighbors:
        new_record = dict(record)
        if bodied < MAX_NEIGHBOR_BODIES and budget[0] > 0:
            body = _body_for_record(
                project_root, cache, record, MAX_NEIGHBOR_LINES, budget
            )
            if body is not None:
                new_record["body"] = body
                bodied += 1
        out.append(new_record)
    return out


def inline_search_summaries(
    project_root: str,
    cache: Any,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach a short body summary (summary tier) to the top search matches.

    Returns new dicts (immutable) with a ``body`` key on the first
    ``MAX_SUMMARY_BODIES`` matches that resolve.  The summary tier is the
    smallest (``MAX_SUMMARY_LINES``) so a 50-match search stays bounded while
    still giving the agent enough content to judge relevance without a Read.
    """
    budget = [MAX_TOTAL_SUMMARY_LINES]
    out: list[dict[str, Any]] = []
    bodied = 0
    for record in results:
        new_record = dict(record)
        if bodied < MAX_SUMMARY_BODIES and budget[0] > 0:
            body = _body_for_record(
                project_root, cache, record, MAX_SUMMARY_LINES, budget
            )
            if body is not None:
                new_record["body"] = body
                bodied += 1
        out.append(new_record)
    return out


#: Deterrent ``next_step`` strings — tell the agent it already has the content.
NAVIGATE_DETERRENT = (
    "Definition body inlined below — answer directly, no Read needed. "
    "Truncated bodies carry full_at file:line for on-demand Read only if needed."
)
NEIGHBORS_DETERRENT = (
    "Each caller/callee's source body is inlined under 'body' — answer "
    "directly, no Read needed. Coordinate-only entries beyond the top-N can be "
    "Read on demand."
)
SEARCH_DETERRENT = (
    "Top matches carry an inlined source body — judge relevance from 'body', "
    "no Read needed. Use codegraph_explore for broader concept matches."
)
