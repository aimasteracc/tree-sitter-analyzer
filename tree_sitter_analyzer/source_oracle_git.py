"""Git inventory and source-generation helpers for the source oracle."""

from __future__ import annotations

import hashlib
import os
import subprocess  # nosec B404
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from .git_subprocess import run_git_bounded
from .source_oracle import (
    RootIdentity,
    SourceOracleError,
    _safe_absolute_regular,
    _supports_nofollow,
    canonical_root,
    normalize_repo_path,
    safe_workspace_path,
    stable_descriptor_chain,
)

_LOCK = threading.RLock()
_T = TypeVar("_T")
_FRAME_DOMAIN = b"tsa-source-generation-v3"
_MAX_INVENTORY_BYTES = 16 * 1024 * 1024
_MAX_WORKTREE_PATHS = 200_000
_MAX_WORKTREE_CONTENT_BYTES = 64 * 1024 * 1024
_EMPTY_TREE_SHA1 = (
    b"4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # pragma: allowlist secret
)
_EMPTY_TREE_SHA256 = b"6ef19b41225c5369f1c104d45d8d85efa9b057b53b14b4b9b939dd74decc5321"  # pragma: allowlist secret


@dataclass(frozen=True)
class GitEpoch:
    """Exact Git identities captured by the first source-oracle pass."""

    head: bytes
    object_format: str
    index_entries: tuple[tuple[bytes, bytes], ...]
    tracked_paths: tuple[bytes, ...]
    dirty_paths: tuple[bytes, ...]
    untracked_paths: tuple[bytes, ...]
    workspace_gitlinks: tuple[tuple[bytes, bytes], ...] = ()

    def index_map(self) -> dict[bytes, bytes]:
        return dict(self.index_entries)

    @property
    def empty_tree(self) -> bytes:
        return (
            _EMPTY_TREE_SHA256 if self.object_format == "sha256" else _EMPTY_TREE_SHA1
        )


def git_output(root: str, args: list[str], *, deadline: float, limit: int) -> bytes:
    """Run Git fail-closed with a shared deadline and bounded retained output."""
    return run_git_bounded(
        root, args, deadline=deadline, limit=limit, popen=subprocess.Popen
    )


def _strip_one_record_terminator(value: bytes) -> bytes:
    return (
        value[:-2]
        if value.endswith(b"\r\n")
        else (value[:-1] if value.endswith(b"\n") else value)
    )


def _object_format(root: str, *, deadline: float) -> str:
    value = git_output(
        root, ["rev-parse", "--show-object-format"], deadline=deadline, limit=64
    ).strip()
    if value not in (b"sha1", b"sha256"):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return value.decode("ascii")


def _head_identity(
    root: str, *, deadline: float, object_format: str | None = None
) -> bytes:
    """Return exact HEAD, or the format-correct empty-tree identity if unborn."""
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


def _index_entries(root: str, *, deadline: float) -> dict[bytes, bytes]:
    """Return stage-zero blob identities, rejecting conflicts and malformed rows."""
    raw = git_output(
        root,
        ["ls-files", "--stage", "-z"],
        deadline=deadline,
        limit=_MAX_INVENTORY_BYTES,
    )
    entries: dict[bytes, bytes] = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        header, separator, path = row.partition(b"\t")
        fields = header.split(b" ")
        if not separator or not path or len(fields) != 3 or fields[2] != b"0":
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        try:
            int(fields[0], 8)
            int(fields[1], 16)
        except ValueError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        if path in entries:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        entries[path] = header
    if len(entries) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries


def _head_entries(
    root: str, *, deadline: float, head: bytes = b"HEAD"
) -> dict[bytes, bytes]:
    """Return bounded per-path HEAD tree identities for clean-file binding."""
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
    manifest: dict[str, tuple[bytes, ...]] | None = None,
) -> int:
    """Frame one no-follow worktree leaf and return its content charge."""
    path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
    is_gitlink = bool(index_entry and index_entry.split(b" ", 1)[0] == b"160000")
    safe = safe_workspace_path(
        root,
        path,
        deadline=deadline,
        limit=content_budget,
        read_regular=content_required and not is_gitlink,
        allow_directory=is_gitlink,
    )
    _frame(digest, b"worktree-path", raw)
    if manifest is not None:
        manifest[path] = stable_descriptor_chain(safe.metadata)
    leaf_metadata = safe.metadata[-1:] if safe.kind != "missing" else ()
    ancestor_metadata = (
        safe.metadata[:-1] if safe.kind != "missing" else safe.metadata[:-1]
    )
    for descriptor in stable_descriptor_chain(tuple(ancestor_metadata)):
        _frame(digest, b"worktree-ancestor-identity", descriptor)
    if safe.kind == "missing":
        _frame(digest, b"worktree-kind", b"missing")
    else:
        # Frame the complete root-to-leaf no-follow descriptor chain; the leaf
        # retains the historical field order for stable generation identity.
        fields = leaf_metadata[0].split(b",")
        if len(fields) != 6:
            raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH")
        _frame(
            digest,
            b"worktree-stat",
            b",".join((fields[2], fields[0], fields[1], *fields[3:])),
        )
        _frame(digest, b"worktree-kind", safe.kind.encode("ascii"))
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
    manifest: dict[str, tuple[bytes, ...]] | None = None,
    epoch_out: list[GitEpoch] | None = None,
) -> tuple[str, RootIdentity]:
    """Return a domain-framed generation and the exact canonical root identity."""
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
    head = _head_identity(root, deadline=end, object_format=object_format)
    _frame(digest, b"object-format", object_format.encode("ascii"))
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
    safe_index = _safe_absolute_regular(
        index_path,
        deadline=end,
        limit=64 * 1024 * 1024,
        allow_missing=head in (_EMPTY_TREE_SHA1, _EMPTY_TREE_SHA256),
    )
    for descriptor in stable_descriptor_chain(safe_index.metadata):
        _frame(digest, b"index-descriptor-identity", descriptor)
    _frame(digest, b"index-kind", safe_index.kind.encode("ascii"))
    index_bytes = safe_index.data or b""
    _frame(digest, b"index-content", hashlib.sha256(index_bytes).digest())
    # Dependency analysis reads the live checkout, not only dirty paths. Bind
    # every tracked path so a transient clean-file write+restore or atomic
    # replacement changes inode/ctime and invalidates the strict result.
    tracked = _tracked_paths(root, deadline=end)
    index_entries = _index_entries(root, deadline=end)
    head_entries = _head_entries(root, deadline=end, head=head)
    if set(tracked) != set(index_entries):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    dirty_raw = git_output(
        root,
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
    )
    untracked_raw = git_output(
        root,
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
            content_required=raw in dirty,
            index_entry=index_entries[raw],
            head_entry=head_entries.get(raw),
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
            content_required=True,
            index_entry=None,
            head_entry=None,
            manifest=manifest,
        )
        remaining_content -= charge

    diff_args = ["diff", "--cached"] if mode == "staged" else ["diff-files"]
    diff_args += [
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
    ]
    patch = git_output(root, diff_args, deadline=end, limit=64 * 1024 * 1024)
    _frame(digest, b"patch", hashlib.sha256(patch).digest())
    return "sg_" + digest.hexdigest(), identity


def source_generation(project_root: str | None, mode: str = "diff") -> str:
    with _LOCK:
        return oracle_generation(project_root, mode)[0]


def capture_consistent(
    project_root: str | None, capture: Callable[[], _T]
) -> tuple[str | None, _T]:
    """Compatibility helper; ctime-inclusive generations reject ordinary ABA writes."""
    with _LOCK:
        before, _ = oracle_generation(project_root)
        value = capture()
        after, _ = oracle_generation(project_root)
    return (before if before == after else None), value
