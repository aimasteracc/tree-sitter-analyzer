"""Ask every corpus target on one or more long-lived servers and keep the verdict fields."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .layout import QUERY_ARGS
from .mcp_client import Server

SITE_FIELDS = (
    "unresolved_inbound_sites",
    "unresolved_sites",
    "name_only_sites",
    "non_call_reference_sites",
)
KEEP = (
    "completeness",
    "completeness_reasons",
    "caller_count",
    "verdict",
    "open_sites",
    "unresolved_inbound_sites_total",
    "unresolved_sites_total",
    "name_only_sites_total",
    "non_call_references",
    "next_step",
    "excluded_by_reason",
)
CALLER_FIELDS = (
    "file",
    "name",
    "line",
    "end_line",
    "resolution_kind",
    "via",
    "confidence_tier",
)
ERROR_FIELDS = ("__error__", "__text__")


def slim(payload: dict[str, Any]) -> dict[str, Any]:
    """The fields the gate compares (same shape as the PR-1/2/4 manual gates)."""
    keep: dict[str, Any] = {k: payload.get(k) for k in KEEP if k in payload}
    for field in ERROR_FIELDS:
        if field in payload:
            keep[field] = payload[field]
    keep["callers"] = [
        {k: c.get(k) for k in CALLER_FIELDS}
        for c in payload.get("callers") or []
        if isinstance(c, dict)
    ]
    for field in SITE_FIELDS:
        if payload.get(field) is not None:
            keep[field] = [
                {
                    "file": s.get("file"),
                    "line": s.get("line"),
                    "callee": s.get("callee"),
                }
                for s in payload[field]
            ]
    return keep


def ask_all(
    server: Server, targets: list[dict[str, Any]], progress: Callable[[int], None]
) -> list[dict[str, Any]]:
    rows = []
    for target in targets:
        args = {
            **QUERY_ARGS,
            "function_name": target["name"],
            "file_path": target["file"],
        }
        full, seconds, size = server.call("nav", args)
        compact, _csecs, csize = server.call("nav", {**args, "format": "compact"})
        compact_row = {
            k: compact.get(k) for k in ("completeness", "open_sites", "answer")
        }
        compact_row.update({k: compact[k] for k in ERROR_FIELDS if k in compact})
        rows.append(
            {
                **target,
                "full": slim(full),
                "seconds": seconds,
                "bytes": size,
                "compact": compact_row,
                "compact_bytes": csize,
            }
        )
        progress(1)
    return rows


def compute_side(
    *,
    label: str,
    python: Path,
    pkg_parent: Path,
    root: Path,
    targets: list[dict[str, Any]],
    shards: int,
    log_dir: Path,
    log: Callable[[str], None],
    costs: dict[tuple[str, str, str], float] | None = None,
) -> tuple[list[dict[str, Any]], float]:
    """Rows in target order. ``shards`` servers share the index (see :func:`split`)."""
    slices = split(targets, shards, costs)
    done = [0]
    lock = threading.Lock()
    started = time.perf_counter()
    step = max(50, len(targets) // 4)

    def progress(n: int) -> None:
        with lock:
            done[0] += n
            if done[0] % step == 0 or done[0] == len(targets):
                log(
                    f"[{label}] {done[0]}/{len(targets)} ({time.perf_counter() - started:.0f}s)"
                )

    def run(index: int) -> list[dict[str, Any]]:
        server = Server(
            python,
            pkg_parent,
            root,
            log_dir / f"{label}.{index}.stderr.log",
            log_dir / f"private-{label}-{index}",
        )
        try:
            return ask_all(server, slices[index], progress)
        finally:
            server.close()

    with ThreadPoolExecutor(max_workers=len(slices)) as pool:
        parts = list(pool.map(run, range(len(slices))))
    order = {(t["mode"], t["file"], t["qual"]): i for i, t in enumerate(targets)}
    rows = sorted(
        (row for part in parts for row in part),
        key=lambda r: order[(r["mode"], r["file"], r["qual"])],
    )
    return rows, time.perf_counter() - started


def split(
    targets: list[dict[str, Any]],
    shards: int,
    costs: dict[tuple[str, str, str], float] | None = None,
) -> list[list[dict[str, Any]]]:
    """Partition ``targets`` over ``shards`` servers; each part keeps corpus order.

    Without costs: contiguous slices. With measured costs (the other side's
    timings): longest-processing-time first, so the slowest server finishes
    close to the others.
    """
    shards = max(1, min(shards, len(targets)))
    if shards == 1:
        return [list(targets)]
    if not costs:
        size = -(-len(targets) // shards)
        return [targets[i : i + size] for i in range(0, len(targets), size)]
    loads = [0.0] * shards
    parts: list[list[int]] = [[] for _ in range(shards)]
    ranked = sorted(
        range(len(targets)),
        key=lambda i: -costs.get(
            (targets[i]["mode"], targets[i]["file"], targets[i]["qual"]), 0.0
        ),
    )
    for i in ranked:
        slot = loads.index(min(loads))
        parts[slot].append(i)
        loads[slot] += costs.get(
            (targets[i]["mode"], targets[i]["file"], targets[i]["qual"]), 0.0
        )
    return [[targets[i] for i in sorted(part)] for part in parts if part]
