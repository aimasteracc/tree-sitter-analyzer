"""Frozen-index inputs used by read-only constraint evaluation."""

from __future__ import annotations

import os
from collections.abc import Callable

from .diff_snapshot_epoch import FrozenGitEnvironment
from .frozen_git_index import frozen_index_output
from .git_path_codec import path_to_raw, raw_to_path
from .git_subprocess import run_git_bounded
from .languages.lang_extension_map import EXT_TO_LANG
from .source_oracle import SafePath, SourceOracleError
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


def _constraint_error(exc: SourceOracleError) -> str:
    code = str(exc)
    if code.startswith("CONSTRAINT_CONFIG_"):
        return code
    if code == "DIFF_SNAPSHOT_CAPACITY":
        return "CONSTRAINT_CONFIG_CAPACITY"
    return "CONSTRAINT_CONFIG_UNSAFE"


def live_constraint_config(
    root: str,
    deadline: float,
    reader: Callable[..., SafePath],
) -> tuple[str | None, bytes | None, tuple[bytes, ...], str | None]:
    """Capture optional constraint evidence without gating generic snapshots."""
    try:
        for candidate in (
            "architectural-constraints.yml",
            ".tree-sitter-analyzer/constraints.yml",
        ):
            probe = reader(
                root,
                candidate,
                deadline=deadline,
                limit=1024 * 1024,
                allow_directory=True,
            )
            if probe.kind in {"missing", "directory"}:
                continue
            if probe.kind != "file" or probe.data is None:
                raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
            return candidate, probe.data, probe.metadata, None
        return None, None, (), None
    except SourceOracleError as exc:
        return None, None, (), _constraint_error(exc)


def staged_constraint_config(
    root: str,
    epoch: GitEpoch,
    deadline: float,
    storage_limit: int,
    reader: Callable[
        ..., tuple[str | None, bytes | None, tuple[bytes, ...]]
    ] = frozen_index_constraint_config,
) -> tuple[str | None, bytes | None, tuple[bytes, ...], str | None]:
    """Capture optional staged constraint evidence without gating other consumers."""
    try:
        path, data, metadata = reader(root, epoch, deadline, storage_limit)
        return path, data, metadata, None
    except SourceOracleError as exc:
        return None, None, (), _constraint_error(exc)


def _ignored_submodule_sources(
    root: str, epoch: GitEpoch, deadline: float, limit: int
) -> tuple[bytes, ...]:
    """Return ignored supported leaves or uncertifiable live gitlinks."""
    gitlinks = tuple(
        path
        for path, entry in epoch.index_map().items()
        if entry.startswith(b"160000 ")
    )
    if not gitlinks:
        return ()
    if not os.path.isfile(os.path.join(root, ".gitmodules")):
        # A legacy/manually staged gitlink can still be an initialized nested
        # repository. Without configuration it cannot be enumerated by Git;
        # conservatively prevent a staged consumer from borrowing its live graph.
        return gitlinks
    script = (
        'printf "H\\0%s\\0" "$displaypath"; '
        "git ls-files --others --ignored --exclude-standard -t -z"
    )
    raw = run_git_bounded(
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
    # A configured gitlink that foreach could not visit also cannot certify
    # staged/live equivalence (for example incomplete initialization metadata).
    supported.extend(path for path in gitlinks if path not in visited)
    return tuple(supported)


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
    if _ignored_submodule_sources(root, epoch, deadline, limit):
        return False
    indexed_paths = epoch.index_map()
    for raw in paths:
        path = raw_to_path(raw)
        if EXT_TO_LANG.get(os.path.splitext(path)[1].lower()) is not None:
            return False
        entry = indexed_paths.get(raw)
        if entry is not None and entry.startswith(b"160000 "):
            # The live full-index walker can index supported descendants of a
            # submodule. Any dirty gitlink therefore diverges from stage zero
            # even though Git reports only the extensionless container path.
            return False
    return True
