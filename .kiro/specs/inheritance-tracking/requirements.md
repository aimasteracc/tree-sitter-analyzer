# Sprint 4: Class Inheritance Chain Tracking — Requirements

## Problem
LLMs frequently ask "where does this method come from?" and "which classes implement this interface?"
Currently, code_map.py does NOT track inheritance relationships despite parsers already extracting
`bases` (Python) and `implements` (TypeScript). Java parser lacks extends/implements extraction entirely.

## Goal
1. `SymbolInfo` for classes includes `bases: list[str]`
2. `CodeMapResult` provides `trace_inheritance(class_name) -> InheritanceChain`
3. `CodeMapResult` provides `find_implementations(interface_name) -> list[SymbolInfo]`
4. Java parser extracts `extends` and `implements`
5. MCP tool exposes "inheritance" and "implementations" actions

## Acceptance Criteria
- AC1: Python classes with base classes show them in SymbolInfo.bases
- AC2: `trace_inheritance("ChildClass")` returns full chain up to root
- AC3: `find_implementations("Interface")` returns all implementing classes
- AC4: Java `extends`/`implements` extracted by parser
- AC5: MCP `code_intelligence` tool supports "inheritance" action
- AC6: All existing tests pass (zero regression)
