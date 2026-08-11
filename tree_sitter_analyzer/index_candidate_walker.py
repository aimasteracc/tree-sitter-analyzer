"""Bounded incremental filesystem enumeration for index candidates."""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Iterable
from typing import Any


class CandidateDiscoveryBudgetExceeded(RuntimeError):
    """Raised after the first filesystem entry beyond a discovery budget."""


class CandidateDiscoveryError(RuntimeError):
    """Raised when filesystem enumeration cannot produce an authoritative scope."""


_DISCOVERY_ERROR = "INDEX_CANDIDATE_DISCOVERY_ERROR"


def walk_candidate_entries(
    project_root: str,
    *,
    excluded_dir_names: frozenset[str],
    entry_budget: int,
    path_byte_budget: int,
    discovery_seconds: float,
    budget_error: str,
) -> Iterable[str]:
    """Yield non-directories while charging every entry before filtering."""
    deadline = time.monotonic() + discovery_seconds
    entry_count = 0
    path_bytes = 0
    if os.name != "posix":  # pragma: no cover - exercised by Windows CI
        yield from _walk_path_entries(
            project_root,
            excluded_dir_names,
            entry_budget,
            path_byte_budget,
            deadline,
            budget_error,
        )
        return

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    scanners: list[tuple[Any, int, str]] = []
    root_fd: int | None = None
    try:
        try:
            root_fd = os.open(project_root, directory_flags)
            os.fstat(root_fd)  # bind discovery to this directory identity
            scanners.append((os.scandir(root_fd), root_fd, ""))
            root_fd = None  # the scanner frame owns it now
        except OSError as exc:
            raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
        while scanners:
            scanner, parent_fd, parent_rel = scanners[-1]
            try:
                entry = next(scanner)
            except StopIteration:
                scanners.pop()
                _close_scanner_fd(scanner, parent_fd)
                continue
            except OSError as exc:
                raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
            entry_count += 1
            rel_path = (
                os.path.join(parent_rel, entry.name) if parent_rel else entry.name
            )
            abs_path = os.path.join(project_root, rel_path)
            try:
                path_bytes += len(
                    os.fspath(abs_path).encode("utf-8", errors="surrogatepass")
                )
            except (TypeError, UnicodeError):
                path_bytes = path_byte_budget + 1
            if (
                entry_count > entry_budget
                or path_bytes > path_byte_budget
                or time.monotonic() > deadline
            ):
                raise CandidateDiscoveryBudgetExceeded(budget_error)
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
            if not is_directory:
                yield abs_path
                continue
            if entry.name in excluded_dir_names or entry.name.startswith("."):
                continue
            child_fd: int | None = None
            try:
                child_fd = os.open(
                    entry.name,
                    directory_flags | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=parent_fd,
                )
                child_info = os.fstat(child_fd)
                if not stat.S_ISDIR(child_info.st_mode):
                    raise OSError("candidate child is not a directory")
                child_scanner = os.scandir(child_fd)
            except OSError as exc:
                if child_fd is not None:
                    os.close(child_fd)
                raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
            scanners.append((child_scanner, child_fd, rel_path))
    finally:
        if root_fd is not None:
            os.close(root_fd)
        for scanner, fd, _rel in reversed(scanners):
            try:
                _close_scanner_fd(scanner, fd)
            except OSError:
                pass


def _close_scanner_fd(scanner: Any, fd: int) -> None:
    try:
        scanner.close()
    finally:
        os.close(fd)


def _walk_path_entries(
    project_root: str,
    excluded_dir_names: frozenset[str],
    entry_budget: int,
    path_byte_budget: int,
    deadline: float,
    budget_error: str,
) -> Iterable[str]:
    """Non-POSIX fallback; secure snapshot capture is unsupported on this path."""
    entry_count = 0
    path_bytes = 0
    scanners: list[Any] = []
    try:
        try:
            scanners.append(os.scandir(project_root))
        except OSError as exc:
            raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
        while scanners:
            scanner = scanners[-1]
            try:
                entry = next(scanner)
            except StopIteration:
                scanners.pop().close()
                continue
            except OSError as exc:
                raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
            entry_count += 1
            try:
                path_bytes += len(
                    os.fspath(entry.path).encode("utf-8", errors="surrogatepass")
                )
            except (TypeError, UnicodeError):
                path_bytes = path_byte_budget + 1
            if (
                entry_count > entry_budget
                or path_bytes > path_byte_budget
                or time.monotonic() > deadline
            ):
                raise CandidateDiscoveryBudgetExceeded(budget_error)
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
            if not is_directory:
                yield os.fspath(entry.path)
            elif entry.name not in excluded_dir_names and not entry.name.startswith(
                "."
            ):
                try:
                    scanners.append(os.scandir(entry.path))
                except OSError as exc:
                    raise CandidateDiscoveryError(_DISCOVERY_ERROR) from exc
    finally:
        for scanner in reversed(scanners):
            scanner.close()
