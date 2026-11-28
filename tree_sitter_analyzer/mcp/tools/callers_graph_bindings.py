"""PR-3: index-unresolved call sites that the call graph already binds.

The two edge guards (``UNRESOLVED_INBOUND``, RFC-0028 §1.2's
``UNRESOLVED_IN_DECLARING_FILE``) count every call row the index left without a
persisted resolution. The in-memory call graph binds some of those rows itself,
and two kinds are not open sites at all (JS/TS only):

* **Listed caller edge** (``listed_caller_edge``). The row's call is the graph's
  certain edge into a target, and its caller is already in the list: the site
  is that listed caller, counted a second time (zod ``ParseStatus.mergeObjectSync``).
* **Bound elsewhere** (``graph_bound_elsewhere``). ``this.m()`` in a method of
  class ``C`` is bound certainly to ``C``'s own ``m`` (#1765), the target is in
  neither the certain nor the possible set of the caller, and the source proves
  the target unreachable through that ``this``: the target's class is not ``C``
  or a subclass of ``C`` (its whole ``extends`` chain is read from source, never
  from inheritance edges) and it is never used as a value that could copy its
  methods onto another class (zod ``ZodBigInt.setLimit`` beside ``ZodNumber``'s
  own ``this.setLimit``). A base class calling ``this.m()`` where subclasses
  override ``m`` keeps its site: the target is then a subclass of ``C``.

A site is dropped only when it is exactly one row of the index (same file, line
and call text) and the only call named like the target on its source line, the
row's caller is a function the graph knows by name and definition line, and the
file still matches the index. Any read failure, any other shape, and any site
list longer than :data:`MAX_SITES` keeps every site.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...call_graph_binding import ref_identity
from ...graph.read_interrupt import raise_if_interrupted
from .callers_dispatch import trailing_segment
from .callers_reference_freshness import stale_reference_files
from .callers_ts_source import (
    JSTS_SUFFIXES,
    SourceReader,
    chain_avoids,
    class_escapes,
    this_is_method_receiver,
)

#: Exclusion reason: the site is a listed caller's own edge into the target.
LISTED_EDGE_REASON = "listed_caller_edge"
#: Exclusion reason: the graph binds the site to the enclosing class's own method.
BOUND_ELSEWHERE_REASON = "graph_bound_elsewhere"
#: Longer site lists are left untouched (bounded work per answer).
MAX_SITES = 64
_NAME = re.compile(r"[A-Za-z_$][\w$]*")
_JSTS_LANGUAGES = ("typescript", "javascript", "tsx")


@dataclass(frozen=True)
class _Row:
    file: str
    line: int
    callee: str
    name: str
    caller: Any


class GraphBindings:
    """One answer's view of the graph bindings behind its unresolved sites."""

    def __init__(
        self,
        graph: Any,
        cache: Any,
        project_root: str,
        targets: list[Any],
        listed: list[dict[str, Any]],
    ) -> None:
        self._graph = graph
        self._cache = cache
        self._reader = SourceReader(project_root)
        self._targets = frozenset(targets)
        self._listed = _listed_keys(listed)
        self._edges: dict[tuple[Any, int], list[Any]] | None = None
        self._rows: dict[tuple[str, int, str], _Row | None] = {}
        self._stale: dict[str, bool] = {}
        self._escape: dict[Any, bool] = {}
        self._jsts_files: list[str] | None = None

    def partition(
        self, sites: list[dict[str, Any]] | None
    ) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
        """``(kept, dropped)``; dropped sites are copies carrying ``reason_code``."""
        if not sites or not self._targets or len(sites) > MAX_SITES:
            return sites, []
        rows = [self._row(site) for site in sites]
        self._load_edges([row.caller for row in rows if row is not None])
        kept: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []
        for site, row in zip(sites, rows, strict=True):
            reason = None if row is None else self._discharge(row)
            if reason is None:
                kept.append(site)
            else:
                dropped.append(
                    {**site, "classification": "excluded", "reason_code": reason}
                )
        return kept, dropped

    # -- the row behind a site -------------------------------------------------

    def _row(self, site: dict[str, Any]) -> _Row | None:
        file = str(site.get("file") or "").replace("\\", "/")
        line = int(site.get("line") or 0)
        callee = str(site.get("callee") or "")
        key = (file, line, callee)
        if key not in self._rows:
            self._rows[key] = self._read_row(file, line, callee)
        return self._rows[key]

    def _read_row(self, file: str, line: int, callee: str) -> _Row | None:
        if not file.lower().endswith(JSTS_SUFFIXES) or line < 1:
            return None
        segment = trailing_segment(callee)
        if segment is None or not _NAME.fullmatch(segment.strip()):
            return None
        name = segment.strip()
        if not any(target.name == name for target in self._targets):
            return None
        rows = _rows_at(self._cache, file, line)
        if rows is None:
            return None
        same = [row for row in rows if str(row.get("callee_full") or "") == callee]
        others = [row for row in rows if str(row.get("callee_full") or "") != callee]
        if len(same) != 1 or any(_may_name(row, name) for row in others):
            return None
        if not self._source_line_ok(file, line, callee, name):
            return None
        caller = self._caller_ref(file, line, same[0])
        return None if caller is None else _Row(file, line, callee, name, caller)

    def _source_line_ok(self, file: str, line: int, callee: str, name: str) -> bool:
        source = self._reader.read(file)
        if source is None or self._is_stale(file):
            return False
        lines = source.data.decode("utf-8", "replace").split("\n")
        if line > len(lines):
            return False
        text = lines[line - 1]
        word = re.compile(r"(?<![\w$#])" + re.escape(name) + r"(?![\w$])")
        if len(word.findall(text)) != 1:
            return False
        parts = [re.escape(part.strip()) for part in callee.split(".")]
        call = re.compile(
            r"(?<![\w$.#])" + r"\s*\.\s*".join(parts) + r"\s*(?:<[^<>()]*>)?\s*\("
        )
        return len(call.findall(text)) == 1

    def _is_stale(self, file: str) -> bool:
        if file not in self._stale:
            stale = stale_reference_files(
                self._cache,
                self._reader.root,
                [{"file": file}],
                {file: self._reader.stamps.get(file)},
            )
            self._stale[file] = stale is None or file in stale
        return self._stale[file]

    def _caller_ref(self, file: str, line: int, row: dict[str, Any]) -> Any | None:
        name = str(row.get("caller_name") or "")
        start = int(row.get("caller_line") or 0)
        if not name or start < 1:
            return None
        try:
            refs = [
                ref
                for ref in self._graph.function_refs_in_file(file)
                if ref.name == name and ref.start_line == start
            ]
        except Exception:  # noqa: BLE001 — unreadable graph: keep the site
            return None
        if len(refs) != 1 or not refs[0].start_line <= line <= refs[0].end_line:
            return None
        return refs[0]

    # -- the graph's bindings --------------------------------------------------

    def _load_edges(self, callers: list[Any]) -> None:
        wanted = {ref_identity(ref) for ref in callers}
        edges: dict[tuple[Any, int], list[Any]] = {}
        try:
            for caller, callee, line in self._graph.call_edges() if wanted else ():
                identity = ref_identity(caller)
                if identity in wanted:
                    edges.setdefault((identity, int(line or 0)), []).append(callee)
        except Exception:  # noqa: BLE001 — unreadable graph: keep every site
            self._edges = None
            return
        self._edges = edges

    def _discharge(self, row: _Row) -> str | None:
        if self._edges is None or not self._targets:
            return None
        certain = [
            ref
            for ref in self._edges.get((ref_identity(row.caller), row.line), [])
            if ref.name == row.name
        ]
        if not certain:
            return None
        if any(ref in self._targets for ref in certain):
            listed = (row.caller.file_path, row.caller.name, row.caller.start_line)
            return LISTED_EDGE_REASON if listed in self._listed else None
        if len(certain) == 1 and self._bound_elsewhere(row, certain[0]):
            return BOUND_ELSEWHERE_REASON
        return None

    def _bound_elsewhere(self, row: _Row, bound: Any) -> bool:
        owner = row.caller.receiver
        if row.callee != f"this.{row.name}" or not owner:
            return False
        if bound.receiver != owner or bound.file_path != row.file:
            return False
        try:
            reachable = set(self._graph.reachable_callee_refs_of(row.caller))
        except Exception:  # noqa: BLE001 — unreadable graph: keep the site
            return False
        if reachable & self._targets:
            return False
        source = self._reader.read(row.file)
        if source is None or not this_is_method_receiver(
            source, row.line, row.name, owner, row.caller.start_line
        ):
            return False
        forbidden = (row.file, owner)
        return all(self._unreachable(target, forbidden) for target in self._targets)

    def _unreachable(self, target: Any, forbidden: tuple[str, str]) -> bool:
        if not target.receiver or not target.file_path.lower().endswith(JSTS_SUFFIXES):
            return False
        if not chain_avoids(self._reader, target.file_path, target.receiver, forbidden):
            return False
        key = (target.file_path, target.receiver)
        if key not in self._escape:
            files = self._indexed_jsts_files()
            self._escape[key] = files is None or class_escapes(
                self._reader, files, target.file_path, target.receiver
            )
        return not self._escape[key]

    def _indexed_jsts_files(self) -> list[str] | None:
        if self._jsts_files is None:
            try:
                marks = ",".join("?" * len(_JSTS_LANGUAGES))
                rows = (
                    self._cache.get_conn()
                    .execute(
                        "SELECT file_path FROM ast_index "  # nosec B608
                        f"WHERE language IN ({marks})",
                        _JSTS_LANGUAGES,
                    )
                    .fetchall()
                )
            except Exception:  # noqa: BLE001 — unreadable index: cannot prove
                return None
            self._jsts_files = sorted(str(row[0]) for row in rows)
        return self._jsts_files


def _listed_keys(listed: list[dict[str, Any]]) -> frozenset[tuple[str, str, int]]:
    keys: set[tuple[str, str, int]] = set()
    for entry in listed:
        file = str(entry.get("file") or "").replace("\\", "/")
        name = str(entry.get("name") or "")
        line = int(entry.get("line") or 0)
        keys.add((file, name, line))
        keys.add((file, name.rpartition(".")[2], line))
    return frozenset(keys)


def _rows_at(cache: Any, file: str, line: int) -> list[dict[str, Any]] | None:
    from ...cache.graph_input_rows import read_call_edge_rows_where

    try:
        rows = read_call_edge_rows_where(
            cache.get_conn(), "file_path = ? AND line = ?", [file, line]
        )
    except Exception:  # noqa: BLE001 — unreadable index: keep the site
        return None
    return rows.to_dicts()


def _may_name(row: dict[str, Any], name: str) -> bool:
    """Whether another call row on the line could also be bound to ``name``."""
    if row.get("import_alias_name"):
        return True
    for text in (row.get("callee_full"), row.get("callee_name")):
        segment = trailing_segment(str(text or ""))
        if segment is None or segment.strip() == name:
            return True
    return False


def graph_bindings(
    get_graph: Callable[[], tuple[Any, str]],
    cache: Any,
    project_root: str | None,
    name: str,
    file_path: str | None,
    *,
    qualified: bool,
    declaring: tuple[str, ...] | None,
    listed: list[dict[str, Any]],
) -> GraphBindings | None:
    """The answer's bindings view; None when its target set cannot be read.

    A qualified query is about the definitions the graph resolves it to; a bare
    one about every definition of the name in the declaring files.
    """
    if cache is None or not project_root:
        return None
    try:
        graph = get_graph()[0]
        if qualified:
            targets = list(graph.resolve_targets(name, file_path))
        elif declaring is None:
            return None
        else:
            targets = [
                ref
                for path in declaring
                for ref in graph.function_refs_in_file(path)
                if ref.name == name
            ]
    except Exception as exc:  # noqa: BLE001 — unreadable graph: keep every site
        raise_if_interrupted(exc)
        return None
    if not targets:
        return None
    return GraphBindings(graph, cache, project_root, targets, listed)


def drop_graph_bound(
    bindings: GraphBindings | None,
    unresolved: list[dict[str, Any]] | None,
    excluded: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None, int]:
    """Declaring-file guard: move graph-bound sites into ``excluded``."""
    if bindings is None or unresolved is None or excluded is None:
        return unresolved, excluded, 0
    kept, dropped = bindings.partition(unresolved)
    if not dropped:
        return unresolved, excluded, 0
    merged = sorted([*excluded, *dropped], key=lambda s: (s["file"], s["line"]))
    return kept, merged, len(dropped)


__all__ = [
    "BOUND_ELSEWHERE_REASON",
    "LISTED_EDGE_REASON",
    "MAX_SITES",
    "GraphBindings",
    "drop_graph_bound",
    "graph_bindings",
]
