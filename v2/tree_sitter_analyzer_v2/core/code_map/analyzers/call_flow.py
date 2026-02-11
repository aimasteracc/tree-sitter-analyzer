"""Call flow tracing analyzer."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import CallFlowResult, SymbolInfo


def trace_call_flow(
    targets: list[SymbolInfo],
    all_symbols: list[SymbolInfo],
    caller_map: dict[str, set[str]],
    callee_map: dict[str, set[str]],
    *,
    max_depth: int = 1,
) -> CallFlowResult:
    """Trace bidirectional call flow for a function.

    Args:
        targets: Pre-resolved target symbols matching function_name
        all_symbols: All project symbols (for FQN lookup)
        caller_map: FQN -> set of caller FQNs
        callee_map: FQN -> set of callee FQNs
        max_depth: How many levels to expand
    """
    from tree_sitter_analyzer_v2.core.code_map.types import CallFlowResult

    if not targets:
        return CallFlowResult(target=None)

    fqn_to_sym = {s.fqn: s for s in all_symbols}
    target_fqns = {t.fqn for t in targets}

    callers: list[SymbolInfo] = []
    callees: list[SymbolInfo] = []
    seen_caller_fqns: set[str] = set()
    seen_callee_fqns: set[str] = set()

    for target in targets:
        target_fqn = target.fqn

        # Upstream callers (BFS with deque for O(1) popleft)
        visited: set[str] = set(target_fqns)
        queue: deque[tuple[str, int]] = deque(
            (fqn, 1) for fqn in caller_map.get(target_fqn, set())
        )
        while queue:
            fqn, depth = queue.popleft()
            if fqn in visited:
                continue
            visited.add(fqn)
            sym = fqn_to_sym.get(fqn)
            if sym and fqn not in seen_caller_fqns:
                callers.append(sym)
                seen_caller_fqns.add(fqn)
            if depth < max_depth:
                queue.extend(
                    (f, depth + 1)
                    for f in caller_map.get(fqn, set())
                    if f not in visited
                )

        # Downstream callees (BFS with deque for O(1) popleft)
        visited2: set[str] = set(target_fqns)
        queue2: deque[tuple[str, int]] = deque(
            (fqn, 1) for fqn in callee_map.get(target_fqn, set())
        )
        while queue2:
            fqn, depth = queue2.popleft()
            if fqn in visited2:
                continue
            visited2.add(fqn)
            sym = fqn_to_sym.get(fqn)
            if sym and fqn not in seen_callee_fqns:
                callees.append(sym)
                seen_callee_fqns.add(fqn)
            if depth < max_depth:
                queue2.extend(
                    (f, depth + 1)
                    for f in callee_map.get(fqn, set())
                    if f not in visited2
                )

    return CallFlowResult(target=targets[0], callers=callers, callees=callees)
