"""``nav action=callers`` 的属性测试：生成的小项目 × 独立 ``ast`` 判定器。

不变量（REA 对比建议 #2；对应缺陷见各测试注释）：

a. ``complete`` ⇒ 判定器的必须覆盖点 ⊆ 已列出调用方覆盖的点；
b. 同一目标，裸名回答不比限定名回答更有把握；
c. 加一个无关的同名方法（或函数）不会让回答升级为 ``complete``；
d. 不改变调用语义的别名 / 改名不改变调用方集合与完整性。

PR CI 用固定种子、少量样例（``TSA_ORACLE_EXAMPLES`` 默认 6）；夜间工作流
``wrong-complete-oracle.yml`` 设 ``TSA_ORACLE_EXAMPLES`` / ``TSA_ORACLE_SEED`` 跑更多样例，
种子写进运行摘要，失败可用同一种子复现。缩小后的反例应作为新用例加入
``tests/known_answer`` 语料。
"""

from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, event, given, seed, settings

from scripts.wrong_complete.py_oracle import python_sites
from scripts.wrong_complete.scorer import caller_keys, score
from scripts.wrong_complete.sites import Target
from scripts.wrong_complete.tsa_driver import (
    index_project,
    query_callers,
    write_project,
)
from tests.property.callers_projects import (
    NAMES_A,
    NAMES_B,
    ProjectSpec,
    projects,
    render,
    target_of,
    with_unrelated,
)

_EXAMPLES = int(os.environ.get("TSA_ORACLE_EXAMPLES", "6"))
_SEED = int(os.environ.get("TSA_ORACLE_SEED", "20261024"))
_SETTINGS = settings(
    max_examples=_EXAMPLES,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

#: 每个样例真实全量索引 1-2 次；PR 默认 6 个样例约 10-20 s，单测 30 s 超时不够宽裕，
#: 按样例数放宽（夜间 300 个样例时由工作流传 ``--timeout=0``）。
_TIMEOUT_S = max(240, _EXAMPLES * 20)

# slow_ok：每个 Hypothesis 样例都做真实索引与查询。
pytestmark = [
    pytest.mark.property,
    pytest.mark.slow_ok,
    pytest.mark.timeout(_TIMEOUT_S),
]


def _answers(
    root: Path, files: dict[str, str], target: Target
) -> dict[str, dict[str, Any]]:
    """索引一次，返回裸名与限定名两种回答。"""

    async def run() -> dict[str, dict[str, Any]]:
        write_project(root, files)
        await index_project(root)
        return {
            "bare": await query_callers(root, target.name, target.file),
            "qualified": await query_callers(root, target.qualified, target.file),
        }

    return asyncio.run(run())


def _resource_limited(answers: dict[str, dict[str, Any]]) -> bool:
    """回答是否因时间 / 资源预算而降级（``*_DEADLINE`` / ``*_BUDGET*`` / ``*TIMEOUT*``）。

    关系型不变量（b / c / d）比较两次回答；预算降级只会把回答变得更不确定，
    与被测语义无关，CI 负载下可能出现，所以这类样例被丢弃（``assume``）。
    不变量 a 不需要：非 complete 回答永远不是错误 complete。
    """
    markers = ("DEADLINE", "BUDGET", "TIMEOUT")
    return any(
        any(marker in str(reason) for marker in markers)
        for answer in answers.values()
        for reason in answer.get("completeness_reasons") or []
    )


def _owners_in_file(files: dict[str, str], target: Target) -> int:
    """目标文件里定义了同名函数 / 方法的不同外层（``@overload`` 存根与实现算同一个）。"""
    tree = ast.parse(files[target.file])
    owners = {
        parent.name if isinstance(parent, ast.ClassDef) else "<module>"
        for parent in ast.walk(tree)
        if isinstance(parent, ast.ClassDef | ast.Module)
        for node in parent.body
        if isinstance(node, ast.FunctionDef) and node.name == target.name
    }
    return len(owners)


def _fresh(factory: pytest.TempPathFactory) -> Path:
    return Path(factory.mktemp("prop"))


@seed(_SEED)
@_SETTINGS
@given(spec=projects())
def test_a_complete_answer_covers_every_oracle_site(
    tmp_path_factory: pytest.TempPathFactory, spec: ProjectSpec
) -> None:
    # 不变量 a（#1740 / #1758 / #1772：complete 却漏掉接收者无法证明的调用点）。
    files = render(spec, NAMES_A)
    target = target_of(spec, files)
    sites = python_sites(files, target)
    answers = _answers(_fresh(tmp_path_factory), files, target)
    for mode, answer in answers.items():
        # 夜间 ``--hypothesis-show-statistics`` 用：样例里 complete 的比例与必须覆盖点数。
        must = sum(1 for s in sites if s.must_cover)
        event(f"{mode}:{answer['completeness']}:must_cover={min(must, 3)}")
    wrong = {
        mode: [s.key() for s in score(a, sites, files).wrong_complete]
        for mode, a in answers.items()
    }
    assert wrong == {"bare": [], "qualified": []}, (files, target, answers)


@seed(_SEED)
@_SETTINGS
@given(spec=projects())
def test_the_bare_answer_is_never_more_confident_than_the_qualified(
    tmp_path_factory: pytest.TempPathFactory, spec: ProjectSpec
) -> None:
    # 不变量 b（#1740：裸名 complete、限定名 unknown；#1759 / #1773 两种形式应一致）。
    files = render(spec, NAMES_A)
    target = target_of(spec, files)
    # 文件里有多个同名定义时，裸名查询的是它们的并集（#1759），不是“同一目标”。
    assume(_owners_in_file(files, target) == 1)
    answers = _answers(_fresh(tmp_path_factory), files, target)
    assume(not _resource_limited(answers))
    pair = (answers["bare"]["completeness"], answers["qualified"]["completeness"])
    assert not (pair[0] == "complete" and pair[1] != "complete"), (files, target, pair)


@seed(_SEED)
@_SETTINGS
@given(spec=projects())
def test_an_unrelated_same_named_definition_never_upgrades_confidence(
    tmp_path_factory: pytest.TempPathFactory, spec: ProjectSpec
) -> None:
    # 不变量 c（#1772：更近的同名定义让真正的目标答出 complete）。
    files = render(spec, NAMES_A)
    target = target_of(spec, files)
    before = _answers(_fresh(tmp_path_factory), files, target)
    after = _answers(_fresh(tmp_path_factory), with_unrelated(files), target)
    assume(not _resource_limited(before) and not _resource_limited(after))
    upgraded = [
        mode
        for mode in ("bare", "qualified")
        if before[mode]["completeness"] != "complete"
        and after[mode]["completeness"] == "complete"
    ]
    assert upgraded == [], (files, target, before, after)


@seed(_SEED)
@_SETTINGS
@given(spec=projects())
def test_a_semantics_preserving_rename_keeps_the_callers(
    tmp_path_factory: pytest.TempPathFactory, spec: ProjectSpec
) -> None:
    # 不变量 d（#1768 / #1670：改名导入、别名不应改变调用方）。
    files_a = render(spec, NAMES_A)
    files_b = render(spec, NAMES_B)
    target_a = target_of(spec, files_a)
    target_b = target_of(spec, files_b)
    first = _answers(_fresh(tmp_path_factory), files_a, target_a)
    second = _answers(_fresh(tmp_path_factory), files_b, target_b)
    assume(not _resource_limited(first) and not _resource_limited(second))
    summary_a = {m: (a["completeness"], caller_keys(a)) for m, a in first.items()}
    summary_b = {m: (a["completeness"], caller_keys(a)) for m, a in second.items()}
    assert summary_a == summary_b, (files_a, files_b)
