"""
Call index builder — constructs caller/callee maps from parsed modules.

Extracted from CodeMapResult to follow SRP (Fowler P0 #1).
Uses FQN (fully-qualified names) as keys to prevent cross-file name collisions.

Also provides the shared `extract_call_sites` function used by both
`parallel.py` (thread-pool path) and `scanner.py` (single-thread path).

DIP: Resolves call extractors via CallExtractorRegistry instead of
directly importing from graph/ (Newman N-1 fix).
"""

from __future__ import annotations

import bisect
import logging
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo, SymbolInfo

logger = logging.getLogger(__name__)


# ──────────────── Shared call-site extraction ────────────────


def extract_call_sites(
    ast_node: Any,
    language: str,
    functions: list[dict[str, Any]],
    classes: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Extract function call sites from an AST node.

    This is the **single source of truth** for call-site extraction,
    used by both the parallel parsing path and the single-thread path.

    DIP: Uses CallExtractorRegistry to resolve extractors, keeping
    core/ independent of graph/ implementation.

    Returns:
        Mapping of caller function name -> list of callee names.
    """
    if not ast_node:
        return {}

    from tree_sitter_analyzer_v2.core.call_extractor_registry import get_call_extractor

    extractor = get_call_extractor(language)
    if not extractor:
        return {}

    all_calls = extractor.extract_calls(ast_node)

    # Build function/method line ranges sorted by start line for bisect lookup
    func_ranges: list[tuple[int, int, str]] = []  # (start, end, name)
    for func in functions:
        name = func.get("name", "")
        if name:
            func_ranges.append(
                (func.get("line_start", 0), func.get("line_end", 0), name)
            )
    for cls in classes:
        for method in cls.get("methods", []):
            name = method.get("name", "")
            if name:
                func_ranges.append(
                    (method.get("line_start", 0), method.get("line_end", 0), name)
                )

    # Sort by start line for O(log n) bisect lookup
    func_ranges.sort()
    starts = [r[0] for r in func_ranges]

    # Assign each call to its enclosing function via bisect (O(log n) per call)
    call_sites: dict[str, list[str]] = {}
    for call in all_calls:
        if call.get("type") not in ("simple", "method"):
            continue
        callee = call.get("name", "")
        call_line = call.get("line", 0)
        if not callee:
            continue
        # bisect_right finds the insertion point; the enclosing function
        # is the one whose start_line is <= call_line
        idx = bisect.bisect_right(starts, call_line) - 1
        if idx >= 0:
            ls, le, func_name = func_ranges[idx]
            if ls <= call_line <= le and func_name != callee:
                call_sites.setdefault(func_name, []).append(callee)

    return call_sites


def build_call_index(
    modules: list[ModuleInfo],
    symbols: list[SymbolInfo],
    module_dependencies: list[tuple[str, str]],
    project_dir: str = "",
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build caller/callee lookup maps using FQN keys.

    Uses pre-extracted call_sites from ModuleInfo (populated during parsing
    via Tree-sitter AST traversal). FQN keys prevent name collision across files.

    Falls back to regex-based scanning only for languages without AST
    extractor support.

    Args:
        modules: Parsed modules.
        symbols: All symbols.
        module_dependencies: Module dependency edges.
        project_dir: Project root directory (needed for regex fallback).

    Returns:
        Tuple of (caller_map, callee_map) where keys are FQNs.
    """
    # Build name-to-symbols lookup for FQN resolution
    sym_by_name: dict[str, list[SymbolInfo]] = {}
    for s in symbols:
        if s.kind in ("function", "method"):
            sym_by_name.setdefault(s.name, []).append(s)
    known_names = set(sym_by_name.keys())

    caller_map: dict[str, set[str]] = {}
    callee_map: dict[str, set[str]] = {}

    for module in modules:
        if module.call_sites:
            # AST-based: use pre-extracted call sites (accurate)
            for caller_name, callees in module.call_sites.items():
                caller_fqn = _name_to_fqn(caller_name, module.path, sym_by_name)
                if not caller_fqn:
                    continue
                for callee_name in callees:
                    if callee_name not in known_names or callee_name == caller_name:
                        continue
                    callee_fqn = _name_to_fqn(
                        callee_name, module.path, sym_by_name
                    )
                    if not callee_fqn:
                        continue
                    caller_map.setdefault(callee_fqn, set()).add(caller_fqn)
                    callee_map.setdefault(caller_fqn, set()).add(callee_fqn)
        elif project_dir:
            # Fallback: regex-based scanning for unsupported languages
            _build_call_index_regex(
                module, known_names, sym_by_name, caller_map, callee_map,
                project_dir=project_dir,
            )

    # Cross-file call resolution via import + AST call sites
    _build_cross_file_calls(
        modules, module_dependencies, caller_map, callee_map, known_names, sym_by_name
    )

    return caller_map, callee_map


def _name_to_fqn(
    name: str,
    preferred_module: str,
    sym_by_name: dict[str, list[SymbolInfo]],
) -> str | None:
    """Resolve a simple name to FQN, preferring symbols in preferred_module."""
    candidates = sym_by_name.get(name, [])
    for c in candidates:
        if c.file == preferred_module:
            return c.fqn
    return candidates[0].fqn if candidates else None


def _build_call_index_regex(
    module: ModuleInfo,
    known_names: set[str],
    sym_by_name: dict[str, list[SymbolInfo]],
    caller_map: dict[str, set[str]],
    callee_map: dict[str, set[str]],
    *,
    project_dir: str,
) -> None:
    """Fallback regex-based call scanning for languages without AST extractor.

    Args:
        project_dir: Project root directory to resolve relative paths.
    """
    try:
        full_path = Path(project_dir) / module.path
        if not full_path.exists():
            logger.debug("Skipping regex scan — file not found: %s", full_path)
            return
        content = full_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
    except Exception as e:
        logger.warning("Regex scan failed for %s: %s", module.path, e)
        return

    def _extract_body(line_start: int, line_end: int) -> str:
        start = max(0, line_start - 1)
        end = min(len(lines), line_end)
        return "\n".join(lines[start:end])

    # Pre-compile a single combined regex for all known names (O(1) per match)
    if not known_names:
        return
    combined_pattern = re.compile(
        r'\b(' + '|'.join(re.escape(n) for n in known_names) + r')\s*\('
    )

    def _scan(caller_name: str, body: str) -> None:
        if not body:
            return
        caller_fqn = _name_to_fqn(caller_name, module.path, sym_by_name)
        if not caller_fqn:
            return
        for match in combined_pattern.finditer(body):
            target = match.group(1)
            if target != caller_name:
                callee_fqn = _name_to_fqn(target, module.path, sym_by_name)
                if callee_fqn:
                    caller_map.setdefault(callee_fqn, set()).add(caller_fqn)
                    callee_map.setdefault(caller_fqn, set()).add(callee_fqn)

    for func in module.functions:
        name = func.get("name", "")
        if name:
            _scan(name, _extract_body(func.get("line_start", 0), func.get("line_end", 0)))
    for cls in module.classes:
        for method in cls.get("methods", []):
            name = method.get("name", "")
            if name:
                _scan(name, _extract_body(
                    method.get("line_start", 0), method.get("line_end", 0)
                ))


def _build_cross_file_calls(
    modules: list[ModuleInfo],
    module_dependencies: list[tuple[str, str]],
    caller_map: dict[str, set[str]],
    callee_map: dict[str, set[str]],
    known_names: set[str],
    sym_by_name: dict[str, list[SymbolInfo]],
) -> None:
    """Resolve cross-file calls using import info + AST call sites (FQN).

    Performance: Uses dict lookup for module resolution instead of O(n)
    linear scan per dependency edge (Torvalds T-1 fix).
    """
    # Pre-build path -> module lookup (O(1) per lookup vs O(n) per next())
    module_by_path: dict[str, ModuleInfo] = {m.path: m for m in modules}

    for src_path, dst_path in module_dependencies:
        src_module = module_by_path.get(src_path)
        dst_module = module_by_path.get(dst_path)
        if not src_module or not dst_module:
            continue

        # Symbols defined in dst_module
        dst_symbols = {
            f.get("name", "") for f in dst_module.functions
        } | {
            c.get("name", "") for c in dst_module.classes
        }

        # Build reverse index: callee_name -> set of caller_names in src_module
        # This avoids re-iterating call_sites for every imported name
        callee_to_callers: dict[str, list[str]] = {}
        for caller_name, callees in src_module.call_sites.items():
            for callee_name in callees:
                callee_to_callers.setdefault(callee_name, []).append(caller_name)

        # Which imported names from dst are actually called in src?
        for imp in src_module.imports:
            if not isinstance(imp, dict):
                continue
            imported_names = set(imp.get("names", []))
            for iname in imported_names:
                if iname not in dst_symbols:
                    continue
                callee_fqn = _name_to_fqn(iname, dst_path, sym_by_name)
                if not callee_fqn:
                    continue
                for caller_name in callee_to_callers.get(iname, []):
                    caller_fqn = _name_to_fqn(
                        caller_name, src_path, sym_by_name
                    )
                    if caller_fqn:
                        caller_map.setdefault(callee_fqn, set()).add(caller_fqn)
                        callee_map.setdefault(caller_fqn, set()).add(callee_fqn)
