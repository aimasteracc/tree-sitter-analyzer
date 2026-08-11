"""Private immutable candidate bytes for destructive full-index rebuilds."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .indexing_snapshot import IndexCandidateSnapshot

from .indexing_snapshot import decode_index_source, index_source_content_hash
from .source_oracle import SourceOracleError, safe_workspace_path

_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_FILES = 100_000
_MATERIALIZE_SECONDS = 10.0


class CandidateMaterializationError(RuntimeError):
    """The destructive rebuild could not freeze its complete input epoch."""


def _write_private_file(root_fd: int, name: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=root_fd)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("candidate materialization made no write progress")
            view = view[written:]
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def index_candidate_snapshot_is_materialized(snapshot: Any) -> bool:
    """Validate the private root and every opaque frozen leaf."""
    root = getattr(snapshot, "frozen_root", None)
    if not root or getattr(snapshot, "frozen_error", None) is not None:
        return False
    try:
        root_info = os.stat(root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_IMODE(root_info.st_mode) != 0o700
        ):
            return False
        if hasattr(os, "getuid") and root_info.st_uid != os.getuid():
            return False
        selected = snapshot.selected_entries
        if len(selected) > min(snapshot.max_files, _MAX_FILES):
            return False
        for entry in selected:
            path = entry.frozen_path
            if path is None or os.path.dirname(path) != root:
                return False
            info = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or info.st_size > _MAX_FILE_BYTES
                or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            ):
                return False
        return len(os.listdir(root)) == len(selected)
    except OSError:
        return False


def cleanup_index_candidate_snapshot(snapshot: IndexCandidateSnapshot) -> None:
    """Remove a snapshot's process-private materialization, if it owns one."""
    root = getattr(snapshot, "frozen_root", None)
    if not root:
        return
    shutil.rmtree(root)


def materialize_index_candidate_snapshot(
    snapshot: IndexCandidateSnapshot,
) -> IndexCandidateSnapshot:
    """Copy every selected POSIX source into one bounded private directory.

    Logical paths remain in the snapshot entries.  ``frozen_path`` is opaque
    process-internal evidence and is never part of an MCP payload or identifier.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        return replace(snapshot, frozen_error="SECURE_MATERIALIZATION_UNSUPPORTED")
    selected = snapshot.selected_entries
    if len(selected) > min(snapshot.max_files, _MAX_FILES):
        return replace(snapshot, frozen_error="INDEX_CANDIDATE_MATERIALIZATION_BUDGET")

    root = tempfile.mkdtemp(prefix="tsa-index-candidate-")
    os.chmod(root, 0o700)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    deadline = time.monotonic() + _MATERIALIZE_SECONDS
    total = 0
    replacements: dict[str, Any] = {}
    try:
        for ordinal, entry in enumerate(selected):
            if time.monotonic() >= deadline:
                raise CandidateMaterializationError(
                    "INDEX_CANDIDATE_MATERIALIZATION_DEADLINE"
                )
            fingerprint = entry.fingerprint
            if fingerprint is None or not fingerprint.content_hash:
                raise CandidateMaterializationError(
                    "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"
                )
            captured = safe_workspace_path(
                snapshot.project_root,
                entry.rel_path,
                deadline=deadline,
                limit=_MAX_FILE_BYTES,
                expected_chain=fingerprint.descriptor_chain,
            )
            if captured.kind != "file" or captured.data is None:
                raise CandidateMaterializationError("INDEX_CANDIDATE_SOURCE_CHANGED")
            data = captured.data
            total += len(data)
            if total > _MAX_TOTAL_BYTES:
                raise CandidateMaterializationError(
                    "INDEX_CANDIDATE_MATERIALIZATION_BUDGET"
                )
            content_hash = index_source_content_hash(decode_index_source(data))
            if content_hash != fingerprint.content_hash:
                raise CandidateMaterializationError("INDEX_CANDIDATE_SOURCE_CHANGED")
            name = f"candidate-{ordinal:08x}"
            _write_private_file(root_fd, name, data)
            replacements[entry.rel_path] = replace(
                entry, frozen_path=os.path.join(root, name)
            )
        entries = tuple(
            replacements.get(entry.rel_path, entry) for entry in snapshot.entries
        )
        return replace(snapshot, entries=entries, frozen_root=root, frozen_error=None)
    except (OSError, SourceOracleError, CandidateMaterializationError) as exc:
        try:
            shutil.rmtree(root)
        except OSError as cleanup_exc:
            return replace(
                snapshot,
                frozen_error=f"INDEX_CANDIDATE_CLEANUP_FAILED: {cleanup_exc}",
            )
        return replace(snapshot, frozen_error=str(exc) or type(exc).__name__)
    finally:
        os.close(root_fd)
