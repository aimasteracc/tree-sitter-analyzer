"""``nav action=callers`` 的已知答案语料：错误 ``complete`` 的持续守卫。

语料来自真实缺陷（每个用例的 ``issue`` 字段）：#1740 裸名跳过 NAME_ONLY 门、
#1758 未解析接收者、#1759 声明文件守卫、#1762 TS 下标调用、#1763/#1766 箭头常量
误报调用方、#1764/#1769 ES 模块导入、#1768 改名默认导入、#1772 Protocol 存根 +
测试遮蔽、#1773 ``@overload``、#1743 Java 类型化接收者与虚分派。

此前“0 个错误 complete”只在 dogfood 轮次里手工测量、证据在仓库之外；这里把它
变成每个 PR 都执行的断言。每个用例、每种模式（裸名 / 限定名）断言：

1. 回答为 ``complete`` 时列出全部手写真值调用点；
2. 回答为 ``complete`` 时覆盖独立判定器找到的全部必须覆盖点；
3. 已列出的真值调用点保持列出（``# gt listed``）；
4. 不列出真值之外的调用方（拒绝虚假声明，#1766）；
5. 未列出的真值调用点必须出现在证据字段里（不静默丢失，#1764）；
6. 裸名回答不比限定名回答更有把握（#1740 不变量）；
7. 目标名只有一处定义时，带不带 ``file_path`` 答案相同（#1798）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from scripts.wrong_complete.scorer import evidence_keys, score
from tests.known_answer._cases import MODES, Case
from tests.known_answer._cases_java_ts import JAVA_TS_CASES
from tests.known_answer._cases_python import PYTHON_CASES
from tests.known_answer._runner import (
    Observation,
    observe,
    oracle_sites,
    truth_sites,
)

CASES: tuple[Case, ...] = (*PYTHON_CASES, *JAVA_TS_CASES)
_IDS = [case.case_id for case in CASES]

# slow_ok：每个用例首次访问时真实全量索引一次（约 0.3-4 s，含首次导入）。
pytestmark = pytest.mark.slow_ok


@pytest.fixture(scope="module")
def observed(tmp_path_factory: pytest.TempPathFactory) -> Callable[[Case], Observation]:
    """按用例缓存的观测（同一 worker 内每个用例只索引一次，约 0.3 s / 用例）。"""
    cache: dict[str, Observation] = {}

    def get(case: Case) -> Observation:
        if case.case_id not in cache:
            root = Path(tmp_path_factory.mktemp(case.case_id.replace("-", "_")[:40]))
            cache[case.case_id] = observe(case, root)
        return cache[case.case_id]

    return get


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_a_complete_answer_lists_every_hand_labelled_caller(
    observed: Callable[[Case], Observation], case: Case, mode: str
) -> None:
    # 回归：case.issue 所列缺陷（#1740 / #1758 / #1762 / #1768 / #1772 均曾是错误 complete）。
    obs = observed(case)
    answer = obs.answers[mode]
    missing = (
        case.truth - obs.listed_truth(mode)
        if answer["completeness"] == "complete"
        else frozenset()
    )
    assert missing == frozenset(), answer


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_a_complete_answer_covers_every_oracle_site(
    observed: Callable[[Case], Observation], case: Case, mode: str
) -> None:
    # 回归：case.issue；判定器独立于 TSA（Python ast / token 扫描）。
    obs = observed(case)
    result = score(obs.answers[mode], obs.sites, case.files)
    assert [site.key() for site in result.wrong_complete] == [], result.as_dict()


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_listed_true_callers_stay_listed(
    observed: Callable[[Case], Observation], case: Case, mode: str
) -> None:
    # 回归：case.issue 的召回修复（#1743 / #1764 / #1766 / #1769 / #1773）不得回退。
    obs = observed(case)
    lost = case.listed_floor - obs.listed_truth(mode)
    assert lost == frozenset(), obs.answers[mode]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_no_listed_caller_is_outside_the_truth(
    observed: Callable[[Case], Observation], case: Case, mode: str
) -> None:
    # 回归：#1766（内层同名函数抢走 16 个外部调用方）——拒绝真值之外的声明。
    obs = observed(case)
    truth = truth_sites(case)
    extra = [c for c in obs.callers(mode) if not any(c.covers(site) for site in truth)]
    assert extra == [], obs.answers[mode]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_an_unlisted_true_caller_is_reported_as_evidence(
    observed: Callable[[Case], Observation], case: Case, mode: str
) -> None:
    # 回归：#1764（``verifying`` 的真实调用既未列出、也不在任何证据字段里）。
    obs = observed(case)
    answer = obs.answers[mode]
    silent = case.truth - obs.listed_truth(mode) - evidence_keys(answer)
    assert silent == frozenset(), answer


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_the_bare_answer_is_never_more_confident_than_the_qualified(
    observed: Callable[[Case], Observation], case: Case
) -> None:
    # 回归：#1740（裸名 complete、限定名 unknown）。
    obs = observed(case)
    pair = (
        obs.answers["bare"]["completeness"],
        obs.answers["qualified"]["completeness"],
    )
    assert not (pair[0] == "complete" and pair[1] != "complete"), pair


def _defines_target_once(case: Case) -> bool:
    """夹具里目标名恰有一处定义（``def`` / ``function`` / 方法头），独立于 TSA。"""
    name = re.escape(case.target_name)
    definition = re.compile(
        rf"^[ \t]*(?:async[ \t]+)?(?:def|function)[ \t]+{name}\b"
        rf"|^[ \t]*(?:(?:public|private|protected|static)[ \t]+)*[\w<>\[\]]+[ \t]+{name}\(",
        re.MULTILINE,
    )
    return sum(len(definition.findall(text)) for text in case.files.values()) == 1


def _parity_shape(answer: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        answer["completeness"],
        tuple(answer.get("completeness_reasons") or ()),
        tuple(sorted((c["file"], c["name"]) for c in answer.get("callers") or [])),
        tuple(
            sorted((s["file"], s["line"]) for s in answer.get("name_only_sites") or [])
        ),
    )


_UNIQUE = [case for case in CASES if _defines_target_once(case)]


def test_the_scope_parity_corpus_covers_unique_names() -> None:
    # 判定器自检：#1798 用例必须在唯一名字集合里，否则下面的参数化静默为空。
    assert "py-1798-unique-name-scope-parity" in {case.case_id for case in _UNIQUE}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", _UNIQUE, ids=[case.case_id for case in _UNIQUE])
def test_a_unique_name_gets_the_same_answer_with_or_without_file_path(
    observed: Callable[[Case], Observation], case: Case, mode: str
) -> None:
    # 回归：#1798（rich ``Text.join``：不带范围列出 48 个调用方，带范围 7 个）。
    obs = observed(case)
    assert _parity_shape(obs.unscoped[mode]) == _parity_shape(obs.answers[mode]), (
        obs.unscoped[mode],
        obs.answers[mode],
    )


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_a_cross_name_batch_answers_every_input_as_a_single_call(
    observed: Callable[[Case], Observation], case: Case
) -> None:
    # RFC-0041 跨名批量：查询作用域内一次 execute_batch（两种模式 + 夹具里的其余名字）
    # 与逐个单次调用逐字节相同——共享的只是与输入无关的工作。
    obs = observed(case)
    assert obs.batch_mismatches == ()


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_the_oracle_finds_exactly_the_hand_labelled_truth(case: Case) -> None:
    # 判定器自检：在语料上与手写真值逐点一致（不运行 TSA）。
    found = frozenset(site.key() for site in oracle_sites(case) if site.must_cover)
    assert found == case.truth
