# Test Coverage Analyzer

## Goal

"Find untested parts of the code"

Test Coverage Analyzer identifies code elements (functions, classes, methods) that lack test coverage by analyzing the source code structure and comparing it against test files. Uses AST-based analysis to provide gap detection without requiring pytest execution.

## MVP Scope

1. **Source Element Extraction**: Parse source files to extract all testable elements (functions, classes, methods)
2. **Test File Detection**: Identify test files by naming patterns (test_*.py, *_test.py, tests/ directory)
3. **Test Element Extraction**: Parse test files to extract which elements are being tested
4. **Gap Analysis**: Compare source vs tested elements to find untested code
5. **MCP Tool Integration**: Expose as `test_coverage` tool in analysis toolset

## Technical Approach

### Core Algorithm

```
1. Scan project for source files (.py, .js, .ts, .java, .go)
2. For each source file:
   - Extract all testable elements (function, class, method names)
   - Build source_elements set
3. Scan corresponding test files:
   - Extract test function names
   - Extract referenced symbols from test bodies
   - Build tested_elements set
4. Compute coverage gap:
   - untested = source_elements - tested_elements
   - coverage_percentage = |tested| / |source| * 100
```

### Module Structure

```
tree_sitter_analyzer/analysis/test_coverage.py
- SourceElement: dataclass (file_path, name, type, line)
- TestCoverageResult: dataclass (source_file, coverage_percent, untested_elements)
- TestCoverageAnalyzer (class)
  - analyze_file(file_path): TestCoverageResult
  - analyze_project(project_root): list[TestCoverageResult]
  - is_test_file(file_path): bool
  - extract_test_references(test_content): set[str]
```

### Dependencies

- Existing tree-sitter language parsers
- `glob` for file discovery
- `re` for test pattern matching

## Implementation Plan

### Sprint 1: Core Analysis Engine ✅ Target

- [x] Create `analysis/test_coverage.py` module
- [x] Implement `SourceElement` dataclass
- [x] Implement `extract_testable_elements(language, content)`
- [x] Implement `is_test_file(file_path)` helper
- [x] Implement basic gap analysis logic
- [x] Add unit tests (15+ tests)

### Sprint 2: Multi-Language Support ✅ Target

- [x] Python: function, class, method extraction
- [x] JavaScript/TypeScript: function, class, method extraction
- [x] Java: class, method extraction
- [x] Go: function, method, interface extraction
- [x] Add integration tests (10+ tests)

### Sprint 3: MCP Tool Integration ✅ Target

- [x] Create `mcp/tools/test_coverage_tool.py`
- [x] Register to ToolRegistry (analysis toolset)
- [x] Add schema: file_path, project_root, include_tested
- [x] Implement TOON format output
- [x] Add tool tests (10+ tests)

## Success Criteria

- [x] 35+ tests passing (15 + 10 + 10)
- [x] Detects untested functions in test projects
- [x] Supports Python, JavaScript, Java, Go
- [x] ruff check passes, mypy --strict passes
- [x] Tool registered and discoverable via tools/list
- [x] Total tools: 28 → 29

## Exit Criteria

- Sprint 1: Core engine + Python support (15+ tests)
- Sprint 2: Multi-language support (10+ tests)
- Sprint 3: MCP tool integration (10+ tests)
- Total: 35+ tests pass
- Documentation updated
