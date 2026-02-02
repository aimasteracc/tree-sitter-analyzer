# E3: Cross-File Call Resolution - Task Breakdown

**Enhancement**: E3 (Cross-File Call Resolution)
**Date**: 2026-02-01
**Estimated Duration**: 6+ hours
**Approach**: TDD (Test-Driven Development)

---

## 任务拆解 (Work Breakdown Structure)

### Phase 1: Import Resolution (2 hours)

#### T1.1: Import Data Structures
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Create**:
  - `v2/tree_sitter_analyzer_v2/graph/imports.py`
- **Objective**: Define `Import` and `ImportResolver` classes
- **Acceptance Criteria**:
  - `Import` dataclass with module, names, alias, type, level fields
  - `ImportResolver` class with __init__(project_root)
  - Type hints for all methods
  - Docstrings following existing codebase style
- **Tests**: None (data structures only)

---

#### T1.2: Import Parsing with Tree-sitter
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Create**:
  - `v2/tests/unit/test_import_resolver.py`
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/imports.py` (add parse_imports method)
- **Objective**: Extract import statements using tree-sitter queries
- **TDD Steps**:
  1. **RED**: Write test `test_parse_simple_import()`
     ```python
     # Test code: "import os"
     imports = resolver.parse_imports(test_file)
     assert len(imports) == 1
     assert imports[0].module == "os"
     assert imports[0].import_type == "absolute"
     ```
  2. **GREEN**: Implement `parse_imports()` to pass test
  3. **REFACTOR**: Clean up code
- **Acceptance Criteria**:
  - Parse `import x`
  - Parse `import x as y`
  - Parse `from x import y`
  - Parse `from x import y as z`
  - Parse `from . import x` (relative)
  - Parse `from .. import x` (parent relative)
  - 6 unit tests passing
  - 80%+ coverage for parse_imports

---

#### T1.3: Absolute Import Resolution
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/imports.py` (add _resolve_absolute)
  - `v2/tests/unit/test_import_resolver.py` (add tests)
- **Objective**: Resolve absolute imports to file paths
- **TDD Steps**:
  1. **RED**: Write test `test_resolve_absolute_module()`
     ```python
     # Project structure: utils/helper.py exists
     # Import: "from utils import helper"
     path = resolver._resolve_absolute(import_stmt)
     assert path == project_root / "utils/helper.py"
     ```
  2. **GREEN**: Implement resolution logic
  3. **REFACTOR**: Extract helper methods
- **Acceptance Criteria**:
  - Resolve `from package.module import func` → `package/module.py`
  - Resolve to `__init__.py` if module is package
  - Return None for external packages (not in project)
  - 4 unit tests passing
  - Edge case: non-existent module returns None

---

#### T1.4: Relative Import Resolution
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/imports.py` (add _resolve_relative)
  - `v2/tests/unit/test_import_resolver.py` (add tests)
- **Objective**: Resolve relative imports
- **TDD Steps**:
  1. **RED**: Write test `test_resolve_relative_sibling()`
     ```python
     # File: app/main.py
     # Import: "from . import helper"
     # Expected: app/helper.py
     path = resolver._resolve_relative(import_stmt, Path("app/main.py"))
     assert path == project_root / "app/helper.py"
     ```
  2. **GREEN**: Implement relative resolution
  3. **REFACTOR**: Handle edge cases
- **Acceptance Criteria**:
  - Resolve `from . import x` (sibling)
  - Resolve `from .. import x` (parent)
  - Resolve `from ...package import x` (grandparent)
  - 5 unit tests passing
  - Handle invalid levels gracefully (return None)

---

#### T1.5: Import Graph Construction
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/imports.py` (add build_import_graph)
  - `v2/tests/unit/test_import_resolver.py` (add tests)
- **Objective**: Build file-level import dependency graph
- **TDD Steps**:
  1. **RED**: Write test `test_build_import_graph_simple()`
     ```python
     # Files: main.py imports helper.py
     graph = resolver.build_import_graph([Path("main.py"), Path("helper.py")])
     assert graph.has_edge("main.py", "helper.py")
     assert graph["main.py"]["helper.py"]["type"] == "IMPORTS"
     ```
  2. **GREEN**: Implement build_import_graph
  3. **REFACTOR**: Optimize for larger file sets
- **Acceptance Criteria**:
  - Build graph with all import edges
  - Store imported_names in edge data
  - Store aliases in edge data
  - 3 unit tests passing
  - Handle circular imports (graph allows cycles)

---

### Phase 2: Symbol Table (1.5 hours)

#### T2.1: Symbol Table Data Structures
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Create**:
  - `v2/tree_sitter_analyzer_v2/graph/symbols.py`
- **Objective**: Define `SymbolEntry` and `SymbolTable` classes
- **Acceptance Criteria**:
  - `SymbolEntry` dataclass with node_id, file_path, name, type, lines
  - `SymbolTable` class with add, lookup, lookup_in_file methods
  - Type hints and docstrings
- **Tests**: None (data structures only)

---

#### T2.2: Symbol Table Construction
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Create**:
  - `v2/tests/unit/test_symbol_table.py`
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/symbols.py` (add SymbolTableBuilder)
- **Objective**: Build symbol table from file graphs
- **TDD Steps**:
  1. **RED**: Write test `test_build_symbol_table()`
     ```python
     # Input: file_graphs with functions
     table = builder.build(file_graphs)
     entry = table.lookup_in_file("helper", "utils/helper.py")
     assert entry is not None
     assert entry.name == "helper"
     ```
  2. **GREEN**: Implement build() method
  3. **REFACTOR**: Optimize data structures
- **Acceptance Criteria**:
  - Extract all FUNCTION and METHOD nodes
  - Store in SymbolTable
  - 4 unit tests passing
  - Handle duplicate names across files

---

#### T2.3: Symbol Lookup Methods
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/symbols.py`
  - `v2/tests/unit/test_symbol_table.py`
- **Objective**: Implement lookup methods with priority
- **TDD Steps**:
  1. **RED**: Write test `test_lookup_prioritizes_same_file()`
     ```python
     # "format" exists in both string.py and number.py
     results = table.lookup("format", context_file="string.py")
     assert len(results) == 1
     assert results[0].file_path == "string.py"
     ```
  2. **GREEN**: Implement prioritized lookup
  3. **REFACTOR**: Extract priority logic
- **Acceptance Criteria**:
  - `lookup()` returns all matches
  - `lookup()` with context prioritizes same-file
  - `lookup_in_file()` returns single match
  - 5 unit tests passing

---

### Phase 3: Cross-File Resolution (2 hours)

#### T3.1: CrossFileCallResolver Structure
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Create**:
  - `v2/tree_sitter_analyzer_v2/graph/cross_file.py`
- **Objective**: Define `CrossFileCallResolver` class
- **Acceptance Criteria**:
  - Class with __init__(import_graph, symbol_table)
  - Method stubs for resolve(), _resolve_call()
  - Type hints and docstrings
- **Tests**: None (structure only)

---

#### T3.2: Call Resolution Logic
- **Status**: ⏳ pending
- **Estimated Time**: 60 minutes
- **Files to Create**:
  - `v2/tests/unit/test_cross_file_resolver.py`
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/cross_file.py`
- **Objective**: Resolve function calls using import context
- **TDD Steps**:
  1. **RED**: Write test `test_resolve_same_file()`
     ```python
     # Call: main() calls helper() in same file
     target = resolver._resolve_call("helper", "app.py", "app.py:main")
     assert target == "app.py:helper"
     ```
  2. **GREEN**: Implement same-file resolution
  3. **RED**: Write test `test_resolve_imported()`
  4. **GREEN**: Implement import-based resolution
  5. **REFACTOR**: Extract priority logic
- **Acceptance Criteria**:
  - Resolve same-file calls (highest priority)
  - Resolve directly imported calls
  - Skip ambiguous calls (log warning)
  - 8 unit tests passing
  - Handle unresolved gracefully

---

#### T3.3: Graph Integration
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/cross_file.py` (add resolve method)
  - `v2/tests/unit/test_cross_file_resolver.py`
- **Objective**: Add cross-file CALLS edges to combined graph
- **TDD Steps**:
  1. **RED**: Write test `test_resolve_adds_cross_file_edges()`
     ```python
     combined = resolver.resolve(file_graphs)
     assert combined.has_edge("main.py:main", "utils/helper.py:helper")
     edge_data = combined["main.py:main"]["utils/helper.py:helper"]
     assert edge_data["cross_file"] is True
     ```
  2. **GREEN**: Implement resolve() method
  3. **REFACTOR**: Optimize graph operations
- **Acceptance Criteria**:
  - Combine all file graphs
  - Add cross-file CALLS edges
  - Mark with cross_file=True attribute
  - 4 unit tests passing
  - No duplicate edges

---

### Phase 4: CodeGraphBuilder Integration (1 hour)

#### T4.1: Add cross_file Parameter
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/builder.py`
- **Objective**: Add `cross_file` parameter to build_from_directory
- **Acceptance Criteria**:
  - Parameter with default False (backward compatible)
  - Docstring updated
  - Type hints correct
- **Tests**: Existing tests should still pass

---

#### T4.2: Implement _build_with_cross_file
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/builder.py`
  - `v2/tests/integration/test_cross_file_builder.py` (new file)
- **Objective**: Implement cross-file resolution path
- **TDD Steps**:
  1. **RED**: Write integration test `test_build_with_cross_file()`
     ```python
     # Test project with known cross-file calls
     graph = builder.build_from_directory("test_project", cross_file=True)
     assert graph.has_edge("main.py:main", "utils/helper.py:helper")
     ```
  2. **GREEN**: Implement _build_with_cross_file()
  3. **REFACTOR**: Extract helper methods
- **Acceptance Criteria**:
  - Calls ImportResolver, SymbolTableBuilder, CrossFileCallResolver
  - Returns combined graph
  - Logs unresolved warnings
  - 3 integration tests passing

---

### Phase 5: MCP Tools Update (30 minutes)

#### T5.1: Update analyze_code_graph Tool
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/mcp/tools/code_graph.py`
  - `v2/tests/integration/test_code_graph_tools.py`
- **Objective**: Add cross_file parameter to MCP tool
- **TDD Steps**:
  1. **RED**: Write test `test_analyze_with_cross_file()`
  2. **GREEN**: Update tool schema and execute method
  3. **REFACTOR**: Update response format
- **Acceptance Criteria**:
  - Schema includes cross_file boolean parameter
  - Passes parameter to builder
  - Returns cross_file_calls count in statistics
  - 2 integration tests passing

---

#### T5.2: Update Other Tools
- **Status**: ⏳ pending
- **Estimated Time**: 10 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/mcp/tools/code_graph.py` (FindFunctionCallersTool, QueryCallChainTool)
- **Objective**: Add cross_file to find_function_callers and query_call_chain
- **Acceptance Criteria**:
  - Both tools support cross_file parameter
  - Documentation updated

---

### Phase 6: Testing & Validation (1 hour)

#### T6.1: Create Test Fixture Project
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Create**:
  - `v2/tests/fixtures/cross_file_project/` (directory structure)
- **Objective**: Create realistic test project for E2E testing
- **Acceptance Criteria**:
  - Project with 5-10 Python files
  - Known cross-file calls documented
  - Absolute and relative imports
  - README explaining structure

---

#### T6.2: End-to-End Integration Tests
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Create**:
  - `v2/tests/integration/test_cross_file_e2e.py`
- **Objective**: Comprehensive E2E tests on test project
- **TDD Steps**:
  1. Write test for each cross-file call in fixture
  2. Test unresolved calls
  3. Test performance (<5s for fixture project)
- **Acceptance Criteria**:
  - 8 E2E tests passing
  - All expected edges present
  - No false positives

---

#### T6.3: Regression Testing
- **Status**: ⏳ pending
- **Estimated Time**: 10 minutes
- **Objective**: Ensure no breaking changes to E1, E2, E4
- **Acceptance Criteria**:
  - All existing 89 Code Graph tests pass
  - All 603 project tests pass
  - cross_file=False produces same results as before

---

### Phase 7: Documentation (30 minutes)

#### T7.1: Update User Documentation
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Modify**:
  - Update CODE_GRAPH_PROGRESS.md
  - Create E3_SUMMARY.md (similar to SESSION_16_E4_SUMMARY.md)
- **Objective**: Document E3 features for users
- **Acceptance Criteria**:
  - Usage examples
  - Parameter documentation
  - Performance characteristics

---

#### T7.2: API Documentation
- **Status**: ⏳ pending
- **Estimated Time**: 10 minutes
- **Files to Modify**:
  - Docstrings in imports.py, symbols.py, cross_file.py
- **Objective**: Ensure all public APIs documented
- **Acceptance Criteria**:
  - All public classes/methods have docstrings
  - Examples in docstrings
  - Type hints complete

---

## 依赖关系 (Dependencies)

```
T1.1 → T1.2 → T1.3, T1.4 → T1.5
                             ↓
T2.1 → T2.2 → T2.3 ──────────→ T3.1 → T3.2 → T3.3
                                                ↓
                                     T4.1 → T4.2 → T5.1 → T5.2
                                                            ↓
                                              T6.1 → T6.2 → T6.3 → T7.1, T7.2
```

**Critical Path**: T1.1 → T1.2 → T1.5 → T2.2 → T3.2 → T3.3 → T4.2 → T6.2

---

## 测试计划 (Testing Plan)

### Test Coverage Targets
- **Unit Tests**: 80%+ coverage for new modules
  - `imports.py`: 85% target
  - `symbols.py`: 85% target
  - `cross_file.py`: 80% target
- **Integration Tests**: All critical paths covered
- **Regression Tests**: 100% pass rate

### Test Categories
| Category | Count | Purpose |
|----------|-------|---------|
| **Unit - Import Resolution** | ~18 | Parse and resolve imports |
| **Unit - Symbol Table** | ~9 | Symbol table construction |
| **Unit - Call Resolution** | ~12 | Cross-file call logic |
| **Integration - Builder** | ~3 | CodeGraphBuilder integration |
| **Integration - MCP** | ~4 | MCP tool integration |
| **E2E - Test Project** | ~8 | End-to-end validation |
| **Regression** | 89 | Ensure no breaking changes |
| **Total New Tests** | **~54** | |

---

## 验收清单 (Acceptance Checklist)

### Functional Requirements
- [ ] Absolute imports resolved correctly
- [ ] Relative imports resolved correctly
- [ ] Symbol table built from file graphs
- [ ] Cross-file calls added to graph
- [ ] Ambiguous calls logged (not added)
- [ ] Unresolved calls logged
- [ ] cross_file parameter works in builder
- [ ] MCP tools support cross_file parameter

### Non-Functional Requirements
- [ ] Performance: <30s for 500 files
- [ ] Test coverage: 80%+ for new code
- [ ] No regressions: All existing tests pass
- [ ] Documentation: All public APIs documented
- [ ] Code quality: Passes mypy, ruff

### Testing Requirements
- [ ] ~54 new tests written (TDD)
- [ ] All new tests passing
- [ ] Integration tests pass
- [ ] E2E tests on fixture project pass
- [ ] Regression tests pass

---

## 时间估算总结 (Time Estimate Summary)

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1: Import Resolution | T1.1-T1.5 | 2h 30min |
| Phase 2: Symbol Table | T2.1-T2.3 | 1h 30min |
| Phase 3: Cross-File Resolution | T3.1-T3.3 | 2h |
| Phase 4: Builder Integration | T4.1-T4.2 | 1h |
| Phase 5: MCP Tools Update | T5.1-T5.2 | 30min |
| Phase 6: Testing & Validation | T6.1-T6.3 | 1h |
| Phase 7: Documentation | T7.1-T7.2 | 30min |
| **Total** | **21 tasks** | **~9 hours** |

**Note**: Original estimate was 6+ hours. With detailed breakdown, more realistic estimate is 8-10 hours.

---

## 下一步行动 (Next Actions)

**Ready to start implementation!**

1. ✅ Create E3_PROGRESS.md to track session-by-session progress
2. ✅ Start with T1.1 (Import Data Structures)
3. ✅ Follow TDD approach strictly (RED → GREEN → REFACTOR)
4. ✅ Update progress.md after each task completion

---

**Tasks Status**: ✅ READY FOR IMPLEMENTATION

**Recommended Starting Point**: T1.1 (Import Data Structures)
