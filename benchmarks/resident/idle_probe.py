"""In-process latency of one ``nav callers`` query: warm, then after an idle gap.

Usage::

    python benchmarks/resident/idle_probe.py --repo PATH --name NAME --file FILE
        [--idle 40] [--out out.json]

Asks the same question three times (``first``, ``warm1``, ``warm2``), sleeps
``--idle`` seconds (past the 35 s certified snapshot TTL by default), then asks
twice more (``after_idle``, ``after_idle_warm``). RFC-0042 measured 50 ms warm
and 334 ms after 40 s idle on ``rich``. ``mcp_latency.py --idle`` measures the
same through a server, where a background loader can renew the lease.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import SuspendClock, write_json  # noqa: E402


async def probe(args: argparse.Namespace) -> dict[str, object]:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(args.repo)
    request = {
        "function_name": args.name,
        "file_path": args.file,
        "include_bodies": False,
    }
    clock = SuspendClock()
    rec: dict[str, object] = {"repo": Path(args.repo).name, "idle_s": args.idle}
    for label in ("first", "warm1", "warm2"):
        t0 = time.perf_counter()
        await tool.execute(request)
        rec[f"{label}_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    time.sleep(args.idle)
    for label in ("after_idle", "after_idle_warm"):
        t0 = time.perf_counter()
        await tool.execute(request)
        rec[f"{label}_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    rec["suspended"] = clock.suspended()
    return rec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--idle", type=float, default=40.0)
    parser.add_argument("--out")
    args = parser.parse_args()
    write_json(args.out, asyncio.run(probe(args)))


if __name__ == "__main__":
    main()
