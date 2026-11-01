"""Raw per-call cost of ``os.stat`` / ``os.path.realpath`` and one ``os.walk`` on this host.

Usage::

    python benchmarks/resident/statcost.py --repo PATH [--ext .py] [--out out.json]

The stat-mode freshness floor of RFC-0042 §9 is one stat per source file of
the target's language; this script measures that unit cost (RFC host: about
83 µs per stat on Windows, 1–3 µs on Linux and macOS).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import write_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ext", default=".py")
    parser.add_argument("--out")
    args = parser.parse_args()
    repo = Path(args.repo)
    files = [
        str(p)
        for p in repo.rglob(f"*{args.ext}")
        if ".ast-cache" not in p.parts and ".git" not in p.parts
    ]
    if not files:
        raise SystemExit(f"no *{args.ext} files under {repo}")
    stat_s = 0.0
    for _ in range(2):  # the second pass is the warm one
        t0 = time.perf_counter()
        for f in files:
            os.stat(f)
        stat_s = (time.perf_counter() - t0) / len(files)
    t0 = time.perf_counter()
    for f in files:
        os.path.realpath(f)
    realpath_s = (time.perf_counter() - t0) / len(files)
    t0 = time.perf_counter()
    dirs = sum(1 for _ in os.walk(repo))
    walk_s = time.perf_counter() - t0
    write_json(
        args.out,
        {
            "repo": repo.name,
            "platform": sys.platform,
            "files": len(files),
            "stat_us": round(stat_s * 1e6, 1),
            "realpath_us": round(realpath_s * 1e6, 1),
            "walk_ms": round(walk_s * 1e3, 1),
            "dirs": dirs,
        },
    )


if __name__ == "__main__":
    main()
