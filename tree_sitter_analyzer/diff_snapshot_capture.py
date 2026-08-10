"""Atomic Git patch capture and immutable file materialization."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from .diff_snapshot_epoch import FrozenGitEnvironment
from .frozen_git_index import invalidate_index_stat_cache
from .git_path_codec import path_to_raw, path_to_wire, raw_to_path
from .source_oracle import (
    SafePath,
    SourceOracleError,
    WorkspaceManifestEntry,
    git_output,
    safe_workspace_path,
)
from .source_oracle_git import GitEpoch, _head_entries


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    old_available: bool
    new_available: bool
    binary: bool
    old_path: str | None = None
    patch_available: bool = True
    old_kind: str = "missing"
    new_kind: str = "missing"
    old_mode: str | None = None
    new_mode: str | None = None
    old_oid: str | None = None
    new_oid: str | None = None
    unsupported_kind: str | None = None
    _raw_path: bytes | None = field(default=None, repr=False, compare=False)
    _raw_old_path: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def raw_path(self) -> bytes:
        return self._raw_path if self._raw_path is not None else path_to_raw(self.path)

    @property
    def raw_old_path(self) -> bytes | None:
        if self._raw_old_path is not None:
            return self._raw_old_path
        return path_to_raw(self.old_path) if self.old_path is not None else None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "path": path_to_wire(self.path),
            "status": self.status,
            "old_available": self.old_available,
            "new_available": self.new_available,
            "binary": self.binary,
            "patch_available": self.patch_available,
            "old_kind": self.old_kind,
            "new_kind": self.new_kind,
        }
        if self.old_path is not None:
            value["old_path"] = path_to_wire(self.old_path)
        for key in (
            "old_mode",
            "new_mode",
            "old_oid",
            "new_oid",
            "unsupported_kind",
        ):
            item = getattr(self, key)
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True)
class FrozenFile:
    record: ChangedFile
    old_bytes: bytes | None
    new_bytes: bytes | None


def _decode_path(raw: bytes) -> str:
    return raw_to_path(raw)


def _row_sort_key(row: tuple[str, bytes | None, bytes]) -> tuple[bytes, bytes, bytes]:
    """Order records by normalized raw destination, then status and source."""
    status, old, path = row
    normalized_path = path_to_raw(_decode_path(path))
    normalized_old = path_to_raw(_decode_path(old)) if old is not None else b""
    return normalized_path, status.encode("ascii"), normalized_old


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


def _frozen_rows(
    git: FrozenGitEnvironment, base: bytes, limit: int
) -> list[tuple[str, bytes | None, bytes]]:
    raw = git.run(
        [
            "diff",
            "--cached",
            "--name-status",
            "-z",
            "--find-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            os.fsdecode(base),
        ],
        limit=limit,
    )
    tokens = [item for item in raw.split(b"\0") if item]
    rows: list[tuple[str, bytes | None, bytes]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index][:1].decode("ascii", "strict")
        index += 1
        try:
            if status in ("R", "C"):
                old, path = tokens[index], tokens[index + 1]
                index += 2
            else:
                old, path = None, tokens[index]
                index += 1
            _decode_path(path)
            if old is not None:
                _decode_path(old)
        except (IndexError, UnicodeError, ValueError) as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        rows.append(("R" if status in ("R", "C") else status, old, path))
    return rows


def _rows(
    root: str, mode: str, deadline: float, limit: int
) -> list[tuple[str, str | None, str, bool]]:
    """Compatibility parser for bounded porcelain status output."""
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--name-status",
        "-z",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
    ]
    tokens = [
        item
        for item in git_output(root, args, deadline=deadline, limit=limit).split(b"\0")
        if item
    ]
    result: list[tuple[str, str | None, str, bool]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index][:1].decode("ascii", "strict")
        index += 1
        try:
            if status in ("R", "C"):
                old = _decode_path(tokens[index])
                path = _decode_path(tokens[index + 1])
                index += 2
            else:
                old = None
                path = _decode_path(tokens[index])
                index += 1
        except (IndexError, UnicodeError, ValueError) as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        result.append(("R" if status in ("R", "C") else status, old, path, True))
    if mode == "diff":
        raw = git_output(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            deadline=deadline,
            limit=limit,
        )
        known = {row[2] for row in result}
        for item in raw.split(b"\0"):
            if item:
                path = _decode_path(item)
                if path not in known:
                    result.append(("A", None, path, False))
    return sorted(result, key=lambda row: path_to_raw(row[2]))


def _tracked_binary_paths(
    root: str, mode: str, deadline: float, limit: int
) -> set[str]:
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--numstat",
        "-z",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
    ]
    raw = git_output(root, args, deadline=deadline, limit=limit)
    tokens = raw.split(b"\0")
    result: set[str] = set()
    index = 0
    while index < len(tokens):
        row = tokens[index]
        index += 1
        if not row:
            continue
        fields = row.split(b"\t", 2)
        if len(fields) != 3:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        path = fields[2]
        if not path:
            try:
                old, path = tokens[index], tokens[index + 1]
            except IndexError as exc:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
            index += 2
            if not old or not path:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if fields[0] == fields[1] == b"-":
            result.add(_decode_path(path))
    return result


def _binary_paths(git: FrozenGitEnvironment, base: bytes, limit: int) -> set[bytes]:
    raw = git.run(
        [
            "diff",
            "--cached",
            "--numstat",
            "-z",
            "--find-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            os.fsdecode(base),
        ],
        limit=limit,
    )
    tokens = raw.split(b"\0")
    binary: set[bytes] = set()
    index = 0
    while index < len(tokens):
        fields = tokens[index].split(b"	", 2)
        index += 1
        if len(fields) != 3:
            if fields == [b""]:
                continue
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        path = fields[2]
        if not path:
            if index + 1 >= len(tokens):
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            old, path = tokens[index], tokens[index + 1]
            index += 2
            if not old or not path:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if fields[0] == fields[1] == b"-":
            binary.add(path)
    return binary


def _blob(
    git: FrozenGitEnvironment, oid: str | None, kind: str, limit: int
) -> bytes | None:
    if oid is None or kind == "gitlink":
        return None
    return git.run(["cat-file", "blob", oid], limit=limit)


def _safe_mode(safe_kind: str, metadata: tuple[bytes, ...]) -> tuple[str | None, str]:
    if safe_kind == "missing":
        return None, "missing"
    if safe_kind == "symlink":
        return "120000", "symlink"
    if safe_kind == "directory":
        return "160000", "gitlink"
    try:
        bits = int(metadata[-1].split(b",")[2])
    except (IndexError, ValueError) as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
    return ("100755" if bits & 0o111 else "100644"), "file"


def _capture_payload(
    root: str,
    mode: str,
    deadline: float,
    ceiling: int,
    expected_manifest: dict[str, WorkspaceManifestEntry] | None = None,
    epoch: GitEpoch | None = None,
) -> tuple[bytes, tuple[FrozenFile, ...]]:
    """Capture frozen index→worktree or frozen HEAD→index payloads."""
    if epoch is None:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    frozen = epoch
    if mode == "staged" and epoch.index_bytes:
        frozen = replace(
            epoch,
            index_bytes=invalidate_index_stat_cache(
                epoch.index_bytes,
                object_format=epoch.object_format,
                assume_valid=True,
            ),
        )
    remaining = ceiling
    index_entries = frozen.index_map()
    head_entries = _head_entries(root, deadline=deadline, head=frozen.head)
    safe_paths: dict[bytes, SafePath] = {}
    with FrozenGitEnvironment(root, frozen, deadline, ceiling) as git:
        # Retained payload bytes and every temporary index/object byte share one
        # ceiling in both staged and workspace modes.
        accounted_temporary = getattr(git, "temporary_bytes", 0)
        remaining -= accounted_temporary
        if remaining < 0:  # pragma: no cover - environment enforces this first
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")

        def reserve_temporary_growth() -> None:
            nonlocal remaining, accounted_temporary
            current_temporary = getattr(git, "temporary_bytes", 0)
            growth = current_temporary - accounted_temporary
            if growth:
                remaining -= growth
                accounted_temporary = current_temporary
            if remaining < 0:  # pragma: no cover - environment enforces this first
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            # The environment's absolute limit permits only the shared budget
            # still unconsumed by payload materialization.
            git.storage_byte_limit = current_temporary + remaining

        reserve_temporary_growth()
        verify_epoch = getattr(git, "verify_source_epoch", None)
        if verify_epoch is not None:
            verify_epoch()
        # The workspace comparison base must be the captured index, not HEAD.
        base = frozen.head
        old_entries = head_entries
        if mode == "diff":
            base = git.run(["write-tree"], limit=4096).strip()
            reserve_temporary_growth()
            if not base:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            old_entries = index_entries
            raw_paths = set(frozen.dirty_paths) | set(frozen.untracked_paths)
            for raw in sorted(raw_paths):
                path = _decode_path(raw)
                manifest_entry = (expected_manifest or {}).get(path)
                if manifest_entry is None:
                    raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
                safe = safe_workspace_path(
                    root,
                    path,
                    deadline=deadline,
                    limit=remaining,
                    expected_chain=manifest_entry.descriptor_chain,
                    # Regular tracked leaves may have been replaced by dirs.
                    allow_directory=True,
                )
                if safe.data is not None:
                    remaining -= len(safe.data)
                safe_paths[raw] = safe
            reserve_temporary_growth()
            workspace_entries = git.apply_workspace(safe_paths, expected_manifest or {})
            reserve_temporary_growth()
        else:
            workspace_entries = {}

        diff_options = [
            "diff",
            "--cached",
            "--binary",
            "--full-index",
            # Normalized patches are a machine format, independent of
            # diff.mnemonicPrefix and the reconstructed commit/index roles.
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--find-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            os.fsdecode(base),
        ]
        patch = git.run(diff_options, limit=remaining)
        remaining -= len(patch)
        reserve_temporary_growth()
        rows = _frozen_rows(git, base, min(8 * 1024 * 1024, remaining))
        patch_row_paths = {row[2] for row in rows}
        binaries = _binary_paths(git, base, min(8 * 1024 * 1024, remaining))
        final_entries = dict(index_entries)
        if mode == "diff":
            for raw, safe in safe_paths.items():
                if safe.kind in ("missing", "directory") and not (
                    safe.kind == "directory" and raw in workspace_entries
                ):
                    final_entries.pop(raw, None)
                else:
                    final_entries[raw] = workspace_entries[raw]
            # A dirty submodule can retain the same HEAD OID. Git then emits no
            # row, but the unsupported dirty identity must never be dropped.
            for raw in sorted(dict(frozen.workspace_gitlinks)):
                if raw in frozen.dirty_paths and raw not in patch_row_paths:
                    rows.append(("M", None, raw))

        # Git may be configured to emit any order.  The public records use one
        # internal raw-path order in both workspace and staged modes; status
        # and rename source provide deterministic ties.
        rows.sort(key=_row_sort_key)

        files: list[FrozenFile] = []
        dirty_gitlinks = set(dict(frozen.workspace_gitlinks)) & set(frozen.dirty_paths)
        for status, old_raw, raw in rows:
            lookup = old_raw or raw
            old_entry = old_entries.get(lookup)
            new_entry = final_entries.get(raw)
            old_mode, old_oid, old_kind = _entry_parts(old_entry)
            new_mode, new_oid, new_kind = _entry_parts(new_entry)
            if status == "A":
                # Includes intent-to-add: an added record has no coherent old
                # identity even when the frozen index contains a placeholder.
                old_mode, old_oid, old_kind = None, None, "missing"
            old = _blob(git, old_oid, old_kind, remaining) if status != "A" else None
            remaining -= len(old or b"")
            reserve_temporary_growth()
            new = _blob(git, new_oid, new_kind, remaining) if status != "D" else None
            remaining -= len(new or b"")
            reserve_temporary_growth()
            if mode == "diff" and raw in safe_paths:
                safe = safe_paths[raw]
                if safe.kind == "directory" and raw not in workspace_entries:
                    new_mode, new_kind, new_oid, new = None, "missing", None, None
                else:
                    workspace_entry = workspace_entries.get(raw)
                    emulated_symlink = (
                        safe.kind == "file"
                        and not frozen.core_symlinks
                        and workspace_entry is not None
                        and workspace_entry.startswith(b"120000 ")
                    )
                    if (
                        safe.kind == "file"
                        and workspace_entry is not None
                        and (not frozen.core_filemode or emulated_symlink)
                    ):
                        new_mode, _temporary_oid, new_kind = _entry_parts(
                            workspace_entry
                        )
                    else:
                        new_mode, new_kind = _safe_mode(safe.kind, safe.metadata)
                    # Temporary object identity is not a repository attestation.
                    new_oid = None
                    if safe.kind == "missing":
                        new = None
            path = _decode_path(raw)
            old_path = _decode_path(old_raw) if old_raw is not None else None
            unsupported = "dirty_gitlink" if raw in dirty_gitlinks else None
            files.append(
                FrozenFile(
                    ChangedFile(
                        path=path,
                        status=status,
                        old_available=old is not None or old_kind == "gitlink",
                        new_available=new is not None or new_kind == "gitlink",
                        binary=raw in binaries,
                        old_path=old_path,
                        patch_available=unsupported is None and raw in patch_row_paths,
                        old_kind=old_kind,
                        new_kind=new_kind,
                        old_mode=old_mode,
                        new_mode=new_mode,
                        old_oid=old_oid,
                        new_oid=new_oid,
                        unsupported_kind=unsupported,
                        _raw_path=raw,
                        _raw_old_path=old_raw,
                    ),
                    old,
                    new,
                )
            )
    return patch, tuple(files)
