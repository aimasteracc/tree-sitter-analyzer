# E5: Java Code Graph Support - Task Breakdown

**Enhancement**: E5 (Java Code Graph Support)
**Date**: 2026-02-02
**Estimated Duration**: 8-12 hours
**Approach**: TDD (Test-Driven Development)

---

## 任务拆解 (Work Breakdown Structure)

### Phase 1: CallExtractor Infrastructure (2 hours)

#### T1.1: Create CallExtractor Protocol
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Create**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py`
- **Objective**: Define protocol for language-specific call extraction
- **Acceptance Criteria**:
  - `CallExtractor` protocol with `extract_calls()` and `get_call_node_types()` methods
  - Type hints for all methods
  - Docstrings with examples
- **Tests**: None (protocol definition only)

---

#### T1.2: Implement PythonCallExtractor
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Create**:
  - `v2/tests/unit/test_python_call_extractor.py`
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py` (add PythonCallExtractor class)
- **Objective**: Extract existing Python call logic into extractor class
- **TDD Steps**:
  1. **RED**: Write test `test_extract_simple_call()`
     ```python
     # Test code: "helper()"
     extractor = PythonCallExtractor()
     calls = extractor.extract_calls(ast_node)
     assert len(calls) == 1
     assert calls[0]['name'] == 'helper'
     assert calls[0]['type'] == 'simple'
     ```
  2. **GREEN**: Implement `PythonCallExtractor.extract_calls()`
  3. **REFACTOR**: Clean up code
- **Acceptance Criteria**:
  - Extract `func()` calls
  - Extract `obj.method()` calls
  - Extract `Module.function()` calls
  - Returns call info with name, line, type, qualifier
  - 6 unit tests passing
  - 80%+ coverage

---

#### T1.3: Refactor CodeGraphBuilder to Use Extractor
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/builder.py`
  - Existing tests should still pass
- **Objective**: Refactor builder to delegate to PythonCallExtractor
- **Acceptance Criteria**:
  - `__init__()` creates appropriate extractor based on language parameter
  - `_build_calls_edges()` uses `self.call_extractor.extract_calls()`
  - All existing 129 Code Graph tests still pass (zero regressions)
  - Python Code Graph behavior unchanged

---

### Phase 2: JavaCallExtractor (2.5 hours)

#### T2.1: JavaCallExtractor - Simple Method Calls
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Create**:
  - `v2/tests/unit/test_java_call_extractor.py`
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py` (add JavaCallExtractor)
- **Objective**: Extract simple Java method calls
- **TDD Steps**:
  1. **RED**: Write test `test_extract_simple_method_call()`
     ```python
     # Java code: "helper();"
     extractor = JavaCallExtractor()
     calls = extractor.extract_calls(ast_node)
     assert len(calls) == 1
     assert calls[0]['name'] == 'helper'
     assert calls[0]['type'] == 'simple'
     ```
  2. **GREEN**: Implement basic method_invocation parsing
  3. **REFACTOR**: Extract helper methods
- **Acceptance Criteria**:
  - Parse `method()` calls
  - Extract method name
  - Extract line number
  - 3 unit tests passing

---

#### T2.2: JavaCallExtractor - Instance Method Calls
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py`
  - `v2/tests/unit/test_java_call_extractor.py`
- **Objective**: Extract instance method calls (obj.method())
- **TDD Steps**:
  1. **RED**: Write test `test_extract_instance_method_call()`
     ```python
     # Java code: "user.getName();"
     calls = extractor.extract_calls(ast_node)
     assert calls[0]['name'] == 'getName'
     assert calls[0]['type'] == 'method'
     assert calls[0]['qualifier'] == 'user'
     ```
  2. **GREEN**: Parse field_access in method_invocation
  3. **REFACTOR**: Extract field_access parsing logic
- **Acceptance Criteria**:
  - Parse `obj.method()` calls
  - Extract qualifier (object name)
  - 4 unit tests passing

---

#### T2.3: JavaCallExtractor - Static Method Calls
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py`
  - `v2/tests/unit/test_java_call_extractor.py`
- **Objective**: Extract static method calls (Class.method())
- **TDD Steps**:
  1. **RED**: Write test `test_extract_static_method_call()`
     ```python
     # Java code: "Math.max(a, b);"
     calls = extractor.extract_calls(ast_node)
     assert calls[0]['name'] == 'max'
     assert calls[0]['qualifier'] == 'Math'
     ```
  2. **GREEN**: Distinguish static from instance calls (same syntax, different semantics)
  3. **REFACTOR**: Consolidate with instance call logic
- **Acceptance Criteria**:
  - Parse `Class.method()` calls
  - Extract class name as qualifier
  - 3 unit tests passing

---

#### T2.4: JavaCallExtractor - Constructor Calls
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py`
  - `v2/tests/unit/test_java_call_extractor.py`
- **Objective**: Extract constructor calls (new ClassName())
- **TDD Steps**:
  1. **RED**: Write test `test_extract_constructor_call()`
     ```python
     # Java code: "new User();"
     calls = extractor.extract_calls(ast_node)
     assert calls[0]['name'] == 'User'
     assert calls[0]['type'] == 'constructor'
     ```
  2. **GREEN**: Parse object_creation_expression nodes
  3. **REFACTOR**: Handle generic types (new List<String>())
- **Acceptance Criteria**:
  - Parse `new ClassName()` calls
  - Handle generics: `new List<String>()`
  - 4 unit tests passing

---

#### T2.5: JavaCallExtractor - Special Cases
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/extractors.py`
  - `v2/tests/unit/test_java_call_extractor.py`
- **Objective**: Handle super/this calls and edge cases
- **TDD Steps**:
  1. Test `super.method()` calls
  2. Test `this.method()` calls
  3. Test chained method calls: `obj.getUser().getName()`
- **Acceptance Criteria**:
  - Parse `super.method()` (type='super')
  - Parse `this.method()` (type='this')
  - Handle chained calls (extract all)
  - 5 unit tests passing

---

### Phase 3: Java Import Resolution (2 hours)

#### T3.1: JavaImport Data Structure
- **Status**: ⏳ pending
- **Estimated Time**: 15 minutes
- **Files to Create**:
  - `v2/tree_sitter_analyzer_v2/graph/java_imports.py`
- **Objective**: Define JavaImport dataclass
- **Acceptance Criteria**:
  - `JavaImport` dataclass with package, class_name, is_static, is_wildcard fields
  - Type hints
  - Docstrings
- **Tests**: None (data structure only)

---

#### T3.2: Parse Java Imports
- **Status**: ⏳ pending
- **Estimated Time**: 45 minutes
- **Files to Create**:
  - `v2/tests/unit/test_java_import_resolver.py`
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/java_imports.py` (add JavaImportResolver)
- **Objective**: Parse import statements from Java files
- **TDD Steps**:
  1. **RED**: Write test `test_parse_single_import()`
     ```python
     # Java code: "import com.example.User;"
     resolver = JavaImportResolver(project_root)
     imports = resolver.parse_imports(java_file)
     assert len(imports) == 1
     assert imports[0].package == "com.example"
     assert imports[0].class_name == "User"
     ```
  2. **GREEN**: Regex-based import parsing
  3. **REFACTOR**: Handle edge cases
- **Acceptance Criteria**:
  - Parse `import pkg.Class;`
  - Parse `import pkg.*;` (wildcard)
  - Parse `import static pkg.Class.method;`
  - 6 unit tests passing

---

#### T3.3: Build Package Index
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/java_imports.py`
  - `v2/tests/unit/test_java_import_resolver.py`
- **Objective**: Index all Java files by package
- **TDD Steps**:
  1. **RED**: Write test `test_build_package_index()`
     ```python
     # Project with src/main/java/com/example/User.java
     resolver = JavaImportResolver(project_root)
     resolver._build_package_index()
     assert "com.example" in resolver._package_to_files
     ```
  2. **GREEN**: Scan .java files and extract package declarations
  3. **REFACTOR**: Cache for performance
- **Acceptance Criteria**:
  - Scan all .java files in project
  - Extract package from each file
  - Build package → files mapping
  - 4 unit tests passing

---

#### T3.4: Resolve Imports to Files
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/java_imports.py`
  - `v2/tests/unit/test_java_import_resolver.py`
- **Objective**: Resolve imports to file paths
- **TDD Steps**:
  1. **RED**: Write test `test_resolve_single_import()`
     ```python
     # import com.example.User;
     files = resolver.resolve_import(java_import)
     assert len(files) == 1
     assert files[0].name == "User.java"
     ```
  2. **GREEN**: Lookup in package index
  3. **REFACTOR**: Handle wildcards
- **Acceptance Criteria**:
  - Resolve single class imports
  - Resolve wildcard imports (return all files in package)
  - Return empty list for external packages (java.*, javax.*)
  - 5 unit tests passing

---

### Phase 4: Java Graph Builder Integration (2 hours)

#### T4.1: Create JavaParser Integration
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/builder.py`
- **Objective**: Support `CodeGraphBuilder(language="java")`
- **Acceptance Criteria**:
  - `__init__` accepts language parameter
  - Creates JavaParser for language="java"
  - Creates JavaCallExtractor for language="java"
  - Raises ValueError for unsupported languages
  - 3 unit tests passing

---

#### T4.2: Implement Java Node Extraction
- **Status**: ⏳ pending
- **Estimated Time**: 45 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/builder.py`
  - `v2/tests/integration/test_java_code_graph.py` (new file)
- **Objective**: Extract Java classes and methods as graph nodes
- **TDD Steps**:
  1. **RED**: Write test `test_build_java_graph_from_file()`
     ```python
     builder = CodeGraphBuilder(language="java")
     graph = builder.build_from_file("Sample.java")
     assert graph.number_of_nodes() > 0
     ```
  2. **GREEN**: Adapt node extraction for Java result structure
  3. **REFACTOR**: Extract common logic
- **Acceptance Criteria**:
  - MODULE node created for Java file
  - CLASS nodes for classes
  - FUNCTION nodes for methods
  - CONTAINS edges: Module → Class → Method
  - 4 integration tests passing

---

#### T4.3: Build Java CALLS Edges (Intra-File)
- **Status**: ⏳ pending
- **Estimated Time**: 45 minutes
- **Files to Modify**:
  - Already refactored in T1.3 to use extractors
- **Objective**: Build CALLS edges for Java using JavaCallExtractor
- **TDD Steps**:
  1. **RED**: Write test `test_java_method_calls()`
     ```python
     # Java file with main() calling helper()
     graph = builder.build_from_file("App.java")
     calls_edges = [(u, v) for u, v, d in graph.edges(data=True) if d['type'] == 'CALLS']
     assert len(calls_edges) > 0
     ```
  2. **GREEN**: Calls extractor already integrated
  3. **REFACTOR**: Test coverage
- **Acceptance Criteria**:
  - Intra-file method calls tracked
  - CALLS edges created: caller → callee
  - 3 integration tests passing

---

### Phase 5: Java Cross-File Resolution (2.5 hours)

#### T5.1: Adapt Cross-File Infrastructure for Java
- **Status**: ⏳ pending
- **Estimated Time**: 60 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/builder.py` (_build_with_cross_file method)
  - `v2/tests/integration/test_java_cross_file.py` (new file)
- **Objective**: Support cross_file=True for Java
- **TDD Steps**:
  1. **RED**: Write test `test_java_cross_file_calls()`
     ```python
     # Project: App.java calls method in Helper.java
     builder = CodeGraphBuilder(language="java")
     graph = builder.build_from_directory("java_project", cross_file=True)
     cross_file_edges = [
         (u, v) for u, v, d in graph.edges(data=True)
         if d.get('cross_file') is True
     ]
     assert len(cross_file_edges) > 0
     ```
  2. **GREEN**: Use JavaImportResolver instead of ImportResolver
  3. **REFACTOR**: Parameterize import resolver by language
- **Acceptance Criteria**:
  - Uses JavaImportResolver for Java files
  - Resolves cross-file method calls
  - Marks edges with cross_file=True
  - 4 integration tests passing

---

#### T5.2: Java Symbol Table
- **Status**: ⏳ pending
- **Estimated Time**: 45 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/symbols.py` (adapt for Java)
- **Objective**: Support Java method names in symbol table
- **Acceptance Criteria**:
  - Symbol table stores Java methods
  - Keyed by (class_name, method_name) for Java
  - Lookup prioritizes same-package methods
  - 3 unit tests passing

---

#### T5.3: Java Cross-File Call Resolver
- **Status**: ⏳ pending
- **Estimated Time**: 45 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/graph/cross_file.py` (adapt for Java calls)
  - `v2/tests/integration/test_java_cross_file.py`
- **Objective**: Resolve Java method calls using import context
- **TDD Steps**:
  1. **RED**: Write test `test_resolve_imported_method()`
     ```python
     # App.java imports Helper, calls Helper.process()
     graph = resolver.resolve(file_graphs)
     assert graph.has_edge("App.java:main", "Helper.java:process")
     ```
  2. **GREEN**: Resolve using JavaImportResolver and SymbolTable
  3. **REFACTOR**: Handle ambiguous cases
- **Acceptance Criteria**:
  - Resolves calls to imported classes
  - Handles qualified calls (ClassName.method)
  - Conservative: skips ambiguous cases
  - 5 integration tests passing

---

### Phase 6: Test Fixtures & E2E Tests (1.5 hours)

#### T6.1: Create Java Test Fixture Project
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Create**:
  - `v2/tests/fixtures/java_project/src/main/java/com/example/App.java`
  - `v2/tests/fixtures/java_project/src/main/java/com/example/service/UserService.java`
  - `v2/tests/fixtures/java_project/src/main/java/com/example/repository/UserRepository.java`
  - `v2/tests/fixtures/java_project/README.md`
- **Objective**: Create realistic Java test project
- **Acceptance Criteria**:
  - 3-5 Java files with known call relationships
  - Documented expected graph structure
  - Includes package declarations and imports
  - Has cross-file method calls

---

#### T6.2: End-to-End Integration Tests
- **Status**: ⏳ pending
- **Estimated Time**: 40 minutes
- **Files to Create**:
  - `v2/tests/integration/test_java_e2e.py`
- **Objective**: Comprehensive E2E tests on Java fixture
- **TDD Steps**:
  1. Test graph construction from fixture
  2. Verify all expected nodes present
  3. Verify all expected edges present
  4. Test cross-file resolution
  5. Test performance (<5s for fixture)
- **Acceptance Criteria**:
  - 8 E2E tests passing
  - All expected nodes/edges verified
  - No false positives

---

#### T6.3: Regression Testing
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Objective**: Ensure no breaking changes
- **Acceptance Criteria**:
  - All 697 existing tests pass
  - All 129 Python Code Graph tests pass
  - No changes to Python graph output
  - CodeGraphBuilder(language="python") produces identical results

---

### Phase 7: MCP Integration (1 hour)

#### T7.1: Update MCP Tools for Java
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/mcp/tools/code_graph.py`
  - `v2/tests/integration/test_code_graph_tools.py`
- **Objective**: Auto-detect Java files and use Java builder
- **TDD Steps**:
  1. **RED**: Write test `test_analyze_java_file_via_mcp()`
     ```python
     result = tool.execute({"file_path": "App.java"})
     assert result["language"] == "java"
     assert result["statistics"]["total_methods"] > 0
     ```
  2. **GREEN**: Detect .java extension, use CodeGraphBuilder(language="java")
  3. **REFACTOR**: Extract language detection
- **Acceptance Criteria**:
  - `.java` files automatically use Java builder
  - `language` parameter in MCP tool schema
  - Statistics include Java-specific metrics
  - 3 integration tests passing

---

#### T7.2: Update Other MCP Tools
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Modify**:
  - `v2/tree_sitter_analyzer_v2/mcp/tools/code_graph.py` (all Code Graph tools)
- **Objective**: Support Java in all Code Graph MCP tools
- **Acceptance Criteria**:
  - `analyze_code_graph` supports Java
  - `find_function_callers` supports Java
  - `query_call_chain` supports Java
  - `visualize_code_graph` supports Java
  - Documentation updated

---

### Phase 8: Documentation (1 hour)

#### T8.1: Create User Documentation
- **Status**: ⏳ pending
- **Estimated Time**: 30 minutes
- **Files to Create**:
  - `v2/docs/JAVA_CODE_GRAPH.md`
- **Objective**: Document Java Code Graph usage
- **Acceptance Criteria**:
  - Usage examples
  - API reference
  - Limitations documented
  - Performance characteristics

---

#### T8.2: Update Progress Tracking
- **Status**: ⏳ pending
- **Estimated Time**: 20 minutes
- **Files to Modify**:
  - `.kiro/specs/v2-complete-rewrite/CODE_GRAPH_PROGRESS.md`
  - `.kiro/specs/v2-complete-rewrite/E5_JAVA_PROGRESS.md` (new)
- **Objective**: Document completion of E5
- **Acceptance Criteria**:
  - Summary of what was built
  - Test metrics
  - Performance results
  - Known limitations

---

#### T8.3: API Docstrings
- **Status**: ⏳ pending
- **Estimated Time**: 10 minutes
- **Objective**: Complete all docstrings
- **Acceptance Criteria**:
  - All public classes have docstrings
  - All public methods have docstrings with examples
  - Type hints complete

---

## 依赖关系 (Dependencies)

```
T1.1 → T1.2 → T1.3
               ↓
T2.1 → T2.2 → T2.3 → T2.4 → T2.5
                              ↓
T3.1 → T3.2 → T3.3 → T3.4 → T4.1 → T4.2 → T4.3
                                            ↓
                              T5.1 → T5.2 → T5.3
                                            ↓
                              T6.1 → T6.2 → T6.3
                                            ↓
                              T7.1 → T7.2
                                      ↓
                              T8.1 → T8.2 → T8.3
```

**Critical Path**: T1.1 → T1.2 → T1.3 → T2.1-T2.5 → T3.4 → T4.2 → T4.3 → T5.3 → T6.2

---

## 测试计划 (Testing Plan)

### Test Coverage Targets
- **Unit Tests**: 80%+ coverage for new modules
  - `extractors.py`: 85% target
  - `java_imports.py`: 85% target
- **Integration Tests**: All critical paths covered
- **Regression Tests**: 100% pass rate (all 697 tests)

### Test Categories
| Category | Count | Purpose |
|----------|-------|---------|
| **Unit - PythonCallExtractor** | ~6 | Verify Python call extraction refactor |
| **Unit - JavaCallExtractor** | ~19 | Parse Java method invocations |
| **Unit - JavaImportResolver** | ~15 | Parse and resolve Java imports |
| **Integration - Java Graph** | ~7 | Build graphs from Java files |
| **Integration - Java Cross-File** | ~9 | Cross-file call resolution |
| **Integration - MCP Tools** | ~3 | MCP integration for Java |
| **E2E - Java Project** | ~8 | End-to-end on fixture |
| **Regression** | 697 | Ensure no breaking changes |
| **Total New Tests** | **~67** | |

---

## 验收清单 (Acceptance Checklist)

### Functional Requirements
- [ ] `CallExtractor` protocol defined
- [ ] `PythonCallExtractor` extracts Python calls
- [ ] `JavaCallExtractor` extracts Java method invocations
- [ ] `JavaImportResolver` parses and resolves imports
- [ ] `CodeGraphBuilder(language="java")` works
- [ ] Can build graph from single Java file
- [ ] Can build graph from Java directory
- [ ] Cross-file call resolution works for Java
- [ ] MCP tools support Java files

### Non-Functional Requirements
- [ ] Performance: <30s for 100 Java files
- [ ] Test coverage: 80%+ for new code
- [ ] No regressions: All 697 tests pass
- [ ] Documentation: All APIs documented
- [ ] Code quality: Passes mypy, ruff

### Testing Requirements
- [ ] ~67 new tests written (TDD)
- [ ] All new tests passing
- [ ] Integration tests pass
- [ ] E2E tests on Java fixture pass
- [ ] Regression tests pass

---

## 时间估算总结 (Time Estimate Summary)

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1: CallExtractor Infrastructure | T1.1-T1.3 | 1h 30min |
| Phase 2: JavaCallExtractor | T2.1-T2.5 | 2h 30min |
| Phase 3: Java Import Resolution | T3.1-T3.4 | 2h 20min |
| Phase 4: Java Graph Builder Integration | T4.1-T4.3 | 2h |
| Phase 5: Java Cross-File Resolution | T5.1-T5.3 | 2h 30min |
| Phase 6: Test Fixtures & E2E | T6.1-T6.3 | 1h 30min |
| Phase 7: MCP Integration | T7.1-T7.2 | 1h |
| Phase 8: Documentation | T8.1-T8.3 | 1h |
| **Total** | **27 tasks** | **~14 hours** |

**Note**: Original estimate was 8-12 hours. Detailed breakdown suggests 12-14 hours is more realistic.

---

## 下一步行动 (Next Actions)

**Ready to start implementation!**

1. ✅ Create `E5_JAVA_PROGRESS.md` to track session progress
2. ✅ Start with T1.1 (CallExtractor Protocol)
3. ✅ Follow TDD approach strictly (RED → GREEN → REFACTOR)
4. ✅ Update progress after each task completion

---

**Tasks Status**: ✅ READY FOR IMPLEMENTATION

**Recommended Starting Point**: T1.1 (CallExtractor Protocol)
