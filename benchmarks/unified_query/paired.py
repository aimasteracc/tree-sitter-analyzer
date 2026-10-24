"""Median wall time of interleaved today/uql runs (RFC-0041 §7).

The machine is shared, so arms measured minutes apart are not comparable.
``paired`` runs alternate the two arms per question in fresh processes,
three rounds; this prints the median of each timing per (question, arm):

* ``warm``   — first execution of the question after a warm-up call (server
  warm, question new);
* ``repeat`` — the same question again in that process (answer cache off);
* ``cold``   — the question as the first call of a fresh process.

Usage: ``python benchmarks/unified_query/paired.py <results-dir> <repo>``
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    root, repo = Path(sys.argv[1]), sys.argv[2]
    samples: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for path in root.glob(f"{repo}-*-p*.jsonl"):
        if path.name.endswith("-texts.jsonl"):
            continue
        arm = path.name.split("-")[1]
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            if row.get("cold"):
                samples[(row["qid"], arm, "cold")].append(row["seconds"])
            else:
                samples[(row["qid"], arm, "warm")].append(row["seconds"])
                if row.get("repeat_seconds") is not None:
                    samples[(row["qid"], arm, "repeat")].append(row["repeat_seconds"])
    print(
        "| Q | today warm | uql warm | today repeat | uql repeat | today cold | uql cold |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for qid in sorted({k[0] for k in samples}):
        cells = []
        for kind in ("warm", "repeat", "cold"):
            for arm in ("today", "uql"):
                values = samples.get((qid, arm, kind), [])
                cells.append(f"{statistics.median(values):.2f}" if values else "-")
        order = [cells[0], cells[1], cells[2], cells[3], cells[4], cells[5]]
        print(f"| {qid} | " + " | ".join(order) + " |")


if __name__ == "__main__":
    main()
