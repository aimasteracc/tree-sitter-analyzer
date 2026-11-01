"""Latency of the same callers query: warm, then after an idle gap past the snapshot TTL.

python -I idle_probe.py <repo> <name> <file> <idle_seconds>
"""

import asyncio
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\git-private\tsa-worktrees\rfc-1855")
repo, name, file, idle = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
from tree_sitter_analyzer.mcp.tools.callers_tool import (  # noqa: E402
    CodeGraphCallersTool,  # noqa: E402
)


async def main():
    tool = CodeGraphCallersTool(repo)
    args = {"function_name": name, "file_path": file, "include_bodies": False}
    out = []
    for label in ("first", "warm1", "warm2"):
        t0 = time.perf_counter()
        await tool.execute(args)
        out.append((label, round((time.perf_counter() - t0) * 1000, 1)))
    time.sleep(idle)
    for label in ("after_idle", "after_idle_warm"):
        t0 = time.perf_counter()
        await tool.execute(args)
        out.append((label, round((time.perf_counter() - t0) * 1000, 1)))
    print(out)


asyncio.run(main())
