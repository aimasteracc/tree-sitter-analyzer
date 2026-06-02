"""Second-pass unresolved reference handling for ASTCache."""

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


def write_unresolved_refs_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbols: dict[str, Any],
    call_edges: list[dict[str, Any]],
) -> None:
    """Refresh unresolved_refs emitted while indexing one file."""
    try:
        conn.execute("DELETE FROM unresolved_refs WHERE file_path = ?", (rel_path,))
    except sqlite3.OperationalError as exc:
        logger.debug("unresolved_refs cleanup failed for %s: %s", rel_path, exc)
        return

    symbol_items = symbols.get("symbols", [])
    local_classes = _local_names(symbol_items, {"class"})
    local_callables = _local_names(symbol_items, {"class", "function", "method"})
    rows: list[tuple[str, str, str, str, int, str, int]] = []
    rows.extend(_parent_refs(rel_path, symbol_items, local_classes))
    rows.extend(
        _call_refs(
            conn,
            rel_path,
            language,
            call_edges,
            local_callables,
        )
    )
    if not rows:
        return
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO unresolved_refs
               (from_node_id, reference_name, reference_kind, file_path,
                line, candidates, resolved)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    except sqlite3.OperationalError as exc:
        logger.debug("unresolved_refs insert failed for %s: %s", rel_path, exc)


def resolve_unresolved_refs(conn: sqlite3.Connection) -> dict[str, int] | None:
    """Resolve pending unresolved_refs rows into unified EdgeStore edges."""
    try:
        rows = conn.execute(
            """SELECT id, from_node_id, reference_name, reference_kind,
                      file_path, line
               FROM unresolved_refs
               WHERE resolved = 0
               ORDER BY id"""
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("unresolved_refs select failed: %s", exc)
        return None

    total = len(rows)
    resolved = unchanged = errors = 0
    store = EdgeStore(conn, ensure_schema=False)
    for row in rows:
        try:
            row_dict = dict(row)
            candidates = _candidate_symbols(
                conn,
                str(row_dict["file_path"]),
                str(row_dict["reference_name"]),
                str(row_dict["reference_kind"]),
            )
            chosen = _choose_candidate(conn, row_dict, candidates)
            payload = _candidate_payload(candidates)
            if chosen is None:
                unchanged += 1
                conn.execute(
                    "UPDATE unresolved_refs SET candidates = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False), row_dict["id"]),
                )
                continue
            edge = _resolved_edge(conn, row_dict, chosen, len(candidates))
            store.upsert_edges([edge])
            _update_call_edge_resolution(conn, row_dict, chosen)
            conn.execute(
                "UPDATE unresolved_refs SET candidates = ?, resolved = 1 WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), row_dict["id"]),
            )
            resolved += 1
        except (sqlite3.OperationalError, TypeError, ValueError) as exc:
            logger.debug("unresolved_refs row failed: %s", exc)
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
    """Return unresolved_refs rows still awaiting a second-pass attempt."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM unresolved_refs WHERE resolved = 0"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["c"] if isinstance(row, sqlite3.Row) else row[0])


def _parent_refs(
    rel_path: str,
    symbol_items: list[dict[str, Any]],
    local_classes: set[str],
) -> list[tuple[str, str, str, str, int, str, int]]:
    rows: list[tuple[str, str, str, str, int, str, int]] = []
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
                (
                    source,
                    parent_name,
                    EdgeKind.EXTENDS.value,
                    rel_path,
                    line,
                    "[]",
                    0,
                )
            )
    return rows


def _call_refs(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    fallback_edges: list[dict[str, Any]],
    local_callables: set[str],
) -> list[tuple[str, str, str, str, int, str, int]]:
    rows: list[tuple[str, str, str, str, int, str, int]] = []
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
        rows.append(
            (
                source,
                callee_name,
                EdgeKind.CALLS.value,
                rel_path,
                ref_line,
                "[]",
                0,
            )
        )
    return rows


def _call_rows(
    conn: sqlite3.Connection,
    rel_path: str,
    fallback_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """SELECT caller_name, caller_file, caller_line, callee_name,
                      callee_full, callee_line, file_path, language,
                      callee_resolution, callee_resolved_file
               FROM ast_call_edges
               WHERE file_path = ?
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
) -> list[dict[str, Any]]:
    names = _reference_names(conn, source_file, reference_name)
    kinds = (
        ["class"]
        if reference_kind in {EdgeKind.EXTENDS.value, EdgeKind.IMPLEMENTS.value}
        else ["function", "method", "class"]
    )
    rows: list[Any] = []
    try:
        for name in names:
            for kind in kinds:
                rows.extend(
                    conn.execute(
                        """SELECT id, name, kind, file_path, language, line
                           FROM ast_symbol_rows
                           WHERE name = ? AND kind = ?
                           ORDER BY file_path, line, name""",
                        (name, kind),
                    ).fetchall()
                )
    except sqlite3.OperationalError as exc:
        logger.debug("candidate symbol lookup failed: %s", exc)
        return []
    candidates: list[dict[str, Any]] = []
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
        candidates.append(item)
    return candidates


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
            """UPDATE ast_call_edges
               SET callee_symbol_id = ?, callee_resolution = 'project',
                   callee_resolved_file = ?
               WHERE file_path = ?
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
        logger.debug("call edge unresolved_refs update failed: %s", exc)


def _candidate_payload(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": str(item["node_id"]),
            "name": str(item["name"]),
            "kind": str(item["kind"]),
            "file_path": str(item["file_path"]),
            "line": int(item["line"]),
        }
        for item in candidates[:20]
    ]


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
