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
