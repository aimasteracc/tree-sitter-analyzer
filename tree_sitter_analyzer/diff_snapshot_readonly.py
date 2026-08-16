"""RFC-0022 P0.4 zero-write diff-capture oracle (Phase A groundwork).

The frozen capture oracle (``source_oracle_git``) materializes request-scoped
temporary index files for its git invocations (P0.2 allows this). This module
reproduces the identical framing with **zero filesystem writes**: every git
command runs against the live index with ``GIT_OPTIONAL_LOCKS=0`` (optional
lock/refresh operations are skipped), so a pinned native authority can
certify the route (P0.4).

Correctness contract: the generation token is byte-identical to the frozen
oracle's on identical source state — both frame the same root identity,
object format, HEAD, index bytes, dirty/untracked inventories, per-path
content digests, settings, and patch digest. The only difference is how
git is invoked (live index + no optional locks vs. a refreshed temporary
index). Because the live invocation skips stat-cache refresh, it reports
dirty files exactly when the cached stat is accurate; the differential
tests below prove equality on typical fixture states. The strace authority
(``scripts/rfc0022_strace_*.py``) certifies that no write is attempted.

The module is the first slice of the P0.4 read-existing backend: the
generation half. Wiring it into ``edit.impact(access_mode="read_existing")``
plus the in-memory blob/patch materialization and the P0.2 golden-corpus
equivalence suite is the remaining work (tracked with the RFC-0022 P0.4
gate).
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from .frozen_git_index import invalidate_index_stat_cache
from .frozen_git_settings import (
    capture_frozen_git_settings as capture_settings,
)
from .frozen_git_settings import (
    frozen_settings_storage,
    reject_active_filters,
)
from .git_readonly import run_git_readonly
from .source_epoch import capture_source_epoch, core_bool
from .source_oracle import (
    SourceOracleError,
    WorkspaceManifestEntry,
    canonical_root,
    stable_descriptor_chain,
)
from .source_oracle_budget import ByteLedger
from .source_oracle_git import (
    _FRAME_DOMAIN,
    _MAX_INDEX_BYTES,
    _MAX_INVENTORY_BYTES,
    _MAX_WORKTREE_CONTENT_BYTES,
    _MAX_WORKTREE_PATHS,
    GitEpoch,
    _frame,
    _frame_workspace_path,
    _safe_absolute_regular,
    _strip_one_record_terminator,
    _supports_nofollow,
    container_storage,
    entry_map_storage,
    git_output,
    has_split_index,
    path_set_storage,
)

_MAX_RETENTION_BYTES = 64 * 1024 * 1024


def _live_index_output(
    root: str,
    index_bytes: bytes,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    refresh: bool = False,
    clear_hints: bool = False,
    object_format: str = "sha1",
    input_: bytes | None = None,
    extra_env: dict[str, str] | None = None,
) -> bytes:
    """Run Git read-only against the live index (P0.4: zero writes).

    Drop-in for the frozen ``frozen_index_output`` call shape: the frozen
    ``index_bytes`` argument is accepted for call-site compatibility and
    deliberately ignored — git reads the live index instead of a
    materialized temporary index. ``GIT_OPTIONAL_LOCKS=0`` makes git skip
    every optional lock-taking sub-operation (notably index stat refresh),
    so the invocation set is read-only; the pinned native authority
    certifies that no write attempt occurs. ``refresh``/``clear_hints`` are
    accepted for compatibility and are no-ops (no stat-cache rewriting in
    memory either) — the differential tests validate the live stat cache
    against the frozen oracle.
    """
    del index_bytes, refresh, clear_hints, object_format
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if extra_env:
        env.update(extra_env)
    return run_git_readonly(
        root,
        args,
        deadline=deadline,
        limit=limit,
        env=env,
        input_=input_,
    )


def _git_output_readonly(
    root: str, args: list[str], *, deadline: float, limit: int
) -> bytes:
    """Zero-write git_output: every oracle git call runs read-only."""
    return run_git_readonly(root, args, deadline=deadline, limit=limit)


def _object_format_readonly(root: str, *, deadline: float) -> str:
    value = _git_output_readonly(
        root, ["rev-parse", "--show-object-format"], deadline=deadline, limit=64
    ).strip()
    if value not in (b"sha1", b"sha256"):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return value.decode("ascii")


def _core_filemode_readonly(root: str, *, deadline: float) -> bool:
    return core_bool(root, "core.filemode", deadline, _git_output_readonly)


def _head_identity_readonly(
    root: str, *, deadline: float, object_format: str | None = None
) -> bytes:
    from .source_oracle_git import _EMPTY_TREE_SHA1, _EMPTY_TREE_SHA256

    try:
        return _git_output_readonly(
            root, ["rev-parse", "--verify", "HEAD"], deadline=deadline, limit=4096
        ).strip()
    except SourceOracleError as head_error:
        try:
            _git_output_readonly(
                root,
                ["symbolic-ref", "-q", "HEAD"],
                deadline=deadline,
                limit=4096,
            )
        except SourceOracleError as symbolic_error:
            raise head_error from symbolic_error
        fmt = object_format or _object_format_readonly(root, deadline=deadline)
        return _EMPTY_TREE_SHA256 if fmt == "sha256" else _EMPTY_TREE_SHA1


def _head_entries_readonly(
    root: str,
    *,
    deadline: float,
    head: bytes = b"HEAD",
    byte_ceiling: int = _MAX_INVENTORY_BYTES,
) -> dict[bytes, bytes]:
    from .source_oracle_git import _EMPTY_TREE_SHA1, _EMPTY_TREE_SHA256

    if head in (_EMPTY_TREE_SHA1, _EMPTY_TREE_SHA256):
        return {}
    raw = _git_output_readonly(
        root,
        ["ls-tree", "-rz", "--full-tree", os.fsdecode(head)],
        deadline=deadline,
        limit=byte_ceiling,
    )
    from .source_oracle_git import parse_head_entries

    return parse_head_entries(
        raw,
        deadline=deadline,
        byte_ceiling=byte_ceiling,
        max_paths=_MAX_WORKTREE_PATHS,
        remaining_fn=lambda value: max(0, value),
    )


def _index_entries_from_bytes(
    index_bytes: bytes, object_format: str, max_paths: int
) -> dict[bytes, bytes]:
    """Parse stage-zero index entries from the captured bytes (P0.4).

    Reads the index binary directly so the entry inventory is bound to the
    exact bytes whose digest is framed — no live index re-open, no
    temporary index file (Codex #1293 P1). Supports index v2/v3; v4 fails
    closed. Returns ``{path: b"<mode> <oid> <stage>"}`` matching git
    ``ls-files --stage`` rows.
    """
    if not index_bytes:
        return {}
    hash_size = 32 if object_format == "sha256" else 20
    version = int.from_bytes(index_bytes[4:8], "big")
    count = int.from_bytes(index_bytes[8:12], "big")
    if version not in (2, 3):
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_INDEX")
    content_end = len(index_bytes) - hash_size
    entries: dict[bytes, bytes] = {}
    offset = 12
    for _ in range(count):
        if offset + 62 > content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        mode = int.from_bytes(index_bytes[offset + 24 : offset + 28], "big")
        oid = index_bytes[offset + 40 : offset + 40 + hash_size]
        flags = int.from_bytes(
            index_bytes[offset + 40 + hash_size : offset + 42 + hash_size], "big"
        )
        extended_offset = offset + 42 + hash_size
        path_start = extended_offset + (2 if flags & 0x4000 else 0)
        path_end = index_bytes.find(b"\0", path_start)
        if path_end < 0 or path_end >= content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        path = index_bytes[path_start:path_end]
        if mode and flags & 0x3000 == 0:  # stage zero only
            entries[path] = f"{mode:o} {oid.hex()} 0".encode("ascii")
        # Each entry is padded to a multiple of 8 bytes total: the fixed
        # part is 62 bytes (40 stat + oid + 2 flags, +2 extended when set),
        # followed by the NUL-terminated path.
        fixed = 62 + (2 if flags & 0x4000 else 0)
        offset = offset + ((fixed + (path_end - path_start) + 1 + 7) & ~7)
    if len(entries) > max_paths:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries


def _hinted_paths(index_bytes: bytes, object_format: str, max_paths: int) -> set[bytes]:
    """Paths with assume-unchanged or skip-worktree hint bits.

    The frozen oracle's stat-cache invalidation preserves these bits, so
    hinted entries are never dirty and their content is never framed; the
    P0.4 oracle must replicate that from the captured index bytes
    (Codex #1293 P1). Supports index v2/v3; v4 fails closed.
    """
    del max_paths
    if not index_bytes:
        return set()
    hash_size = 32 if object_format == "sha256" else 20
    version = int.from_bytes(index_bytes[4:8], "big")
    count = int.from_bytes(index_bytes[8:12], "big")
    if version not in (2, 3):
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_INDEX")
    content_end = len(index_bytes) - hash_size
    hinted: set[bytes] = set()
    offset = 12
    flags_offset = 40 + hash_size
    for _ in range(count):
        if offset + flags_offset + 2 > content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        flags = int.from_bytes(
            index_bytes[offset + flags_offset : offset + flags_offset + 2], "big"
        )
        extended_offset = offset + flags_offset + 2
        path_start = extended_offset + (2 if flags & 0x4000 else 0)
        path_end = index_bytes.find(b"\0", path_start)
        if path_end < 0 or path_end >= content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if flags & (0x8000 | 0x4000):
            hinted.add(index_bytes[path_start:path_end])
        fixed = 62 + (2 if flags & 0x4000 else 0)
        offset = offset + ((fixed + (path_end - path_start) + 1 + 7) & ~7)
    return hinted


def _reject_frozen_filters_readonly(
    root: str,
    paths: tuple[bytes, ...],
    deadline: float,
    object_format: str,
) -> None:
    """Reject active clean filters via the live index (read-only)."""
    path_input = b"".join(path + b"\0" for path in paths)
    raw = _live_index_output(
        root,
        b"",
        ["check-attr", "-z", "filter", "--stdin"],
        deadline=deadline,
        limit=16 * 1024 * 1024,
        object_format=object_format,
        input_=path_input,
        extra_env={"GIT_ATTR_NOSYSTEM": "1"},
    )
    reject_active_filters(raw, paths)


def oracle_generation_readonly(
    project_root: str | None,
    mode: str = "diff",
    *,
    deadline: float | None = None,
    manifest: dict[str, WorkspaceManifestEntry] | None = None,
    epoch_out: list[GitEpoch] | None = None,
    byte_ceiling: int = _MAX_RETENTION_BYTES,
) -> tuple[str, Any]:
    """P0.4 oracle: same source-generation framing, zero filesystem writes.

    Mirrors ``source_oracle_git.oracle_generation`` frame for frame, but
    every index-bound git call runs read-only against the live index
    (``GIT_OPTIONAL_LOCKS=0``) instead of a materialized temporary index.
    On identical source state the returned generation token is
    byte-identical to the frozen oracle's (differential tests prove it).
    """
    if not _supports_nofollow():
        raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")
    root, identity = canonical_root(project_root)
    end = deadline if deadline is not None else time.monotonic() + 35.0
    digest = hashlib.sha256()
    _frame(digest, b"domain", _FRAME_DOMAIN)
    _frame(digest, b"root", os.fsencode(identity.realpath))
    _frame(digest, b"root-stat", f"{identity.device},{identity.inode}".encode())
    top_level = _git_output_readonly(
        root, ["rev-parse", "--show-toplevel"], deadline=end, limit=64 * 1024
    )
    top_level = _strip_one_record_terminator(top_level)
    try:
        top_root, top_identity = canonical_root(os.fsdecode(top_level))
    except (UnicodeError, SourceOracleError) as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH") from exc
    if top_root != root or top_identity != identity:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH")
    object_format = _object_format_readonly(root, deadline=end)
    core_filemode = _core_filemode_readonly(root, deadline=end)
    core_symlinks = core_bool(root, "core.symlinks", end, _git_output_readonly)
    head = _head_identity_readonly(root, deadline=end, object_format=object_format)
    _frame(digest, b"object-format", object_format.encode("ascii"))
    _frame(digest, b"core-filemode", b"true" if core_filemode else b"false")
    _frame(digest, b"core-symlinks", b"true" if core_symlinks else b"false")
    _frame(digest, b"HEAD", head)
    git_dir = _git_output_readonly(
        root, ["rev-parse", "--git-dir"], deadline=end, limit=64 * 1024
    )
    git_dir = _strip_one_record_terminator(git_dir)
    decoded_git_dir = os.fsdecode(git_dir)
    index_path = (
        os.path.join(decoded_git_dir, "index")
        if os.path.isabs(decoded_git_dir)
        else os.path.join(root, decoded_git_dir, "index")
    )
    if byte_ceiling <= 0:  # pragma: no cover - registry rejects first
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    ledger = ByteLedger(byte_ceiling)
    safe_index = _safe_absolute_regular(
        index_path,
        deadline=end,
        limit=min(_MAX_INDEX_BYTES, ledger.remaining),
        allow_missing=True,
    )
    for descriptor in stable_descriptor_chain(safe_index.metadata):
        _frame(digest, b"index-descriptor-identity", descriptor)
    _frame(digest, b"index-state", safe_index.kind.encode("ascii"))
    index_bytes = safe_index.data or b""
    ledger.charge(len(index_bytes))
    _frame(digest, b"index-content", hashlib.sha256(index_bytes).digest())
    if index_bytes and has_split_index(index_bytes, object_format=object_format):
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_INDEX")
    index_entries = _index_entries_from_bytes(
        index_bytes, object_format=object_format, max_paths=_MAX_WORKTREE_PATHS
    )
    ledger.charge(entry_map_storage(index_entries))
    tracked = list(index_entries)
    ledger.charge(container_storage(tracked))
    head_entries = _head_entries_readonly(
        root,
        deadline=end,
        head=head,
        byte_ceiling=ledger.remaining,
    )
    ledger.charge(entry_map_storage(head_entries))
    filter_candidates = tuple(sorted(index_entries))
    ledger.require_available(container_storage(filter_candidates))
    if filter_candidates:
        _reject_frozen_filters_readonly(
            root,
            filter_candidates,
            end,
            object_format,
        )
    filter_candidates = ()
    dirty_raw = b""
    untracked_raw = b""
    if mode == "diff":
        refresh_temporary = 2 * len(index_bytes)
        ledger.require_available(refresh_temporary)
        dirty_raw = _live_index_output(
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
            limit=min(_MAX_INVENTORY_BYTES, ledger.remaining - refresh_temporary),
        )
        ledger.require_available(len(dirty_raw) + len(index_bytes))
        untracked_raw = _live_index_output(
            root,
            index_bytes,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            deadline=end,
            limit=min(
                _MAX_INVENTORY_BYTES,
                ledger.remaining - len(dirty_raw) - len(index_bytes),
            ),
        )
    dirty = {path for path in dirty_raw.split(b"\0") if path}
    untracked = {path for path in untracked_raw.split(b"\0") if path}
    retained_paths = path_set_storage(dirty) + path_set_storage(untracked)
    ledger.require_available(len(dirty_raw) + len(untracked_raw) + retained_paths)
    ledger.charge(retained_paths)
    dirty_raw = untracked_raw = b""
    if len(dirty | untracked) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    tracked_set = set(tracked)
    ledger.charge(container_storage(tracked_set))
    if not dirty <= tracked_set or untracked & tracked_set:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    settings_inventory = tuple(
        sorted(
            tracked_set | set(head_entries) | (untracked if mode == "diff" else set())
        )
    )
    ledger.charge(container_storage(settings_inventory))
    frozen_settings = capture_settings(
        root,
        settings_inventory,
        end,
        git_output,
        byte_ceiling=ledger.remaining,
    )
    ledger.charge(frozen_settings_storage(frozen_settings))
    if ledger.remaining <= 0:  # pragma: no cover - settings bound first
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    settings_epoch = capture_source_epoch(
        root,
        index_bytes,
        settings_inventory,
        deadline=end,
        object_format=object_format,
        frozen_output=_live_index_output,
        byte_ceiling=ledger.remaining,
    )
    ledger.charge(64)
    _frame(digest, b"attributes", settings_epoch.attribute_fingerprint)
    _frame(digest, b"config", settings_epoch.config_hash)
    _frame(digest, b"git-settings", frozen_settings.fingerprint)
    hinted = _hinted_paths(
        index_bytes, object_format=object_format, max_paths=_MAX_WORKTREE_PATHS
    )
    workspace_gitlinks: dict[bytes, bytes] = {}
    for raw in sorted(dirty) if mode == "diff" else ():
        entry = index_entries[raw]
        if not entry.startswith(b"160000 "):
            continue
        workspace_gitlinks[raw] = entry
        _frame(digest, b"worktree-gitlink-dirty", raw)
        _frame(digest, b"worktree-gitlink-index", raw + b"\0" + entry)
    if epoch_out is not None:
        epoch_out.append(
            GitEpoch(
                head=head,
                object_format=object_format,
                index_entries=tuple(sorted(index_entries.items())),
                tracked_paths=tuple(tracked),
                dirty_paths=(
                    tuple(
                        sorted(
                            raw
                            for raw in tracked
                            if not index_entries[raw].startswith(b"160000 ")
                            and raw not in hinted
                        )
                    )
                    if mode == "diff"
                    else ()
                ),
                untracked_paths=tuple(sorted(untracked)),
                workspace_gitlinks=tuple(sorted(workspace_gitlinks.items())),
                core_filemode=core_filemode,
                core_symlinks=core_symlinks,
                index_bytes=index_bytes,
                source_epoch=settings_epoch,
                git_settings=frozen_settings,
                settings_inventory=settings_inventory,
            )
        )
    remaining_content = min(_MAX_WORKTREE_CONTENT_BYTES, ledger.remaining)
    initial_content = remaining_content
    for raw in sorted(tracked, key=os.fsencode) if mode == "diff" else ():
        charge = _frame_workspace_path(
            digest,
            root,
            raw,
            deadline=end,
            content_budget=remaining_content,
            # Replicate the frozen oracle's framing exactly: its stat-cache
            # invalidation makes git report every tracked path dirty, so the
            # generation frames workspace content for all of them — except
            # assume-unchanged/skip-worktree hinted paths, which the frozen
            # invalidation preserves and git never reports dirty (Codex
            # #1293 P1). The P0.4 token must be byte-identical.
            content_required=mode == "diff" and raw not in hinted,
            index_entry=index_entries[raw],
            head_entry=head_entries.get(raw),
            core_symlinks=core_symlinks,
            object_format=object_format,
            manifest=manifest,
        )
        remaining_content -= charge
    for raw in sorted(untracked, key=os.fsencode) if mode == "diff" else ():
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
    ledger.charge(initial_content - remaining_content)
    config_list = _git_output_readonly(
        root,
        ["config", "--null", "--list", "--includes"],
        deadline=end,
        limit=16 * 1024 * 1024,
    )
    order_file_active = any(
        record.split(b"\n", 1)[0].lower() == b"diff.orderfile"
        for record in config_list.split(b"\0")
        if record
    )
    if order_file_active:
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_ORDERFILE")
    diff_args = ["diff", "--cached"] if mode == "staged" else ["diff-files"]
    diff_args += [
        "--binary",
        "--full-index",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--submodule=short",
        "--ignore-submodules=all",
    ]
    if mode == "staged":
        diff_args.append(os.fsdecode(head))
    patch_index = index_bytes
    if mode == "staged" and index_bytes:
        patch_index = invalidate_index_stat_cache(
            index_bytes, object_format=object_format, assume_valid=True
        )
    patch_temporary = len(patch_index) if patch_index is not index_bytes else 0
    ledger.require_available(patch_temporary + 1)
    patch = _live_index_output(
        root,
        index_bytes,
        diff_args,
        deadline=end,
        limit=min(64 * 1024 * 1024, ledger.remaining - patch_temporary),
    )
    _frame(digest, b"patch", hashlib.sha256(patch).digest())
    return "sg_" + digest.hexdigest(), identity
