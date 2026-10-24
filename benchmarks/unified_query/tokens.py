"""Count tokens for recorded benchmark texts (RFC-0041).

Estimator: tiktoken ``o200k_base``. Claude's tokenizer is not public, so this
is a labelled *estimate*; it counts request plus response text for every call
(the whole task, not just one reply). ``bytes/4`` is reported alongside for
comparison with ``benchmarks/agent-tasks``. Run with::

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
