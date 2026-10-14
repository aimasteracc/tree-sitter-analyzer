"""调用图中的“可能边”：无法区分的同名候选（#1559 / #1560）。

精确答案（nav callers / callees）只使用确定的边；而安全 / 影响类消费者
（死代码、爆炸半径、风险评分、change-impact 的上游计数）必须**过近似**：
一个只经由接收者未知的调用（``x.publish()``）到达的方法，不能因为模糊候选
被丢弃就显示 0 个调用方——那会把判定翻成 SAFE，属于最糟糕的假绿。

因此模糊候选不进入 ``_callers`` / ``_callees``，而是记录在这里，并通过
``reachable_*`` / ``possible_*`` 接口提供给安全类消费者，输出中以
``match: "name_only"`` 标记。
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .call_graph import FunctionRef

#: 仅凭同名匹配得到的调用方 / 被调用方在输出中的标记值。
NAME_ONLY_MATCH = "name_only"


class PossibleEdgesMixin:
    """为 :class:`CallGraph` 提供可能边的存储与查询。"""

    if TYPE_CHECKING:
        _callers: dict[FunctionRef, list[FunctionRef]]
        _callees: dict[FunctionRef, list[FunctionRef]]

        def build(self) -> None: ...

        def _resolve_targets(
            self, func_name: str, file_path: str | None = None
        ) -> list[FunctionRef]: ...

    def _init_possible_edges(self) -> None:
        self._possible_callees: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)
        self._possible_callers: dict[FunctionRef, list[FunctionRef]] = defaultdict(list)

    def _add_possible_edges(
        self, caller: FunctionRef, candidates: list[FunctionRef]
    ) -> None:
        """记录 ``caller`` 可能调用的模糊候选（双向）。"""
        if not candidates:
            return
        self._possible_callees[caller].extend(candidates)
        for candidate in candidates:
            self._possible_callers[candidate].append(caller)

    def reachable_callee_refs_of(self, func: FunctionRef) -> list[FunctionRef]:
        """确定的被调用方加上模糊候选；供死代码 / 爆炸半径过近似使用。"""
        self.build()
        return [*self._callees.get(func, []), *self._possible_callees.get(func, [])]

    def reachable_caller_refs_of(self, func: FunctionRef) -> list[FunctionRef]:
        """确定的调用方加上仅同名匹配的调用方；供影响 / 风险过近似使用。"""
        self.build()
        return [*self._callers.get(func, []), *self._possible_callers.get(func, [])]

    def possible_caller_refs_of(self, func: FunctionRef) -> list[FunctionRef]:
        """只经由同名匹配到达 ``func`` 的调用方（不含已确定的调用方）。"""
        self.build()
        certain = set(self._callers.get(func, []))
        seen: set[FunctionRef] = set()
        result: list[FunctionRef] = []
        for caller in self._possible_callers.get(func, []):
            if caller not in certain and caller not in seen:
                seen.add(caller)
                result.append(caller)
        return result

    def possible_callers_of(
        self, func_name: str, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """``callers_of`` 的过近似补集：仅同名匹配的调用方，带 ``match`` 标记。"""
        self.build()
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for target in self._resolve_targets(func_name, file_path):
            for caller in self.possible_caller_refs_of(target):
                key = caller.qualified_name()
                if key not in seen:
                    seen.add(key)
                    result.append({**caller.to_dict(), "match": NAME_ONLY_MATCH})
        return result
