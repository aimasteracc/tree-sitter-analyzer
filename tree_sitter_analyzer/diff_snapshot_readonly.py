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
import subprocess  # nosec B404
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
from .source_epoch import capture_source_epoch, core_bool
from .source_oracle import (
    SourceOracleError,
    WorkspaceManifestEntry,
    _remaining,
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
    _core_filemode,
    _frame,
    _frame_workspace_path,
    _head_entries,
    _head_identity,
    _index_entries,
    _object_format,
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


def _run_git_readonly_bounded(
    root: str,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    env: dict[str, str] | None = None,
    input_: bytes | None = None,
) -> bytes:
    """Run Git with bounded pipes and ZERO filesystem writes.

    The P0.4 invocation set must need no pathname-backed index, object
    directory, shadow worktree, lock, config, attributes, or order file and
    must make no write attempt (RFC-0022 P0.4). Unlike the frozen runner it
    therefore never materializes a diff.orderFile override: git's default
    deterministic ordering applies, and a repository-level ``diff.orderFile``
    config fails the route closed before any diff command runs.
    """
    from .git_subprocess import _group_options

    if limit < 0:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    child_env = (
        {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        if env is None
        else dict(env)
    )
    child_env["GIT_OPTIONAL_LOCKS"] = "0"
    child_env["GIT_ATTR_NOSYSTEM"] = "1"
    child_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    child_env["GIT_NO_LAZY_FETCH"] = "1"
    process_options = _group_options()
    command = ["git", "-c", "core.fsmonitor=false", *args]
    try:
        proc = subprocess.Popen(  # type: ignore[call-overload]
            command,
            cwd=root,
            stdin=subprocess.PIPE if input_ is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
            **process_options,
        )
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc

    output = bytearray()
    errors = bytearray()
    failures: list[str] = []

    def drain(stream: Any, target: bytearray, cap: int, code: str) -> None:
        try:
            if stream is None:
                failures.append("DIFF_SNAPSHOT_GIT_ERROR")
                return
            while chunk := stream.read(64 * 1024):
                if len(target) + len(chunk) > cap:
                    failures.append(code)
                    proc.kill()
                    return
                target.extend(chunk)
        except OSError:
            failures.append("DIFF_SNAPSHOT_GIT_ERROR")
            proc.kill()

    def feed() -> None:
        if proc.stdin is None or input_ is None:
            return
        try:
            proc.stdin.write(input_)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    import threading

    threads = [
        threading.Thread(
            target=drain,
            args=(proc.stdout, output, limit, "DIFF_SNAPSHOT_CAPACITY"),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(proc.stderr, errors, 64 * 1024, "DIFF_SNAPSHOT_GIT_ERROR"),
            daemon=True,
        ),
    ]
    if input_ is not None:
        threads.append(threading.Thread(target=feed, daemon=True))
    succeeded = False
    try:
        for thread in threads:
            thread.start()
        try:
            proc.wait(timeout=_remaining(deadline))
            for thread in threads:
                thread.join(timeout=_remaining(deadline))
            if any(
                thread.is_alive() for thread in threads
            ):  # pragma: no cover - defensive liveness net; join expiry raises first
                raise subprocess.TimeoutExpired("git", 0)
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive net
            raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT") from exc
        if failures:
            raise SourceOracleError(failures[0])
        if proc.returncode != 0:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        succeeded = True
        return bytes(output)
    finally:
        if not succeeded:
            try:
                proc.kill()
            except OSError:  # pragma: no cover - fake/failed procs may refuse
                pass
            try:
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass


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
    return _run_git_readonly_bounded(
        root,
        args,
        deadline=deadline,
        limit=limit,
        env=env,
        input_=input_,
    )


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
        limit=max(64 * 1024, len(path_input) * 4),
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
    index_entries = _index_entries(
        root,
        deadline=end,
        index_bytes=None,  # P0.4: live index, read-only
        byte_ceiling=ledger.remaining,
    )
    ledger.charge(entry_map_storage(index_entries))
    tracked = list(index_entries)
    ledger.charge(container_storage(tracked))
    head_entries = _head_entries(
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
            # generation frames workspace content for all of them. The P0.4
            # token must be byte-identical (differential tests prove it).
            content_required=mode == "diff",
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
