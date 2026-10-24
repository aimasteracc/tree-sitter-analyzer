"""供 UQL 测试使用的内存版 :class:`~tree_sitter_analyzer.uql.backends.Backends`。

生产者载荷遵循 ``nav action=callers`` 的契约结构，使引擎对
``completeness`` / ``completeness_reasons`` / ``caller_count`` /
``callers_listed`` 的消费方式与生产环境完全一致地得到验证。
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.uql.backends import IndexState, Selection
from tree_sitter_analyzer.uql.coverage import COMPLETE_COVERAGE, Coverage


def callers_payload(
    *callers: tuple[str, str, int],
    completeness: str | None = "complete",
    reasons: tuple[str, ...] = (),
    caller_count: int | None = None,
) -> dict[str, Any]:
    entries = [{"name": n, "file": f, "line": line} for n, f, line in callers]
    payload: dict[str, Any] = {
        "success": True,
        "callers": entries,
        "caller_count": len(entries) if caller_count is None else caller_count,
        "callers_listed": len(entries),
        "completeness_reasons": list(reasons),
    }
    if completeness is not None:
        payload["completeness"] = completeness
    return payload


class FakeBackends:
    def __init__(
        self,
        symbols: dict[str, list[dict[str, Any]]] | None = None,
        callers: dict[str, dict[str, Any]] | None = None,
        callees: dict[str, dict[str, Any]] | None = None,
        *,
        gate: Coverage = COMPLETE_COVERAGE,
        state: str = "ready",
        generation: str | None = "gen-1",
        selection: list[dict[str, Any]] | None = None,
        counts: dict[str, int] | None = None,
    ) -> None:
        self.counts = counts or {}
        self.symbols = symbols or {}
        self.callers_map = callers or {}
        self.callees_map = callees or {}
        self.gate = gate
        self.state = state
        self.gen = generation
        self.selection = selection or []
        self.calls: list[tuple[str, str, str | None]] = []

    def index_state(self) -> IndexState:
        return IndexState(self.state, 10 if self.state == "ready" else 0)

    def select(self, selector: Any, cap: int) -> Selection:
        base = selector.selectors[0].base
        rows = self.symbols.get(base[1], []) if base[0] == "name" else self.selection
        return Selection(list(rows[:cap]), len(rows), len(rows) > cap)

    def definitions(
        self, name: str, *, cls: str | None, file: str | None
    ) -> list[dict[str, Any]]:
        return [
            s
            for s in self.symbols.get(name, [])
            if (not cls or s.get("class") == cls) and (not file or file in s["file"])
        ]

    def source_gate(self, files: list[str], languages: frozenset[str]) -> Coverage:
        return self.gate

    def definition_count(self, name: str) -> int | None:
        return self.counts.get(name, 1)

    async def callers(self, name: str, file: str | None) -> dict[str, Any]:
        self.calls.append(("callers", name, file))
        return self.callers_map.get(name, callers_payload())

    async def callees(self, name: str, file: str | None) -> dict[str, Any]:
        self.calls.append(("callees", name, file))
        return self.callees_map.get(name, {"success": True, "callees": []})

    def generation(self) -> str | None:
        return self.gen


def sym(
    name: str, file: str = "src/a.py", line: int = 1, **extra: Any
) -> dict[str, Any]:
    return {"name": name, "file": file, "line": line, "language": "python", **extra}
