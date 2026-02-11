"""
ProjectCodeMap - One-shot project intelligence for LLMs.

Scans an entire project and produces a comprehensive, token-optimized map that gives
LLMs instant understanding of:
- All modules, classes, functions (global symbol index)
- Module dependency graph (who imports whom)
- Entry points (main functions, __main__ blocks)
- Dead code (unreachable symbols with 0 callers)
- Hot spots (most-connected symbols, highest impact)
- Call flow tracing (bidirectional call chain analysis)
- Impact analysis (change impact prediction)
- Context gathering for LLM (relevant code section extraction)
- Mermaid visualization of module dependencies

Usage:
    code_map = ProjectCodeMap()
    result = code_map.scan("/path/to/project", extensions=[".py"])
    print(result.to_toon())   # Token-optimized output for LLM
    print(result.to_mermaid()) # Visual module dependency graph
"""

from tree_sitter_analyzer_v2.core.code_map.result import CodeMapResult
from tree_sitter_analyzer_v2.core.code_map.scanner import ProjectCodeMap
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
    ParsedClass,
    ParsedFunction,
    ParsedImport,
    RefactoringSuggestion,
    SymbolInfo,
)

__all__ = [
    "SymbolInfo", "CodeSection", "CallFlowResult", "ImpactResult",
    "ContextResult", "ModuleInfo", "InheritanceChain", "RefactoringSuggestion",
    "ChangeRiskReport", "CodeSmell", "ArchitectureTestReport",
    "ParsedFunction", "ParsedClass", "ParsedImport",
    "CodeMapResult", "ProjectCodeMap",
]
