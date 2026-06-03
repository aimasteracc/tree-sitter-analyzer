"""Second-pass cross-file reference resolution for ASTCache.

B1.3 removed the ``unresolved_refs`` work-queue table. The second pass now runs
directly over the unified ``edges`` table + the indexed symbol/import data:

* The pending work set is recomputed in-memory per Python file from the same
  sources the queue was derived from (the file's symbols give EXTENDS parents,
  the file's CALLS edges give unresolved calls). The exact filtering logic that
  used to gate queue insertion (``_parent_refs`` / ``_call_refs`` — skip local
  names, skip obvious externals, skip already-resolved) is preserved verbatim,
  so Python resolution semantics are byte-for-byte unchanged.
* A resolved EXTENDS reference is upserted as a real ``edges`` row (provenance
  ``unresolved_refs``); a resolved CALLS reference UPDATEs the resolution
  columns of its existing ``edges`` CALLS row. No separate queue table, no
  double-write into ``ast_call_edges``.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

from .graph.edge_store import Edge, EdgeKind, EdgeStore, parse_node_id, symbol_node

logger = logging.getLogger(__name__)

_CALL_ROW_COLUMNS = (
    "caller_name",
    "caller_file",
    "caller_line",
    "callee_name",
    "callee_full",
    "callee_line",
    "file_path",
    "language",
    "callee_resolution",
    "callee_resolved_file",
)


def _refs_supported(language: str) -> bool:
    """Whether second-pass resolution adds value for a language.

    Only Python has structured import parsing (``synapse_resolver/_imports.py``
    hard-returns ``[]`` for every other language). Without ``ast_imports`` rows,
    the second-pass resolver can only fall back to ambiguous name matching, which
    is rejected ~100% of the time for languages like Java/COBOL/C#/Go. Resolving
    those refs is pure waste (and the dominant cost / OOM trigger on large Java
    repos). So we skip non-Python languages entirely. Python is unchanged.
    """
    return language == "python"


def _pending_refs_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbols: dict[str, Any],
) -> list[dict[str, Any]]:
    """Recompute the pending second-pass refs for one Python file.

    Returns ref dicts ``{from_node_id, reference_name, reference_kind,
    file_path, line}`` — the in-memory equivalent of the rows the old
    ``unresolved_refs`` queue persisted, derived from the file's symbols
    (EXTENDS parents) and its ``edges`` CALLS rows (unresolved calls).
    """
    if not _refs_supported(language):
        return []
    symbol_items = symbols.get("symbols", [])
    local_classes = _local_names(symbol_items, {"class"})
    local_callables = _local_names(symbol_items, {"class", "function", "method"})
    refs: list[dict[str, Any]] = []
    refs.extend(_parent_refs(rel_path, symbol_items, local_classes))
    refs.extend(_call_refs(conn, rel_path, language, [], local_callables))
    return refs


def resolve_unresolved_refs(conn: sqlite3.Connection) -> dict[str, int] | None:
    """Resolve pending cross-file refs into unified ``edges`` rows.

    Iterates Python files from ``ast_index``, recomputes each file's pending
    refs in-memory, and either upserts a resolved EXTENDS edge or UPDATEs a
    CALLS edge's resolution columns. The aggregate ``total/resolved/unchanged/
    errors`` shape matches the legacy queue-based pass so callers/stats are
    unchanged.
    """
    try:
        index_rows = conn.execute(
            "SELECT file_path, language, symbols_json FROM ast_index "
            "WHERE language = 'python' ORDER BY file_path"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("unresolved second-pass index select failed: %s", exc)
        return None

    total = resolved = unchanged = errors = 0
    store = EdgeStore(conn, ensure_schema=False)
    # Per-run candidate cache keyed by ``(name, kind)``. The candidate set for a
    # given name/kind is file-independent (see ``_candidates_for_name_kind``), so
    # the dominant cost — one ``ast_symbol_rows`` SELECT per (name, kind) per ref
    # — collapses to one SELECT per distinct (name, kind) across the whole pass.
    candidate_cache: dict[tuple[str, str], list[dict[str, Any]] | None] = {}
    for index_row in index_rows:
        rel_path = str(index_row["file_path"])
        try:
            symbols = json.loads(index_row["symbols_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        refs = _pending_refs_for_file(
            conn, rel_path, str(index_row["language"]), symbols
        )
        for ref in refs:
            total += 1
            try:
                candidates = _candidate_symbols(
                    conn,
                    str(ref["file_path"]),
                    str(ref["reference_name"]),
                    str(ref["reference_kind"]),
                    candidate_cache,
                )
                chosen = _choose_candidate(conn, ref, candidates)
                if chosen is None:
                    unchanged += 1
                    continue
                if ref["reference_kind"] == EdgeKind.CALLS.value:
                    # CALLS resolution is recorded in place on the existing edge
                    # row's resolution columns — no separate edge, so callees
                    # aren't double-counted (B1.3). The resolved file makes the
                    # call cross-file-queryable via ``callee_resolved_file``.
                    _update_call_edge_resolution(conn, ref, chosen)
                else:
                    # EXTENDS/IMPLEMENTS: upsert a real edge pointing at the
                    # resolved base class so class_hierarchy can traverse it.
                    edge = _resolved_edge(conn, ref, chosen, len(candidates))
                    store.upsert_edges([edge])
                resolved += 1
            except (sqlite3.OperationalError, TypeError, ValueError) as exc:
                logger.debug("unresolved ref failed: %s", exc)
                errors += 1
    try:
        conn.commit()
    except sqlite3.OperationalError:
        pass
    return {
        "total": total,
        "resolved": resolved,
        "unchanged": unchanged,
        "errors": errors,
    }


def pending_unresolved_count(conn: sqlite3.Connection) -> int:
    """Return a cheap count of references still awaiting cross-file resolution.

    Replaces the ``unresolved_refs WHERE resolved = 0`` gate (B1.3). Counts
    EXTENDS edges that still point at an unresolved ``class:`` synthetic target
    — the genuine cross-file work the second pass resolves into real edges.
    Unknown CALLS edges are *not* counted: most are terminal externals (stdlib /
    builtins) that never resolve, so counting them would keep this gate
    permanently > 0 and re-trigger the resolve-only pass on every warm access.
    Used only as a boolean ``> 0`` trigger; the resolve-only pass is idempotent.
    """
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM edges "
            "WHERE kind = 'extends' AND target_node_id LIKE 'class:%'"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["c"] if isinstance(row, sqlite3.Row) else row[0])


def _ref(
    from_node_id: str,
    reference_name: str,
    reference_kind: str,
    file_path: str,
    line: int,
) -> dict[str, Any]:
    return {
        "from_node_id": from_node_id,
        "reference_name": reference_name,
        "reference_kind": reference_kind,
        "file_path": file_path,
        "line": line,
    }


def _parent_refs(
    rel_path: str,
    symbol_items: list[dict[str, Any]],
    local_classes: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sym in symbol_items:
        if sym.get("kind") != "class" or not sym.get("parents"):
            continue
        class_name = str(sym.get("name") or "")
        if not class_name:
            continue
        line = _line(sym.get("line"))
        source = symbol_node(rel_path, class_name, line)
        for parent in sym.get("parents", []):
            parent_name = str(parent).strip()
            base_parent = _base_name(parent_name)
            if (
                not parent_name
                or parent_name in local_classes
                or base_parent in local_classes
            ):
                continue
            rows.append(
                _ref(source, parent_name, EdgeKind.EXTENDS.value, rel_path, line)
            )
    return rows


def _call_refs(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    fallback_edges: list[dict[str, Any]],
    local_callables: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for edge in _call_rows(conn, rel_path, fallback_edges):
        if _call_is_resolved(edge):
            continue
        callee_name = str(edge.get("callee_name") or "").strip()
        base = _base_name(callee_name)
        if not callee_name or base in local_callables or callee_name in local_callables:
            continue
        if _is_obvious_external(language, callee_name):
            continue
        caller_name = str(edge.get("caller_name") or "")
        caller_line = _line(edge.get("caller_line"))
        source = symbol_node(rel_path, caller_name, caller_line)
        ref_line = _line(edge.get("callee_line")) or caller_line
        rows.append(_ref(source, callee_name, EdgeKind.CALLS.value, rel_path, ref_line))
    return rows


def _call_rows(
    conn: sqlite3.Connection,
    rel_path: str,
    fallback_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return this file's CALLS rows from the unified ``edges`` table (B1.3)."""
    try:
        rows = conn.execute(
            """SELECT caller_name, file_path AS caller_file, caller_line,
                      callee_name, callee_full, callee_line, file_path, language,
                      callee_resolution, callee_resolved_file
               FROM edges
               WHERE kind = 'calls' AND file_path = ?
               ORDER BY id""",
            (rel_path,),
        ).fetchall()
    except sqlite3.OperationalError:
        return [dict(edge) for edge in fallback_edges]
    if not rows:
        return [dict(edge) for edge in fallback_edges]
    return [_row_to_dict(row, _CALL_ROW_COLUMNS) for row in rows]


def _candidate_symbols(
    conn: sqlite3.Connection,
    source_file: str,
    reference_name: str,
    reference_kind: str,
    cache: dict[tuple[str, str], list[dict[str, Any]] | None] | None = None,
) -> list[dict[str, Any]]:
    names = _reference_names(conn, source_file, reference_name)
    kinds = (
        ["class"]
        if reference_kind in {EdgeKind.EXTENDS.value, EdgeKind.IMPLEMENTS.value}
        else ["function", "method", "class"]
    )
    candidates: list[dict[str, Any]] = []
    for name in names:
        for kind in kinds:
            bucket = _candidates_for_name_kind(conn, name, kind, cache)
            if bucket is None:
                # ``ast_symbol_rows`` missing / broken connection — preserve the
                # legacy whole-call abort so a single failed SELECT yields [].
                return []
            candidates.extend(bucket)
    return candidates


def _candidates_for_name_kind(
    conn: sqlite3.Connection,
    name: str,
    kind: str,
    cache: dict[tuple[str, str], list[dict[str, Any]] | None] | None,
) -> list[dict[str, Any]] | None:
    """Built candidate items for one ``(name, kind)``; cached when ``cache`` given.

    The SQL result for a ``(name, kind)`` pair is independent of which file/ref
    requested it (``_reference_names`` already expanded the file's import
    aliases into the ``name`` set upstream), and the derived ``node_id`` /
    ``line`` are pure functions of the row, so the built list is safe to reuse
    verbatim across refs. On large Python trees the same hot names (``get``,
    ``run``, ``build`` …) recur across thousands of refs, so caching collapses
    those duplicate SELECTs. Returns ``None`` to signal the legacy
    ``OperationalError`` abort path (caller short-circuits to ``[]``); a real
    empty result is cached/returned as ``[]``.
    """
    key = (name, kind)
    if cache is not None and key in cache:
        return cache[key]
    try:
        rows = conn.execute(
            """SELECT id, name, kind, file_path, language, line
               FROM ast_symbol_rows
               WHERE name = ? AND kind = ?
               ORDER BY file_path, line, name""",
            (name, kind),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("candidate symbol lookup failed: %s", exc)
        if cache is not None:
            cache[key] = None
        return None
    bucket: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(
            row, ("id", "name", "kind", "file_path", "language", "line")
        )
        item["line"] = _line(item.get("line"))
        item["node_id"] = symbol_node(
            str(item["file_path"]),
            str(item["name"]),
            int(item["line"]),
        )
        bucket.append(item)
    if cache is not None:
        cache[key] = bucket
    return bucket


def _reference_names(
    conn: sqlite3.Connection,
    source_file: str,
    reference_name: str,
) -> list[str]:
    base = _base_name(reference_name)
    names = [reference_name, base]
    try:
        rows = conn.execute(
            """SELECT local_name, alias_of
               FROM ast_imports
               WHERE file_path = ?""",
            (source_file,),
        ).fetchall()
    except sqlite3.OperationalError:
        return _unique(names)
    for row in rows:
        item = _row_to_dict(row, ("local_name", "alias_of"))
        local_name = str(item.get("local_name") or "")
        alias_of = str(item.get("alias_of") or "")
        if local_name in {reference_name, base} and alias_of:
            names.extend([alias_of, _base_name(alias_of)])
    return _unique(names)


def _choose_candidate(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None
    source_file = str(row["file_path"])
    source_node = str(row["from_node_id"])
    reference_name = str(row["reference_name"])
    base = _base_name(reference_name)
    import_hints = _import_target_hints(conn, source_file, reference_name)
    eligible = [item for item in candidates if item.get("node_id") != source_node]
    if not eligible:
        return None
    source_dir = os.path.dirname(source_file)

    def score(item: dict[str, Any]) -> tuple[int, int, int, int, str, int]:
        file_path = str(item["file_path"])
        imported = 0 if _matches_import_hint(file_path, import_hints) else 1
        same_file = 0 if file_path == source_file else 1
        same_dir = 0 if os.path.dirname(file_path) == source_dir else 1
        exact = 0 if item["name"] in {reference_name, base} else 1
        return (imported, same_file, same_dir, exact, file_path, int(item["line"]))

    return sorted(eligible, key=score)[0]


def _resolved_edge(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    candidate: dict[str, Any],
    candidate_count: int,
) -> Edge:
    kind = str(row["reference_kind"])
    reference_name = str(row["reference_name"])
    resolved_file = str(candidate["file_path"])
    metadata: dict[str, Any] = {
        "language": _file_language(conn, str(row["file_path"])),
        "reference_name": reference_name,
        "reference_kind": kind,
        "resolved_file": resolved_file,
        "resolved_name": str(candidate["name"]),
        "resolved_symbol_id": int(candidate["id"]),
        "resolution": "unresolved_refs",
        "candidate_count": candidate_count,
    }
    if kind in {EdgeKind.EXTENDS.value, EdgeKind.IMPLEMENTS.value}:
        metadata["parent"] = str(candidate["name"])
        metadata["parent_reference"] = reference_name
    if kind == EdgeKind.CALLS.value:
        metadata.update(
            {
                "callee_name": str(candidate["name"]),
                "callee_full": reference_name,
                "callee_resolution": "project",
                "callee_resolved_file": resolved_file,
            }
        )
    return Edge(
        str(row["from_node_id"]),
        str(candidate["node_id"]),
        kind,
        _line(row.get("line")),
        provenance="unresolved_refs",
        metadata=metadata,
    )


def _update_call_edge_resolution(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    if row["reference_kind"] != EdgeKind.CALLS.value:
        return
    source = parse_node_id(str(row["from_node_id"]))
    if not source.name:
        return
    line = _line(row.get("line"))
    try:
        conn.execute(
            """UPDATE edges
               SET callee_symbol_id = ?, callee_resolution = 'project',
                   callee_resolved_file = ?
               WHERE kind = 'calls'
                 AND file_path = ?
                 AND caller_name = ?
                 AND caller_line = ?
                 AND callee_name = ?
                 AND (callee_line = ? OR ? = 0)""",
            (
                int(candidate["id"]),
                str(candidate["file_path"]),
                str(row["file_path"]),
                source.name,
                source.line,
                str(row["reference_name"]),
                line,
                line,
            ),
        )
    except sqlite3.OperationalError as exc:
        logger.debug("call edge cross-file update failed: %s", exc)


def _import_target_hints(
    conn: sqlite3.Connection,
    source_file: str,
    reference_name: str,
) -> set[str]:
    base = _base_name(reference_name)
    try:
        rows = conn.execute(
            """SELECT module_path, local_name, alias_of
               FROM ast_imports
               WHERE file_path = ?""",
            (source_file,),
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    hints: set[str] = set()
    for row in rows:
        item = _row_to_dict(row, ("module_path", "local_name", "alias_of"))
        local_name = str(item.get("local_name") or "")
        alias_of = str(item.get("alias_of") or "")
        if local_name not in {reference_name, base} and alias_of not in {
            reference_name,
            base,
        }:
            continue
        hints.update(_module_path_candidates(str(item.get("module_path") or "")))
    return hints


def _module_path_candidates(module_path: str) -> set[str]:
    clean = module_path.lstrip(".").replace(".", "/").strip("/")
    if not clean:
        return set()
    return {f"{clean}.py", f"{clean}/__init__.py"}


def _matches_import_hint(file_path: str, hints: set[str]) -> bool:
    if not hints:
        return False
    return any(file_path == hint or file_path.endswith(f"/{hint}") for hint in hints)


def _file_language(conn: sqlite3.Connection, file_path: str) -> str:
    try:
        row = conn.execute(
            "SELECT language FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
    except sqlite3.OperationalError:
        return ""
    if row is None:
        return ""
    return str(row["language"] if isinstance(row, sqlite3.Row) else row[0])


def _call_is_resolved(edge: dict[str, Any]) -> bool:
    resolution = str(edge.get("callee_resolution") or "unknown")
    resolved_file = str(edge.get("callee_resolved_file") or "")
    if resolution == "stdlib":
        return True
    return resolution in {"local", "project"} and bool(resolved_file)


def _is_obvious_external(language: str, callee_name: str) -> bool:
    if language != "python":
        return False
    try:
        from .synapse_resolver import BUILTINS_PY, STDLIB_NAMES_PY
    except Exception:  # pragma: no cover
        return False
    base = _base_name(callee_name)
    qualifier = callee_name.split(".", 1)[0]
    return base in BUILTINS_PY or qualifier in STDLIB_NAMES_PY


def _local_names(symbol_items: list[dict[str, Any]], kinds: set[str]) -> set[str]:
    return {
        str(sym.get("name") or "")
        for sym in symbol_items
        if sym.get("kind") in kinds and sym.get("name")
    }


def _base_name(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _line(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _row_to_dict(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(zip(columns, row, strict=False))
