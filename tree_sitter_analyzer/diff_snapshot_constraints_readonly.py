"""RFC-0022 P0.4 zero-write staged constraint probes (Phase A groundwork).

The frozen staged probes (``diff_snapshot_constraints``) read the captured
index through a temporary index/object store (P0.2 allows this). These
variants reproduce the same evidence with zero filesystem writes: the
constraint file blob is read with ``git cat-file`` against the live object
database, and the staged-sources match check runs the same diff-files /
ls-files invocation set read-only against the live index with
``GIT_OPTIONAL_LOCKS=0``.
"""

from __future__ import annotations

import os

from .diff_snapshot_constraints import _entry_parts
from .diff_snapshot_readonly import _live_index_output
from .diff_snapshot_readonly_capture import _blob_readonly
from .git_path_codec import path_to_raw, raw_to_path
from .git_readonly import run_git_readonly
from .languages.lang_extension_map import EXT_TO_LANG
from .source_oracle import SourceOracleError
from .source_oracle_git import GitEpoch


def frozen_index_constraint_config_readonly(
    root: str, epoch: GitEpoch, deadline: float, storage_limit: int
) -> tuple[str | None, bytes | None, tuple[bytes, ...]]:
    """Read constraint discovery and bytes from the captured stage-zero index.

    Identical evidence to the frozen probe, but the blob comes from the
    live object database through the zero-write runner.
    """
    entries = epoch.index_map()
    for candidate in (
        "architectural-constraints.yml",
        ".tree-sitter-analyzer/constraints.yml",
    ):
        raw = path_to_raw(candidate)
        entry = entries.get(raw)
        if entry is None:
            continue
        mode, oid, kind = _entry_parts(entry)
        if mode not in ("100644", "100755") or oid is None or kind != "file":
            raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
        data = _blob_readonly(root, oid, kind, deadline, 1024 * 1024)
        if data is None:
            raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
        return candidate, data, (raw + b"\0" + entry,)
    return None, None, ()


def _ignored_submodule_sources_readonly(
    root: str, epoch: GitEpoch, deadline: float, limit: int
) -> tuple[bytes, ...]:
    """Return ignored supported leaves or uncertifiable live gitlinks.

    Mirrors ``diff_snapshot_constraints._ignored_submodule_sources`` with
    the zero-write runner for ``git submodule foreach``.
    """
    gitlinks = tuple(
        path
        for path, entry in epoch.index_map().items()
        if entry.startswith(b"160000 ")
    )
    if not gitlinks:
        return ()
    if not os.path.isfile(os.path.join(root, ".gitmodules")):
        return gitlinks
    script = (
        'printf "H\\0%s\\0" "$displaypath"; '
        "git ls-files --others --ignored --exclude-standard -t -z"
    )
    raw = run_git_readonly(
        root,
        ["submodule", "foreach", "--recursive", "--quiet", script],
        deadline=deadline,
        limit=limit,
    )
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    supported: list[bytes] = []
    visited: set[bytes] = set()
    prefix: bytes | None = None
    index = 0
    while index < len(fields):
        field = fields[index]
        if field == b"H":
            index += 1
            if index >= len(fields):
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            prefix = fields[index]
            visited.add(prefix)
            index += 1
            continue
        if prefix is None or not field.startswith(b"? "):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        leaf = field[2:]
        path = raw_to_path(prefix + b"/" + leaf)
        if EXT_TO_LANG.get(os.path.splitext(path)[1].lower()) is not None:
            supported.append(prefix + b"/" + leaf)
        index += 1
    supported.extend(path for path in gitlinks if path not in visited)
    return tuple(supported)


def frozen_index_sources_match_worktree_readonly(
    root: str, epoch: GitEpoch, deadline: float, limit: int
) -> bool:
    """Return whether every supported source has the same index/worktree plane.

    The frozen probe refreshes a temporary index whose stat cache is fully
    invalidated; with ``GIT_OPTIONAL_LOCKS=0`` that refresh is skipped, so
    the frozen probe's dirty set is *every* tracked path. The zero-write
    variant reproduces that exact effective semantic without any stat
    machinery: any supported-language tracked path (or untracked path, or
    uncertifiable gitlink) makes the check fail.
    """
    paths: set[bytes] = set(epoch.index_map())
    untracked_raw = _live_index_output(
        root,
        epoch.index_bytes,
        ["ls-files", "--others", "-z"],
        deadline=deadline,
        limit=limit,
    )
    paths.update(path for path in untracked_raw.split(b"\0") if path)
    if _ignored_submodule_sources_readonly(root, epoch, deadline, limit):
        return False
    indexed_paths = epoch.index_map()
    for raw in paths:
        path = raw_to_path(raw)
        if EXT_TO_LANG.get(os.path.splitext(path)[1].lower()) is not None:
            return False
        entry = indexed_paths.get(raw)
        if entry is not None and entry.startswith(b"160000 "):
            return False
    return True
