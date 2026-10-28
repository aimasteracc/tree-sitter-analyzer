"""UQL 引导效果的脚本化剧本对比 (RFC-0041 采纳)。

四个对照组回答同一组问题 (``benchmarks/unified_query/questions.py``)，
真值来自同一个独立 oracle (``oracle.py``，只用标准库 ``ast``)：

``old``
    旧引导：每个问题用现有 ``nav``/``search`` 单工具的最佳组合
    (``plans_today``)，不理会 ``next_step`` 提示。
``all_uql``
    全部改用一条 ``search action=uql`` (``plans_uql``)，单跳问题也不例外。
``routed``
    新引导 (本分支的技能 / CLAUDE.md 规则 10)：五类多跳问题
    (``MULTI_HOP``) 用 uql，单跳问题 (callers / tests / callees) 留在单工具。
``old_hints``
    旧引导，但 agent 照做响应中 ``agent_summary.next_step`` 给出的 uql 查询：
    一旦某次响应里出现 ``search action=uql query="..."``，就原样执行该查询
    并停止手工展开。只对能由提示查询直接回答的问题类型切换
    (``_HINT_ANSWERS``)；其余类型照旧方案执行。

这是确定性的剧本，不是让模型现场决策：它衡量的是 "若 agent 遵循该引导"
时的调用数、字节数与正确性上限，不衡量模型是否真的会遵循。

用法 (以 ``ANSWER_CACHE_BUDGET_MB=0`` 运行，避免任何组命中答案缓存)::

    python benchmarks/agent-tasks/uql_guidance/playbooks.py \
        --repo tsa --root <TSA 检出> --out <结果目录>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_UQ = Path(__file__).resolve().parents[2] / "unified_query"
sys.path.insert(0, str(_UQ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture  # noqa: E402
import plans_today  # noqa: E402
import plans_uql  # noqa: E402
from harness import Trace, TsaClient  # noqa: E402
from oracle import Oracle  # noqa: E402
from questions import QUESTIONS, oracle_answer  # noqa: E402
from run import _score  # noqa: E402

QUESTIONS = {**QUESTIONS, "fixture": fixture.QUESTIONS}

Answer = tuple[dict[str, set[str]], dict[str, str | None]]
Plan = Callable[[Any, dict[str, Any]], Answer]

#: 新引导中路由到 uql 的多跳问题类型 (与技能 / CLAUDE.md 规则 10 一致)。
MULTI_HOP = frozenset(
    {"callers_tests", "module_untested", "callers_depth", "implementers", "impact"}
)
ARMS = ("old", "all_uql", "routed", "old_hints")

_HINTED_QUERY = re.compile(r'search action=uql query="([^"]+)"')


class HintSwitch(Exception):
    """响应中出现了 uql 提示；agent 放弃手工展开，改执行该查询。"""

    def __init__(self, query: str) -> None:
        super().__init__(query)
        self.query = query


class HintFollowingClient:
    """包装 ``TsaClient``：在允许切换时，遇到 uql 提示即抛出 ``HintSwitch``。"""

    def __init__(self, inner: TsaClient) -> None:
        self.inner = inner
        self.armed = False

    @property
    def trace(self) -> Trace:
        return self.inner.trace

    @trace.setter
    def trace(self, value: Trace) -> None:
        self.inner.trace = value

    def call(self, facade: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.inner.call(facade, arguments)
        if self.armed and facade == "nav":
            summary = result.get("agent_summary")
            next_step = summary.get("next_step") if isinstance(summary, dict) else None
            match = _HINTED_QUERY.search(next_step or "")
            if match:
                raise HintSwitch(match.group(1))
        return result


def _run_uql(c: Any, query: str) -> dict[str, Any]:
    return c.call("search", {"action": "uql", "query": query, "limit": 500})


def _hinted_callers_tests(c: Any, query: str, p: dict[str, Any]) -> Answer:
    r = _run_uql(c, query)
    return (
        {
            "callers": plans_uql._group(r, "callers"),
            "tests": plans_uql._group(r, "tests"),
        },
        {
            "callers": plans_uql._claim(r, "callers"),
            "tests": plans_uql._claim(r, "tests"),
        },
    )


def _hinted_module_untested(c: Any, query: str, p: dict[str, Any]) -> Answer:
    # 提示给的是 ``.callers().tests()``，并注明 ``.untested()`` 用于无测试调用方；
    # 遵循提示的 agent 换成 ``.untested()``，再在客户端按模块过滤。
    untested = query.replace(".callers().tests()", ".callers().untested()")
    r = _run_uql(c, untested)
    keep = {
        k
        for k in plans_uql._group(r, "callers")
        if k.split("::")[0] == p["module"] and not k.endswith("::<module>")
    }
    return {"functions": keep}, {"functions": plans_uql._last_claim(r)}


def _hinted_impact(c: Any, query: str, p: dict[str, Any]) -> Answer:
    r = _run_uql(c, query)
    tests = plans_uql._group(r, "impact.tests")
    callers = plans_uql._group(r, "impact") | tests
    files = set(r.get("files") or [])
    files -= {k.split("::")[0] for k in plans_uql._group(r, "symbol")} - {
        k.split("::")[0] for k in callers
    }
    claim = plans_uql._claim(r, "impact")
    return (
        {"callers": callers, "tests": tests, "files": files},
        {"callers": claim, "tests": claim, "files": claim},
    )


#: 提示查询能直接回答的问题类型 → 执行并解析提示查询的方式。
_HINT_ANSWERS: dict[str, Callable[[Any, str, dict[str, Any]], Answer]] = {
    "callers_tests": _hinted_callers_tests,
    "module_untested": _hinted_module_untested,
    "impact": _hinted_impact,
}


def plan_for(arm: str, kind: str) -> Plan:
    if arm in ("old", "old_hints"):
        return plans_today.PLANS[kind]
    if arm == "all_uql":
        return plans_uql.PLANS[kind]
    if arm == "routed":
        return (plans_uql if kind in MULTI_HOP else plans_today).PLANS[kind]
    raise ValueError(f"unknown arm {arm}")


def discovery_for(arm: str, kinds: set[str]) -> list[tuple[str, dict[str, Any]]]:
    """每组只付一次的语法发现调用。"""
    tql = ("search", {"action": "tql_schema"})
    uql = ("search", {"action": "help", "target_action": "uql"})
    needs_tql = bool(kinds & set(plans_today.DISCOVERY))
    if arm in ("old", "old_hints"):
        # old_hints 的提示给出完整查询，无需 uql 语法发现。
        return [tql] if needs_tql else []
    if arm == "all_uql":
        return [uql]
    routed_tql = {k for k in kinds if k not in MULTI_HOP} & set(plans_today.DISCOVERY)
    return [uql] + ([tql] if routed_tql else [])


def run_question(
    arm: str, client: Any, kind: str, params: dict[str, Any]
) -> tuple[Answer, str]:
    """执行一个问题；返回答案与提示处理结果 (``""`` 或 ``switched:<查询>``)。"""
    plan = plan_for(arm, kind)
    handler = _HINT_ANSWERS.get(kind)
    if arm != "old_hints" or handler is None:
        return plan(client, params), ""
    client.armed = True
    try:
        return plan(client, params), ""
    except HintSwitch as switch:
        client.armed = False
        return handler(client, switch.query, params), f"switched:{switch.query}"
    finally:
        client.armed = False


_NO_INDEX = ('"UQL_INDEX_UNAVAILABLE"', '"INDEX_MISSING"')



def run_arm(arm: str, repo: str, root: str, truths: dict[str, Any]) -> dict[str, Any]:
    inner = TsaClient(root)
    client: Any = HintFollowingClient(inner) if arm == "old_hints" else inner
    # 预热：一次不计入的无关 callers 调用，模拟长驻服务器已建好图。
    inner.trace = Trace()
    warm = inner.call("nav", {"action": "callers", "function_name": "main"})
    if warm.get("index_missing"):
        # 没有索引时所有组都只会得到空答案，比较毫无意义：直接失败。
        raise SystemExit(
            f"no index under {root}: run `tree-sitter-analyzer --ast-cache "
            "--ast-cache-mode index --project-root <root>` first"
        )
    rows: list[dict[str, Any]] = []
    for q in QUESTIONS[repo]:
        client.trace = Trace()
        answer_claims, hint = run_question(arm, client, q.kind, q.params)
        trace = inner.trace
        answer, claims = answer_claims
        if any(code in c.response for c in trace.calls for code in _NO_INDEX):
            raise SystemExit(f"{arm} {q.qid}: a call reported no index under {root}")
        rows.append(
            {
                "arm": arm,
                "qid": q.qid,
                "kind": q.kind,
                "calls": len(trace.calls),
                "tools": [
                    json.loads(c.request)["arguments"].get("action")
                    for c in trace.calls
                ],
                "response_bytes": trace.response_bytes,
                "request_bytes": trace.request_bytes,
                "seconds": round(trace.seconds, 3),
                "hint": hint,
                "score": _score(answer, claims, truths[q.qid]),
            }
        )
        r = rows[-1]
        print(
            f"{arm:9} {q.qid} calls={r['calls']:2} bytes={r['response_bytes']:6} "
            f"exact={r['score']['exact']} wrong_complete={r['score']['wrong_complete']}"
            + (f" {hint}" if hint else ""),
            flush=True,
        )
    inner.trace = Trace()
    for facade, dargs in discovery_for(arm, {q.kind for q in QUESTIONS[repo]}):
        inner.call(facade, dargs)
    return {
        "arm": arm,
        "rows": rows,
        "discovery_bytes": inner.trace.response_bytes,
        "discovery_calls": len(inner.trace.calls),
    }


def _sets_exact(row: dict[str, Any]) -> str:
    sets = row["score"]["sets"]
    return (
        "exact"
        if row["score"]["exact"]
        else (f"{sum(s['exact'] for s in sets.values())}/{len(sets)}")
    )


def render(repo: str, label: str, results: list[dict[str, Any]]) -> str:
    by_arm = {r["arm"]: r for r in results}
    lines = [
        f"Target: {label}. Bytes are the JSON the agent receives "
        "(tokens ~ bytes/4). Discovery is a one-time cost per arm.",
        "",
        "| Q | kind | "
        + " | ".join(f"{a} calls / bytes / correct" for a in ARMS)
        + " |",
        "| --- | --- |" + " --- |" * len(ARMS),
    ]
    for i, q in enumerate(QUESTIONS[repo]):
        cells = []
        for a in ARMS:
            row = by_arm[a]["rows"][i]
            cells.append(
                f"{row['calls']} / {row['response_bytes']:,} / {_sets_exact(row)}"
            )
        lines.append(f"| {q.qid} | {q.kind} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "| arm | calls | response bytes | + discovery bytes | exact answers | wrong `complete` | hint switches |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for a in ARMS:
        rows = by_arm[a]["rows"]
        lines.append(
            f"| {a} | {sum(r['calls'] for r in rows)} "
            f"| {sum(r['response_bytes'] for r in rows):,} "
            f"| {by_arm[a]['discovery_bytes']:,} "
            f"| {sum(r['score']['exact'] for r in rows)}/{len(rows)} "
            f"| {sum(r['score']['wrong_complete'] for r in rows)} "
            f"| {sum(r['hint'].startswith('switched') for r in rows)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, choices=sorted(QUESTIONS))
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="", help="target description for the report")
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    oracle = Oracle(args.root)
    truths = {q.qid: oracle_answer(oracle, q) for q in QUESTIONS[args.repo]}
    results = [
        run_arm(arm, args.repo, args.root, truths) for arm in args.arms.split(",")
    ]
    (out / f"{args.repo}-uql-guidance.json").write_text(
        json.dumps(results, indent=2, default=sorted), encoding="utf-8"
    )
    if set(args.arms.split(",")) == set(ARMS):
        report = render(args.repo, args.label or args.root, results)
        (out / f"{args.repo}-uql-guidance.md").write_text(report, encoding="utf-8")
        print(report)


if __name__ == "__main__":
    main()
