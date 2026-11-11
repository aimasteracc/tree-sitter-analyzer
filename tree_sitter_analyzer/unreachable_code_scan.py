#!/usr/bin/env python3
"""Project-wide unreachable-code scan that keeps its evidence counts (#1955).

``analyze_project_unreachable`` returns only the files with findings or
errors. A caller that sums ``functions_analyzed`` over that list counts 0 on
every clean project, and that looks the same as "scanned nothing". This scan
keeps the per-file results the old API returned, plus how much was actually
analyzed and skipped, so the answer can say *how much* evidence it rests on.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from .project_graph import _language_from_ext
from .unreachable_code import (
    _EXCLUDE_DIRS,
    UnreachableCodeResult,
    analyze_file_unreachable,
)

_TEST_PATH = re.compile(
    r"(?:^test_|_test\.|\.test\.|\.spec\.|_spec\.|tests?/|Test\.py$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProjectUnreachableScan:
    """What a project scan found and how much it looked at."""

    results: list[UnreachableCodeResult] = field(default_factory=list)
    files_analyzed: int = 0
    functions_analyzed: int = 0
    skipped_test_files: int = 0
    truncated: bool = False
    #: First analyzed file (absolute), for a concrete follow-up command.
    sample_file: str | None = None


def scan_project_unreachable(
    project_root: str,
    *,
    include_test_files: bool = False,
    max_files: int = 500,
) -> ProjectUnreachableScan:
    """Scan ``project_root`` and count every analyzed file and function."""
    results: list[UnreachableCodeResult] = []
    files = functions = skipped = 0
    truncated = False
    sample: str | None = None

    for full, rel_posix in _source_files(project_root):
        if not include_test_files and _TEST_PATH.search(rel_posix):
            skipped += 1
            continue
        if files >= max_files:
            truncated = True
            break
        result = analyze_file_unreachable(full, language=_language_from_ext(full))
        files += 1
        functions += result.functions_analyzed
        sample = sample or full
        if result.unreachable_blocks or result.errors:
            results.append(result)

    return ProjectUnreachableScan(
        results=results,
        files_analyzed=files,
        functions_analyzed=functions,
        skipped_test_files=skipped,
        truncated=truncated,
        sample_file=sample,
    )


def _source_files(project_root: str) -> Iterator[tuple[str, str]]:
    """Yield ``(absolute path, root-relative posix path)`` for source files."""
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        )
        for fname in sorted(filenames):
            full = os.path.join(dirpath, fname)
            if _language_from_ext(full) is None:
                continue
            rel = os.path.relpath(full, project_root)
            yield full, rel.replace(os.sep, "/")
