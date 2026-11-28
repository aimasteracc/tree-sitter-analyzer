"""#1942: ``call_path`` endpoints given as ``Class.method``.

A qualified endpoint is resolved to one definition before any search runs, the
way ``nav action=callers`` resolves ``Class.method``. When it names no
definition, or several (the same class name in two files), the tool fails closed
with ``ENDPOINT_NOT_RESOLVED`` / ``ENDPOINT_AMBIGUOUS``, the candidates and the
exact retry, instead of a ``NO_PATH`` that reads like evidence of absence.
A resolved pair is searched by definition (:mod:`...call_path_pinned`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...call_path_pinned import (
    NAME_ONLY,
    OPEN_SITES_CAP,
    RESOLVED,
    Definition,
    SymbolBook,
    callee_of,
    find_pinned_paths,
    incoming,
    outgoing,
)

NOT_RESOLVED = "ENDPOINT_NOT_RESOLVED"
AMBIGUOUS = "ENDPOINT_AMBIGUOUS"
#: Candidates listed per endpoint.
_CANDIDATES_CAP = 10
#: Neighbours listed per endpoint on a dead end.
_NEIGHBORS_CAP = 12

_FLAGS = {
    "source": ("--call-path-source", "--call-path-source-file", "source_file"),
    "target": ("--call-path-target", "--call-path-target-file", "target_file"),
}


@dataclass(frozen=True)
class Endpoint:
    role: str
    query: str
    file: str | None
    #: ``resolved`` / ``not_resolved`` / ``ambiguous``.
    status: str
    definition: Definition | None = None
    candidates: tuple[Definition, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        block: dict[str, Any] = {"query": self.query, "status": self.status}
        if self.file:
            block["file"] = self.file
        if self.definition is not None:
            block["resolved"] = self.definition.to_dict()
        if self.status != "resolved":
            block["candidates"] = [
                d.to_dict() for d in self.candidates[:_CANDIDATES_CAP]
            ]
            block["candidates_total"] = len(self.candidates)
        return block


def is_qualified(name: str) -> bool:
    """``Class.method`` (or ``pkg.Class.method``), not a path or a bare name."""
    owner, _, bare = name.rpartition(".")
    return bool(owner and bare) and not any(ch in name for ch in "/\\:")


def resolve(book: SymbolBook, role: str, name: str, file: str | None) -> Endpoint:
    """The one definition ``name`` names, optionally in ``file``.

    ``Class.method`` must match the owner class; a bare name (the other endpoint
    of a qualified query) any definition of that name.
    """
    owner, _, bare = name.rpartition(".") if is_qualified(name) else ("", "", name)
    wanted = _normalized(file)
    every = book.named(bare)
    owned = [d for d in every if not owner or _owner_matches(d.owner, owner)]
    matches = [d for d in owned if wanted is None or d.file == wanted]
    if len(matches) == 1:
        return Endpoint(role, name, file, "resolved", matches[0])
    if matches:
        return Endpoint(role, name, file, "ambiguous", candidates=tuple(matches))
    return Endpoint(role, name, file, "not_resolved", candidates=tuple(owned or every))


def failure_response(endpoints: list[Endpoint]) -> dict[str, Any]:
    """The fail-closed answer for endpoints that are not one definition each."""
    failing = [ep for ep in endpoints if ep.status != "resolved"]
    status = (
        AMBIGUOUS if all(ep.status == "ambiguous" for ep in failing) else NOT_RESOLVED
    )
    return {
        "success": True,
        "verdict": "WARN",
        "path_status": status,
        "path_count": 0,
        "paths": [],
        "endpoints": {ep.role: ep.to_dict() for ep in endpoints},
        "next_step": " ".join(_retry(ep) for ep in failing),
    }


def pinned_response(
    conn: Any,
    book: SymbolBook,
    source: Endpoint,
    target: Endpoint,
    max_depth: int,
    max_paths: int,
) -> dict[str, Any]:
    """Search between two resolved endpoints; ``NO_PATH`` carries completeness."""
    if source.definition is None or target.definition is None:
        return failure_response([source, target])
    found = find_pinned_paths(
        conn, book, source.definition, target.definition, max_depth, max_paths
    )
    paths = [
        {"hops": hops, "total_hops": len(hops), "files_crossed": _files(hops)}
        for hops in found.paths[:max_paths]
    ]
    result: dict[str, Any] = {
        "success": True,
        "verdict": "INFO" if paths else "NOT_FOUND",
        "path_status": "PATH_FOUND" if paths else "NO_PATH",
        "data_source": "sql",
        "search": "definitions",
        "source": source.query,
        "target": target.query,
        "path_count": len(paths),
        "truncated": len(found.paths) >= max_paths,
        "paths": paths,
        "endpoints": {"source": source.to_dict(), "target": target.to_dict()},
    }
    if any(
        hop["callee_resolution"] == NAME_ONLY for hops in found.paths for hop in hops
    ):
        result["name_only_hops"] = True
    if not paths:
        result["completeness"] = "complete" if found.complete else "unknown"
        if found.reasons:
            result["completeness_reason"] = found.reasons[0]
            result["completeness_reasons"] = found.reasons
        result["open_sites"] = found.open_sites[:OPEN_SITES_CAP]
        result["open_sites_total"] = len(found.open_sites)
        result["depth_limited"] = found.depth_limited
        result["dead_end"] = {
            "source_endpoint": _endpoint_block(conn, book, source.definition),
            "target_endpoint": _endpoint_block(conn, book, target.definition),
        }
        result["next_step"] = _no_path_step(source, target, found)
    return result


def path_definitions(book: SymbolBook, result: dict[str, Any]) -> list[Definition]:
    """Every definition on the answer's paths (or its dead-end endpoints), once."""
    coordinates: list[tuple[str, int]] = []
    for path in result.get("paths") or ():
        for hop in path["hops"]:
            coordinates.append((hop["caller_file"], hop["caller_line"]))
            coordinates.append((hop["callee_file"], hop["callee_line"]))
    for block in (result.get("dead_end") or {}).values():
        coordinates.append((block["file"], block["line"]))
    found: list[Definition] = []
    for file, line in dict.fromkeys(coordinates):
        match = [d for d in book.in_file(file) if d.line == line]
        if match:
            found.append(match[0])
    return found


def _endpoint_block(conn: Any, book: SymbolBook, node: Definition) -> dict[str, Any]:
    callees = []
    for row in outgoing(conn, node)[: _NEIGHBORS_CAP * 4]:
        callee = callee_of(book, row)
        entry: dict[str, Any] = {
            "name": callee.label if callee else str(row.get("callee_name") or ""),
            "call_site_file": node.file,
            "call_site_line": int(row.get("line") or 0),
            "resolution": RESOLVED
            if callee
            else str(row.get("callee_resolution") or NAME_ONLY),
        }
        if callee is not None:
            entry["file"] = callee.file
            entry["line"] = callee.line
        elif row.get("callee_resolved_file"):
            entry["file"] = str(row["callee_resolved_file"])
        callees.append(entry)
    callers = [
        {
            "name": _caller_label(book, row),
            "file": str(row.get("file_path") or ""),
            "line": int(row.get("caller_line") or 0),
            "call_site_line": int(row.get("line") or 0),
            "resolution": row["resolution"],
        }
        for row in incoming(conn, book, node)
    ]
    return {
        "name": node.label,
        "file": node.file,
        "line": node.line,
        "callers": callers[:_NEIGHBORS_CAP],
        "callers_total": len(callers),
        "callees": callees[:_NEIGHBORS_CAP],
        "callees_total": len(callees),
    }


def _caller_label(book: SymbolBook, row: dict[str, Any]) -> str:
    name = str(row.get("caller_name") or "")
    found = book.at(
        name, str(row.get("file_path") or ""), int(row.get("caller_line") or 0)
    )
    return found[0].label if found else name


def _no_path_step(source: Endpoint, target: Endpoint, found: Any) -> str:
    if found.complete:
        return (
            f"No call path from {source.query!r} to {target.query!r}: every call "
            "reachable from the source was followed and none reaches the target."
        )
    sites = "; ".join(
        f"{site['file']}:{site['line']} (`{site['callee']}`)"
        for site in found.open_sites[:3]
    )
    more = len(found.open_sites) - 3
    if more > 0:
        sites += f"; and {more} more"
    limit = " The depth limit was reached." if found.depth_limited else ""
    return (
        "No static path found, but the search is not complete: "
        f"{len(found.open_sites)} call(s) on the explored frontier go through a "
        f"receiver the index could not bind (`open_sites`): {sites or 'none'}."
        f"{limit} Read those sites; any of them may lead to {target.query!r}."
    )


def _retry(ep: Endpoint) -> str:
    flag, file_flag, arg = _FLAGS[ep.role]
    shown = ", ".join(f"{d.label} ({d.file}:{d.line})" for d in ep.candidates[:5])
    if ep.status == "ambiguous":
        first = ep.candidates[0]
        return (
            f"{ep.role} {ep.query!r} matches {len(ep.candidates)} definitions: "
            f"{shown}. Retry with {arg} (CLI: {flag} {ep.query} {file_flag} "
            f"{first.file})."
        )
    if not ep.candidates:
        return (
            f"{ep.role} {ep.query!r} names no function or method in the index. "
            "Check the spelling, or use nav action=symbol to find it."
        )
    first = ep.candidates[0]
    return (
        f"{ep.role} {ep.query!r} names no definition"
        f"{' in ' + ep.file if ep.file else ''}; same-named definitions: {shown}. "
        f"Retry with one of them (CLI: {flag} {first.label} {file_flag} {first.file})."
    )


def _owner_matches(owner: str | None, wanted: str) -> bool:
    if not owner:
        return False
    return (
        owner == wanted or wanted.endswith("." + owner) or owner.endswith("." + wanted)
    )


def _normalized(file: str | None) -> str | None:
    if not file:
        return None
    normalized = file.replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def _files(hops: list[dict[str, Any]]) -> int:
    return len(
        {hop["callee_file"] for hop in hops} | {hop["caller_file"] for hop in hops}
    )


__all__ = [
    "AMBIGUOUS",
    "NOT_RESOLVED",
    "Endpoint",
    "failure_response",
    "is_qualified",
    "path_definitions",
    "pinned_response",
    "resolve",
]
