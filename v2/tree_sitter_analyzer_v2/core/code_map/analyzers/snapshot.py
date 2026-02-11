"""Token economics, project snapshot, and symbol index."""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import (
        CodeSmell,
        ModuleInfo,
        RefactoringSuggestion,
        SymbolInfo,
    )

_CHARS_PER_TOKEN = 4


def token_economics(
    toon_output: str,
    symbols: list[SymbolInfo],
    module_dependencies: list[tuple[str, str]],
    dead_code: list[SymbolInfo],
    hot_spots: list[tuple[SymbolInfo, int]],
    total_files: int,
) -> dict[str, Any]:
    """Calculate token budget comparison: TOON vs JSON."""
    toon_tokens = len(toon_output) // _CHARS_PER_TOKEN

    json_data = {
        "files": total_files,
        "symbols": [
            {"name": s.name, "kind": s.kind, "file": s.file,
             "line_start": s.line_start, "line_end": s.line_end,
             "bases": s.bases}
            for s in symbols
        ],
        "dependencies": module_dependencies,
        "dead_code": [s.fqn for s in dead_code],
        "hot_spots": [(s.name, c) for s, c in hot_spots],
    }
    json_str = _json.dumps(json_data)
    json_tokens = len(json_str) // _CHARS_PER_TOKEN

    savings = json_tokens - toon_tokens
    savings_pct = round(savings / json_tokens * 100) if json_tokens > 0 else 0

    return {
        "total_symbols": len(symbols),
        "total_files": total_files,
        "toon_tokens": toon_tokens,
        "json_tokens": json_tokens,
        "savings": savings,
        "savings_percent": savings_pct,
    }


def symbol_index(symbols: list[SymbolInfo], total_files: int) -> str:
    """Compact symbol index for progressive disclosure."""
    lines: list[str] = [f"SYMBOL_INDEX ({len(symbols)} symbols, {total_files} files):"]
    for s in symbols:
        lines.append(f"  {s.kind[0].upper()} {s.name} {s.file}:L{s.line_start}")
    return "\n".join(lines)


def project_snapshot(
    project_dir: str,
    modules: list[ModuleInfo],
    symbols: list[SymbolInfo],
    module_dependencies: list[tuple[str, str]],
    dead_code: list[SymbolInfo],
    hot_spots: list[tuple[SymbolInfo, int]],
    entry_points: list[SymbolInfo],
    toon_output: str,
    detect_smells_func: Callable[[], list[CodeSmell]],
    suggest_refactorings_func: Callable[[], list[RefactoringSuggestion]],
) -> str:
    """One-shot project snapshot for AI consumption.

    Args:
        detect_smells_func: Callable returning list of CodeSmell.
        suggest_refactorings_func: Callable returning list of RefactoringSuggestion.
    """
    total_files = len(modules)
    total_symbols = len(symbols)
    total_classes = sum(1 for s in symbols if s.kind == "class")
    total_functions = sum(1 for s in symbols if s.kind in ("function", "method"))
    total_lines = sum(m.lines for m in modules)
    eco = token_economics(toon_output, symbols, module_dependencies, dead_code, hot_spots, total_files)
    smells = detect_smells_func()
    suggestions = suggest_refactorings_func()

    lines: list[str] = [
        f"PROJECT_SNAPSHOT: {project_dir.split('/')[-1] or project_dir}",
        f"  FILES: {total_files} | SYMBOLS: {total_symbols} "
        f"(classes={total_classes} funcs={total_functions})",
        f"  LINES: {total_lines}",
        f"  LANGUAGES: {', '.join(sorted({m.language for m in modules}))}",
        f"  TOKEN_BUDGET: TOON={eco['toon_tokens']} JSON={eco['json_tokens']} "
        f"savings={eco['savings_percent']}%",
    ]

    if hot_spots:
        top = hot_spots[:5]
        lines.append(f"  HOT_SPOTS ({len(hot_spots)} total, top 5):")
        for s, c in top:
            lines.append(f"    {s.name} refs={c} ({s.file})")

    if dead_code:
        lines.append(f"  DEAD_CODE: {len(dead_code)} unreferenced symbols")

    if smells:
        by_kind: dict[str, int] = {}
        for s in smells:
            by_kind[s.kind] = by_kind.get(s.kind, 0) + 1
        lines.append(f"  CODE_SMELLS ({len(smells)}): {', '.join(f'{k}={v}' for k, v in by_kind.items())}")

    if suggestions:
        lines.append(f"  REFACTORING_SUGGESTIONS: {len(suggestions)}")

    if module_dependencies:
        lines.append(f"  MODULE_DEPS: {len(module_dependencies)} edges")

    lines.append(f"  ENTRY_POINTS: {len(entry_points)}")

    return "\n".join(lines)
