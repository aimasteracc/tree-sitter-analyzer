"""Shared helpers for the RFC-0042 resident-substrate harness (``benchmarks/resident``).

The harness imports ``tree_sitter_analyzer`` the normal way, so it measures
whatever ``PYTHONPATH`` or the active environment provides (a worktree, a
wheel, a release venv). Nothing here is machine-specific.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import time
from pathlib import Path
from typing import Any

#: Stop long runs when the system drive has less free space than this (GiB).
MIN_FREE_GB = 2.0


def free_gb(path: str | os.PathLike[str] = ".") -> float:
    """Free space on the drive that holds ``path``, in GiB."""
    return shutil.disk_usage(os.path.abspath(path)).free / 2**30


def load_targets(sample: str | None, repo: str, n: int) -> list[tuple[str, str, str]]:
    """``(qualified, bare, file)`` per target.

    ``sample`` is a JSON file: either ``{"targets": [...]}`` (dogfood sample
    format) or a bare list. A row names its target with ``qual``, or with
    ``class`` + ``name``, or with ``name`` alone, plus ``file`` (repo-relative).
    Without a sample, targets are picked deterministically from the index
    (:func:`auto_targets`).
    """
    if not sample:
        return auto_targets(repo, n)
    data = json.loads(Path(sample).read_text(encoding="utf-8"))
    rows = data["targets"] if isinstance(data, dict) else data
    out: list[tuple[str, str, str]] = []
    for row in rows:
        qual = row.get("qual") or (
            f"{row['class']}.{row['name']}" if row.get("class") else row["name"]
        )
        out.append((qual, qual.rsplit(".", 1)[-1], row["file"]))
    return out[:n]


def auto_targets(repo: str, n: int) -> list[tuple[str, str, str]]:
    """``n`` targets spread evenly over the indexed definitions, sorted by file and line.

    Deterministic for one index: the same repo and commit give the same list.
    """
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    cache = ASTCache(repo)
    try:
        graph = CachedCallGraph(repo, cache=cache, fallback=False, persist=False)
        graph.build()
        refs = sorted(
            {
                (str(ref.file_path), int(ref.start_line), ref.name, ref.receiver or "")
                for ref in graph._functions
                if ref.name
            }
        )
    finally:
        cache.close()
    if not refs:
        return []
    step = max(1, len(refs) // max(1, n))
    picked = refs[::step][:n]
    return [
        (f"{receiver}.{name}" if receiver else name, name, file)
        for file, _line, name, receiver in picked
    ]


def summary_ms(seconds: list[float]) -> dict[str, Any]:
    """Median / p90 / max / n of a latency list, in milliseconds."""
    if not seconds:
        return {"n": 0}
    ordered = sorted(seconds)
    p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
    return {
        "n": len(ordered),
        "median_ms": round(statistics.median(ordered) * 1000, 1),
        "p90_ms": round(p90 * 1000, 1),
        "max_ms": round(ordered[-1] * 1000, 1),
        "mean_ms": round(statistics.fmean(ordered) * 1000, 1),
    }


class SuspendClock:
    """Detects a host suspend during a measurement: wall and monotonic drift apart."""

    def __init__(self) -> None:
        self.wall = time.time()
        self.mono = time.monotonic()

    def suspended(self, tolerance_s: float = 3.0) -> bool:
        wall = time.time() - self.wall
        mono = time.monotonic() - self.mono
        return abs(wall - mono) > tolerance_s


def write_json(path: str | None, record: dict[str, Any]) -> None:
    """Print ``record`` as one JSON line and optionally save it (indented)."""
    if path:
        Path(path).write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record))
