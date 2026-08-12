"""Private immutable candidate bytes for destructive full-index rebuilds."""

from __future__ import annotations

import codecs
import logging
import os
import stat
import tempfile
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .indexing_snapshot import IndexCandidateSnapshot, IndexFileFingerprint

from .indexing_snapshot import index_source_content_hash
from .source_oracle import SourceOracleError, safe_workspace_path

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_FILES = 100_000
_MAX_READ_CHUNK = 1024 * 1024
_MATERIALIZE_SECONDS = 10.0
_FROZEN_READ_SECONDS = 35.0
_CLEANUP_WARNING_CHARS = 240


class CandidateMaterializationError(RuntimeError):
    """The destructive rebuild could not freeze its complete input epoch."""


def secure_candidate_materialization_supported() -> bool:
    """Whether this host can produce authoritative private frozen evidence."""
    return os.name == "posix" and hasattr(os, "O_NOFOLLOW")


def open_index_candidate_snapshot_root(snapshot: Any) -> int | None:
    """Open and identity-bind the captured root for fd-relative mutations."""
    expected = getattr(snapshot, "root_identity", None)
    if expected is None or not secure_candidate_materialization_supported():
        return None
    root = os.path.realpath(os.path.abspath(snapshot.project_root))
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    fd: int | None = None
    try:
        fd = os.open(root, flags)
        info = os.fstat(fd)
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None
    if (
        not stat.S_ISDIR(info.st_mode)
        or (
            root,
            int(info.st_dev),
            int(info.st_ino),
        )
        != expected
    ):
        try:
            os.close(fd)
        except OSError:
            pass
        return None
    return fd


def index_candidate_snapshot_root_is_current(snapshot: Any) -> bool:
    """Revalidate the canonical project-root object captured at discovery."""
    fd = open_index_candidate_snapshot_root(snapshot)
    if fd is None:
        return False
    try:
        os.close(fd)
    except OSError:
        return False
    return True


def index_candidate_cache_hierarchy_is_current(
    snapshot: Any, cache: Any, *, root_fd: int | None = None
) -> bool:
    """Require the pinned cache directory to remain visible below the captured root."""
    if not getattr(cache, "_uses_project_mirror", True):
        return True
    cache_fd = getattr(cache, "_cache_dir_fd", None)
    if cache_fd is None or not secure_candidate_materialization_supported():
        return False
    owns_root = root_fd is None
    if root_fd is None:
        root_fd = open_index_candidate_snapshot_root(snapshot)
    if root_fd is None:
        return False
    probe_fd: int | None = None
    try:
        expected_root = getattr(snapshot, "root_identity", None)
        root_info = os.fstat(root_fd)
        if expected_root is None or (
            int(root_info.st_dev),
            int(root_info.st_ino),
        ) != (expected_root[1], expected_root[2]):
            return False
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        probe_fd = os.open(".ast-cache", flags, dir_fd=root_fd)
        expected = os.fstat(cache_fd)
        observed = os.fstat(probe_fd)
        return (expected.st_dev, expected.st_ino) == (
            observed.st_dev,
            observed.st_ino,
        )
    except OSError:
        return False
    finally:
        if probe_fd is not None:
            os.close(probe_fd)
        if owns_root:
            try:
                os.close(root_fd)
            except OSError:
                pass


def _write_private_file(root_fd: int, name: str, data: bytes) -> tuple[int, int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(name, flags, 0o600, dir_fd=root_fd)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("candidate materialization made no write progress")
            view = view[written:]
        os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        return (int(info.st_dev), int(info.st_ino), int(info.st_size))
    finally:
        os.close(fd)


def read_frozen_candidate(
    path: str,
    *,
    expected: IndexFileFingerprint | None = None,
    frozen_identity: tuple[int, int, int] | None = None,
    deadline: float | None = None,
    limit: int = _MAX_FILE_BYTES,
) -> str:
    """Read and certify one frozen leaf without pathname-following or blocking IO."""
    if deadline is None:
        deadline = time.monotonic() + _FROZEN_READ_SECONDS
    if time.monotonic() >= deadline:
        raise OSError("frozen candidate read deadline exceeded")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        identity = (
            int(getattr(info, "st_dev", 0)),
            int(getattr(info, "st_ino", 0)),
            int(info.st_size),
        )
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > limit
            or (frozen_identity is not None and identity != frozen_identity)
        ):
            raise OSError("invalid frozen candidate")
        if expected is not None and info.st_size != expected.file_size:
            raise OSError("frozen candidate source size changed")

        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pieces: list[str] = []
        total = 0
        while True:
            if time.monotonic() >= deadline:
                raise OSError("frozen candidate read deadline exceeded")
            chunk = os.read(fd, min(_MAX_READ_CHUNK, limit - total + 1))
            if time.monotonic() >= deadline:
                raise OSError("frozen candidate read deadline exceeded")
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise OSError("frozen candidate exceeds byte limit")
            pieces.append(decoder.decode(chunk, final=False))
        pieces.append(decoder.decode(b"", final=True))
        source = "".join(pieces).replace("\r\n", "\n").replace("\r", "\n")
        if expected is not None and (
            total != expected.file_size
            or index_source_content_hash(source) != expected.content_hash
        ):
            raise OSError("frozen candidate source fingerprint changed")
        return source
    finally:
        os.close(fd)


def index_candidate_snapshot_is_materialized(
    snapshot: Any, *, deadline: float | None = None
) -> bool:
    """Preflight the private root and re-read every opaque frozen leaf."""
    root = getattr(snapshot, "frozen_root", None)
    if deadline is None:
        deadline = getattr(snapshot, "frozen_read_deadline", None)
    if (
        not root
        or getattr(snapshot, "frozen_error", None) is not None
        or deadline is None
        or not index_candidate_snapshot_root_is_current(snapshot)
    ):
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
            fingerprint = entry.fingerprint
            if (
                path is None
                or os.path.dirname(path) != root
                or fingerprint is None
                or entry.frozen_identity is None
            ):
                return False
            info = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            ):
                return False
            read_frozen_candidate(
                path,
                expected=fingerprint,
                frozen_identity=entry.frozen_identity,
                deadline=deadline,
            )
        return len(os.listdir(root)) == len(selected)
    except OSError:
        return False


def _cleanup_warning(exc: BaseException) -> str:
    detail = " ".join(str(exc).split()) or type(exc).__name__
    return f"INDEX_CANDIDATE_CLEANUP_FAILED: {detail}"[:_CLEANUP_WARNING_CHARS]


def cleanup_index_candidate_snapshot(snapshot: IndexCandidateSnapshot) -> str | None:
    """Best-effort idempotent cleanup which never masks a committed result."""
    root = getattr(snapshot, "frozen_root", None)
    if not root:
        return None
    errors: list[BaseException] = []
    root_fd: int | None = None
    try:
        root_fd = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
    except FileNotFoundError:
        return None
    except Exception as exc:
        errors.append(exc)

    root_matches_capture = False
    if root_fd is not None:
        try:
            opened = os.fstat(root_fd)
            expected_identity = getattr(snapshot, "frozen_root_identity", None)
            root_matches_capture = (
                expected_identity is None
                or (int(opened.st_dev), int(opened.st_ino)) == expected_identity
            )
            if not root_matches_capture:
                errors.append(
                    CandidateMaterializationError(
                        "INDEX_CANDIDATE_CLEANUP_ROOT_REPLACED"
                    )
                )
            else:
                for entry in snapshot.selected_entries:
                    path = entry.frozen_path
                    if path is None or os.path.dirname(path) != root:
                        continue
                    name = os.path.basename(path)
                    try:
                        os.unlink(name, dir_fd=root_fd)
                        continue
                    except FileNotFoundError:
                        continue
                    except Exception:
                        pass
                    try:
                        os.chmod(name, 0o600, dir_fd=root_fd, follow_symlinks=False)
                        os.unlink(name, dir_fd=root_fd)
                    except FileNotFoundError:
                        pass
                    except Exception as exc:
                        errors.append(exc)
                for name in os.listdir(root_fd):
                    try:
                        os.unlink(name, dir_fd=root_fd)
                    except FileNotFoundError:
                        pass
                    except Exception as exc:
                        errors.append(exc)
        except Exception as exc:
            errors.append(exc)
        finally:
            try:
                os.close(root_fd)
            except OSError as exc:
                errors.append(exc)

    if root_matches_capture:
        try:
            current = os.stat(root, follow_symlinks=False)
            expected_identity = getattr(snapshot, "frozen_root_identity", None)
            if (
                expected_identity is not None
                and (int(current.st_dev), int(current.st_ino)) != expected_identity
            ):
                raise CandidateMaterializationError(
                    "INDEX_CANDIDATE_CLEANUP_ROOT_REPLACED"
                )
            # Known frozen leaves were removed through the captured directory fd.
            # A non-recursive removal cannot erase a pathname replacement's contents.
            os.rmdir(root)
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append(exc)
    if not errors:
        return None
    warning = _cleanup_warning(errors[-1])
    logger.warning("candidate materialization cleanup warning: %s", warning)
    return warning


def release_index_candidate_snapshot(
    snapshot: IndexCandidateSnapshot, result: dict[str, Any] | None = None
) -> None:
    """Release once at an ownership boundary and attach a non-fatal metric."""
    try:
        warning = cleanup_index_candidate_snapshot(snapshot)
    except Exception as exc:  # final ownership boundary: never mask primary output
        warning = _cleanup_warning(exc)
        logger.warning("candidate materialization cleanup warning: %s", warning)
    if warning is not None and result is not None:
        result["cleanup_warning"] = warning


def materialize_index_candidate_snapshot(
    snapshot: IndexCandidateSnapshot,
) -> IndexCandidateSnapshot:
    """Copy every selected POSIX source into one bounded private directory."""
    if not secure_candidate_materialization_supported():
        return replace(snapshot, frozen_error="SECURE_MATERIALIZATION_UNSUPPORTED")
    selected = snapshot.selected_entries
    if len(selected) > min(snapshot.max_files, _MAX_FILES):
        return replace(snapshot, frozen_error="INDEX_CANDIDATE_MATERIALIZATION_BUDGET")

    root: str | None = None
    root_fd: int | None = None
    root_identity: tuple[int, int] | None = None
    started = time.monotonic()
    deadline = started + _MATERIALIZE_SECONDS
    read_deadline = started + _FROZEN_READ_SECONDS
    total = 0
    replacements: dict[str, Any] = {}
    try:
        root = tempfile.mkdtemp(prefix="tsa-index-candidate-")
        os.chmod(root, 0o700)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_info = os.fstat(root_fd)
        root_identity = (int(root_info.st_dev), int(root_info.st_ino))
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
            if (
                len(data) != fingerprint.file_size
                or index_source_content_hash(
                    data.decode("utf-8", errors="replace")
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                )
                != fingerprint.content_hash
            ):
                raise CandidateMaterializationError("INDEX_CANDIDATE_SOURCE_CHANGED")
            name = f"candidate-{ordinal:08x}"
            identity = _write_private_file(root_fd, name, data)
            replacements[entry.rel_path] = replace(
                entry,
                frozen_path=os.path.join(root, name),
                frozen_identity=identity,
            )
        entries = tuple(
            replacements.get(entry.rel_path, entry) for entry in snapshot.entries
        )
        return replace(
            snapshot,
            entries=entries,
            frozen_root=root,
            frozen_root_identity=root_identity,
            frozen_error=None,
            frozen_read_deadline=read_deadline,
        )
    except (OSError, SourceOracleError, CandidateMaterializationError) as exc:
        partial_entries = tuple(
            replacements.get(entry.rel_path, entry) for entry in snapshot.entries
        )
        failed = replace(
            snapshot,
            entries=partial_entries,
            frozen_root=root,
            frozen_root_identity=root_identity,
        )
        if root_fd is not None:
            os.close(root_fd)
            root_fd = None
        cleanup_warning = cleanup_index_candidate_snapshot(failed)
        reason = str(exc) or type(exc).__name__
        if cleanup_warning is not None:
            logger.warning("freeze failure followed by %s", cleanup_warning)
        return replace(snapshot, frozen_error=reason)
    finally:
        if root_fd is not None:
            os.close(root_fd)
        if root is not None and root_identity is None:
            try:
                os.rmdir(root)
            except OSError:
                pass
