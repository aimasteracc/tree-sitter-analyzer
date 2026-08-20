#!/usr/bin/env python3
"""Measure RFC-0025 Layer 5 latency and write a durable baseline JSON.

Why this exists
---------------
CLAUDE.md §11: a non-functional claim that is not an executable invariant is a
**belief**. The project's headline promise is that it answers *instantly*; this
script is what turns that into a number on record.

What it does
------------
Drives a small set of representative ``(facade, action)`` routes **in-process**
through the real facades, so the instrumented seam
(:meth:`FacadeTool.execute`) records them exactly as it would for a live MCP
server. Each route is called once cold and :data:`WARM_REPEATS` times warm, so
cold and warm land in separate reservoirs and the report can be read honestly.
The resulting self-health report is written to ``docs/baselines/`` together
with provenance (platform, python version, commit, UTC date), following the
shape conventions of ``docs/baselines/no1-006b-macos-e0.json``.

Usage::

    uv run python scripts/measure_self_health_baseline.py
    uv run python scripts/measure_self_health_baseline.py --warm-repeats 3
    uv run python scripts/measure_self_health_baseline.py --stdout

Note on evidence level: this is **E0** — a single un-isolated host, no CPU
pinning, no power/thermal control. The magnitudes are load-bearing; the digits
are not. That limitation is recorded in the artifact rather than hidden.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tree_sitter_analyzer.latency import get_latency_recorder  # noqa: E402
from tree_sitter_analyzer.mcp.tools.self_health_tool import (  # noqa: E402
    SelfHealthTool,
)

#: Warm calls per route, after the one cold call.
WARM_REPEATS = 5

BASELINE_DIR = REPO_ROOT / "docs" / "baselines"
ROADMAP_ID = "RFC-0025-L5"
SCHEMA_VERSION = 1

#: Representative routes. Deliberately small and deliberately spread across
#: the cost spectrum measured on this repo: a cheap single-file structural
#: read, a mid-cost health score, a known-expensive cold call-graph query, and
#: the edit-safety gate that showed no warm benefit at all.
ROUTES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("structure", "outline", {"file_path": "tree_sitter_analyzer/latency.py"}),
    ("health", "file", {"file_path": "tree_sitter_analyzer/latency.py"}),
    ("nav", "callers", {"symbol": "percentile_ns"}),
    ("edit", "safe", {"file_path": "tree_sitter_analyzer/latency.py"}),
)

#: The interleaved pair this project's own skills prescribe **per edit**
#: (``.claude/skills/tsa-edit-safety/SKILL.md:16`` — "edit action=safe +
#: edit action=impact + health action=file"; ``tsa-edit-then-verify/SKILL.md:6``
#: — "edit action=safe + baseline health action=file").
#:
#: Why this exists (RFC-0027 L6.1 review, P1-3): :data:`ROUTES` above is driven
#: as ``for route: for repeat:`` — every repeat of a route is grouped, so any
#: per-route cache state stays constant inside a measurement block. A
#: route-scoped component in the answer cache's eviction prelude therefore
#: produced a **0% hit rate in the real workflow while this harness measured a
#: 62x speedup**, and the harness could not see it. Measuring the routes
#: alternating is the only way the published number describes the workflow the
#: agent actually runs.
INTERLEAVED_ROUTES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("edit", "safe", {"file_path": "tree_sitter_analyzer/latency.py"}),
    ("health", "file", {"file_path": "tree_sitter_analyzer/latency.py"}),
)

#: Rounds of the interleaved pair. Round 1 is cold for both; every later round
#: is a repeat at an unchanged generation and must hit.
INTERLEAVED_ROUNDS = 4

_FACADE_BUILDERS = {
    "structure": "structure_facade.build_structure_facade",
    "health": "health_facade.build_health_facade",
    "nav": "nav_facade.build_nav_facade",
    "edit": "edit_facade.build_edit_facade",
}


def _build_facade(name: str, project_root: str) -> Any:
    """Import and build the named facade lazily."""
    import importlib

    module_name, attr = _FACADE_BUILDERS[name].split(".")
    module = importlib.import_module(f"tree_sitter_analyzer.mcp.tools.{module_name}")
    return getattr(module, attr)(project_root)


def _git(*args: str) -> str:
    """Run a read-only git command, returning ``"unknown"`` on any failure."""
    try:
        out = subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


async def _drive_routes(project_root: str, warm_repeats: int) -> list[dict[str, Any]]:
    """Call every route once cold then *warm_repeats* times warm.

    Returns a per-route execution log so a route that could not be measured is
    visible in the artifact instead of silently missing.
    """
    log: list[dict[str, Any]] = []
    for facade_name, action, params in ROUTES:
        facade = _build_facade(facade_name, project_root)
        errors: list[str] = []
        for _ in range(1 + warm_repeats):
            try:
                await facade.execute({"action": action, **params})
            except Exception as exc:  # noqa: BLE001 — record, never abort
                errors.append(f"{type(exc).__name__}: {exc}")
        log.append(
            {
                "tool": facade_name,
                "action": action,
                "params": params,
                "calls": 1 + warm_repeats,
                "errors": errors,
            }
        )
        print(
            f"  {facade_name} action={action}: "
            f"{1 + warm_repeats} calls, {len(errors)} error(s)",
            file=sys.stderr,
        )
    return log


async def _drive_interleaved(project_root: str, rounds: int) -> dict[str, Any]:
    """Drive the prescribed route pair **alternating**, and report served_from.

    This is the number that describes the documented workflow. It is kept
    separate from :func:`_drive_routes` (and from the latency reservoirs) so the
    grouped-repeat rows above stay comparable with earlier artifacts, while the
    interleaved rows record what an agent actually experiences.

    ``served_from`` is read straight off the response, so a 0% hit rate is
    visible as data rather than having to be inferred from a timing that a
    grouped harness would have flattered.
    """
    # Start from an empty answer cache: the grouped phase above already warmed
    # both routes, so without this every round would be a hit and the block
    # would not show its own cold->warm transition.
    from tree_sitter_analyzer.cache.answer_cache import reset_answer_cache

    reset_answer_cache()

    facades = {
        name: _build_facade(name, project_root)
        for name, _action, _params in INTERLEAVED_ROUTES
    }
    per_route: dict[str, dict[str, Any]] = {}
    for facade_name, action, params in INTERLEAVED_ROUTES:
        per_route[f"{facade_name}.{action}"] = {
            "tool": facade_name,
            "action": action,
            "params": params,
            "served_from": [],
            "elapsed_ms": [],
            "errors": [],
        }

    for _round in range(rounds):
        for facade_name, action, params in INTERLEAVED_ROUTES:
            row = per_route[f"{facade_name}.{action}"]
            started = time.perf_counter_ns()
            try:
                result = await facades[facade_name].execute(
                    {"action": action, **params}
                )
            except Exception as exc:  # noqa: BLE001 — record, never abort
                row["errors"].append(f"{type(exc).__name__}: {exc}")
                continue
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            provenance = result.get("provenance") if isinstance(result, dict) else None
            served = (
                provenance.get("served_from") if isinstance(provenance, dict) else None
            )
            row["served_from"].append(served)
            row["elapsed_ms"].append(round(elapsed_ms, 3))

    summary: dict[str, Any] = {"rounds": rounds, "routes": per_route}
    served_all = [served for row in per_route.values() for served in row["served_from"]]
    cache_hits = sum(1 for served in served_all if served == "cache")
    summary["observations"] = len(served_all)
    summary["cache_hits"] = cache_hits
    summary["hit_rate"] = round(cache_hits / len(served_all), 4) if served_all else None
    # Rounds after the first are repeats at an unchanged generation, so every
    # one of them must be a hit. Anything less is the P1-3 class of bug.
    expected_hits = len(INTERLEAVED_ROUTES) * (rounds - 1)
    summary["expected_cache_hits"] = expected_hits
    summary["verdict"] = "OK" if cache_hits == expected_hits else "CACHE_NOT_SERVING"
    print(
        f"  interleaved: {cache_hits}/{expected_hits} expected hits "
        f"({summary['verdict']})",
        file=sys.stderr,
    )
    return summary


def _sha256_file(path: Path) -> str:
    """Hash a file's bytes, or ``"unknown"`` if it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unknown"


def _git_dirty_lines() -> tuple[str, ...]:
    """Return porcelain status lines. Empty tuple means a clean tree.

    The collector contract for ``no1-006b-macos-e0.json`` gates on exactly this
    (``--untracked-files=all``), and skipping it here already cost us: the first
    committed artifact recorded a commit that contained neither ``latency.py``
    nor this script, because both were untracked when it ran. So the recorded
    ``reproduction_command`` was impossible to execute at the stated provenance.
    """
    raw = _git("status", "--porcelain=v1", "--untracked-files=all")
    if raw in ("", "unknown"):
        return ()
    return tuple(line for line in raw.splitlines() if line.strip())


def _ast_index_matches(observed: dict[str, Any], required: str) -> bool:
    """Gate the run on a declared on-disk AST-index state."""
    if required == "any":
        return True
    status = observed.get("status")
    if required == "absent":
        return status == "ABSENT"
    if required == "present":
        return bool(observed.get("present"))
    # populated: present AND holding at least one indexed file
    return bool(observed.get("present")) and bool(observed.get("indexed_files"))


def _ast_index_state(project_root: str) -> dict[str, Any]:
    """Observed on-disk AST-index state, recorded as a first-class field.

    The cold column depends on this and nothing in the artifact used to say so:
    the same host at the same commit produced ``edit/safe`` cold p50 of
    18014.645 / 14065.642 / 4104.113 ms minutes apart, purely because the
    on-disk index differed. Warm numbers were stable throughout.
    """
    from tree_sitter_analyzer.mcp.tools.self_health_tool import _ast_index_report

    return _ast_index_report(project_root)


async def _collect(
    project_root: str, warm_repeats: int, *, allow_dirty: bool
) -> dict[str, Any]:
    """Drive the routes and assemble the baseline artifact."""
    started = datetime.now(timezone.utc)
    ast_index_before = _ast_index_state(project_root)
    dirty = _git_dirty_lines()
    get_latency_recorder().reset()
    print("Driving routes (cold + warm)...", file=sys.stderr)
    route_log = await _drive_routes(project_root, warm_repeats)
    # Snapshot the latency report BEFORE the interleaved phase. That phase
    # deliberately empties the answer cache, so its first call recomputes — and
    # because the route has already completed once, that expensive sample lands
    # in the *warm* reservoir and drags the grouped p95 to the cold value. It
    # did exactly that once (edit.safe warm p95 == the interleaved first call,
    # 5320.7 ms), which is the same class of self-flattering/self-maligning
    # instrumentation error as timing a cache hit outside the measured window.
    report = await SelfHealthTool(project_root=project_root).execute(
        {"output_format": "json"}
    )
    print("Driving the prescribed pair interleaved...", file=sys.stderr)
    interleaved = await _drive_interleaved(project_root, INTERLEAVED_ROUNDS)
    finished = datetime.now(timezone.utc)

    return {
        "roadmap_id": ROADMAP_ID,
        "schema_version": SCHEMA_VERSION,
        "evidence_level": "E0",
        "evidence_level_note": (
            "Single un-isolated host: no CPU pinning, no thermal or power "
            "control, no repeat-host cross-check. Magnitudes are load-bearing; "
            "individual digits are not."
        ),
        "cold_column_status": "INDICATIVE_SINGLE_OBSERVATION",
        "cold_column_caveat": (
            "Every cold row is ONE observation and depends on the on-disk "
            "AST-index state recorded in preconditions.ast_index_before. "
            "Measured spread on one host at one commit: edit/safe cold p50 "
            "18014.645 / 14065.642 / 4104.113 ms (3.4x) purely from that state. "
            "Treat cold as indicative of magnitude only; do NOT use it in any "
            "cross-run or cross-commit comparison. Warm rows were stable "
            "(3845 / 3394 / 3624 ms) and are the comparable column."
        ),
        "preconditions": {
            "ast_index_before": ast_index_before,
            "declared_via": "--require-ast-index",
            "git_dirty": bool(dirty),
            "git_dirty_entry_count": len(dirty),
            "git_dirty_allowed_by_flag": allow_dirty,
            "provenance_valid": not dirty,
            "provenance_note": (
                "provenance_valid is false when the working tree was dirty: the "
                "recorded commit then does NOT describe the measured code, and "
                "reproduction_command cannot reproduce these numbers."
            ),
        },
        "measured_axis": _system_axis(),
        "collection_started_at_utc": started.isoformat(),
        "collection_finished_at_utc": finished.isoformat(),
        "warm_repeats": warm_repeats,
        "integrity": {
            "script_sha256": _sha256_file(Path(__file__).resolve()),
            "recorder_module_sha256": _sha256_file(
                REPO_ROOT / "tree_sitter_analyzer" / "latency.py"
            ),
            "tool_module_sha256": _sha256_file(
                REPO_ROOT
                / "tree_sitter_analyzer"
                / "mcp"
                / "tools"
                / "self_health_tool.py"
            ),
        },
        "source": {
            "commit": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        },
        "environment": {
            "system": _system_axis(),
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
            },
        },
        "routes_driven": route_log,
        "interleaved_workflow": interleaved,
        "interleaved_workflow_note": (
            "The prescribed pre-edit pair (edit action=safe + health "
            "action=file) driven ALTERNATING rather than grouped. routes_driven "
            "above groups all repeats of one route together, which holds any "
            "per-route cache state constant inside a block; that structure hid "
            "a 0% real-workflow cache hit rate behind a 62x grouped-repeat "
            "speedup (RFC-0027 L6.1 review P1-3). Judge the answer cache on "
            "these rows, not on the warm column above."
        ),
        "reproduction_command": (
            "uv run python scripts/measure_self_health_baseline.py"
        ),
        "self_health": report,
    }


def _system_axis() -> str:
    """Normalise ``platform.system()`` to the axis names used in baselines."""
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
        platform.system(), platform.system().lower()
    )


def _output_path() -> Path:
    return BASELINE_DIR / f"rfc0025-l5-latency-{_system_axis()}-e0.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--warm-repeats",
        type=int,
        default=WARM_REPEATS,
        help=f"Warm calls per route after the cold one (default: {WARM_REPEATS})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the artifact to stdout instead of writing to docs/baselines/",
    )
    parser.add_argument(
        "--require-ast-index",
        choices=("any", "absent", "present", "populated"),
        default="any",
        help=(
            "Declare the on-disk AST-index state the cold column is measured "
            "from, and refuse to run if it does not match. The cold numbers are "
            "meaningless without this, so 'any' is recorded in the artifact as "
            "an undeclared (accidental) state. Default: any"
        ),
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "Write the artifact even though the working tree is dirty. The "
            "recorded commit will NOT describe the measured code, so "
            "provenance_valid is set false and the artifact is marked as "
            "unreproducible. Refused without this flag."
        ),
    )
    args = parser.parse_args()
    if args.warm_repeats < 1:
        parser.error("--warm-repeats must be >= 1")

    observed = _ast_index_state(str(REPO_ROOT))
    if not _ast_index_matches(observed, args.require_ast_index):
        print(
            f"REFUSED: --require-ast-index={args.require_ast_index} but the "
            f"on-disk index is status={observed.get('status')} "
            f"indexed_files={observed.get('indexed_files')}. The cold column "
            f"depends on this state; fix the state or relax the flag.",
            file=sys.stderr,
        )
        return 2

    dirty = _git_dirty_lines()
    if dirty and not args.allow_dirty:
        print(
            f"REFUSED: working tree has {len(dirty)} uncommitted/untracked "
            f"entries, so the commit recorded in the artifact would not describe "
            f"the measured code (this exact mistake produced an artifact whose "
            f"reproduction_command could not run). Commit first, or pass "
            f"--allow-dirty to write a provenance_valid=false artifact.",
            file=sys.stderr,
        )
        return 2

    artifact = asyncio.run(
        _collect(str(REPO_ROOT), args.warm_repeats, allow_dirty=args.allow_dirty)
    )
    payload = json.dumps(artifact, indent=2, sort_keys=True) + "\n"

    if args.stdout:
        print(payload, end="")
        return 0

    destination = _output_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps the artifact byte-identical across platforms — Windows
    # text mode would otherwise rewrite every \n as \r\n and the committed
    # baseline would differ by the OS that produced it.
    with destination.open("w", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    print(f"Wrote {destination.relative_to(REPO_ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
