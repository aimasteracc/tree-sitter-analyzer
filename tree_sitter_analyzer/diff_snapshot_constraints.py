"""Frozen-index inputs used by read-only constraint evaluation."""

from __future__ import annotations

import os

from .diff_snapshot_epoch import FrozenGitEnvironment
from .frozen_git_index import frozen_index_output
from .git_path_codec import path_to_raw, raw_to_path
from .languages.lang_extension_map import EXT_TO_LANG
from .source_oracle import SourceOracleError
from .source_oracle_git import GitEpoch


def _entry_parts(entry: bytes | None) -> tuple[str | None, str | None, str]:
    if entry is None:
        return None, None, "missing"
    fields = entry.split(b" ")
    if len(fields) < 2:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    mode = fields[0].decode("ascii", "strict")
    oid_field = fields[1] if len(fields) == 3 and fields[2] == b"0" else fields[-1]
    oid = oid_field.decode("ascii", "strict")
    kind = "gitlink" if mode == "160000" else "symlink" if mode == "120000" else "file"
    return mode, oid, kind


def _blob(
    git: FrozenGitEnvironment, oid: str | None, kind: str, limit: int
) -> bytes | None:
    if oid is None or kind == "gitlink":
        return None
    return git.run(["cat-file", "blob", oid], limit=limit)


def frozen_index_constraint_config(
    root: str, epoch: GitEpoch, deadline: float, storage_limit: int
) -> tuple[str | None, bytes | None, tuple[bytes, ...]]:
    """Read constraint discovery and bytes from the captured stage-zero index."""
    entries = epoch.index_map()
    with FrozenGitEnvironment(root, epoch, deadline, storage_limit) as git:
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
            data = _blob(git, oid, kind, 1024 * 1024)
            if data is None:
                raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
            return candidate, data, (raw + b"\0" + entry,)
    return None, None, ()


def frozen_index_sources_match_worktree(
    root: str, epoch: GitEpoch, deadline: float, limit: int
) -> bool:
    """Return whether every supported source has the same index/worktree plane."""
    dirty_raw = frozen_index_output(
        root,
        epoch.index_bytes,
        [
            "diff-files",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
        ],
        deadline=deadline,
        limit=limit,
        refresh=True,
        clear_hints=True,
        object_format=epoch.object_format,
    )
    untracked_raw = frozen_index_output(
        root,
        epoch.index_bytes,
        ["ls-files", "--others", "-z"],
        deadline=deadline,
        limit=limit,
        object_format=epoch.object_format,
    )
    paths = {path for path in dirty_raw.split(b"\0") if path}
    paths.update(path for path in untracked_raw.split(b"\0") if path)
    for raw in paths:
        path = raw_to_path(raw)
        if EXT_TO_LANG.get(os.path.splitext(path)[1].lower()) is not None:
            return False
    return True
