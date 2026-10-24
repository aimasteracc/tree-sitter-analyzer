"""交错运行 today/uql 两组时的墙钟时间中位数 (RFC-0041 §7)。

机器是共享的，相隔数分钟测得的两组数据不可比。``paired`` 运行会在全新进程中
对每个问题交替执行两组，共三轮；本脚本按 (问题, 组) 打印每种计时的中位数：

* ``warm``   —— 预热调用之后首次执行该问题 (服务器已预热、问题是新的)；
* ``repeat`` —— 在同一进程中再次执行同一问题 (answer cache 关闭)；
* ``cold``   —— 该问题作为全新进程的第一次调用。

用法：``python benchmarks/unified_query/paired.py <results-dir> <repo>``
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
