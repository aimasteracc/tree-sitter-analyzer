"""夜间真实仓库扫描：抽样目标 → TSA 全量索引 → 两种模式查询 → 独立判定器评分。

移植自 dogfood r10-r12 的 ``bare_sweep.py`` / ``audit_complete.py``。任何**未被
已审查排除项覆盖**的错误 ``complete``（判定器的 ``target`` / ``possible`` 点没有被
已列出的调用方覆盖）都让进程以退出码 1 结束。

用法::

    uv run python -m scripts.wrong_complete.sweep --repo /tmp/rich --lang py \\
        --seed 20261024 --count 40 --out scores-rich.json \\
        [--exclusions scripts/wrong_complete/exclusions.json --label rich]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from scripts.wrong_complete.candidates import Candidate, sample, tracked_files
from scripts.wrong_complete.py_model import Project
from scripts.wrong_complete.py_oracle import PythonOracle
from scripts.wrong_complete.scorer import score
from scripts.wrong_complete.sites import Site, Target
from scripts.wrong_complete.token_oracle import JAVA_SUFFIXES, TokenCorpus, TokenOracle

MODES = ("bare", "qualified")
#: 真实仓库的索引文件上限（远大于 pinned 仓库的文件数）。
REPO_MAX_FILES = 20000


class LazySources(Mapping[str, str]):
    """按需读取仓库文件的只读映射（评分器补调用方区间时用）。"""

    def __init__(self, repo: Path, files: list[str]) -> None:
        self.repo = repo
        self.files = files
        self._known = frozenset(files)
        self._cache: dict[str, str] = {}

    def __getitem__(self, key: str) -> str:
        if key not in self._cache:
            if key not in self._known:
                raise KeyError(key)
            self._cache[key] = (self.repo / key).read_text(
                encoding="utf-8", errors="replace"
            )
        return self._cache[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.files)

    def __len__(self) -> int:
        return len(self.files)


def build_oracle(
    lang: str, sources: Mapping[str, str]
) -> Callable[[Target], list[Site]]:
    """语言 → ``target -> sites``（项目模型只构建一次）。"""
    if lang == "py":
        project = Project({p: sources[p] for p in sources if p.endswith(".py")})
        return lambda target: PythonOracle(project, target).run()
    corpus = TokenCorpus(
        {p: sources[p] for p in sources if p.endswith(JAVA_SUFFIXES)}, JAVA_SUFFIXES
    )
    return lambda target: TokenOracle(corpus, target).run()


def load_exclusions(
    path: Path | None, label: str
) -> dict[tuple[str, str, str, int], str]:
    """已审查排除项：``(label, 限定名, file, line)`` → 理由。"""
    if path is None or not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {
        (row["repo"], row["target"], row["file"], int(row["line"])): row["reason"]
        for row in rows
        if row["repo"] == label
    }


def judge(
    candidate: Candidate,
    answers: Mapping[str, Mapping[str, Any]],
    sites: list[Site],
    sources: Mapping[str, str],
    exclusions: Mapping[tuple[str, str, str, int], str],
    label: str,
) -> dict[str, Any]:
    """一个目标两种模式的评分记录；``wrong`` 为未被排除的错误 complete 点。"""
    target = candidate.target
    row: dict[str, Any] = {
        "target": target.qualified,
        "file": target.file,
        "line": target.line,
        "grep_call_lines": candidate.call_lines,
        "oracle_must_cover": sum(1 for s in sites if s.must_cover),
    }
    for mode in MODES:
        answer = answers[mode]
        result = score(answer, sites, sources)
        wrong = [
            s
            for s in result.wrong_complete
            if (label, target.qualified, s.file, s.line) not in exclusions
        ]
        row[mode] = {
            "completeness": answer.get("completeness"),
            "reasons": answer.get("completeness_reasons"),
            "listed": len(result.listed),
            "evidenced": len(result.evidenced),
            "silent": len(result.silent),
            "excluded": len(result.wrong_complete) - len(wrong),
            "wrong": [
                {
                    "file": s.file,
                    "line": s.line,
                    "verdict": s.verdict,
                    "reason": s.reason,
                    "caller": s.caller,
                }
                for s in wrong
            ],
        }
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """按模式汇总：样本数、complete 数、错误 complete 目标数与点数。"""
    out: dict[str, Any] = {"n": len(rows)}
    for mode in MODES:
        out[mode] = {
            "complete": sum(1 for r in rows if r[mode]["completeness"] == "complete"),
            "wrong_complete_targets": sum(1 for r in rows if r[mode]["wrong"]),
            "wrong_complete_sites": sum(len(r[mode]["wrong"]) for r in rows),
            "excluded_sites": sum(r[mode]["excluded"] for r in rows),
        }
    return out


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    from scripts.wrong_complete.tsa_driver import index_project, query_callers

    repo = Path(args.repo).resolve()
    started = time.perf_counter()
    candidates = sample(repo, args.lang, args.seed, args.count)
    sources = LazySources(repo, tracked_files(repo))
    oracle = build_oracle(args.lang, sources)
    indexed = await index_project(repo, max_files=REPO_MAX_FILES)
    index_seconds = round(time.perf_counter() - started, 1)
    exclusions = load_exclusions(
        Path(args.exclusions) if args.exclusions else None, args.label
    )
    rows = []
    for candidate in candidates:
        target = candidate.target
        answers = {
            "bare": await query_callers(repo, target.name, target.file),
            "qualified": await query_callers(repo, target.qualified, target.file),
        }
        rows.append(
            judge(candidate, answers, oracle(target), sources, exclusions, args.label)
        )
    return {
        "label": args.label,
        "repo": str(repo),
        "lang": args.lang,
        "seed": args.seed,
        "indexed_files": indexed.get("files_indexed") or indexed.get("indexed_files"),
        "index_seconds": index_seconds,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "summary": summarize(rows),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    """命令行入口；有未排除的错误 complete 时返回 1。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--lang", choices=("py", "java"), required=True)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--exclusions", default=None)
    args = parser.parse_args(argv)
    args.label = args.label or Path(args.repo).name
    report = asyncio.run(_run(args))
    Path(args.out).write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps({"label": report["label"], **report["summary"]}, ensure_ascii=False)
    )
    wrong = sum(report["summary"][mode]["wrong_complete_sites"] for mode in MODES)
    for row in report["rows"]:
        for mode in MODES:
            for site in row[mode]["wrong"]:
                print(
                    f"WRONG COMPLETE {mode} {row['target']} ({row['file']}) misses {site['file']}:{site['line']} [{site['verdict']}/{site['reason']}]"
                )
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
