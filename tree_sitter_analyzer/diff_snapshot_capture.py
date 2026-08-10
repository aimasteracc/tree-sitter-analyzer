"""Atomic Git patch capture and immutable file materialization."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .diff_snapshot_epoch import FrozenGitEnvironment
from .git_path_codec import path_to_wire
from .source_oracle import (
    SafePath,
    SourceOracleError,
    git_output,
    normalize_repo_path,
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
        for key in ("old_mode", "new_mode", "old_oid", "new_oid"):
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
    return normalize_repo_path(raw.decode("utf-8", "surrogateescape"))


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
    return sorted(result, key=lambda row: os.fsencode(row[2]))


def _tracked_binary_paths(
    root: str, mode: str, deadline: float, limit: int
) -> set[str]:
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--numstat",
        "-z",
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
    expected_manifest: dict[str, tuple[bytes, ...]] | None = None,
    epoch: GitEpoch | None = None,
) -> tuple[bytes, tuple[FrozenFile, ...]]:
    """Capture using only the exact pre-oracle index/HEAD and safe leaf reads."""
    if epoch is None:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    frozen = epoch
    remaining = ceiling
    head_entries = _head_entries(root, deadline=deadline, head=frozen.head)
    safe_paths: dict[bytes, SafePath] = {}
    with FrozenGitEnvironment(root, frozen, deadline) as git:
        if mode == "diff":
            staged = _frozen_rows(git, frozen.head, min(8 * 1024 * 1024, remaining))
            raw_paths = set(frozen.dirty_paths) | set(frozen.untracked_paths)
            raw_paths.update(path for _, _, path in staged)
            # Capture every workspace-side leaf before hashing or mutating index two.
            for raw in sorted(raw_paths):
                path = _decode_path(raw)
                entry = frozen.index_map().get(raw)
                is_gitlink = bool(entry and entry.startswith(b"160000 "))
                safe = safe_workspace_path(
                    root,
                    path,
                    deadline=deadline,
                    limit=remaining,
                    expected_chain=(expected_manifest or {}).get(path),
                    allow_directory=is_gitlink,
                )
                if safe.data is not None:
                    remaining -= len(safe.data)
                safe_paths[raw] = safe
            workspace_entries = git.apply_workspace(safe_paths)
        else:
            workspace_entries = {}
        patch = git.run(
            [
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                "--no-textconv",
                "--ignore-submodules=none",
                os.fsdecode(frozen.head),
            ],
            limit=remaining,
        )
        remaining -= len(patch)
        rows = _frozen_rows(git, frozen.head, min(8 * 1024 * 1024, remaining))
        binaries = _binary_paths(git, frozen.head, min(8 * 1024 * 1024, remaining))
        final_entries = frozen.index_map()
        if mode == "diff":
            for raw, safe in safe_paths.items():
                if safe.kind == "missing":
                    final_entries.pop(raw, None)
                else:
                    # Every accepted non-missing leaf is materialized or fail-closed.
                    final_entries[raw] = workspace_entries[raw]
        files: list[FrozenFile] = []
        for status, old_raw, raw in rows:
            lookup = old_raw or raw
            old_entry = head_entries.get(lookup)
            new_entry = final_entries.get(raw)
            old_mode, old_oid, old_kind = _entry_parts(old_entry)
            new_mode, new_oid, new_kind = _entry_parts(new_entry)
            old = _blob(git, old_oid, old_kind, remaining) if status != "A" else None
            remaining -= len(old or b"")
            new = _blob(git, new_oid, new_kind, remaining) if status != "D" else None
            remaining -= len(new or b"")
            if mode == "diff" and raw in safe_paths:
                safe = safe_paths[raw]
                new_mode, new_kind = _safe_mode(safe.kind, safe.metadata)
                # Temporary object identity is an implementation detail, not a repository OID.
                new_oid = None
                if safe.kind == "missing":
                    new = None
            path = _decode_path(raw)
            old_path = _decode_path(old_raw) if old_raw is not None else None
            files.append(
                FrozenFile(
                    ChangedFile(
                        path=path,
                        status=status,
                        old_available=old is not None or old_kind == "gitlink",
                        new_available=new is not None or new_kind == "gitlink",
                        binary=raw in binaries,
                        old_path=old_path,
                        old_kind=old_kind,
                        new_kind=new_kind,
                        old_mode=old_mode,
                        new_mode=new_mode,
                        old_oid=old_oid,
                        new_oid=new_oid,
                    ),
                    old,
                    new,
                )
            )
    return patch, tuple(files)
