#!/usr/bin/env python3
"""Call-path output enrichment — coordinates → content + deterrent.

This module upgrades the ``call_path`` response from bare coordinates
(``{caller, callee, file, line}``) into a self-contained answer that
inlines the *verbatim source body* of every function on the path, plus a
``next_step`` deterrent telling the agent it already has everything.

Rationale (turn-saving trade-off, intentional):
    The bare-coordinate output forces the consuming agent to issue a
    follow-up ``Read`` per ``file:line`` to see the actual code.  An agent's
    real cost is ``turns x tokens-per-turn``; paying once for inlined bodies
    (a bigger single response) eliminates N downstream ``Read`` turns, so the
    total cost drops.  Output is capped (see ``MAX_BODY_LINES`` /
    ``MAX_TOTAL_BODY_LINES``) so the single response stays bounded; truncated
    bodies are flagged with ``file:line`` so the agent can still Read on demand.

Two enrichment paths:
    - Path found:  inline the body of every unique function across all hops.
    - Dead end (no static path — dynamic dispatch / missing edge): inline
      *both endpoints'* bodies and list each endpoint's direct callers/callees,
      mirroring ``codegraph_trace`` dead-end behaviour, so the agent can reason
      about the gap without a single extra call.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from ..._language_family import languages_compatible
from ._codegraph_explore_helpers import extract_snippet_from_lines, read_file_lines

# ---------------------------------------------------------------------------
# Caps — bound the single (intentionally larger) response.
# ---------------------------------------------------------------------------

#: Max source lines inlined per function body before truncation.
MAX_BODY_LINES = 80
#: Max total source lines inlined across the whole response.
MAX_TOTAL_BODY_LINES = 600
#: Max direct neighbours (callers / callees) listed per endpoint on a dead end.
MAX_NEIGHBORS = 12


# ---------------------------------------------------------------------------
# Function-definition index — name -> [definition spans]
# ---------------------------------------------------------------------------


def _build_def_index(cache: Any, names: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Return ``name -> [ {file, line, end_line, language, class} ]`` for ``names``.

    Fast path: a single **indexed** lookup against ``ast_symbol_rows`` (``name``
    is indexed). The previous implementation scanned *every* ``ast_index`` row
    and JSON-parsed each file's symbol blob to find one symbol's span — ~28 ms
    per call on a 1.8k-file repo, and it ran once per body inlined. The indexed
    lookup is ~0.03 ms (≈1000×). Falls back to the JSON scan when
    ``ast_symbol_rows`` is absent (no-FTS5 builds / unit-test fixtures that only
    populate ``ast_index``). Degrades to an empty index on any failure.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    if not names:
        return index
    try:
        conn = cache.get_conn()
    except Exception:
        return index
    try:
        # ``placeholders`` is only a run of ``?,?,?`` bind marks sized to
        # ``names`` — never interpolated data; every value is parameterised via
        # ``tuple(names)``. Canonical SQLite ``IN (?, …)`` pattern, not injection.
        placeholders = ",".join("?" * len(names))
        sql = (  # nosec B608
            "SELECT name, file_path, language, line, end_line "  # nosec B608
            "FROM ast_symbol_rows "
            f"WHERE name IN ({placeholders}) AND kind IN ('function', 'method')"
        )
        rows = conn.execute(sql, tuple(names)).fetchall()
    except sqlite3.OperationalError:
        return _build_def_index_scan(conn, names)
    for row in rows:
        index.setdefault(str(row["name"]), []).append(
            {
                "file": str(row["file_path"]),
                "language": str(row["language"] or ""),
                "line": int(row["line"] or 0),
                "end_line": int(row["end_line"] or 0),
                "class": None,
            }
        )
    # ast_symbol_rows may exist but lack rows for names indexed before the FTS
    # backfill ran (unchanged files skip check_cache_or_read). Fall back to the
    # legacy scan for just those missing names so bodies are still inlined.
    missing = names - index.keys()
    if missing:
        for name, defs in _build_def_index_scan(conn, missing).items():
            index.setdefault(name, defs)
    return index


def _build_def_index_scan(
    conn: Any, names: set[str]
) -> dict[str, list[dict[str, Any]]]:
    """Legacy fallback: scan ``ast_index`` + JSON-parse (no ``ast_symbol_rows``)."""
    index: dict[str, list[dict[str, Any]]] = {}
    try:
        rows = conn.execute(
            "SELECT file_path, language, symbols_json FROM ast_index"
        ).fetchall()
    except Exception:
        return index
    for row in rows:
        try:
            symbols = json.loads(row["symbols_json"]).get("symbols", [])
        except Exception:
            continue
        try:
            row_language = str(row["language"] or "")
        except (IndexError, KeyError):
            row_language = ""
        for sym in symbols:
            name = sym.get("name")
            if name not in names or sym.get("kind") not in ("function", "method"):
                continue
            index.setdefault(name, []).append(
                {
                    "file": row["file_path"],
                    "language": row_language,
                    "line": int(sym.get("line", 0) or 0),
                    "end_line": int(sym.get("end_line", 0) or 0),
                    "class": sym.get("class"),
                }
            )
    return index


def _resolve_def(
    index: dict[str, list[dict[str, Any]]],
    name: str,
    file_hint: str | None,
    lang_hint: str | None = None,
) -> dict[str, Any] | None:
    """Pick the best definition span for ``name``, preferring ``file_hint``.

    When ``lang_hint`` is given, a candidate in a *different* language is never
    returned. The call-site ``file_hint`` is the caller file, so for a callee
    defined elsewhere the exact-file match misses and the fallback would
    otherwise return ``candidates[0]`` regardless of language — that is how a
    Python ``sorted()`` builtin call (no Python def) grabbed a Swift
    ``func sorted`` body. Gate the fallback so an unresolved/builtin call stays
    body-less rather than inlining a foreign-language definition.
    """
    candidates = index.get(name)
    if not candidates:
        return None
    if lang_hint:
        same_lang = [
            cand
            for cand in candidates
            if not cand.get("language")
            or languages_compatible(lang_hint, str(cand.get("language") or ""))
        ]
        if not same_lang:
            return None
        candidates = same_lang
    if file_hint:
        hint = file_hint.replace("\\", "/")
        for cand in candidates:
            if cand["file"].replace("\\", "/") == hint:
                return cand
    return candidates[0]


# ---------------------------------------------------------------------------
# Body extraction with caps
# ---------------------------------------------------------------------------


def _read_body(
    project_root: str,
    defn: dict[str, Any],
    budget: list[int],
    max_body_lines: int | None = None,
) -> dict[str, Any] | None:
    """Read a verbatim function body, honouring per-body and total caps.

    ``budget`` is a single-element mutable list carrying remaining total
    lines so multiple calls share one global cap.  ``max_body_lines`` overrides
    the per-body cap for callers that want a tighter tier (e.g. P2's neighbour
    / summary tiers); it defaults to :data:`MAX_BODY_LINES` so the call_path
    path is unchanged.
    """
    per_body_cap = MAX_BODY_LINES if max_body_lines is None else max_body_lines
    file_path = defn.get("file", "")
    start = int(defn.get("line", 0) or 0)
    if not file_path or start < 1 or budget[0] <= 0:
        return None
    abs_path = (
        file_path if os.path.isabs(file_path) else os.path.join(project_root, file_path)
    )
    lines = read_file_lines(abs_path)
    if not lines:
        return None
    end = int(defn.get("end_line", 0) or 0)
    if end < start:
        end = start + per_body_cap - 1
    span = end - start + 1
    truncated = False
    # Per-body cap.
    if span > per_body_cap:
        end = start + per_body_cap - 1
        truncated = True
    # Total cap.
    allowed = budget[0]
    if (end - start + 1) > allowed:
        end = start + allowed - 1
        truncated = True
    content = extract_snippet_from_lines(lines, start, end)
    if not content:
        return None
    consumed = end - start + 1
    budget[0] = max(0, budget[0] - consumed)
    block: dict[str, Any] = {
        "name": defn.get("name", ""),
        "file": file_path,
        "start_line": start,
        "end_line": min(end, len(lines)),
        "content": content,
    }
    if defn.get("class"):
        block["class"] = defn["class"]
    if truncated:
        block["truncated"] = True
        block["full_at"] = f"{file_path}:{start}"
    return block


# ---------------------------------------------------------------------------
# Path-found enrichment — inline every unique function on the path
# ---------------------------------------------------------------------------


def _collect_path_functions(
    paths: list[dict[str, Any]],
) -> list[tuple[str, str | None]]:
    """Ordered unique ``(name, file_hint)`` pairs across all path hops."""
    seen: set[str] = set()
    ordered: list[tuple[str, str | None]] = []
    for path in paths:
        for hop in path.get("hops", []):
            for role, file_key in (
                ("caller", "caller_file"),
                ("callee", "callee_file"),
            ):
                name = hop.get(role)
                if not name or name in seen:
                    continue
                seen.add(name)
                ordered.append((name, hop.get(file_key) or None))
    return ordered


def inline_path_bodies(
    project_root: str,
    cache: Any,
    paths: list[dict[str, Any]],
    endpoint_hints: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return ``(source_bodies, any_truncated)`` for a found path.

    De-duplicates: each unique function is inlined exactly once.
    ``endpoint_hints`` maps a function name to a caller-supplied file hint
    (e.g. the explicit ``source_file`` / ``target_file`` args) used to
    disambiguate otherwise ambiguous bare names whose hops carry no file.
    """
    functions = _collect_path_functions(paths)
    if endpoint_hints:
        functions = [
            (name, file_hint or endpoint_hints.get(name))
            for name, file_hint in functions
        ]
    names = {name for name, _ in functions}
    index = _build_def_index(cache, names)
    budget = [MAX_TOTAL_BODY_LINES]
    bodies: list[dict[str, Any]] = []
    any_truncated = False
    for name, file_hint in functions:
        defn = _resolve_def(index, name, file_hint)
        if defn is None:
            continue
        defn = {**defn, "name": name}
        block = _read_body(project_root, defn, budget)
        if block is None:
            continue
        any_truncated = any_truncated or bool(block.get("truncated"))
        bodies.append(block)
    return bodies, any_truncated


# ---------------------------------------------------------------------------
# Dead-end enrichment — inline both endpoints + their neighbours
# ---------------------------------------------------------------------------


def _neighbor_list(rows: list[dict[str, Any]], name_key: str) -> list[dict[str, Any]]:
    """Compact, de-duplicated neighbour list (name + file + line)."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        nm = row.get(name_key, "")
        if not nm:
            continue
        file_key = (
            "caller_file" if name_key == "caller_name" else "callee_resolved_file"
        )
        fl = row.get(file_key) or row.get("callee_file") or row.get("caller_file") or ""
        key = (nm, fl)
        if key in seen:
            continue
        seen.add(key)
        line_key = "caller_line" if name_key == "caller_name" else "callee_line"
        out.append({"name": nm, "file": fl, "line": row.get(line_key, 0)})
        if len(out) >= MAX_NEIGHBORS:
            break
    return out


def _endpoint_block(
    project_root: str,
    cache: Any,
    index: dict[str, list[dict[str, Any]]],
    name: str,
    file_hint: str | None,
    budget: list[int],
) -> dict[str, Any]:
    """Build one endpoint block: body + direct callers + direct callees."""
    defn = _resolve_def(index, name, file_hint)
    block: dict[str, Any] = {"name": name}
    if defn is not None:
        body = _read_body(project_root, {**defn, "name": name}, budget)
        if body is not None:
            block["body"] = body
    try:
        callers = cache.query_callers(name, file_hint, 1)
    except Exception:
        callers = []
    try:
        callees = cache.query_callees(name, file_hint, 1)
    except Exception:
        callees = []
    block["callers"] = _neighbor_list(callers, "caller_name")
    block["callees"] = _neighbor_list(callees, "callee_name")
    return block


def build_dead_end(
    project_root: str,
    cache: Any,
    source: str,
    target: str,
    source_file: str | None,
    target_file: str | None,
) -> dict[str, Any]:
    """Return a dead-end payload with both endpoints inlined + neighbours."""
    index = _build_def_index(cache, {source, target})
    budget = [MAX_TOTAL_BODY_LINES]
    return {
        "source_endpoint": _endpoint_block(
            project_root, cache, index, source, source_file, budget
        ),
        "target_endpoint": _endpoint_block(
            project_root, cache, index, target, target_file, budget
        ),
    }
