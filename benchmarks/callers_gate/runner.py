"""``run``: per repo, ensure the index, get base answers (cache or compute), compute head answers."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import answers, corpus, index_store, keys, sides
from .layout import REPOS, Layout, RepoPin
from .query import compute_side
from .transitions import classify_pair, row_key

#: Attempts to re-ask a budget-limited row after the main pass.
MAX_BUDGET_RETRIES = 2
#: Resident memory of one server (GiB; measured peak ~0.2) with headroom, for the --jobs default.
SERVER_GB = 0.5
#: Relative cost per target (seconds, measured) -- orders repos longest first.
COST_HINT = {
    "zod": 3.4,
    "fastapi": 0.5,
    "pydantic": 0.45,
    "axios": 0.4,
    "hono": 0.65,
    "gson": 0.13,
    "rich": 0.12,
}


def default_jobs() -> int:
    """Concurrent servers: bounded by cores (2 per server) and by free memory."""
    cpus = os.cpu_count() or 2
    free_gb = _free_memory_gb()
    by_mem = int(max(1.0, (free_gb - 2.0) / SERVER_GB)) if free_gb else 4
    return max(1, min(cpus // 2, by_mem, 8))


def _free_memory_gb() -> float | None:
    if os.name == "nt":
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _Status()
        status.dwLength = ctypes.sizeof(_Status)
        kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009 - Windows-only attribute
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return float(status.ullAvailPhys) / 2**30
        return None
    sysconf = getattr(os, "sysconf", None)
    try:
        return (
            float(sysconf("SC_AVPHYS_PAGES") * sysconf("SC_PAGE_SIZE")) / 2**30
            if sysconf
            else None
        )
    except (ValueError, OSError):
        return None


@dataclass
class RepoRun:
    repo: str
    index_key: str = ""
    index_built: bool = False
    baseline_hit: bool = False
    baseline_source: str = ""
    base_rows: list[dict[str, Any]] = field(default_factory=list)
    head_rows: list[dict[str, Any]] = field(default_factory=list)
    root: Path | None = None
    timings: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    retried: list[dict[str, Any]] = field(default_factory=list)
    retry_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    layout: Layout
    python: Path
    base: sides.Side
    head: sides.Side
    git_dir: Path  # a TSA checkout that can resolve both refs
    env_key: str
    manifest: dict[str, str]
    run_dir: Path
    shards: dict[str, int]
    log: Callable[[str], None]
    _materialize_lock: threading.Lock = field(default_factory=threading.Lock)

    def pkg(self, side: sides.Side) -> Path:
        with self._materialize_lock:
            return sides.materialize(self.layout, self.git_dir, side)


def run_repo(ctx: RunContext, pin: RepoPin) -> RepoRun:
    out = RepoRun(pin.name)
    log = ctx.log
    t0 = time.perf_counter()
    targets, targets_sha = corpus.load_targets(ctx.layout, pin.name, ctx.manifest)
    query_key = keys.query_key(targets_sha256=targets_sha)
    out.index_key = keys.index_key(
        repo=pin.name,
        repo_sha=pin.sha,
        package_blobs=ctx.head.blobs,
        pyproject_blob=ctx.head.pyproject_blob,
        env_fingerprint=ctx.env_key,
    )
    head_pkg = ctx.pkg(ctx.head)
    info = index_store.ensure_index(
        ctx.layout,
        pin,
        out.index_key,
        python=ctx.python,
        head_pkg_parent=head_pkg,
        excluded_modules=keys.query_only_modules(ctx.head.blobs),
        built_by=ctx.head.tree,
        log=log,
    )
    out.root, out.index_built = info.root, info.built
    out.timings["index"] = time.perf_counter() - t0
    log(
        f"[{pin.name}] index {out.index_key} {'built' if info.built else 'reused'} ({out.timings['index']:.0f}s)"
    )

    base_key = answers.AnswerKey(
        ctx.base.tree, out.index_key, pin.name, pin.sha, query_key
    )
    base_path = ctx.layout.baseline(ctx.base.tree, out.index_key, pin.name)
    cached = answers.read_answers(base_path, base_key, log)
    if cached is None:
        promoted = answers.read_answers(
            ctx.layout.result(ctx.base.tree, out.index_key, pin.name), base_key, log
        )
        if promoted is not None:
            answers.write_answers(base_path, base_key, promoted, "promoted:results")
            cached = promoted
            log(
                f"[{pin.name}] base answers promoted from results/ (same tree, same index key)"
            )
    shards = ctx.shards.get(pin.name, 1)
    if cached is not None:
        out.base_rows, out.baseline_hit, out.baseline_source = cached, True, "cache"
        out.timings["base"] = 0.0
        log(f"[{pin.name}] base answers: cache hit ({len(cached)} rows)")
    else:
        rows, secs = compute_side(
            label=f"{pin.name}-base",
            python=ctx.python,
            pkg_parent=ctx.pkg(ctx.base),
            root=info.root,
            targets=targets,
            shards=shards,
            log_dir=ctx.run_dir / "logs",
            log=log,
        )
        answers.write_answers(base_path, base_key, rows, "computed")
        out.base_rows, out.baseline_source = rows, "computed"
        out.timings["base"] = secs
        log(f"[{pin.name}] base answers computed in {secs:.0f}s")

    costs = {
        (r["mode"], r["file"], r["qual"]): float(r.get("seconds") or 0.0)
        for r in out.base_rows
    }
    rows, secs = compute_side(
        costs=costs,
        label=f"{pin.name}-head",
        python=ctx.python,
        pkg_parent=head_pkg,
        root=info.root,
        targets=targets,
        shards=shards,
        log_dir=ctx.run_dir / "logs",
        log=log,
    )
    head_key = answers.AnswerKey(
        ctx.head.tree, out.index_key, pin.name, pin.sha, query_key
    )
    answers.write_answers(
        ctx.layout.result(ctx.head.tree, out.index_key, pin.name),
        head_key,
        rows,
        "computed",
    )
    out.head_rows = rows
    out.timings["head"] = secs
    out.timings["total"] = time.perf_counter() - t0
    out.retry_context = {
        "targets": targets,
        "base": (ctx.pkg(ctx.base), base_path, base_key),
        "head": (
            head_pkg,
            ctx.layout.result(ctx.head.tree, out.index_key, pin.name),
            head_key,
        ),
    }
    log(
        f"[{pin.name}] head answers computed in {secs:.0f}s; repo total {out.timings['total']:.0f}s"
    )
    return out


def run_all(ctx: RunContext, repos: list[str], jobs: int) -> list[RepoRun]:
    pins = sorted((REPOS[r] for r in repos), key=lambda p: -COST_HINT.get(p.name, 1.0))
    results: dict[str, RepoRun] = {}
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(run_repo, ctx, pin): pin.name for pin in pins}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - one repo failing must not hide the others
                ctx.log(f"[{name}] ERROR {type(exc).__name__}: {exc}")
                results[name] = RepoRun(name, error=f"{type(exc).__name__}: {exc}")
    for name in repos:
        run = results[name]
        if run.error is None:
            try:
                retry_budget_rows(ctx, run)
            except Exception as exc:  # noqa: BLE001 - reported, never a silent pass
                ctx.log(f"[{name}] ERROR in budget retry {type(exc).__name__}: {exc}")
                run.error = f"budget retry: {type(exc).__name__}: {exc}"
    return [results[r] for r in repos]


def budget_limited(row: dict[str, Any]) -> bool:
    """An answer that a wall-clock budget may have degraded (load-dependent, not code-dependent).

    TSA reports ``*_UNCHECKED`` when a check ran out of time, and the compact
    form is computed by a separate call that may land on the other side of a
    budget. Such a row is re-asked once the machine is quieter.
    """
    full = row["full"]
    if any(
        str(r).endswith("_UNCHECKED") for r in full.get("completeness_reasons") or ()
    ):
        return True
    compact = (row.get("compact") or {}).get("completeness")
    return bool(compact != full.get("completeness"))


def retry_budget_rows(
    ctx: RunContext, run: RepoRun, attempts: int = MAX_BUDGET_RETRIES
) -> None:
    """Re-ask, on one quiet server per side, every changed row that a budget may explain.

    Runs after all repos finished (so with little contention). A retried row
    replaces the cached one only when it is no longer budget-limited; the cache
    file is rewritten with the conclusive answer for the same code and index.
    """
    base_by = {row_key(r): r for r in run.base_rows}
    keys_ = [
        row_key(r)
        for r in run.head_rows
        if row_key(r) in base_by
        and classify_pair(base_by[row_key(r)], r)
        and (budget_limited(r) or budget_limited(base_by[row_key(r)]))
    ]
    if not keys_ or run.root is None:
        return
    started = time.perf_counter()
    wanted = set(keys_)
    targets = [
        t
        for t in run.retry_context["targets"]
        if (t["mode"], t["file"], t["qual"]) in wanted
    ]
    for side in ("base", "head"):
        rows = run.base_rows if side == "base" else run.head_rows
        pkg, path, akey = run.retry_context[side]
        by_key = {row_key(r): r for r in rows}
        pending = [
            t
            for t in targets
            if budget_limited(by_key[(t["mode"], t["file"], t["qual"])])
        ]
        for attempt in range(1, attempts + 1):
            if not pending:
                break
            fresh, _secs = compute_side(
                label=f"{run.repo}-{side}-retry{attempt}",
                python=ctx.python,
                pkg_parent=pkg,
                root=run.root,
                targets=pending,
                shards=1,
                log_dir=ctx.run_dir / "logs",
                log=ctx.log,
            )
            for row in fresh:
                key = row_key(row)
                run.retried.append(
                    {
                        "side": side,
                        "attempt": attempt,
                        "mode": key[0],
                        "file": key[1],
                        "qual": key[2],
                        "before": by_key[key]["full"].get("completeness_reasons"),
                        "after": row["full"].get("completeness_reasons"),
                        "conclusive": not budget_limited(row),
                    }
                )
                if not budget_limited(row):
                    by_key[key] = row
            pending = [
                t
                for t in pending
                if budget_limited(by_key[(t["mode"], t["file"], t["qual"])])
            ]
        new_rows = [by_key[row_key(r)] for r in rows]
        if new_rows != rows:
            answers.write_answers(path, akey, new_rows, "computed+budget-retry")
            if side == "base":
                run.base_rows = new_rows
            else:
                run.head_rows = new_rows
    run.timings["retry"] = time.perf_counter() - started
    ctx.log(
        f"[{run.repo}] budget retry: {len(keys_)} row(s), {sum(r['conclusive'] for r in run.retried)} conclusive ({run.timings['retry']:.0f}s)"
    )
