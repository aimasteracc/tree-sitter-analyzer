"""Git patch capture and immutable file materialization for diff snapshots."""

from __future__ import annotations

import base64
import json
import os
import stat
from dataclasses import dataclass

from .source_oracle import (
    SourceOracleError,
    git_output,
    normalize_repo_path,
    safe_workspace_path,
)
from .source_oracle_git import _head_entries, _head_identity, _index_entries


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
            "path": self.path,
            "status": self.status,
            "old_available": self.old_available,
            "new_available": self.new_available,
            "binary": self.binary,
            "patch_available": self.patch_available,
        }
        if self.old_path is not None:
            value["old_path"] = self.old_path
        value["old_kind"] = self.old_kind
        value["new_kind"] = self.new_kind
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


def _rows(
    root: str, mode: str, deadline: float, limit: int
) -> list[tuple[str, str | None, str, bool]]:
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--name-status",
        "-z",
        "--find-renames",
        "--no-ext-diff",
    ]
    raw = git_output(root, args, deadline=deadline, limit=limit)
    tokens = [x for x in raw.split(b"\0") if x]
    result: list[tuple[str, str | None, str, bool]] = []
    index = 0
    while index < len(tokens):
        status_raw = tokens[index]
        index += 1
        status = status_raw[:1].decode("ascii", "strict")
        try:
            if status in ("R", "C"):
                old_raw, path_raw = tokens[index : index + 2]
                index += 2
                old = normalize_repo_path(old_raw.decode("utf-8", "surrogateescape"))
            else:
                path_raw = tokens[index]
                index += 1
                old = None
            path = normalize_repo_path(path_raw.decode("utf-8", "surrogateescape"))
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
            if not item:
                continue
            path = normalize_repo_path(item.decode("utf-8", "surrogateescape"))
            if path not in known:
                result.append(("A", None, path, False))
    return sorted(result, key=lambda row: os.fsencode(row[2]))


def _blob(root: str, spec: str, deadline: float, limit: int) -> bytes:
    return git_output(root, ["show", spec], deadline=deadline, limit=limit)


def _tracked_binary_paths(
    root: str, mode: str, deadline: float, limit: int
) -> set[str]:
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--numstat",
        "-z",
        "--no-ext-diff",
    ]
    raw = git_output(root, args, deadline=deadline, limit=limit)
    binary: set[str] = set()
    tokens = raw.split(b"\0")
    index = 0
    while index < len(tokens):
        row = tokens[index]
        index += 1
        if not row:
            continue
        fields = row.split(b"\t", 2)
        if len(fields) != 3:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        path_raw = fields[2]
        if not path_raw:
            # With -z, rename/copy rows continue as old-path NUL new-path NUL.
            try:
                _old_raw = tokens[index]
                path_raw = tokens[index + 1]
            except IndexError as exc:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
            index += 2
            if not _old_raw or not path_raw:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if fields[0] == fields[1] == b"-":
            binary.add(normalize_repo_path(path_raw.decode("utf-8", "surrogateescape")))
    return binary


def _untracked_segment(path: str, data: bytes, file_mode: int, binary: bool) -> bytes:
    # Synthetic records are deliberately not represented as fake Git patches.
    record = {
        "binary": binary,
        "content_b64": base64.b64encode(data).decode("ascii"),
        "mode": stat.S_IMODE(file_mode),
        "path_b64": base64.b64encode(os.fsencode(path)).decode("ascii"),
        "type": "tsa-untracked-v1",
    }
    return (
        b"\n"
        + json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        + b"\n"
    )


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


def _capture_payload(
    root: str,
    mode: str,
    deadline: float,
    ceiling: int,
    expected_manifest: dict[str, tuple[bytes, ...]] | None = None,
) -> tuple[bytes, tuple[FrozenFile, ...]]:
    remaining = ceiling
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--binary",
        "--full-index",
        "--no-ext-diff",
    ]
    patch = git_output(root, args, deadline=deadline, limit=remaining)
    remaining -= len(patch)
    rows = _rows(root, mode, deadline, min(8 * 1024 * 1024, remaining))
    binaries = _tracked_binary_paths(
        root, mode, deadline, min(8 * 1024 * 1024, remaining)
    )
    index_entries: dict[bytes, bytes] | None = None
    head_entries: dict[bytes, bytes] | None = None
    files: list[FrozenFile] = []
    additions = bytearray()
    for status, old_path, path, tracked in rows:
        lookup = old_path or path
        if tracked and index_entries is None:
            index_entries = _index_entries(root, deadline=deadline)
            head = _head_identity(root, deadline=deadline)
            head_entries = _head_entries(root, deadline=deadline, head=head)
        old_entry = None
        new_entry = None
        if tracked:
            assert index_entries is not None and head_entries is not None
            old_entry = (
                head_entries.get(os.fsencode(lookup))
                if mode == "staged"
                else index_entries.get(os.fsencode(lookup))
            )
            new_entry = index_entries.get(os.fsencode(path))
        old_mode, old_oid, old_kind = _entry_parts(old_entry)
        new_mode, new_oid, new_kind = _entry_parts(new_entry)
        old: bytes | None = None
        new: bytes | None = None
        mode_bits = 0
        if status != "A" and old_kind != "gitlink":
            old = _blob(
                root,
                f"HEAD:{lookup}" if mode == "staged" else f":{lookup}",
                deadline,
                remaining,
            )
            remaining -= len(old)
        if status != "D" and new_kind != "gitlink":
            if mode == "staged":
                new = _blob(root, f":{path}", deadline, remaining)
                remaining -= len(new)
            else:
                safe = safe_workspace_path(
                    root,
                    path,
                    deadline=deadline,
                    limit=remaining,
                    expected_chain=(expected_manifest or {}).get(path),
                )
                if safe.data is None:
                    raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
                new = safe.data
                new_kind = safe.kind
                remaining -= len(new)
                if safe.metadata:
                    try:
                        mode_bits = int(safe.metadata[-1].split(b",")[2])
                    except (ValueError, IndexError):
                        mode_bits = 0
        binary = path in binaries or (not tracked and new is not None and b"\0" in new)
        record = ChangedFile(
            path,
            status,
            status != "A",
            status != "D",
            binary,
            old_path,
            tracked,
            old_kind,
            new_kind,
            old_mode,
            new_mode,
            old_oid,
            new_oid,
        )
        files.append(FrozenFile(record, old, new))
        if not tracked and new is not None:
            segment = _untracked_segment(path, new, mode_bits, binary)
            if len(segment) > remaining:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            additions.extend(segment)
            remaining -= len(segment)
    return patch + bytes(additions), tuple(files)
