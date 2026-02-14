# Tasks: Code Intelligence Graph

**Change ID**: `add-code-intelligence-graph`

---

## Phase 1: Foundation — Call Graph Extraction

### Task 1.1: Add Python call queries
- **File**: `tree_sitter_analyzer/queries/python.py`
- **TDD**: Write `tests/unit/queries/test_python_call_queries.py` FIRST
- **Deliverable**: `call_expression` and `calls` queries

### Task 1.2: Intelligence data models
- **File**: `tree_sitter_analyzer/intelligence/models.py`
- **TDD**: Write `tests/unit/intelligence/test_models.py` FIRST
- **Deliverable**: CallSite, SymbolDefinition, SymbolReference, DependencyEdge, etc.

### Task 1.3: Python import resolver
- **File**: `tree_sitter_analyzer/intelligence/import_resolver.py`
- **TDD**: Write `tests/unit/intelligence/test_import_resolver.py` FIRST
- **Deliverable**: PythonImportResolver with relative/absolute/external resolution

### Task 1.4: Call graph builder
- **File**: `tree_sitter_analyzer/intelligence/call_graph.py`
- **TDD**: Write `tests/unit/intelligence/test_call_graph.py` FIRST
- **Deliverable**: CallGraphBuilder with file/directory analysis

### Task 1.5: Symbol index
- **File**: `tree_sitter_analyzer/intelligence/symbol_index.py`
- **TDD**: Write `tests/unit/intelligence/test_symbol_index.py` FIRST
- **Deliverable**: SymbolIndex with definition/reference lookup

---

## Phase 2: trace_symbol MCP Tool

### Task 2.1: trace_symbol tool implementation
- **File**: `tree_sitter_analyzer/mcp/tools/trace_symbol_tool.py`
- **TDD**: Write `tests/unit/mcp/test_tools/test_trace_symbol_tool.py` FIRST
- **Deliverable**: Working MCP tool with all trace types

### Task 2.2: Intelligence output formatters
- **File**: `tree_sitter_analyzer/intelligence/formatters.py`
- **TDD**: Covered by tool tests
- **Deliverable**: summary, tree, json formatters

### Task 2.3: Integration tests
- **File**: `tests/integration/mcp/test_trace_symbol_integration.py`
- **Deliverable**: End-to-end tests with real Python files

---

## Phase 3: assess_change_impact MCP Tool

### Task 3.1: Dependency graph builder
- **File**: `tree_sitter_analyzer/intelligence/dependency_graph.py`
- **TDD**: Write `tests/unit/intelligence/test_dependency_graph.py` FIRST

### Task 3.2: Impact analyzer
- **File**: `tree_sitter_analyzer/intelligence/impact_analyzer.py`
- **TDD**: Write `tests/unit/intelligence/test_impact_analyzer.py` FIRST

### Task 3.3: assess_change_impact tool
- **File**: `tree_sitter_analyzer/mcp/tools/assess_change_impact_tool.py`
- **TDD**: Write tool + integration tests FIRST

---

## Phase 4: check_architecture_health MCP Tool

### Task 4.1: Cycle detector (Tarjan)
- **File**: `tree_sitter_analyzer/intelligence/cycle_detector.py`
- **TDD**: Write `tests/unit/intelligence/test_cycle_detector.py` FIRST

### Task 4.2: Architecture metrics
- **File**: `tree_sitter_analyzer/intelligence/architecture_metrics.py`
- **TDD**: Write `tests/unit/intelligence/test_architecture_metrics.py` FIRST

### Task 4.3: check_architecture_health tool
- **File**: `tree_sitter_analyzer/mcp/tools/check_architecture_health_tool.py`
- **TDD**: Write tool + integration tests FIRST

---

## Phase 5: Integration & Registration

### Task 5.1: MCP server registration
- **File**: `tree_sitter_analyzer/mcp/server.py`
- **Deliverable**: Register 3 new tools

### Task 5.2: End-to-end tests
- **File**: `tests/integration/intelligence/test_code_intelligence_e2e.py`
- **Deliverable**: Full workflow tests with multi-file Python project

### Task 5.3: Documentation
- Update `docs/api/mcp_tools_specification.md`

---

## Phase 6: v2 Bug Fixes & Improvements (MCP Self-Analysis Driven)

> All tasks completed 2026-02-14. Bugs identified by running the three MCP tools against their own codebase.

### Task 6.1: ProjectIndexer — Lazy Project-Wide Indexer ✅
- **File**: `tree_sitter_analyzer/intelligence/project_indexer.py` (NEW)
- **Deliverable**: Central class that scans, parses, and populates SymbolIndex + CallGraphBuilder + DependencyGraphBuilder
- **TDD**: Integration tests in `test_code_intelligence_e2e.py`

### Task 6.2: C1 — ImpactAnalyzer File Path Target ✅
- **File**: `tree_sitter_analyzer/intelligence/impact_analyzer.py`
- **TDD**: `tests/unit/intelligence/test_impact_analyzer_file_target.py` (7 tests)
- **Deliverable**: `assess()` detects file path targets (contains `/` or `.py`) and finds importers + callers of defined symbols

### Task 6.3: C2 — Architecture Metrics Path Scoping ✅
- **File**: `tree_sitter_analyzer/intelligence/architecture_metrics.py`
- **TDD**: `tests/unit/intelligence/test_architecture_metrics_scoping.py` (6 tests)
- **Deliverable**: All `_detect_*` and `_compute_*` methods accept `scope` and filter results by path prefix

### Task 6.4: C3 — Abstractness Calculation ✅
- **File**: `tree_sitter_analyzer/intelligence/architecture_metrics.py`, `project_indexer.py`
- **TDD**: `tests/unit/intelligence/test_abstractness.py` (5 tests)
- **Deliverable**: `_compute_coupling()` computes abstractness from ABC/Protocol/abstractmethod in `modifiers`; `_extract_class_def()` detects abstract base classes

### Task 6.5: H1 — TYPE_CHECKING Awareness ✅
- **Files**: `models.py` (new field), `project_indexer.py` (detection), `architecture_metrics.py` (filtering)
- **TDD**: `tests/unit/intelligence/test_type_checking_awareness.py` (7 tests)
- **Deliverable**: `DependencyEdge.is_type_check_only`, `_walk_for_imports()` detects `if TYPE_CHECKING:` blocks, `_detect_cycles()` excludes type-check-only edges
- **Note**: `cycle_detector.py` NOT modified — filtering happens in `architecture_metrics` when building adjacency

### Task 6.6: H2 — Score Capping ✅
- **File**: `tree_sitter_analyzer/intelligence/architecture_metrics.py`
- **TDD**: `tests/unit/intelligence/test_architecture_metrics_scoping.py` (3 score tests)
- **Deliverable**: `_compute_score()` uses per-category caps (cycles: -25, violations: -20, god classes: -20, dead code: -20, D>0.7: -15)

### Task 6.7: H3 — Shared ProjectIndexer ✅
- **Files**: `server.py`, 3 tool files
- **Deliverable**: `_setup_shared_indexer()` creates one indexer, injects via `set_indexer()` into all 3 tools

### Task 6.8: M1 — Import Parsing Fixes ✅
- **File**: `tree_sitter_analyzer/intelligence/project_indexer.py`
- **Deliverable**: `wildcard_import` node handling, `is_type_check_only` context propagation
