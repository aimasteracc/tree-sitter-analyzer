"""Locate the opt-in SCIP index, prove it describes the project, and map the target.

Opt in by either:

* ``TSA_SCIP_INDEX=<path>`` (relative paths are taken from the project root), or
* a file at ``<project>/.ast-cache/scip/index.scip``.

Without either, :func:`open_source` returns ``None`` and ``nav action=callers``
answers exactly as without this module (no field, no check). With either, the
answer carries ``scip.status``:

=========================  ===================================================
``used``                   the index and its manifest describe the project
``stale``                  the manifest is missing or no longer matches the
                           project (another commit, edited / untracked files,
                           a changed lockfile, a rewritten index)
``absent``                 ``TSA_SCIP_INDEX`` names a file that does not exist
``invalid``                the index or the manifest cannot be decoded, or the
                           index was not written by a supported indexer
``unsupported_language``   the target is not TypeScript / JavaScript
=========================  ===================================================

Only ``used`` yields evidence; every other status leaves the answer as it is.
"""

from __future__ import annotations

import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import callers_scip_symbols as sym
from .callers_scip_index import ScipFormatError, ScipIndex, parse_index
from .callers_scip_manifest import (
    ManifestError,
    file_sha256,
    manifest_path,
    project_state,
    read_manifest,
    stale_reason,
)
from .callers_scip_trust import TargetContext, TypeGraph, target_context

INDEX_ENV = "TSA_SCIP_INDEX"
DEFAULT_INDEX = Path(".ast-cache") / "scip" / "index.scip"

USED = "used"
STALE = "stale"
ABSENT = "absent"
INVALID = "invalid"
UNSUPPORTED_LANGUAGE = "unsupported_language"

#: Target files the TS / JS trust rules cover.
SUPPORTED_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
SUPPORTED_INDEXERS = frozenset({"scip-typescript"})
#: Decoded indexes kept in memory, keyed by the index file's sha256.
_PARSED_CAP = 2
_PARSED: OrderedDict[str, tuple[ScipIndex, TypeGraph]] = OrderedDict()
#: scip-typescript names a class constructor ``<constructor>``.
_CONSTRUCTOR = {"<constructor>": "constructor"}


@dataclass
class ScipSource:
    """The opt-in state of one query, and the mapped target when ``used``."""

    status: str
    project_root: Path
    detail: str | None = None
    index_path: Path | None = None
    index: ScipIndex | None = None
    graph: TypeGraph | None = None
    targets: frozenset[str] = frozenset()
    #: ``None`` when mapped, else why the target has no SCIP symbol.
    unmapped: str | None = None
    context: TargetContext | None = None
    _lines: dict[str, list[str]] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.status == USED and self.unmapped is None and self.index is not None

    def lines(self, path: str) -> list[str]:
        """Source lines of a project file (the manifest proved they match the index)."""
        found = self._lines.get(path)
        if found is None:
            try:
                text = (self.project_root / path).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                text = ""
            found = text.splitlines()
            self._lines[path] = found
        return found

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status}
        if self.detail:
            out["detail"] = self.detail
        if self.index is not None:
            out["indexer"] = f"{self.index.tool_name} {self.index.tool_version}".strip()
        if self.status == USED:
            out["target"] = (
                {"mapped": True, "symbols": sorted(self.targets)}
                if self.unmapped is None
                else {"mapped": False, "reason": self.unmapped}
            )
        return out


def locate(project_root: Path) -> tuple[Path | None, bool]:
    """``(index path, named by the environment)``; ``(None, False)`` = not opted in."""
    value = os.environ.get(INDEX_ENV, "").strip()
    if value:
        path = Path(value)
        return (path if path.is_absolute() else project_root / path), True
    default = project_root / DEFAULT_INDEX
    return (default, False) if default.is_file() else (None, False)


def _decoded(index_path: Path, sha: str) -> tuple[ScipIndex, TypeGraph]:
    cached = _PARSED.get(sha)
    if cached is not None:
        _PARSED.move_to_end(sha)
        return cached
    index = parse_index(index_path.read_bytes())
    entry = (index, TypeGraph(index))
    _PARSED[sha] = entry
    while len(_PARSED) > _PARSED_CAP:
        _PARSED.popitem(last=False)
    return entry


def open_source(
    project_root: str | None, file_path: str | None, func_name: str, qualified: bool
) -> ScipSource | None:
    """The SCIP state for one callers query; ``None`` when SCIP is not opted in."""
    if not project_root:
        return None
    root = Path(project_root)
    index_path, from_env = locate(root)
    if index_path is None:
        return None
    if not str(file_path or "").lower().endswith(SUPPORTED_SUFFIXES):
        return ScipSource(UNSUPPORTED_LANGUAGE, root, index_path=index_path)
    if not index_path.is_file():
        detail = f"{INDEX_ENV} names a missing file" if from_env else None
        return ScipSource(ABSENT, root, detail=detail, index_path=index_path)
    try:
        manifest = read_manifest(manifest_path(index_path))
    except ManifestError as exc:
        missing = not manifest_path(index_path).exists()
        status = STALE if missing else INVALID
        return ScipSource(status, root, detail=str(exc), index_path=index_path)
    try:
        sha = file_sha256(index_path)
    except OSError as exc:
        return ScipSource(INVALID, root, detail=str(exc), index_path=index_path)
    state = project_state(root, exclude=(index_path, manifest_path(index_path)))
    reason = stale_reason(manifest, sha, state)
    if reason is not None:
        return ScipSource(STALE, root, detail=reason, index_path=index_path)
    try:
        index, graph = _decoded(index_path, sha)
    except (ScipFormatError, OSError) as exc:
        return ScipSource(INVALID, root, detail=str(exc), index_path=index_path)
    if index.tool_name not in SUPPORTED_INDEXERS:
        return ScipSource(
            INVALID,
            root,
            detail=f"unsupported indexer {index.tool_name!r}",
            index_path=index_path,
            index=index,
        )
    source = ScipSource(USED, root, index_path=index_path, index=index, graph=graph)
    rel = str(file_path).replace("\\", "/")
    targets, unmapped = map_target(index, rel, func_name, qualified)
    source.targets, source.unmapped = targets, unmapped
    if unmapped is None:
        source.context = target_context(graph, targets)
    return source


def member_name(symbol: str) -> str | None:
    """The member name TSA uses for a SCIP symbol (``<constructor>`` -> ``constructor``)."""
    name = sym.last_name(symbol)
    return _CONSTRUCTOR.get(name, name) if name is not None else None


_DEFINABLE = frozenset({"method", "term", "type"})
_QUOTED = re.compile(r'^"(.*)"$')


def _parts(func_name: str) -> list[str]:
    return [_QUOTED.sub(r"\1", part) for part in func_name.split(".") if part]


def map_target(
    index: ScipIndex, file_path: str, func_name: str, qualified: bool
) -> tuple[frozenset[str], str | None]:
    """The target's SCIP symbols in its declaring file, or why there are none.

    Qualified ``Class.member``: exactly one symbol whose type / term / method
    path ends with the query path (several = ambiguous: no evidence). Bare
    ``name``: every definition named ``name`` in the file, the same union TSA
    answers for a bare name with several same-named definitions.
    """
    if file_path not in index.documents:
        return frozenset(), "file_not_indexed"
    parts = _parts(func_name)
    if not parts:
        return frozenset(), "not_found"
    found: set[str] = set()
    for occ in index.documents[file_path]:
        if not occ.is_definition or sym.last_kind(occ.symbol) not in _DEFINABLE:
            continue
        names = sym.qual_names(occ.symbol) or []
        if names and member_name(occ.symbol) is not None:
            names = [*names[:-1], member_name(occ.symbol) or ""]
        if qualified:
            if len(names) >= len(parts) and names[-len(parts) :] == parts:
                found.add(occ.symbol)
        elif names and names[-1] == parts[-1] and sym.last_kind(occ.symbol) != "type":
            found.add(occ.symbol)
    if not found:
        return frozenset(), "not_found"
    if qualified:
        shortest = min(len(sym.qual_names(s) or []) for s in found)
        found = {s for s in found if len(sym.qual_names(s) or []) == shortest}
        if len(found) != 1:
            return frozenset(), "ambiguous"
    return frozenset(found), None


__all__ = [
    "ABSENT",
    "DEFAULT_INDEX",
    "INDEX_ENV",
    "INVALID",
    "STALE",
    "SUPPORTED_SUFFIXES",
    "UNSUPPORTED_LANGUAGE",
    "USED",
    "ScipSource",
    "locate",
    "map_target",
    "member_name",
    "open_source",
]
