"""Bounded incremental filesystem enumeration for index candidates."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from typing import Any


class CandidateDiscoveryBudgetExceeded(RuntimeError):
    """Raised after the first filesystem entry beyond a discovery budget."""


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
    scanners: list[Any] = []
    try:
        try:
            scanners.append(os.scandir(project_root))
        except OSError:
            return
        while scanners:
            scanner = scanners[-1]
            try:
                entry = next(scanner)
            except StopIteration:
                scanners.pop().close()
                continue
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
            except OSError:
                is_directory = False
            if not is_directory:
                yield os.fspath(entry.path)
            elif entry.name not in excluded_dir_names and not entry.name.startswith(
                "."
            ):
                scanners.append(os.scandir(entry.path))
    finally:
        for scanner in reversed(scanners):
            scanner.close()
