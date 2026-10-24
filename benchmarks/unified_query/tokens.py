"""统计已记录基准文本的 token 数 (RFC-0041)。

估算器：tiktoken ``o200k_base``。Claude 的 tokenizer 未公开，因此这是明确标注的
*估算值*；它统计每次调用的请求加响应文本 (整个任务，而非单次回复)。同时输出
``bytes/4`` 以便与 ``benchmarks/agent-tasks`` 对比。运行方式::

    uv run --with tiktoken python benchmarks/unified_query/tokens.py <results-dir>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import tiktoken


def main() -> None:
    root = Path(sys.argv[1])
    enc = tiktoken.get_encoding("o200k_base")
    for texts_file in sorted(root.glob("*-texts.jsonl")):
        stem = texts_file.name[: -len("-texts.jsonl")]
        totals: dict[str, dict[str, int]] = defaultdict(
            lambda: {"task": 0, "discovery": 0}
        )
        for line in texts_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            bucket = "discovery" if row["discovery"] else "task"
            totals[row["qid"]][bucket] += len(enc.encode(row["text"]))
        rows_file = root / f"{stem}.jsonl"
        rows = [
            json.loads(x)
            for x in rows_file.read_text(encoding="utf-8").splitlines()
            if x.strip()
        ]
        for row in rows:
            row["tokens_o200k"] = totals[row["qid"]]["task"]
            row["discovery_tokens_o200k"] = totals[row["qid"]]["discovery"]
            row["tokens_bytes_div4"] = (
                row["response_bytes"] + row["request_bytes"]
            ) // 4
        rows_file.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        print(f"{stem}: tokens written for {len(rows)} rows")


if __name__ == "__main__":
    main()
