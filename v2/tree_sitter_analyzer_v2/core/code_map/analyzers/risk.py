"""Change risk assessment analyzer."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import (
        ChangeRiskReport,
        ImpactResult,
        SymbolInfo,
    )


def assess_change_risk(
    symbols: list[SymbolInfo],
    hot_spots: list[tuple[SymbolInfo, int]],
    impact_func: Callable[[str], ImpactResult],
    changed_files: list[str],
) -> ChangeRiskReport:
    """Predict the risk level of changing a set of files.

    Args:
        symbols: All symbols in the project.
        hot_spots: Most-referenced symbols.
        impact_func: Callable that takes a symbol name and returns ImpactResult.
        changed_files: List of changed file paths.
    """
    from tree_sitter_analyzer_v2.core.code_map.types import ChangeRiskReport

    changed_set = {f.replace("\\", "/") for f in changed_files}

    changed_symbols: list[SymbolInfo] = [
        s for s in symbols if s.file in changed_set
    ]

    if not changed_symbols:
        return ChangeRiskReport(
            risk_level="low",
            changed_files=list(changed_set),
            reasons=["No known symbols in changed files"],
        )

    affected_files: set[str] = set()
    affected_syms: set[str] = set()

    for sym in changed_symbols:
        impact = impact_func(sym.name)
        for imp_sym in impact.affected_symbols:
            affected_syms.add(imp_sym.name)
            affected_files.add(imp_sym.file)

    affected_files -= changed_set

    hot_spot_names = {s.name for s, _ in hot_spots[:20]}
    hot_changed = [s.name for s in changed_symbols if s.name in hot_spot_names]

    reasons: list[str] = []
    score = 0

    if len(affected_files) > 10:
        score += 3
        reasons.append(f"High blast radius: {len(affected_files)} affected files")
    elif len(affected_files) > 3:
        score += 2
        reasons.append(f"Moderate blast radius: {len(affected_files)} affected files")
    elif len(affected_files) > 0:
        score += 1
        reasons.append(f"Low blast radius: {len(affected_files)} affected files")

    if hot_changed:
        score += 2
        reasons.append(f"Hot spots modified: {', '.join(hot_changed)}")

    if len(changed_symbols) > 20:
        score += 2
        reasons.append(f"Large change: {len(changed_symbols)} symbols modified")
    elif len(changed_symbols) > 5:
        score += 1
        reasons.append(f"Medium change: {len(changed_symbols)} symbols modified")

    if score >= 5:
        risk_level = "critical"
    elif score >= 3:
        risk_level = "high"
    elif score >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    return ChangeRiskReport(
        risk_level=risk_level,
        changed_files=list(changed_set),
        affected_files=sorted(affected_files),
        affected_symbols=sorted(affected_syms),
        reasons=reasons,
    )
