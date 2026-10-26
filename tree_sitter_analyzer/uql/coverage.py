"""统一查询语言的逐阶段完整性 (RFC-0041 §3)。

完整性*由实际检查过的内容推导*，绝不因为缺少失败标志就认定完整：

* 阶段初始为 ``unknown``，只有当它检查过的每个输入都给出了正向覆盖时才变为
  ``complete`` (对关系阶段而言即生产者自身的 ``completeness == "complete"``
  —— ``nav action=callers`` 的结果原样采用)；
* 完全不报告覆盖的生产者记为 ``unknown``
  (:data:`PRODUCER_COVERAGE_MISSING`)，而不是 complete；
* 阶段的*有效*覆盖会折叠其之前的所有阶段，因此只有每个阶段都 ``complete``
  时查询整体才是 ``complete``。

状态顺序：``complete`` < ``incomplete`` (已知下界) <
``unknown`` (连下界都不是)。合并时取最差状态，并按顺序取原因的并集。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

COMPLETE = "complete"
INCOMPLETE = "incomplete"
UNKNOWN = "unknown"
STATUSES = (COMPLETE, INCOMPLETE, UNKNOWN)
_RANK = {COMPLETE: 0, INCOMPLETE: 1, UNKNOWN: 2}

# -- UQL 自有的原因码 (封闭集合；调用方自己的原因码原样透传) ----------
#: 生产者未返回 completeness 字段。
PRODUCER_COVERAGE_MISSING = "PRODUCER_COVERAGE_MISSING"
#: 生产者调用失败；保留已有的部分行 (若有)。
RELATION_ERROR = "RELATION_ERROR"
#: 生产者列出的行数少于其统计的行数。
RELATION_LIMIT = "RELATION_LIMIT"
#: 遍历在单次查询的节点预算处停止。
RELATION_NODE_BUDGET = "RELATION_NODE_BUDGET"
#: ``impact()`` 在深度上限处停止，仍有未展开的前沿。
RELATION_DEPTH_LIMIT = "RELATION_DEPTH_LIMIT"
#: ``callees()`` 没有生产者的覆盖声明。
CALLEES_COVERAGE_UNREPORTED = "CALLEES_COVERAGE_UNREPORTED"
#: 部分 callee 未能解析到项目内的定义。
CALLEE_UNRESOLVED = "CALLEE_UNRESOLVED"
#: 测试文件中的辅助函数本身又被其他辅助函数调用 (> 1 跳)。
TEST_HELPER_DEPTH = "TEST_HELPER_DEPTH"
#: ``tested()`` / ``untested()`` 无法判定部分行。
MEMBERSHIP_UNKNOWN = "MEMBERSHIP_UNKNOWN"
#: 选择器使用了没有覆盖证明的边 / 历史 / 规则谓词。
SELECTOR_PREDICATE_UNPROVEN = "SELECTOR_PREDICATE_UNPROVEN"
#: 选择器匹配的符号数超过求值器上限。
SELECT_CAP_REACHED = "SELECT_CAP_REACHED"
#: 本阶段之前的某个阶段不完整。
UPSTREAM_INCOMPLETE = "UPSTREAM_INCOMPLETE"
UPSTREAM_UNKNOWN = "UPSTREAM_UNKNOWN"
#: 跨调用分页无法固定到同一个源码代次 (generation)。
CURSOR_GENERATION_UNVERIFIED = "CURSOR_GENERATION_UNVERIFIED"

#: 来源阶段的全量源码复核超出期限（2 s），因此不能宣称普查。
SOURCE_RECHECK_DEADLINE = "SOURCE_RECHECK_DEADLINE"

#: 查询未执行（解析、校验或执行失败），因此答复的完整性未知 (#1811)。
QUERY_NOT_EXECUTED = "QUERY_NOT_EXECUTED"

UQL_REASONS = frozenset(
    {
        SOURCE_RECHECK_DEADLINE,
        QUERY_NOT_EXECUTED,
        PRODUCER_COVERAGE_MISSING,
        RELATION_ERROR,
        RELATION_LIMIT,
        RELATION_NODE_BUDGET,
        RELATION_DEPTH_LIMIT,
        CALLEES_COVERAGE_UNREPORTED,
        CALLEE_UNRESOLVED,
        TEST_HELPER_DEPTH,
        MEMBERSHIP_UNKNOWN,
        SELECTOR_PREDICATE_UNPROVEN,
        SELECT_CAP_REACHED,
        UPSTREAM_INCOMPLETE,
        UPSTREAM_UNKNOWN,
        CURSOR_GENERATION_UNVERIFIED,
    }
)


@dataclass(frozen=True)
class Coverage:
    """完整性状态，以及非 complete 时说明理由的原因码。"""

    status: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _RANK:
            raise ValueError(f"invalid completeness status: {self.status!r}")
        if self.status == COMPLETE and self.reasons:
            raise ValueError("complete coverage cannot carry reasons")
        if self.status != COMPLETE and not self.reasons:
            raise ValueError("non-complete coverage must name a reason")

    @property
    def complete(self) -> bool:
        return self.status == COMPLETE


COMPLETE_COVERAGE = Coverage(COMPLETE)


def gap(status: str, *reasons: str) -> Coverage:
    return Coverage(status, tuple(dict.fromkeys(reasons)))


def combine(coverages: Iterable[Coverage]) -> Coverage:
    """取最差状态与按序合并的原因。未检查任何输入时为 unknown。"""
    items = list(coverages)
    if not items:
        return gap(UNKNOWN, PRODUCER_COVERAGE_MISSING)
    worst = max(items, key=lambda c: _RANK[c.status]).status
    if worst == COMPLETE:
        return COMPLETE_COVERAGE
    reasons: dict[str, None] = {}
    for item in items:
        for reason in item.reasons:
            reasons[reason] = None
    return Coverage(worst, tuple(reasons))


def combine_or_complete(coverages: Iterable[Coverage]) -> Coverage:
    """与 :func:`combine` 相同，但空输入集视为空真意义上的 complete。

    仅用于输入集本身已确立的阶段 (例如上游为零行的关系阶段什么都不检查，
    也不额外声明任何内容)。
    """
    items = list(coverages)
    return combine(items) if items else COMPLETE_COVERAGE


def with_upstream(own: Coverage, upstream: Coverage) -> Coverage:
    """阶段的有效覆盖：自身缺口加上上游标记。"""
    if upstream.complete:
        return own
    marker = UPSTREAM_UNKNOWN if upstream.status == UNKNOWN else UPSTREAM_INCOMPLETE
    status = max((own.status, upstream.status), key=lambda s: _RANK[s])
    return gap(status, *own.reasons, marker)


def from_producer(response: Mapping[str, Any] | Any) -> Coverage:
    """原样采用 ``nav action=callers`` payload 的覆盖契约。"""
    if not isinstance(response, Mapping) or response.get("success") is False:
        return gap(UNKNOWN, RELATION_ERROR)
    status = response.get("completeness")
    if status not in _RANK:
        return gap(UNKNOWN, PRODUCER_COVERAGE_MISSING)
    reasons = tuple(str(r) for r in response.get("completeness_reasons") or ())
    if status == COMPLETE:
        listed = response.get("callers_listed")
        counted = response.get("caller_count")
        if isinstance(listed, int) and isinstance(counted, int) and counted > listed:
            return gap(INCOMPLETE, RELATION_LIMIT)
        return COMPLETE_COVERAGE
    if not reasons:
        reasons = (PRODUCER_COVERAGE_MISSING,)
    return Coverage(str(status), reasons)
