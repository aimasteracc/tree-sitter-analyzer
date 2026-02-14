# Proposal: Add Code Intelligence Graph

**Change ID**: `add-code-intelligence-graph`
**Status**: Implemented (v4 — 2026-02-14)
**Priority**: High
**Author**: aisheng.yu
**Date**: 2026-02-13

---

## Problem Statement

Tree-sitter Analyzer currently extracts code elements (functions, classes, imports, variables) at the single-file level. While this provides useful structure information, AI coding assistants need deeper intelligence to understand codebases holistically:

1. **No call graph**: Cannot answer "who calls this function?" or "what does this function call?"
2. **No cross-file dependency resolution**: Import statements are extracted but not resolved to actual project files
3. **No impact analysis**: Cannot predict which code will be affected by a change
4. **No architecture metrics**: Cannot assess coupling, cohesion, circular dependencies, or layer violations

These gaps force AI assistants to read entire files sequentially, wasting tokens and losing context.

---

## Root Cause Analysis

The current architecture is optimized for **single-file analysis**. The `UnifiedAnalysisEngine` processes one file at a time, and the `PluginManager` dispatches to language-specific extractors that return `AnalysisResult` per file. There is no cross-file correlation layer.

Additionally, while tree-sitter grammars support `call_expression` nodes, the Python plugin does not extract function/method call sites — only definitions.

---

## Proposed Solution

Add a **Code Intelligence Graph** module (`tree_sitter_analyzer/intelligence/`) that builds on the existing analysis engine to provide:

1. **Call Graph Extraction**: Extract function/method call sites using new tree-sitter queries, build caller/callee relationships
2. **Symbol Index**: Project-wide index of all symbol definitions and references
3. **Import Resolution**: Resolve import statements to actual project files
4. **Dependency Graph**: File-level and module-level dependency graphs with cycle detection
5. **Impact Analysis**: Predict blast radius of code changes
6. **Architecture Metrics**: Coupling, instability, abstractness, layer violations, god class detection

Expose these through three new MCP tools:
- `trace_symbol`: Symbol tracing (definitions, usages, call chains, inheritance)
- `assess_change_impact`: Change impact analysis (blast radius, affected tests)
- `check_architecture_health`: Architecture health assessment (metrics, cycles, violations)

---

## Scope

### In Scope
- Python language support (first phase)
- Three new MCP tools
- New `intelligence/` module with clean separation from existing code
- Comprehensive test suite (unit, integration, property)

### Out of Scope
- Other language support (future phases)
- IDE plugin integration
- Web dashboard / visualization
- Git history-based temporal coupling (future enhancement)

---

## Impact Analysis

### Existing Code Changes (Minimal)
- `tree_sitter_analyzer/queries/python.py`: Add 2 new call-related queries
- `tree_sitter_analyzer/mcp/server.py`: Register 3 new tools
- No changes to core/, plugins/, languages/, formatters/

### New Code
- `tree_sitter_analyzer/intelligence/` module (9 new files)
- 3 new MCP tool files
- ~150 new test cases

### Risk Assessment
- **Low risk**: New module is additive, no changes to existing analysis pipeline
- **Medium risk**: Call graph accuracy depends on AST-level name matching (not semantic)
- **Mitigation**: Clear documentation of precision boundaries

---

## Success Criteria

1. All three MCP tools functional with Python codebases
2. >80% test coverage for new code
3. Call graph extraction working for simple/method/chained/cross-file calls
4. Cycle detection correctly identifies circular dependencies
5. Impact analysis correctly predicts direct and transitive impacts
6. Architecture metrics match manual calculation on test projects

---

## v2 Improvements (2026-02-14)

Based on self-analysis using the three MCP tools against their own codebase, the following bugs were identified and fixed:

### Critical Fixes
- **C1**: `assess_change_impact` now supports **file paths as targets** (not just symbol names)
- **C2**: `check_architecture_health` `path` parameter now correctly **scopes** all metrics to the specified directory
- **C3**: **Abstractness** metric now computed from ABC/Protocol/abstractmethod ratio (was always 0.0)

### High-Priority Fixes
- **H1**: `if TYPE_CHECKING:` imports are now marked as `is_type_check_only` and **excluded from cycle detection**
- **H2**: Architecture score uses **per-category caps** (cycles: -25, violations: -20, god classes: -20, dead code: -20, D>0.7: -15) to prevent score collapse to 0
- **H3**: Three intelligence tools now **share a single ProjectIndexer** instead of each creating their own

### Medium-Priority Fixes
- **M1**: Import parser now handles **wildcard imports** (`from X import *`) and properly passes `is_type_check_only` context

### New Components
- `ProjectIndexer`: Central class for lazy project-wide indexing (added in v1, enhanced in v2)
- 4 new test files, 28 new test cases — **123 total tests passing**

---

## v3 Improvements (2026-02-14)

Expert-verified analysis of MCP tool self-check results led to the following fixes and new features:

### Tool Bug Fixes
- **P0**: `_MAX_FILES` increased from 500 to 2000 with **two-phase discovery** (source files first, then tests). Fixes `mcp/` directory being excluded from indexing, which caused Ce=0 false reports.
- **P1**: Dead code detection now **excludes @property, @staticmethod, @classmethod** decorated methods (false positives due to attribute-access not generating call references).

### New Feature: Test Coverage Analysis (AH-012)
- New `"test_coverage"` check in `check_architecture_health`
- Detects **untested symbols** (public source methods with no test references)
- Detects **over-tested symbols** (referenced by >N distinct test functions)
- Detects **test-only symbols** (referenced only from test code, not business code)
- Reports **coverage_ratio** (proportion of public symbols with test coverage)

### Code Quality Fixes
- Circular dependency `html_formatter <-> formatter_registry` broken by extracting `IFormatter`/`IStructureFormatter` to new `interfaces.py` module
- Removed 9 confirmed dead code symbols: `FormatterSelector`, PHP/Ruby formatter subclasses, `ProjectIndexer.reset`

### Infrastructure
- `SymbolIndex.lookup_references` now supports **file_filter** callable parameter
- `ProjectIndexer.is_test_file()` static method for test file classification
- `ProjectIndexer.get_test_files()` / `get_source_files()` for file partitioning
- New data models: `TestCoverageReport`, `UntestedSymbol`, `OvertestedSymbol`
- 4 new test files, 30 new test cases — **143 total tests passing**

---

## v4 Improvements (2026-02-14)

Expert panel review of v3 test_coverage results identified tool false positives, dead code, and a real test gap:

### Tool Accuracy Fixes (AH-013, AH-014)
- **AH-013**: `test_coverage` now **excludes @property/@staticmethod/@classmethod** methods and **inner/nested functions** from untested list. Properties are accessed via attribute syntax; inner functions inherit coverage from their enclosing function.
- **AH-014**: Overtested counts now **scoped by (file_path, name)** instead of name-only. Prevents common method names like `execute`/`format` across different classes from being falsely aggregated as a single overtested entry.

### Dead Code Cleanup
- Removed `safe_execute_async` and `mcp_exception_handler` from `exceptions.py` (never called, superseded by `handle_mcp_errors`)
- Removed `TempFileList`, `contextlib` shim, and `write_files_to_temp` from `fd_rg_utils.py` (never invoked; `files_from` always None)
- Removed `CallGraphBuilder.index_file()` method (dead wrapper; `ProjectIndexer` calls `extract_calls_from_source` directly)

### New Test Coverage
- Added 5 async tests for `read_file_safe_async` in `test_encoding_utils.py` (was a real P1 gap: used by 3 language plugins but had zero direct tests)
- Added 9 new test cases for AH-013 and AH-014 scenarios

### Test Results
- 203 intelligence + encoding tests passing, 0 failures
- 9/9 self-check verification points passed
