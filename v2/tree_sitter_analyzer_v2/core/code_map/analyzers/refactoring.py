"""Refactoring suggestions analyzer.

Generates actionable refactoring suggestions from code analysis data.
Rules:
  - remove_dead_code: unreachable symbols (0 callers)
  - reduce_coupling: symbols with excessive callers/refs
  - split_module: oversized modules (lines or symbol count)
  - long_method: functions/methods exceeding line threshold
  - too_many_params: functions with excessive parameters
  - complex_method: functions that are both long AND have many params
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import (
        ModuleInfo,
        RefactoringSuggestion,
        SymbolInfo,
    )

# ── Thresholds (tunable constants) ──

_DEAD_CODE_LIMIT = 50
_HOT_SPOT_THRESHOLD = 8
_LARGE_MODULE_THRESHOLD = 500
_LARGE_MODULE_SYMBOLS = 20
_LONG_METHOD_THRESHOLD = 50       # lines
_TOO_MANY_PARAMS_THRESHOLD = 5    # parameter count
_COMPLEX_METHOD_LINES = 30        # lines (lower when combined with params)
_COMPLEX_METHOD_PARAMS = 3        # params (lower when combined with lines)


def _count_params(params_str: str) -> int:
    """Count parameters from a comma-separated string, ignoring empty."""
    if not params_str or not params_str.strip():
        return 0
    return len([p for p in params_str.split(",") if p.strip()])


def suggest_refactorings(
    dead_code: list[SymbolInfo],
    hot_spots: list[tuple[SymbolInfo, int]],
    modules: list[ModuleInfo],
    symbols: list[SymbolInfo],
) -> list[RefactoringSuggestion]:
    """Generate refactoring suggestions from code analysis."""
    from tree_sitter_analyzer_v2.core.code_map.types import RefactoringSuggestion

    suggestions: list[RefactoringSuggestion] = []

    # Rule 1: Dead code removal
    for sym in dead_code[:_DEAD_CODE_LIMIT]:
        suggestions.append(RefactoringSuggestion(
            kind="remove_dead_code",
            severity="info",
            message=f"{sym.kind} '{sym.name}' has 0 callers and can be removed",
            symbol_name=sym.name,
            file_path=sym.file,
            line=sym.line_start,
        ))

    # Rule 2: Excessive coupling
    for sym, ref_count in hot_spots:
        if ref_count >= _HOT_SPOT_THRESHOLD:
            suggestions.append(RefactoringSuggestion(
                kind="reduce_coupling",
                severity="warning",
                message=(
                    f"{sym.kind} '{sym.name}' has {ref_count} callers/refs "
                    f"- consider extracting an interface or splitting"
                ),
                symbol_name=sym.name,
                file_path=sym.file,
                line=sym.line_start,
                detail=f"refs={ref_count}",
            ))

    # Rule 3: Oversized modules
    symbols_per_file: dict[str, int] = {}
    for s in symbols:
        symbols_per_file[s.file] = symbols_per_file.get(s.file, 0) + 1

    for module in modules:
        sym_count = symbols_per_file.get(module.path, 0)
        if module.lines > _LARGE_MODULE_THRESHOLD or sym_count > _LARGE_MODULE_SYMBOLS:
            suggestions.append(RefactoringSuggestion(
                kind="split_module",
                severity="warning",
                message=(
                    f"Module '{module.path}' has {module.lines} lines and "
                    f"{sym_count} symbols - consider splitting"
                ),
                symbol_name=module.path,
                file_path=module.path,
                detail=f"lines={module.lines} symbols={sym_count}",
            ))

    # Rules 4-6: Function-level suggestions (long method, too many params, complexity)
    for sym in symbols:
        if sym.kind not in ("function", "method"):
            continue

        func_length = sym.line_end - sym.line_start
        param_count = _count_params(sym.params)

        # Rule 4: Long method → extract method
        if func_length > _LONG_METHOD_THRESHOLD:
            suggestions.append(RefactoringSuggestion(
                kind="long_method",
                severity="warning",
                message=(
                    f"{sym.kind} '{sym.name}' is {func_length} lines long "
                    f"- consider extracting smaller methods"
                ),
                symbol_name=sym.name,
                file_path=sym.file,
                line=sym.line_start,
                detail=f"lines={func_length}",
            ))

        # Rule 5: Too many parameters → introduce parameter object
        if param_count > _TOO_MANY_PARAMS_THRESHOLD:
            suggestions.append(RefactoringSuggestion(
                kind="too_many_params",
                severity="info",
                message=(
                    f"{sym.kind} '{sym.name}' has {param_count} parameters "
                    f"- consider introducing a parameter object or config"
                ),
                symbol_name=sym.name,
                file_path=sym.file,
                line=sym.line_start,
                detail=f"params={param_count}",
            ))

        # Rule 6: Complex method (long + many params combined)
        if (
            func_length > _COMPLEX_METHOD_LINES
            and param_count > _COMPLEX_METHOD_PARAMS
        ):
            suggestions.append(RefactoringSuggestion(
                kind="complex_method",
                severity="warning",
                message=(
                    f"{sym.kind} '{sym.name}' is {func_length} lines with "
                    f"{param_count} params - high complexity, simplify"
                ),
                symbol_name=sym.name,
                file_path=sym.file,
                line=sym.line_start,
                detail=f"lines={func_length} params={param_count}",
            ))

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    suggestions.sort(key=lambda s: severity_order.get(s.severity, 9))
    return suggestions
