"""Impact analysis analyzer."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import ImpactResult, SymbolInfo


def impact_analysis(
    symbols: list[SymbolInfo],
    caller_map: dict[str, set[str]],
    symbol_name: str,
) -> ImpactResult:
    """Analyze the impact of changing a symbol.

    Computes the transitive closure of all callers.
    """
    from tree_sitter_analyzer_v2.core.code_map.types import ImpactResult

    target = next((s for s in symbols if s.name == symbol_name), None)
    if not target:
        return ImpactResult(target=None)

    fqn_to_sym = {s.fqn: s for s in symbols}
    target_fqn = target.fqn

    affected: list[SymbolInfo] = []
    visited: set[str] = {target_fqn}
    initial = list(caller_map.get(target_fqn, set()))
    queue: deque[str] = deque(initial)
    max_depth = 0
    depth_map: dict[str, int] = dict.fromkeys(initial, 1)

    while queue:
        fqn = queue.popleft()
        if fqn in visited:
            continue
        visited.add(fqn)
        current_depth = depth_map.get(fqn, 1)
        max_depth = max(max_depth, current_depth)

        sym = fqn_to_sym.get(fqn)
        if sym:
            affected.append(sym)
            for parent_fqn in caller_map.get(fqn, set()):
                if parent_fqn not in visited:
                    queue.append(parent_fqn)
                    depth_map[parent_fqn] = current_depth + 1

    affected_files = sorted({s.file for s in affected})
    blast_radius = len(affected)

    if blast_radius >= 10 or len(affected_files) >= 5:
        risk_level = "high"
    elif blast_radius >= 3 or len(affected_files) >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    return ImpactResult(
        target=target,
        affected_symbols=affected,
        affected_files=affected_files,
        blast_radius=blast_radius,
        depth=max_depth,
        risk_level=risk_level,
    )
