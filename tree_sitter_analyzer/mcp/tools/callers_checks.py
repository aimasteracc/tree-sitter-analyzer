"""RFC-0040: ``nav action=callers`` 的 ``complete`` 必须由证据构成（proof-carrying）。

#1740 / #1758 / #1759 / #1772 / #1644 同属一类：``complete`` 曾由“没有任何失败
标志”推出。门没有运行、或在过窄的范围上运行时，它的计数默认为 0，答案便成了
``complete``。这里把推导反过来：

* 每道必需检查报告 :class:`Checked`（在查询目标集上运行过，附带发现的问题码）
  或 :class:`NotChecked`（未能运行，附带点名该检查的原因码）。
* ``complete`` 只能由 :func:`prove` 构成，且仅当 :data:`REQUIRED_CHECKS` 中的
  **每一道**检查都在同一目标集上报告 ``Checked`` 且没有问题。
* 漏记的检查（代码路径忘了运行它、或新加入登记表而尚未接线）按
  ``NotChecked(spec.unchecked_reason)`` 处理——默认失败即关闭（fail closed），
  不依赖评审者记得。

原因码与先后顺序沿用 #1632 的契约（``callers_reasons``）：调用边层的原因可并存，
复核门的原因单独出现（#1672 的 ``also`` 例外由该门自己的问题码元组表达）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from .callers_absence import ACCESSOR_UNCHECKED_REASON
from .callers_absence import UNCHECKED_REASON as NON_CALL_UNCHECKED_REASON
from .callers_decorators import DECORATED_REASON
from .callers_outcomes import Checked, CheckOutcome, NotChecked, Scope, checked
from .callers_reasons import (
    DECLARING_FILE_REASON,
    NAME_ONLY_REASON,
    NAME_ONLY_UNCHECKED_REASON,
    UNATTRIBUTED_REASON,
    UNATTRIBUTED_UNCHECKED_REASON,
    UNCHECKED_REASON,
    UNRESOLVED_INBOUND_REASON,
)
from .callers_target import UNCHECKED_REASON as TARGET_UNCHECKED_REASON
from .relation_freshness import UNKNOWN_REASON
from .unindexed_sources import UNCHECKED_REASON as UNINDEXED_UNCHECKED_REASON


@dataclass(frozen=True)
class CheckSpec:
    """一道必需检查：名字、所在层，以及未运行时报告的原因码。"""

    name: str
    layer: str
    unchecked_reason: str


#: 调用边层（原因可并存）。顺序即 #1632 的原因码优先级。
EDGE: Final = "edge"
#: 复核门（按序，首个未通过者给出原因）。
REVIEW: Final = "review"

#: ``complete`` 所需的全部检查（闭集，顺序即原因优先级）。
REQUIRED_CHECKS: Final[tuple[CheckSpec, ...]] = (
    CheckSpec("unresolved_inbound", EDGE, UNCHECKED_REASON),
    CheckSpec("declaring_file", EDGE, UNCHECKED_REASON),
    CheckSpec("name_only", EDGE, NAME_ONLY_UNCHECKED_REASON),
    CheckSpec("unattributed", EDGE, UNATTRIBUTED_UNCHECKED_REASON),
    CheckSpec("evidence_base", EDGE, UNCHECKED_REASON),
    CheckSpec("freshness", REVIEW, UNKNOWN_REASON),
    CheckSpec("target_defined", REVIEW, TARGET_UNCHECKED_REASON),
    CheckSpec("unindexed_sources", REVIEW, UNINDEXED_UNCHECKED_REASON),
    CheckSpec("reference_freshness", REVIEW, UNKNOWN_REASON),
    CheckSpec("accessor", REVIEW, ACCESSOR_UNCHECKED_REASON),
    CheckSpec("non_call_references", REVIEW, NON_CALL_UNCHECKED_REASON),
    CheckSpec("registering_decorator", REVIEW, DECORATED_REASON),
)
CHECK_NAMES: Final = frozenset(spec.name for spec in REQUIRED_CHECKS)

#: 调用边层的“受门控”主因：有调用方时为 incomplete，否则 unknown。
_GATED = (UNRESOLVED_INBOUND_REASON, DECLARING_FILE_REASON, NAME_ONLY_REASON)


@dataclass(frozen=True)
class Ledger:
    """一次查询的检查记录（不可变；:meth:`record` 返回新的记录）。"""

    scope: Scope
    outcomes: Mapping[str, CheckOutcome] = MappingProxyType({})

    def record(self, name: str, outcome: CheckOutcome) -> Ledger:
        if name not in CHECK_NAMES:
            raise ValueError(f"unknown callers check {name!r}")
        return Ledger(self.scope, MappingProxyType({**self.outcomes, name: outcome}))

    def record_all(self, outcomes: Iterable[tuple[str, CheckOutcome]]) -> Ledger:
        ledger = self
        for name, outcome in outcomes:
            ledger = ledger.record(name, outcome)
        return ledger

    def outcome(self, spec: CheckSpec) -> CheckOutcome:
        """该检查的结果；漏记或范围不符时为 ``NotChecked``（失败即关闭）。"""
        found = self.outcomes.get(spec.name)
        if isinstance(found, Checked) and found.scope == self.scope:
            return found
        if isinstance(found, NotChecked):
            return found
        return NotChecked(spec.unchecked_reason)


@dataclass(frozen=True)
class Proof:
    """由检查记录推导出的 completeness、原因码与紧凑的检查摘要。"""

    completeness: str
    reasons: tuple[str, ...]
    checks: dict[str, Any]

    @property
    def primary(self) -> str | None:
        return self.reasons[0] if self.reasons else None


def edge_outcome(
    scope: Scope, value: int | None, problem: str, unchecked: str
) -> CheckOutcome:
    """计数型调用边检查：``None`` 为未能运行，正数即问题成立。"""
    if value is None:
        return NotChecked(unchecked)
    return checked(scope, problem if value else None)


def prove_edges(ledger: Ledger, total_callers: int) -> Proof:
    """只看调用边层：通过时 completeness 为 ``complete``——这还不是最终答案。

    复核门是否运行取决于它；最终答案只由 :func:`prove` 给出。
    """
    edge_specs = _layer(EDGE)
    unchecked: list[str] = []
    problems: list[str] = []
    for spec in edge_specs:
        found = ledger.outcome(spec)
        if isinstance(found, NotChecked):
            if found.reason not in unchecked:
                unchecked.append(found.reason)
        else:
            problems.extend(code for code in found.problems if code not in problems)
    reasons = (*unchecked, *problems)
    summary = _summary(ledger, edge_specs)
    if unchecked:
        return Proof("unknown", reasons, summary)
    if not problems:
        return Proof("complete", (), summary)
    if problems[0] in _GATED:
        return Proof("incomplete" if total_callers else "unknown", reasons, summary)
    if problems[0] == UNATTRIBUTED_REASON:
        return Proof("incomplete", reasons, summary)
    return Proof("unknown", reasons, summary)


def prove(ledger: Ledger, total_callers: int) -> Proof:
    """``complete`` 的唯一构造处：每道必需检查都在目标集上通过才成立。"""
    edges = prove_edges(ledger, total_callers)
    edge_specs = _layer(EDGE)
    if edges.completeness != "complete":
        return Proof(edges.completeness, edges.reasons, _summary(ledger, edge_specs))
    downgraded = "incomplete" if total_callers else "unknown"
    reached = list(edge_specs)
    for spec in _layer(REVIEW):
        reached.append(spec)
        found = ledger.outcome(spec)
        if isinstance(found, NotChecked):
            return Proof(downgraded, (found.reason,), _summary(ledger, tuple(reached)))
        if found.problems:
            return Proof(downgraded, found.problems, _summary(ledger, tuple(reached)))
    return Proof("complete", (), _summary(ledger, REQUIRED_CHECKS))


def not_checked_hint(func_name: str, proof: Proof, *, listed: int = 0) -> str:
    """点名未能运行的必需检查（没有更具体的提示时使用）。"""
    missing = proof.checks.get("not_checked") or {}
    named = ", ".join(f"`{name}` ({reason})" for name, reason in missing.items())
    detail = f": {named}" if named else ""
    if listed:
        return (
            f"{listed} caller(s) are listed for {func_name!r}, but a required "
            f"check did not run{detail}, so the list may be incomplete."
        )
    return (
        f"No resolved caller for {func_name!r}, and a required check did not "
        f"run{detail}. Do not treat this as absence."
    )


def _layer(layer: str) -> tuple[CheckSpec, ...]:
    return tuple(spec for spec in REQUIRED_CHECKS if spec.layer == layer)


def _summary(ledger: Ledger, reached: tuple[CheckSpec, ...]) -> dict[str, Any]:
    """紧凑、有界（≤ 12 项）的检查摘要。

    ``{"required": 12, "checked": k}``，另有：

    * ``not_checked``：推导时考察到、却未能运行（或漏记）的检查及其原因码；
    * ``not_run``：复核门按序短路——先行的门已判定答案非 complete 时，其后的门
      不运行，这里只给出它们的个数。
    """
    not_checked: dict[str, str] = {}
    count = 0
    for spec in reached:
        found = ledger.outcome(spec)
        if isinstance(found, Checked):
            count += 1
        else:
            not_checked[spec.name] = found.reason
    summary: dict[str, Any] = {"required": len(REQUIRED_CHECKS), "checked": count}
    if not_checked:
        summary["not_checked"] = not_checked
    skipped = len(REQUIRED_CHECKS) - len(reached)
    if skipped:
        summary["not_run"] = skipped
    return summary


__all__ = [
    "CHECK_NAMES",
    "EDGE",
    "REQUIRED_CHECKS",
    "REVIEW",
    "CheckOutcome",
    "CheckSpec",
    "Checked",
    "Ledger",
    "NotChecked",
    "Proof",
    "Scope",
    "checked",
    "edge_outcome",
    "not_checked_hint",
    "prove",
    "prove_edges",
]
