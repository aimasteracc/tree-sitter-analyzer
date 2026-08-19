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
import json
import platform
import subprocess
import sys
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


async def _collect(project_root: str, warm_repeats: int) -> dict[str, Any]:
    """Drive the routes and assemble the baseline artifact."""
    started = datetime.now(timezone.utc)
    get_latency_recorder().reset()
    print("Driving routes (cold + warm)...", file=sys.stderr)
    route_log = await _drive_routes(project_root, warm_repeats)
    report = await SelfHealthTool(project_root=project_root).execute(
        {"output_format": "json"}
    )
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
        "measured_axis": _system_axis(),
        "collection_started_at_utc": started.isoformat(),
        "collection_finished_at_utc": finished.isoformat(),
        "warm_repeats": warm_repeats,
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
    args = parser.parse_args()
    if args.warm_repeats < 1:
        parser.error("--warm-repeats must be >= 1")

    artifact = asyncio.run(_collect(str(REPO_ROOT), args.warm_repeats))
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
