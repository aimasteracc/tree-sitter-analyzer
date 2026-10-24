"""根据基准结果行渲染前后对比表 (RFC-0041 §7)。

用法：``uv run python benchmarks/unified_query/report.py <results-dir>``
(需先由 ``tokens.py`` 写入 token 计数)。

``correct`` 为 ``exact`` (每个答案集合都与 oracle 相同) 或匹配的集合数；
``claims`` 列出每个集合声明的完整性 (``-`` = 无声明)。``WRONG`` 标记声明为
``complete`` 却遗漏了 oracle 元素的集合。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ARMS = ("today", "uql", "grep")


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _load(root: Path, repo: str, arm: str) -> dict[str, dict[str, Any]]:
    path = root / f"{repo}-{arm}.jsonl"
    if not path.exists():
        return {}
    rows = {r["qid"]: r for r in _rows(path)}
    for cold in root.glob(f"{repo}-{arm}-cold-*.jsonl"):
        if cold.name.endswith("-texts.jsonl"):
            continue
        for row in _rows(cold):
            if row["qid"] in rows:
                rows[row["qid"]]["cold_seconds"] = row["seconds"]
    return rows


def _t(value: Any) -> str:
    return "-" if value is None else f"{value:.2f}"


def _correct(row: dict[str, Any]) -> str:
    sets = row["score"]["sets"]
    good = sum(1 for s in sets.values() if s["exact"])
    text = "exact" if good == len(sets) else f"{good}/{len(sets)} sets"
    if row["score"]["wrong_complete"]:
        text += " WRONG"
    return text


def _claims(row: dict[str, Any]) -> str:
    return ",".join((s["claim"] or "-") for s in row["score"]["sets"].values())


def main() -> None:
    root = Path(sys.argv[1])
    repos = sorted({p.name.split("-")[0] for p in root.glob("*-today.jsonl")})
    print(
        "| repo | Q | arm | calls | resp bytes | tokens (o200k) | warm s | "
        "repeat s | cold s | correct | claims |"
    )
    print("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    totals: dict[tuple[str, str], list[float]] = {}
    for repo in repos:
        data = {arm: _load(root, repo, arm) for arm in ARMS}
        for qid in sorted(data["today"]):
            for arm in ARMS:
                row = data[arm].get(qid)
                if row is None:
                    continue
                tokens = row.get("tokens_o200k", 0)
                print(
                    f"| {repo} | {qid} | {arm} | {row['calls']} | "
                    f"{row['response_bytes']:,} | {tokens:,} | {_t(row['seconds'])} | "
                    f"{_t(row.get('repeat_seconds'))} | {_t(row.get('cold_seconds'))} | "
                    f"{_correct(row)} | {_claims(row)} |"
                )
                acc = totals.setdefault((repo, arm), [0, 0, 0, 0.0, 0, 0])
                acc[0] += row["calls"]
                acc[1] += row["response_bytes"]
                acc[2] += tokens
                acc[3] += row["seconds"]
                acc[4] += int(row["score"]["exact"])
                acc[5] += int(row["score"]["wrong_complete"])
    print()
    print(
        "| repo | arm | calls | resp bytes | tokens | warm s | exact | wrong complete |"
    )
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for (repo, arm), acc in sorted(totals.items()):
        print(
            f"| {repo} | {arm} | {acc[0]} | {acc[1]:,} | {acc[2]:,} | "
            f"{acc[3]:.1f} | {acc[4]}/8 | {acc[5]} |"
        )


if __name__ == "__main__":
    main()
