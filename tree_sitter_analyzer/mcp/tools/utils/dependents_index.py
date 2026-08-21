"""RFC-0025 Layer 1: incremental derivation of a file's dependents.

``edit action=safe`` is the call an agent makes before every edit, and the
question it cannot answer cheaply is *who imports this file*. Before this
module that answer was re-derived on every call by walking the whole tree,
reading every source file, and substring-matching the target's basename
(``safe_to_edit_helpers._target_dependents``). Two things were wrong with it:

* **Cost.** A cProfile of one warm ``edit action=safe`` on this repository
  attributed 2.026 s of 3.739 s to ``Path.read_text`` over 5,799 calls, ~956 ms
  of it inside the dependents walk. The L6.1 answer cache makes a *repeat*
  question cheap, but every edit bumps the generation, so the first call after
  each edit — the only call the edit loop actually makes — paid it again.
* **Precision.** The needle set includes the target's bare basename, so any
  file merely *mentioning* the word counted. Measured against a
  filesystem-confirmed resolver over 10 targets in this repository: 821
  reported dependents, 39 genuine, **782 false**. ``cache/schema.py`` reported
  479 dependents; 7 import it.

This module derives the answer from the persisted AST index instead:
``ast_index.imports_json`` already holds every file's import statements for
every language whose plugin extracts them. The tree is still enumerated — with
``os.scandir`` and no reads — because completeness requires accounting for
files the index has never seen. Only files the index cannot vouch for are
read, which makes the derivation incremental per changed file.

Freshness contract
------------------
A row vouches for a file when ``(mtime_ns, file_size)`` match the live entry.
That is the same predicate ``incremental_sync_support.file_changed`` uses to
decide what to re-index, so this path cannot disagree with the writer about
what "unchanged" means. It is deliberately *stricter*: ``file_changed`` falls
back to a content hash when only the mtime moved and may still conclude
"unchanged", whereas any mismatch here sends the file to the delta and it is
read. The residual hole is a mtime-preserving same-size replacement
(``tar -x``, ``cp -p``, ``rsync --times``); RFC-0027 §L6.1 records the same
residual for the answer-cache stamp. The RFC-0025 watch loop closes it; this
module does not attempt to.

Certification
-------------
The ``call-graph-built`` marker is honoured as a **label, not a gate**. It
certifies the call-edge pipeline, and this answer reads no call edges: it reads
``ast_index.imports_json``, verified per file against the live tree. Refusing
to answer on a revoked marker would make the pre-edit gate unusable — measured
on a stock checkout of this repository, ``--full-index`` exits 1 with
``verdict=WARN`` and ``built=0`` purely because two optional grammars (Swift,
Lua) are not installed, which has nothing to do with Python import edges. So a
revoked marker yields the derived answer with ``certified=False`` and
``certification_reason="CALL_GRAPH_INCOMPLETE"``, never a silently smaller set
and never a silently authoritative one.

Known coverage gap (unchanged by this module, and not claimed to be fixed):
Go, Rust and C/C++ include syntax is resolved by neither the derived path nor
the scan it replaces, so those files contribute no dependents in either. They
are not reported as ``unestablished`` because that field tracks *this call's*
failures, not a pre-existing language gap.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .safe_to_edit_helpers import (
    _DEPENDENCY_SKIP_DIRS,
    _DEPENDENCY_SOURCE_EXTS,
    _extract_import_specs,
    _import_targets_from_text,
    _module_path_without_suffix,
    _resolve_import_spec,
    _target_dependents_by_scan,
)

logger = logging.getLogger(__name__)

#: Above this many files the index is too far behind to be an incremental
#: derivation, and reading them one by one would cost more than the scan it
#: replaces. The scan is a proven superset, so falling back to it is the safe
#: direction.
DELTA_READ_CAP = 400

Basis = Literal["index", "index_delta", "scan"]


@dataclass(frozen=True)
class DependentsAnswer:
    """One dependents set plus how completely it was established."""

    dependents: frozenset[str]
    basis: Basis
    certified: bool
    certification_reason: str | None
    scanned_files: int
    delta_files: int
    unestablished: tuple[str, ...]


def prefilter_needles(target_rel: str) -> frozenset[str]:
    """Return substrings that every import naming *target_rel* must contain.

    This is a **soundness-critical superset**: an import statement that
    resolves to the target and contains none of these would be dropped before
    the exact resolver ever saw it, which is the dangerous direction.

    The target's own module path is not sufficient. Three forms name a file
    without containing it:

    * ``from .. import pkg`` names ``pkg/__init__.py``,
    * ``import x from "./dir"`` names ``dir/index.ts``,
    * ``import com.foo.*;`` names ``com/foo/Bar.java``.

    All three contain the file's parent directory name, so that token is added
    for exactly those three shapes. It is *not* added otherwise: the parent of
    a top-level module is the distribution package itself
    (``tree_sitter_analyzer``), which appears in nearly every import statement
    in the repository, and adding it made the filter select ~everything —
    measured at a 0.3x slowdown before this restriction. Every other import
    form must spell the file's own stem.
    """
    path = Path(target_rel)
    stem = _module_path_without_suffix(path).name
    needles = {stem}
    if stem in {"__init__", "index"} or path.suffix.lower() == ".java":
        needles.add(path.parent.name)
    return frozenset(token for token in needles if token)


def scan_dependents(target_rel: str, root: Path) -> frozenset[str]:
    """Return the legacy whole-tree scan answer (a superset, and slow)."""
    return frozenset(_target_dependents_by_scan(root / target_rel, target_rel, root))


def _live_inventory(root: Path) -> dict[str, tuple[int, int]]:
    """Map repo-relative path to ``(mtime_ns, size)`` without reading a file.

    ``os.scandir`` carries the stat data the directory enumeration already
    returned, so freshness verification costs no extra syscall per file.
    """
    inventory: dict[str, tuple[int, int]] = {}
    stack = [str(root)]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if entry.name not in _DEPENDENCY_SKIP_DIRS:
                    stack.append(entry.path)
                continue
            if Path(entry.name).suffix.lower() not in _DEPENDENCY_SOURCE_EXTS:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            rel = os.path.relpath(entry.path, root).replace("\\", "/")
            inventory[rel] = (stat.st_mtime_ns, stat.st_size)
    return inventory


def _fresh_rows(
    conn: sqlite3.Connection, inventory: dict[str, tuple[int, int]], root: Path
) -> set[str]:
    """Return the inventory paths whose index row matches the live file.

    Rows for in-scope extensions that this module's enumeration did not produce
    are *reconciled*, not ignored. Two things can cause them: the file was
    deleted (harmless), or the enumeration disagrees with the indexer's — for
    example ``os.walk`` follows a symlinked directory and this module's
    ``is_dir(follow_symlinks=False)`` does not. The second case would drop a
    real dependent, which is the dangerous direction, so any such row that
    still resolves to a file is added to the inventory and read. The stat cost
    is bounded by the number of rows *absent* from the enumeration, which is
    zero on a tree the enumeration covers.
    """
    fresh: set[str] = set()
    for file_path, mtime_ns, file_size in conn.execute(
        "SELECT file_path, mtime_ns, file_size FROM ast_index"
    ):
        rel = str(file_path).replace("\\", "/")
        live = inventory.get(rel)
        if live is None:
            if (
                Path(rel).suffix.lower() in _DEPENDENCY_SOURCE_EXTS
                and (root / rel).is_file()
            ):
                # Enumeration gap, not a deletion: force it into the delta.
                inventory[rel] = (-1, -1)
            continue
        if live == (int(mtime_ns or 0), int(file_size or 0)):
            fresh.add(rel)
    return fresh


def _indexed_candidates(
    conn: sqlite3.Connection, needles: frozenset[str], fresh: set[str]
) -> list[tuple[str, str]]:
    """Return ``(rel_path, imports_json)`` for fresh rows passing the prefilter.

    ``instr`` rather than ``LIKE``: an underscore is a ``LIKE`` wildcard and
    module names are full of them, so ``LIKE`` would need escaping to mean what
    a substring test means. ``instr`` is already a byte-exact substring test.
    """
    ordered = sorted(needles)
    if not ordered:
        return []
    clause = " OR ".join("instr(imports_json, ?) > 0" for _ in ordered)
    rows = conn.execute(
        f"SELECT file_path, imports_json FROM ast_index WHERE {clause}",  # noqa: S608
        tuple(ordered),
    )
    candidates: list[tuple[str, str]] = []
    for file_path, imports_json in rows:
        rel = str(file_path).replace("\\", "/")
        if rel in fresh:
            candidates.append((rel, imports_json or "[]"))
    return candidates


def _imports_name_target(
    imports_json: str,
    importer_rel: str,
    target_rel: str,
    inventory_set: frozenset[str],
    needles: frozenset[str],
) -> bool | None:
    """Resolve one file's projected imports. ``None`` means unparseable.

    The SQL prefilter matched the file's whole import blob; most individual
    statements in that blob still cannot name the target, so the same
    soundness-preserving needle test is applied per statement before paying for
    the exact resolver.
    """
    try:
        entries = json.loads(imports_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(entries, list):
        return None
    for entry in entries:
        text = entry.get("text", "") if isinstance(entry, dict) else ""
        if not text or not any(needle in text for needle in needles):
            continue
        if target_rel in _import_targets_from_text(text, importer_rel, inventory_set):
            return True
    return False


def _read_imports_target(importer_rel: str, target_rel: str, root: Path) -> bool | None:
    """Establish one file's imports by reading it. ``None`` means unreadable."""
    try:
        source = (root / importer_rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    suffix = Path(importer_rel).suffix.lower()
    for spec in _extract_import_specs(source, suffix):
        if _resolve_import_spec(spec, importer_rel, root) == target_rel:
            return True
    return False


def _scan_answer(
    target_rel: str, root: Path, reason: str, scanned: int
) -> DependentsAnswer:
    return DependentsAnswer(
        dependents=scan_dependents(target_rel, root),
        basis="scan",
        certified=False,
        certification_reason=reason,
        scanned_files=scanned,
        delta_files=0,
        unestablished=(),
    )


def _marker_is_current(conn: sqlite3.Connection) -> bool:
    """Read the marker row only, not the call-edge consistency scan.

    ``call_graph_marker_is_current`` also runs ``call_graph_edges_are_consistent``,
    which walks every ``edges`` row — 185,952 of them on this repository, and
    measured at 5-14 s per call, dominating everything else this module does.
    That scan certifies that resolved *call* targets are not dangling. This
    answer reads no call edges, so the scan is irrelevant to it; the marker row
    is the part that says "the pipeline certified itself at the current
    version", and that is what the label reports.
    """
    from ....cache.callgraph_state import exact_call_graph_marker

    try:
        return bool(exact_call_graph_marker(conn))
    except sqlite3.DatabaseError:
        return False


def resolve_dependents(target_rel: str, root: Path) -> DependentsAnswer:
    """Return who imports *target_rel*, derived from the persisted index.

    The tree is enumerated (stat only) so that a file the index has never seen
    is still accounted for; only files the index cannot vouch for are read.
    """
    root = Path(root)
    target_rel = target_rel.replace("\\", "/")
    db_path = root / ".ast-cache" / "index.db"
    inventory = _live_inventory(root)
    if not db_path.is_file():
        return _scan_answer(target_rel, root, "INDEX_ABSENT", len(inventory))

    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error:
        return _scan_answer(target_rel, root, "INDEX_UNREADABLE", len(inventory))
    try:
        return _derive(conn, target_rel, root, inventory)
    except sqlite3.DatabaseError:
        logger.debug("dependents index unreadable; falling back", exc_info=True)
        return _scan_answer(target_rel, root, "INDEX_UNREADABLE", len(inventory))
    finally:
        conn.close()


def _derive(
    conn: sqlite3.Connection,
    target_rel: str,
    root: Path,
    inventory: dict[str, tuple[int, int]],
) -> DependentsAnswer:
    """Derive the answer from *conn*, reading only what the index cannot cover."""
    fresh = _fresh_rows(conn, inventory, root)
    inventory_set = frozenset(inventory)
    if target_rel not in inventory_set:
        # The resolvers can only name a file that is in the inventory, so an
        # out-of-scope target (``.cs``, ``.rb``, ``.kt``, ``.swift``, ...) would
        # yield an empty set that *looks* like a proven "nothing imports this".
        # The scan is not a usable fallback here either: it only reads
        # in-scope extensions, so every match it reports for such a target is a
        # prose match by construction. Report the empty set as unestablished.
        return DependentsAnswer(
            dependents=frozenset(),
            basis="index",
            certified=False,
            certification_reason="TARGET_OUT_OF_SCOPE",
            scanned_files=len(inventory),
            delta_files=0,
            unestablished=(target_rel,),
        )
    delta = sorted(rel for rel in inventory if rel not in fresh and rel != target_rel)
    if len(delta) > DELTA_READ_CAP:
        return _scan_answer(target_rel, root, "DELTA_CAP_EXCEEDED", len(inventory))

    needles = prefilter_needles(target_rel)
    dependents: set[str] = set()
    unestablished: list[str] = []
    extra_delta: list[str] = []
    for rel, imports_json in _indexed_candidates(conn, needles, fresh):
        if rel == target_rel:
            continue
        named = _imports_name_target(
            imports_json, rel, target_rel, inventory_set, needles
        )
        if named is None:
            extra_delta.append(rel)
        elif named:
            dependents.add(rel)

    for rel in [*delta, *extra_delta]:
        named = _read_imports_target(rel, target_rel, root)
        if named is None:
            unestablished.append(rel)
        elif named:
            dependents.add(rel)

    delta_files = len(delta) + len(extra_delta)
    marker_current = _marker_is_current(conn)
    if unestablished:
        reason: str | None = "UNESTABLISHED_FILES"
    elif not marker_current:
        reason = "CALL_GRAPH_INCOMPLETE"
    else:
        reason = None
    return DependentsAnswer(
        dependents=frozenset(dependents),
        basis="index_delta" if delta_files else "index",
        certified=reason is None,
        certification_reason=reason,
        scanned_files=len(inventory),
        delta_files=delta_files,
        unestablished=tuple(sorted(unestablished)),
    )
