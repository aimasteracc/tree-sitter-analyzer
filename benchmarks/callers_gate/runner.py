"""``run``: per repo, ensure the index, get base answers (cache or compute), compute head answers."""

from __future__ import annotations

import hashlib
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
    """One repo of a run.

    ``base_rows``: base code on the head-built index (isolates the query path).
    ``cross_rows``: base code on the base's own index; set only when the index
    keys differ (the indexer changed), and then the reference for "pre-existing".
    """

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
    base_index_key: str = ""
    cross_rows: list[dict[str, Any]] = field(default_factory=list)
    cross_source: str = ""
    base_root: Path | None = None
    base_index_built: bool = False
    query_key: str = ""
    #: ``--scip``: digest of the repo's SCIP index + manifest, and the head env.
    scip_digest: str = ""
    head_env: dict[str, str] | None = None


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
    #: Recompute every base side (no cache) so base and head timings share one load.
    fresh_base: bool = False
    #: ``run --scip DIR``: the head side reads ``DIR/<repo>.scip`` (+ manifest).
    scip_dir: Path | None = None

    @property
    def run_id(self) -> str:
        return self.run_dir.name

    def pkg(self, side: sides.Side) -> Path:
        with self._materialize_lock:
            return sides.materialize(self.layout, self.git_dir, side)


def _index_key(ctx: RunContext, pin: RepoPin, side: sides.Side) -> str:
    return keys.index_key(
        repo=pin.name,
        repo_sha=pin.sha,
        package_blobs=side.blobs,
        pyproject_blob=side.pyproject_blob,
        env_fingerprint=ctx.env_key,
    )


def _ensure(
    ctx: RunContext, pin: RepoPin, key: str, side: sides.Side
) -> index_store.IndexInfo:
    """The index ``side``'s code builds for ``pin`` (reused when its manifest is valid)."""
    return index_store.ensure_index(
        ctx.layout,
        pin,
        key,
        python=ctx.python,
        head_pkg_parent=ctx.pkg(side),
        excluded_modules=keys.query_only_modules(side.blobs),
        built_by=side.tree,
        log=ctx.log,
    )


def _cached_answers(
    ctx: RunContext, pin: RepoPin, tree: str, key: answers.AnswerKey
) -> list[dict[str, Any]] | None:
    """``baseline/<tree>/<key>``, else agreeing ``results/<tree>/<key>/<run>`` promoted."""
    path = ctx.layout.baseline(tree, key.index_key, pin.name)
    cached = answers.read_answers(path, key, ctx.log)
    if cached is not None:
        return cached
    promoted = answers.pick_run(
        ctx.layout.result_runs(tree, key.index_key, pin.name), key, None, ctx.log
    )
    if promoted is not None:
        answers.write_answers(path, key, promoted, "promoted:results")
        ctx.log(
            f"[{pin.name}] answers of {tree[:12]} promoted from results/ ({key.index_key})"
        )
    return promoted


def _side_answers(
    ctx: RunContext,
    pin: RepoPin,
    *,
    label: str,
    side: sides.Side,
    key: answers.AnswerKey,
    root: Callable[[], Path],
    targets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, float]:
    """(rows, source, seconds) of ``side``'s code on the index named by ``key``."""
    cached = None if ctx.fresh_base else _cached_answers(ctx, pin, side.tree, key)
    if cached is not None:
        ctx.log(f"[{pin.name}] {label} answers: cache hit ({len(cached)} rows)")
        return cached, "cache", 0.0
    rows, secs = compute_side(
        label=f"{pin.name}-{label}",
        python=ctx.python,
        pkg_parent=ctx.pkg(side),
        root=root(),
        targets=targets,
        shards=ctx.shards.get(pin.name, 1),
        log_dir=ctx.run_dir / "logs",
        log=ctx.log,
    )
    answers.write_answers(
        ctx.layout.baseline(side.tree, key.index_key, pin.name), key, rows, "computed"
    )
    ctx.log(f"[{pin.name}] {label} answers computed in {secs:.0f}s")
    return rows, "computed", secs


def _own_index_answers(
    ctx: RunContext, pin: RepoPin, out: RepoRun, targets: list[dict[str, Any]]
) -> None:
    """Base code on the base's own index: the comparison that sees indexer changes."""
    started = time.perf_counter()
    key = answers.AnswerKey(
        ctx.base.tree, out.base_index_key, pin.name, pin.sha, out.query_key
    )

    def root() -> Path:
        info = _ensure(ctx, pin, out.base_index_key, ctx.base)
        out.base_root, out.base_index_built = info.root, info.built
        return info.root

    out.cross_rows, out.cross_source, secs = _side_answers(
        ctx,
        pin,
        label="base-own-index",
        side=ctx.base,
        key=key,
        root=root,
        targets=targets,
    )
    out.retry_context["cross"] = (
        lambda: ctx.pkg(ctx.base),
        lambda: out.base_root if out.base_root is not None else root(),
        ctx.layout.baseline(ctx.base.tree, out.base_index_key, pin.name),
        key,
    )
    out.timings["base_own_index"] = time.perf_counter() - started
    out.timings["cross"] = secs


#: The variable that points a TSA server at a SCIP index.
SCIP_ENV = "TSA_SCIP_INDEX"
SCIP_MANIFEST_SUFFIX = ".manifest.json"


@dataclass(frozen=True)
class ScipInput:
    index: Path
    manifest: Path
    digest: str


def scip_input(scip_dir: Path, repo: str) -> ScipInput:
    """``<dir>/<repo>.scip`` and its manifest; both must exist (fail closed)."""
    index = (scip_dir / f"{repo}.scip").resolve()
    manifest = index.with_name(index.name + SCIP_MANIFEST_SUFFIX)
    if not index.is_file() or not manifest.is_file():
        raise FileNotFoundError(
            f"--scip: {repo} needs {index.name} and {manifest.name} in {scip_dir}"
        )
    digest = hashlib.blake2b(digest_size=12)
    for path in (index, manifest):
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return ScipInput(index, manifest, digest.hexdigest())


def run_repo(ctx: RunContext, pin: RepoPin) -> RepoRun:
    out = RepoRun(pin.name)
    log = ctx.log
    t0 = time.perf_counter()
    targets, targets_sha = corpus.load_targets(ctx.layout, pin.name, ctx.manifest)
    query_key = out.query_key = keys.query_key(targets_sha256=targets_sha)
    out.index_key = _index_key(ctx, pin, ctx.head)
    out.base_index_key = _index_key(ctx, pin, ctx.base)
    head_pkg = ctx.pkg(ctx.head)
    info = _ensure(ctx, pin, out.index_key, ctx.head)
    out.root, out.index_built = info.root, info.built
    out.timings["index"] = time.perf_counter() - t0
    log(
        f"[{pin.name}] index {out.index_key} {'built' if info.built else 'reused'} ({out.timings['index']:.0f}s)"
    )

    base_key = answers.AnswerKey(
        ctx.base.tree, out.index_key, pin.name, pin.sha, query_key
    )
    base_path = ctx.layout.baseline(ctx.base.tree, out.index_key, pin.name)
    out.base_rows, out.baseline_source, out.timings["base"] = _side_answers(
        ctx,
        pin,
        label="base",
        side=ctx.base,
        key=base_key,
        root=lambda: info.root,
        targets=targets,
    )
    out.baseline_hit = out.baseline_source == "cache"
    if out.base_index_key != out.index_key:
        log(
            f"[{pin.name}] the index keys differ (indexer change): base {out.base_index_key} vs head {out.index_key}"
        )
        _own_index_answers(ctx, pin, out, targets)
    shards = ctx.shards.get(pin.name, 1)

    costs = {
        (r["mode"], r["file"], r["qual"]): float(r.get("seconds") or 0.0)
        for r in out.base_rows
    }
    scip = scip_input(ctx.scip_dir, pin.name) if ctx.scip_dir else None
    out.head_env = {SCIP_ENV: str(scip.index)} if scip else None
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
        extra_env=out.head_env,
    )
    head_key = answers.AnswerKey(
        ctx.head.tree,
        out.index_key,
        pin.name,
        pin.sha,
        keys.query_key(targets_sha256=targets_sha, scip=scip.digest)
        if scip
        else query_key,
    )
    if scip:
        out.scip_digest = scip.digest
        head_path = ctx.layout.scip_result(
            ctx.head.tree, out.index_key, scip.digest, pin.name, ctx.run_id
        )
    else:
        head_path = ctx.layout.result(
            ctx.head.tree, out.index_key, pin.name, ctx.run_id
        )
    answers.write_answers(head_path, head_key, rows, "computed")
    out.head_rows = rows
    out.timings["head"] = secs
    out.timings["total"] = time.perf_counter() - t0
    out.retry_context.update(
        {
            "targets": targets,
            "base": (lambda: ctx.pkg(ctx.base), info.root, base_path, base_key),
            "head": (head_pkg, info.root, head_path, head_key),
        }
    )
    log(
        f"[{pin.name}] head answers computed in {secs:.0f}s; repo total {out.timings['total']:.0f}s"
    )
    return out


def _guarded(ctx: RunContext, pin: RepoPin) -> RepoRun:
    try:
        return run_repo(ctx, pin)
    except Exception as exc:  # noqa: BLE001 - one repo failing must not hide the others
        ctx.log(f"[{pin.name}] ERROR {type(exc).__name__}: {exc}")
        return RepoRun(pin.name, error=f"{type(exc).__name__}: {exc}")


def run_all(ctx: RunContext, repos: list[str], jobs: int) -> list[RepoRun]:
    """Run every repo. ``jobs == 1`` is strictly sequential: one repo at a time, in
    this thread, and one server per side (shards are forced to 1)."""
    pins = sorted((REPOS[r] for r in repos), key=lambda p: -COST_HINT.get(p.name, 1.0))
    results: dict[str, RepoRun] = {}
    if jobs <= 1:
        ctx.shards = dict.fromkeys(REPOS, 1)
        for pin in pins:
            results[pin.name] = _guarded(ctx, pin)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(_guarded, ctx, pin): pin.name for pin in pins}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
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
    budget. Such a row is re-asked once the machine is quieter. #1923: the
    ``open_sites`` bound reruns review gates under their own budgets, so an
    ``open_sites`` that says ``*_UNCHECKED``, or a compact bound that differs from
    the full answer's, is budget-limited too.
    """
    full = row["full"]
    if any(
        str(r).endswith("_UNCHECKED") for r in full.get("completeness_reasons") or ()
    ):
        return True
    bound = full.get("open_sites")
    if isinstance(bound, dict) and str(bound.get("reason") or "").endswith(
        "_UNCHECKED"
    ):
        return True
    compact = row.get("compact") or {}
    if compact.get("completeness") != full.get("completeness"):
        return True
    # #1923: the compact call computes its own bound; one that landed on the
    # other side of a budget carries a different (or no) ``open_sites``.
    return bool(compact.get("open_sites") != _projected_bound(full))


def _projected_bound(full: dict[str, Any]) -> dict[str, Any] | None:
    """The ``open_sites`` the compact form projects from this full answer."""
    bound = full.get("open_sites")
    if full.get("completeness") != "unknown" or not isinstance(bound, dict):
        return None
    if bound.get("enumerated") is True:
        return {"total": bound.get("total"), "enumerated": True}
    if bound.get("reason") == "REVIEW_UNCHECKED":
        return {
            "enumerated": False,
            "reason": "REVIEW_UNCHECKED",
            "unchecked": bound.get("unchecked") or "REVIEW_UNCHECKED",
        }
    return None


def check_missing(row: dict[str, Any]) -> bool:
    """The non-call reference check left no result (missing or null)."""
    return row["full"].get("non_call_references") is None


def pair_limited(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """A changed pair a budget may explain: either side ``budget_limited``, or one side
    finished the non-call reference check and the other left it missing / null (the
    check ran out of time without saying ``*_UNCHECKED``)."""
    return (
        budget_limited(a) or budget_limited(b) or check_missing(a) != check_missing(b)
    )


def _side_limited(row: dict[str, Any], other: dict[str, Any] | None) -> bool:
    """This side's row should be re-asked (against the other side's row)."""
    return budget_limited(row) or (
        other is not None and check_missing(row) and not check_missing(other)
    )


def _changed_limited(
    rows: list[dict[str, Any]], head_rows: list[dict[str, Any]]
) -> set[tuple[str, str, str]]:
    """Keys whose answer changed between ``rows`` and head and a budget may explain."""
    by = {row_key(r): r for r in rows}
    return {
        row_key(h)
        for h in head_rows
        if row_key(h) in by
        and classify_pair(by[row_key(h)], h)
        and pair_limited(by[row_key(h)], h)
    }


def _value(item: Any) -> Any:
    return item() if callable(item) else item


def retry_budget_rows(
    ctx: RunContext, run: RepoRun, attempts: int = MAX_BUDGET_RETRIES
) -> None:
    """Re-ask, on one quiet server per side, every changed row that a budget may explain.

    Runs after all repos finished (so with little contention). A retried row
    replaces the cached one only when it is no longer budget-limited; the cache
    file is rewritten with the conclusive answer for the same code and index.
    Both comparisons count: base vs head on the head index and, when the index
    keys differ, base on its own index vs head.
    """
    wanted = {"base": _changed_limited(run.base_rows, run.head_rows)}
    if run.cross_rows:
        wanted["cross"] = _changed_limited(run.cross_rows, run.head_rows)
    wanted["head"] = set().union(*wanted.values())
    if not wanted["head"] or run.root is None:
        return
    started = time.perf_counter()
    for side in ("base", "cross", "head"):
        if side not in wanted:
            continue
        rows = {"base": run.base_rows, "cross": run.cross_rows, "head": run.head_rows}[
            side
        ]
        pkg, root, path, akey = run.retry_context[side]
        by_key = {row_key(r): r for r in rows}
        counterpart = {
            row_key(r): r for r in (run.base_rows if side == "head" else run.head_rows)
        }

        def limited(
            key: tuple[str, str, str],
            row: dict[str, Any],
            counterpart: dict[tuple[str, str, str], dict[str, Any]] = counterpart,
        ) -> bool:
            return _side_limited(row, counterpart.get(key))

        pending = [
            t
            for t in run.retry_context["targets"]
            if (t["mode"], t["file"], t["qual"]) in wanted[side]
            and limited(
                (t["mode"], t["file"], t["qual"]),
                by_key[(t["mode"], t["file"], t["qual"])],
            )
        ]
        for attempt in range(1, attempts + 1):
            if not pending:
                break
            fresh, _secs = compute_side(
                label=f"{run.repo}-{side}-retry{attempt}",
                python=ctx.python,
                pkg_parent=_value(pkg),
                root=_value(root),
                targets=pending,
                shards=1,
                log_dir=ctx.run_dir / "logs",
                log=ctx.log,
                extra_env=run.head_env if side == "head" else None,
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
                        "conclusive": not limited(key, row),
                    }
                )
                if not limited(key, row):
                    by_key[key] = row
            pending = [
                t
                for t in pending
                if limited(
                    (t["mode"], t["file"], t["qual"]),
                    by_key[(t["mode"], t["file"], t["qual"])],
                )
            ]
        new_rows = [by_key[row_key(r)] for r in rows]
        if new_rows != rows:
            answers.write_answers(path, akey, new_rows, "computed+budget-retry")
            if side == "base":
                run.base_rows = new_rows
            elif side == "cross":
                run.cross_rows = new_rows
            else:
                run.head_rows = new_rows
    run.timings["retry"] = time.perf_counter() - started
    ctx.log(
        f"[{run.repo}] budget retry: {len(wanted['head'])} row(s), {sum(r['conclusive'] for r in run.retried)} conclusive ({run.timings['retry']:.0f}s)"
    )
