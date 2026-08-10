"""Git inventory and source-generation helpers for the source oracle."""

from __future__ import annotations

import hashlib
import os
import subprocess  # nosec B404
import tempfile
import time
from typing import Any

from .frozen_git_index import (
    frozen_index_entries,
    frozen_index_output,
    git_filtered_oid,
    has_split_index,
    invalidate_index_stat_cache,
    reject_frozen_filters,
)
from .frozen_git_settings import capture_frozen_git_settings as capture_settings
from .git_subprocess import run_git_bounded
from .source_epoch import (
    _EMPTY_TREE_SHA1,
    _EMPTY_TREE_SHA256,
    GitEpoch,
    capture_source_epoch,
    core_bool,
    raw_blob_oid,
)
from .source_oracle import (
    RootIdentity,
    SourceOracleError,
    WorkspaceManifestEntry,
    _safe_absolute_regular,
    _supports_nofollow,
    canonical_root,
    normalize_repo_path,
    safe_workspace_path,
    stable_descriptor_chain,
)
from .source_oracle_consistency import (
    capture_consistent as capture_consistent,
)
from .source_oracle_consistency import source_generation as source_generation

_FRAME_DOMAIN = b"tsa-source-generation-v5"
_MAX_INVENTORY_BYTES = 16 * 1024 * 1024
_MAX_WORKTREE_PATHS = 200_000
_MAX_WORKTREE_CONTENT_BYTES = 64 * 1024 * 1024
_frozen_index_output = frozen_index_output


def git_output(root: str, args: list[str], *, deadline: float, limit: int) -> bytes:
    """Run Git fail-closed with a shared deadline and bounded retained output."""
    return run_git_bounded(
        root, args, deadline=deadline, limit=limit, popen=subprocess.Popen
    )


def _strip_one_record_terminator(value: bytes) -> bytes:
    if value.endswith(b"\r\n"):
        return value[:-2]
    return value[:-1] if value.endswith(b"\n") else value


def _object_format(root: str, *, deadline: float) -> str:
    value = git_output(
        root, ["rev-parse", "--show-object-format"], deadline=deadline, limit=64
    ).strip()
    if value not in (b"sha1", b"sha256"):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return value.decode("ascii")


def _core_filemode(root: str, *, deadline: float) -> bool:
    return core_bool(root, "core.filemode", deadline, git_output)


def _head_identity(
    root: str, *, deadline: float, object_format: str | None = None
) -> bytes:
    try:
        return git_output(
            root, ["rev-parse", "--verify", "HEAD"], deadline=deadline, limit=4096
        ).strip()
    except SourceOracleError as head_error:
        try:
            git_output(
                root, ["symbolic-ref", "-q", "HEAD"], deadline=deadline, limit=4096
            )
        except SourceOracleError as symbolic_error:
            raise head_error from symbolic_error
        fmt = object_format or _object_format(root, deadline=deadline)
        return _EMPTY_TREE_SHA256 if fmt == "sha256" else _EMPTY_TREE_SHA1


def _frame(digest: Any, label: bytes, value: bytes) -> None:
    update = digest.update
    update(len(label).to_bytes(4, "big") + label)
    update(len(value).to_bytes(8, "big") + value)


def _index_entries(
    root: str, *, deadline: float, index_bytes: bytes | None = None
) -> dict[bytes, bytes]:
    return frozen_index_entries(
        root,
        deadline=deadline,
        max_inventory_bytes=_MAX_INVENTORY_BYTES,
        max_paths=_MAX_WORKTREE_PATHS,
        index_bytes=index_bytes,
        git_output_fn=git_output,
        bounded_git_fn=run_git_bounded,
        popen=subprocess.Popen,
        mkstemp=tempfile.mkstemp,
        unlink=os.unlink,
    )


def _head_entries(
    root: str, *, deadline: float, head: bytes = b"HEAD"
) -> dict[bytes, bytes]:
    if head in (_EMPTY_TREE_SHA1, _EMPTY_TREE_SHA256):
        return {}
    raw = git_output(
        root,
        ["ls-tree", "-rz", "--full-tree", os.fsdecode(head)],
        deadline=deadline,
        limit=_MAX_INVENTORY_BYTES,
    )
    entries: dict[bytes, bytes] = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        header, separator, path = row.partition(b"\t")
        fields = header.split(b" ")
        if not separator or not path or len(fields) != 3:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        try:
            int(fields[0], 8)
            int(fields[2], 16)
        except ValueError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        if fields[1] not in (b"blob", b"commit") or path in entries:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        entries[path] = header
    if len(entries) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries


def _tracked_paths(root: str, *, deadline: float) -> list[bytes]:
    """List every tracked worktree path with exact bounded ``git ls-files -z``."""
    raw = git_output(
        root, ["ls-files", "-z"], deadline=deadline, limit=_MAX_INVENTORY_BYTES
    )
    paths = [path for path in raw.split(b"\0") if path]
    if len(paths) > _MAX_WORKTREE_PATHS or len(paths) != len(set(paths)):
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return paths


def capture_inventory(
    root: str, mode: str, *, deadline: float, limit: int
) -> tuple[str, ...]:
    """Capture the bounded scope-existence inventory inside an oracle epoch.

    Staged analysis is scoped to stage-zero index identities. Workspace analysis
    additionally includes Git's bounded untracked inventory. Callers must bracket
    this read with equal source generations and retain this tuple, never re-read
    the live filesystem when validating a frozen request.
    """
    tracked = _tracked_paths(root, deadline=deadline)
    raw_paths = set(tracked)
    if mode == "diff":
        untracked_raw = git_output(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            deadline=deadline,
            limit=min(_MAX_INVENTORY_BYTES, limit),
        )
        untracked = {path for path in untracked_raw.split(b"\0") if path}
        if untracked & raw_paths:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        raw_paths.update(untracked)
    if len(raw_paths) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    normalized: list[str] = []
    charged = 0
    for raw in sorted(raw_paths):
        path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
        encoded = os.fsencode(path)
        if len(encoded) > 4096:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        charged += len(encoded) + 1
        if charged > limit:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        normalized.append(path)
    return tuple(normalized)


def _frame_workspace_path(
    digest: Any,
    root: str,
    raw: bytes,
    *,
    deadline: float,
    content_budget: int,
    content_required: bool,
    index_entry: bytes | None,
    head_entry: bytes | None,
    core_symlinks: bool = True,
    object_format: str = "sha1",
    manifest: dict[str, WorkspaceManifestEntry] | None = None,
) -> int:
    path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
    is_gitlink = bool(index_entry and index_entry.split(b" ", 1)[0] == b"160000")
    safe = safe_workspace_path(
        root,
        path,
        deadline=deadline,
        limit=content_budget,
        read_regular=content_required and not is_gitlink,
        allow_directory=True,
    )
    _frame(digest, b"worktree-path", raw)
    descriptor_chain = stable_descriptor_chain(safe.metadata)
    filtered_oid: bytes | None = None
    index_mode = index_entry.split(b" ", 1)[0] if index_entry else None
    emulated_symlink = (
        not core_symlinks and safe.kind == "file" and index_mode == b"120000"
    )
    if safe.kind == "file" and content_required and not is_gitlink:
        filtered_oid = (
            raw_blob_oid(safe.data or b"", object_format)
            if emulated_symlink
            else git_filtered_oid(root, raw, safe.data or b"", deadline=deadline)
        )
        _frame(digest, b"worktree-filtered-oid", filtered_oid)
    if manifest is not None:
        manifest[path] = WorkspaceManifestEntry(descriptor_chain, filtered_oid)
    leaf_metadata = safe.metadata[-1:] if safe.kind != "missing" else ()
    ancestor_metadata = (
        safe.metadata[:-1] if safe.kind != "missing" else safe.metadata[:-1]
    )
    for descriptor in stable_descriptor_chain(tuple(ancestor_metadata)):
        _frame(digest, b"worktree-ancestor-identity", descriptor)
    if safe.kind == "missing":
        _frame(digest, b"worktree-kind", b"missing")
    else:
        fields = leaf_metadata[0].split(b",")
        if len(fields) != 6:  # pragma: no cover - safe reader invariant
            raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH")
        _frame(
            digest,
            b"worktree-stat",
            b",".join((fields[2], fields[0], fields[1], *fields[3:])),
        )
        effective_kind = "symlink" if emulated_symlink else safe.kind
        _frame(digest, b"worktree-kind", effective_kind.encode("ascii"))
    if index_entry is not None:
        _frame(digest, b"index-blob", index_entry)
    _frame(digest, b"HEAD-blob", head_entry or b"missing")
    if safe.kind == "symlink" or (content_required and not is_gitlink):
        data = safe.data or b""
        _frame(digest, b"worktree-content", hashlib.sha256(data).digest())
        return len(data)
    return 0


def oracle_generation(
    project_root: str | None,
    mode: str = "diff",
    *,
    deadline: float | None = None,
    manifest: dict[str, WorkspaceManifestEntry] | None = None,
    epoch_out: list[GitEpoch] | None = None,
) -> tuple[str, RootIdentity]:
    root, identity = canonical_root(project_root)
    if not _supports_nofollow():
        raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")
    end = deadline if deadline is not None else time.monotonic() + 35.0
    digest = hashlib.sha256()
    _frame(digest, b"domain", _FRAME_DOMAIN)
    _frame(digest, b"root", os.fsencode(identity.realpath))
    _frame(digest, b"root-stat", f"{identity.device},{identity.inode}".encode())
    top_level = git_output(
        root, ["rev-parse", "--show-toplevel"], deadline=end, limit=64 * 1024
    )
    top_level = _strip_one_record_terminator(top_level)
    try:
        top_root, top_identity = canonical_root(os.fsdecode(top_level))
    except (UnicodeError, SourceOracleError) as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH") from exc
    if top_root != root or top_identity != identity:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH")
    object_format = _object_format(root, deadline=end)
    core_filemode = _core_filemode(root, deadline=end)
    core_symlinks = core_bool(root, "core.symlinks", end, git_output)
    head = _head_identity(root, deadline=end, object_format=object_format)
    _frame(digest, b"object-format", object_format.encode("ascii"))
    _frame(digest, b"core-filemode", b"true" if core_filemode else b"false")
    _frame(digest, b"core-symlinks", b"true" if core_symlinks else b"false")
    _frame(digest, b"HEAD", head)
    git_dir = git_output(
        root, ["rev-parse", "--git-dir"], deadline=end, limit=64 * 1024
    )
    git_dir = _strip_one_record_terminator(git_dir)
    decoded_git_dir = os.fsdecode(git_dir)
    index_path = (
        os.path.join(decoded_git_dir, "index")
        if os.path.isabs(decoded_git_dir)
        else os.path.join(root, decoded_git_dir, "index")
    )
    # Missing is an empty index for born and unborn HEADs, and is framed exactly.
    safe_index = _safe_absolute_regular(
        index_path, deadline=end, limit=64 * 1024 * 1024, allow_missing=True
    )
    for descriptor in stable_descriptor_chain(safe_index.metadata):
        _frame(digest, b"index-descriptor-identity", descriptor)
    _frame(digest, b"index-state", safe_index.kind.encode("ascii"))
    index_bytes = safe_index.data or b""
    _frame(digest, b"index-content", hashlib.sha256(index_bytes).digest())
    if index_bytes and has_split_index(index_bytes, object_format=object_format):
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_INDEX")
    index_entries = _index_entries(root, deadline=end, index_bytes=index_bytes)
    tracked = list(index_entries)
    head_entries = _head_entries(root, deadline=end, head=head)
    dirty_raw = _frozen_index_output(
        root,
        index_bytes,
        [
            "diff-files",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
        ],
        deadline=end,
        limit=_MAX_INVENTORY_BYTES,
        refresh=True,
        object_format=object_format,
    )
    untracked_raw = _frozen_index_output(
        root,
        index_bytes,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        deadline=end,
        limit=_MAX_INVENTORY_BYTES,
    )
    dirty = {path for path in dirty_raw.split(b"\0") if path}
    untracked = {path for path in untracked_raw.split(b"\0") if path}
    if len(dirty | untracked) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    tracked_set = set(tracked)
    if not dirty <= tracked_set or untracked & tracked_set:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    filter_paths = tuple(sorted(dirty | untracked))
    if filter_paths:
        reject_frozen_filters(root, index_bytes, filter_paths, end, object_format)
    settings_inventory = tuple(sorted(tracked_set | untracked))
    frozen_settings = capture_settings(root, settings_inventory, end, git_output)
    settings_epoch = capture_source_epoch(
        root,
        index_bytes,
        settings_inventory,
        deadline=end,
        object_format=object_format,
        frozen_output=_frozen_index_output,
    )
    _frame(digest, b"attributes", settings_epoch.attribute_fingerprint)
    _frame(digest, b"config", settings_epoch.config_hash)
    _frame(digest, b"git-settings", frozen_settings.fingerprint)
    workspace_gitlinks: dict[bytes, bytes] = {}
    for raw in sorted(dirty) if mode == "diff" else ():
        entry = index_entries[raw]
        if not entry.startswith(b"160000 "):
            continue
        path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
        safe_gitlink = safe_workspace_path(
            root, path, deadline=end, limit=0, read_regular=False, allow_directory=True
        )
        if safe_gitlink.kind != "directory":
            continue
        submodule_root = os.path.join(root, os.fsdecode(raw))
        oid = _strip_one_record_terminator(
            git_output(
                submodule_root,
                ["rev-parse", "--verify", "HEAD"],
                deadline=end,
                limit=4096,
            )
        )
        try:
            int(oid, 16)
        except ValueError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        if len(oid) != len(head):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        workspace_gitlinks[raw] = b"160000 " + oid + b" 0"
        _frame(digest, b"worktree-gitlink-dirty", raw)
        _frame(digest, b"worktree-gitlink-head", raw + b"\0" + oid)
    if epoch_out is not None:
        epoch_out.append(
            GitEpoch(
                head=head,
                object_format=object_format,
                index_entries=tuple(sorted(index_entries.items())),
                tracked_paths=tuple(tracked),
                dirty_paths=tuple(sorted(dirty)),
                untracked_paths=tuple(sorted(untracked)),
                workspace_gitlinks=tuple(sorted(workspace_gitlinks.items())),
                core_filemode=core_filemode,
                core_symlinks=core_symlinks,
                index_bytes=index_bytes,
                source_epoch=settings_epoch,
                git_settings=frozen_settings,
            )
        )

    remaining_content = _MAX_WORKTREE_CONTENT_BYTES
    for raw in sorted(tracked, key=os.fsencode):
        charge = _frame_workspace_path(
            digest,
            root,
            raw,
            deadline=end,
            content_budget=remaining_content,
            content_required=mode == "diff" and raw in dirty,
            index_entry=index_entries[raw],
            head_entry=head_entries.get(raw),
            core_symlinks=core_symlinks,
            object_format=object_format,
            manifest=manifest,
        )
        remaining_content -= charge
    for raw in sorted(untracked, key=os.fsencode):
        charge = _frame_workspace_path(
            digest,
            root,
            raw,
            deadline=end,
            content_budget=remaining_content,
            content_required=mode == "diff",
            index_entry=None,
            head_entry=None,
            core_symlinks=core_symlinks,
            object_format=object_format,
            manifest=manifest,
        )
        remaining_content -= charge

    diff_args = ["diff", "--cached"] if mode == "staged" else ["diff-files"]
    diff_args += [
        "--binary",
        "--full-index",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
    ]
    if mode == "staged":
        diff_args.append(os.fsdecode(head))
    patch_index = index_bytes
    if mode == "staged" and index_bytes:
        patch_index = invalidate_index_stat_cache(
            index_bytes, object_format=object_format, assume_valid=True
        )
    patch = _frozen_index_output(
        root,
        patch_index,
        diff_args,
        deadline=end,
        limit=64 * 1024 * 1024,
        refresh=mode == "diff",
        object_format=object_format,
    )
    _frame(digest, b"patch", hashlib.sha256(patch).digest())
    return "sg_" + digest.hexdigest(), identity
