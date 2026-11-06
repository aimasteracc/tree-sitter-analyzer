"""Replay stored callers-gate answers in-process: answer identity and warm latency (RFC-0043).

Usage::

    python benchmarks/resident/corpus_replay.py --repo PATH --stored ANSWERS.json
        [--rounds 2] [--out out.json]

``ANSWERS.json`` is one callers-gate answer file
(``<gate root>/v2/results/<tree>/<index key>/<run>/<repo>.json`` or a
``baseline/`` file, see ``docs/dev/callers-gate.md``). ``--repo`` is a project
root whose published index was built by the code that produced those answers
(the same gate index key). Never point ``--repo`` at the gate's own cache: copy
it first with ``copy_gate_index.py``, which rebinds the copy to its new root.

One in-process ``CodeGraphCallersTool`` answers an untimed warm-up query, then
every stored row (full form, the gate's ``QUERY_ARGS``) ``--rounds`` times.
Round 1 is the first touch of each row on a warm tool; later rounds repeat
every row. Each answer is projected with the gate's own ``slim`` and compared
with the stored row, so the identity check covers exactly the fields the gate
judges. The record reports, per round, the latency split by answer kind
(``review`` when the RFC-0040 review gates ran, else ``edge_only``), the
exclusive stage buckets of ``prof_callers.py``, process RSS, and every
differing row. Exit status 1 when any row differs.

Run it with ``TSA_RESIDENT=off`` and without it to compare both paths with the
same stored answers; gate servers run with ``TSA_EVIDENCE_STORE=off`` and
``PYTHONHASHSEED=0``, so set those too.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent))

import prof_callers as pc  # noqa: E402
from _common import summary_ms, write_json  # noqa: E402

from benchmarks.callers_gate.layout import QUERY_ARGS  # noqa: E402
from benchmarks.callers_gate.query import slim  # noqa: E402

#: Report at most this many differing rows in full (the count is always exact).
MAX_REPORTED_DIFFS = 200


def rss_mb() -> float | None:
    """Resident set size of this process in MiB (``None`` without psutil)."""
    try:
        import psutil
    except ImportError:
        return None
    return round(psutil.Process().memory_info().rss / 2**20, 1)


def tool_args(row: dict[str, Any]) -> dict[str, Any]:
    """The gate's query arguments for one row, without the facade's ``action``."""
    args = {k: v for k, v in QUERY_ARGS.items() if k != "action"}
    return {**args, "function_name": row["name"], "file_path": row["file"]}


def differing_keys(got: dict[str, Any], stored: dict[str, Any]) -> list[str]:
    return sorted(k for k in set(got) | set(stored) if got.get(k) != stored.get(k))


async def replay(repo: str, rows: list[dict[str, Any]], rounds: int) -> dict[str, Any]:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(repo)
    rec: dict[str, Any] = {"repo": Path(repo).name, "rows": len(rows)}
    rec["rss_start_mb"] = rss_mb()
    started = time.perf_counter()
    await tool.execute(tool_args({"name": "__warm_up__", "file": rows[0]["file"]}))
    rec["first_query_s"] = round(time.perf_counter() - started, 3)
    rec["rss_after_first_mb"] = rss_mb()
    diffs: list[dict[str, Any]] = []
    n_diffs = 0
    per_round = []
    for number in range(1, rounds + 1):
        pc.EXCL.clear()
        pc.CALLS.clear()
        latencies: list[float] = []
        by_kind: dict[str, list[float]] = {"edge_only": [], "review": []}
        for index, row in enumerate(rows):
            scans = pc.CALLS.get("G.review._reference_scan", 0)
            t0 = time.perf_counter()
            answer = await tool.execute(tool_args(row))
            latencies.append(time.perf_counter() - t0)
            gated = pc.CALLS.get("G.review._reference_scan", 0) > scans
            by_kind["review" if gated else "edge_only"].append(latencies[-1])
            got = slim(json.loads(json.dumps(answer, default=str)))
            if got == row["full"]:
                continue
            n_diffs += 1
            if len(diffs) < MAX_REPORTED_DIFFS:
                diffs.append(
                    {
                        "round": number,
                        "index": index,
                        "mode": row.get("mode"),
                        "file": row["file"],
                        "qual": row.get("qual"),
                        "stored": row["full"].get("completeness"),
                        "got": got.get("completeness"),
                        "keys": differing_keys(got, row["full"]),
                    }
                )
        total = sum(latencies)
        per_round.append(
            {
                "round": number,
                "all": summary_ms(latencies),
                "by_kind": {k: summary_ms(v) for k, v in by_kind.items()},
                "stages_ms_per_query": {
                    k: round(v * 1000 / len(rows), 2)
                    for k, v in sorted(pc.EXCL.items(), key=lambda kv: -kv[1])
                    if v * 1000 / len(rows) >= 0.05
                },
                "unwrapped_ms_per_query": round(
                    (total - sum(pc.EXCL.values())) * 1000 / len(rows), 2
                ),
            }
        )
    rec["rounds"] = per_round
    rec["rss_end_mb"] = rss_mb()
    rec["n_diff_rows"] = n_diffs
    rec["diffs"] = diffs
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--repo", required=True, help="project root (a copy, never the gate cache)"
    )
    parser.add_argument("--stored", required=True, help="callers-gate answer file")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--out")
    args = parser.parse_args()
    stored = json.loads(Path(args.stored).read_text(encoding="utf-8"))
    rows = stored["rows"]
    if not rows:
        parser.error("the answer file has no rows")
    pc.install_wrappers()
    rec = asyncio.run(replay(args.repo, rows, max(1, args.rounds)))
    rec["stored"] = {
        k: stored.get(k) for k in ("tree", "index_key", "repo", "repo_sha", "query_key")
    }
    write_json(args.out, rec)
    return 1 if rec["n_diff_rows"] else 0


if __name__ == "__main__":
    sys.exit(main())
