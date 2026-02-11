"""
CodeMapResult — Complete project code map data and intelligence methods.

Extracted from __init__.py to follow SRP (Fowler P0 #1).
This module contains the core data class and all analysis delegation methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.code_map.types import (
    ArchitectureTestReport,
    CallFlowResult,
    ChangeRiskReport,
    CodeSection,
    CodeSmell,
    ContextResult,
    ImpactResult,
    InheritanceChain,
    ModuleInfo,
    RefactoringSuggestion,
    SymbolInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class CodeMapResult:
    """Complete project code map result."""

    project_dir: str
    modules: list[ModuleInfo] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    module_dependencies: list[tuple[str, str]] = field(default_factory=list)
    entry_points: list[SymbolInfo] = field(default_factory=list)
    dead_code: list[SymbolInfo] = field(default_factory=list)
    hot_spots: list[tuple[SymbolInfo, int]] = field(default_factory=list)
    scan_duration_ms: float = 0.0  # Observability: total scan wall-clock time

    @property
    def total_files(self) -> int:
        return len(self.modules)

    @property
    def total_symbols(self) -> int:
        return len(self.symbols)

    @property
    def total_classes(self) -> int:
        return sum(1 for s in self.symbols if s.kind == "class")

    @property
    def total_functions(self) -> int:
        return sum(1 for s in self.symbols if s.kind in ("function", "method"))

    @property
    def total_lines(self) -> int:
        return sum(m.lines for m in self.modules)

    def find_symbol(self, name: str) -> list[SymbolInfo]:
        """Find symbols by partial name match, ranked by relevance.

        Ranking order: exact match > prefix match > contains match.
        """
        name_lower = name.lower()
        exact: list[SymbolInfo] = []
        prefix: list[SymbolInfo] = []
        contains: list[SymbolInfo] = []

        for s in self.symbols:
            s_lower = s.name.lower()
            if s_lower == name_lower:
                exact.append(s)
            elif s_lower.startswith(name_lower):
                prefix.append(s)
            elif name_lower in s_lower:
                contains.append(s)

        return exact + prefix + contains

    def find_symbol_exact(self, name: str) -> SymbolInfo | None:
        """Find first symbol by exact name match."""
        for s in self.symbols:
            if s.name == name:
                return s
        return None

    def find_symbol_by_fqn(self, fqn: str) -> SymbolInfo | None:
        """Find a symbol by its fully-qualified name (file:name)."""
        for s in self.symbols:
            if s.fqn == fqn:
                return s
        return None

    def find_symbols_all(self, name: str) -> list[SymbolInfo]:
        """Find ALL symbols by exact name (returns every match, not just first)."""
        return [s for s in self.symbols if s.name == name]

    def to_toon(self) -> str:
        """Generate token-optimized TOON output for LLM consumption."""
        from tree_sitter_analyzer_v2.core.code_map.formatters import format_toon
        return format_toon(self)

    def to_mermaid(self, kind: str = "dependencies") -> str:
        """Generate Mermaid graph. Delegates to analyzers.mermaid."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.mermaid import to_mermaid as _mermaid
        return _mermaid(self.module_dependencies, self.symbols, kind)

    # ──────────────── Token Economics & Progressive Disclosure ────────────────

    _CHARS_PER_TOKEN = 4  # Conservative estimate

    def token_economics(self) -> dict[str, Any]:
        """Calculate token budget comparison."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.snapshot import token_economics as _token_eco
        return _token_eco(
            self.to_toon(), self.symbols, self.module_dependencies,
            self.dead_code, self.hot_spots, self.total_files,
        )

    def symbol_index(self) -> str:
        """Compact symbol index."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.snapshot import symbol_index as _sym_idx
        return _sym_idx(self.symbols, self.total_files)

    def project_snapshot(self) -> str:
        """One-shot project snapshot."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.snapshot import project_snapshot as _snapshot
        return _snapshot(
            self.project_dir, self.modules, self.symbols,
            self.module_dependencies, self.dead_code, self.hot_spots,
            self.entry_points, self.to_toon(),
            self.detect_code_smells, self.suggest_refactorings,
        )

    def audit_test_architecture(
        self, test_roots: list[str] | None = None
    ) -> ArchitectureTestReport:
        """Audit test architecture."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.test_audit import audit_test_architecture as _audit
        return _audit(self.project_dir, self.modules, self.symbols, self.hot_spots, test_roots)

    # ──────────────── Inheritance Intelligence ────────────────

    def trace_inheritance(self, class_name: str) -> InheritanceChain:
        """Trace inheritance chain."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.inheritance import trace_inheritance as _trace
        return _trace(self.symbols, class_name)

    def find_implementations(self, interface_name: str) -> list[SymbolInfo]:
        """Find all implementing/extending classes."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.inheritance import find_implementations as _find
        return _find(self.symbols, interface_name)

    # ──────────────── Analysis Delegates ────────────────

    def suggest_refactorings(self) -> list[RefactoringSuggestion]:
        """Generate refactoring suggestions."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.refactoring import suggest_refactorings as _suggest
        return _suggest(self.dead_code, self.hot_spots, self.modules, self.symbols)

    def detect_code_smells(self) -> list[CodeSmell]:
        """Detect code smells."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.smell import detect_code_smells as _detect
        return _detect(self.modules, self.symbols, self.module_dependencies)

    def assess_change_risk(self, changed_files: list[str]) -> ChangeRiskReport:
        """Predict change risk."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.risk import assess_change_risk as _assess
        return _assess(self.symbols, self.hot_spots, self.impact_analysis, changed_files)

    # ──────────────── Intelligence Methods ────────────────

    def trace_call_flow(
        self, function_name: str, *, max_depth: int = 1
    ) -> CallFlowResult:
        """Trace bidirectional call flow."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.call_flow import trace_call_flow as _trace
        caller_map, callee_map = self._get_call_index()
        return _trace(
            self.find_symbols_all(function_name),
            self.symbols,
            caller_map, callee_map,
            max_depth=max_depth,
        )

    def impact_analysis(self, symbol_name: str) -> ImpactResult:
        """Analyze change impact."""
        from tree_sitter_analyzer_v2.core.code_map.analyzers.impact import impact_analysis as _impact
        caller_map, _ = self._get_call_index()
        return _impact(self.symbols, caller_map, symbol_name)

    def gather_context(
        self, query: str, max_tokens: int = 4000, max_symbols: int = 20
    ) -> ContextResult:
        """Gather all code context related to a query for LLM consumption."""
        matched = self.find_symbol(query)
        if not matched:
            return ContextResult(query=query)

        matched = matched[:max_symbols]

        caller_map, callee_map = self._get_call_index()
        fqn_to_sym = {s.fqn: s for s in self.symbols}

        relevant_symbols: list[tuple[SymbolInfo, str]] = []
        seen_fqns: set[str] = set()

        for sym in matched:
            if sym.fqn not in seen_fqns:
                relevant_symbols.append((sym, "definition"))
                seen_fqns.add(sym.fqn)

            for caller_fqn in caller_map.get(sym.fqn, set()):
                if caller_fqn not in seen_fqns:
                    caller_sym = fqn_to_sym.get(caller_fqn)
                    if caller_sym:
                        relevant_symbols.append((caller_sym, "caller"))
                        seen_fqns.add(caller_fqn)

            for callee_fqn in callee_map.get(sym.fqn, set()):
                if callee_fqn not in seen_fqns:
                    callee_sym = fqn_to_sym.get(callee_fqn)
                    if callee_sym:
                        relevant_symbols.append((callee_sym, "callee"))
                        seen_fqns.add(callee_fqn)

        max_chars = max_tokens * 4
        total_chars = 0
        sections: list[CodeSection] = []

        relevant_files: set[str] = set()
        for sym, _ in relevant_symbols:
            relevant_files.add(sym.file)

        imported_files_added: set[str] = set()
        for sym, relevance in relevant_symbols:
            if relevance == "definition":
                continue
            if sym.file in imported_files_added:
                continue
            imported_files_added.add(sym.file)

            module = next((m for m in self.modules if m.path == sym.file), None)
            if module:
                import_items = _extract_import_sections(
                    module, {s.name for s in matched}
                )
                for import_line, line_num in import_items:
                    if total_chars + len(import_line) <= max_chars:
                        sections.append(CodeSection(
                            file_path=sym.file,
                            start_line=line_num,
                            end_line=line_num,
                            content=import_line,
                            relevance="import",
                        ))
                        total_chars += len(import_line)

        for sym, relevance in relevant_symbols:
            if total_chars >= max_chars:
                break

            content = _read_symbol_code(self.project_dir, sym)
            if not content:
                continue

            section_chars = len(content)
            if total_chars + section_chars > max_chars:
                remaining = max_chars - total_chars
                content = content[:remaining] + "\n... [truncated]"
                section_chars = len(content)

            sections.append(CodeSection(
                file_path=sym.file,
                start_line=sym.line_start,
                end_line=sym.line_end,
                content=content,
                relevance=relevance,
            ))
            total_chars += section_chars

        total_tokens = total_chars // 4

        return ContextResult(
            query=query,
            matched_symbols=matched,
            code_sections=sections,
            total_tokens=total_tokens,
        )

    # ──────────────── Internal Helpers ────────────────

    def _get_call_index(
        self,
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Get caller/callee maps, building and caching on first call.

        Uses functools-style manual caching via __dict__ since dataclass
        fields cannot use @functools.cached_property.
        """
        cache_key = "_call_index_cache"
        if cache_key not in self.__dict__:
            from tree_sitter_analyzer_v2.core.code_map.call_index import build_call_index
            caller_map, callee_map = build_call_index(
                self.modules, self.symbols, self.module_dependencies,
                project_dir=self.project_dir,
            )
            self.__dict__[cache_key] = (caller_map, callee_map)
        cached: tuple[dict[str, set[str]], dict[str, set[str]]] = self.__dict__[cache_key]
        return cached


# ──────────────── Module-level helpers ────────────────


def _extract_import_sections(
    module: ModuleInfo, target_names: set[str]
) -> list[tuple[str, int]]:
    """Extract import statements from a module that reference target names."""
    results: list[tuple[str, int]] = []
    for imp in module.imports:
        if not isinstance(imp, dict):
            continue
        imported_names = set(imp.get("names", []))
        if imported_names & target_names:
            mod_name = imp.get("module", "")
            names = ", ".join(sorted(imported_names & target_names))
            line_num = imp.get("line_start", imp.get("line", 1))
            if mod_name:
                results.append((f"from {mod_name} import {names}", line_num))
            else:
                results.append((f"import {names}", line_num))
    return results


def _read_symbol_code(project_dir: str, sym: SymbolInfo) -> str:
    """Read the actual source code for a symbol from disk."""
    try:
        project_path = Path(project_dir)
        file_path = project_path / sym.file
        if not file_path.exists():
            return ""
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        start = max(0, sym.line_start - 1)
        end = min(len(lines), sym.line_end)
        if end <= start:
            end = min(len(lines), start + 10)
        return "\n".join(lines[start:end])
    except Exception as e:
        logger.debug("Cannot read symbol code for %s: %s", sym.fqn, e)
        return ""
