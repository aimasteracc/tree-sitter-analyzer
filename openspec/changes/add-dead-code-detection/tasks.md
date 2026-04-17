# Dead Code Detection

## Goal

"Find code that exists but is never used"

Dead code (unused code) increases maintenance burden without adding value. This feature identifies functions, classes, and imports that are defined but never referenced in the codebase.

## MVP Scope

1. **Unused Function Detection**: Find functions/methods that are never called
2. **Unused Class Detection**: Find classes that are never instantiated or extended
3. **Unused Import Detection**: Find imports that are never referenced
4. **Public API Consideration**: Distinguish between internal dead code vs public API (which may be unused internally but used externally)
5. **MCP Tool Integration**: Expose as `dead_code` tool in analysis toolset

## Technical Approach

### Core Algorithm

```
1. Scan all files in project
2. Build symbol table: {symbol_name: [{file, line, type}]}
3. Build reference graph: {symbol_name: [referenced_locations]}
4. For each symbol:
   - Check if symbol_name appears in reference graph
   - Exclude: main/entry points, test files, exported symbols
   - Flag as "potentially dead" if no references found
```

### Module Structure

```
tree_sitter_analyzer/analysis/dead_code.py
- DeadCodeType: enum (UNUSED_FUNCTION, UNUSED_CLASS, UNUSED_IMPORT)
- DeadCodeIssue: dataclass (name, type, file, line, confidence)
- detect_dead_code(project_root): List[DeadCodeIssue]
- is_entry_point(symbol): bool (main, test, exported)
- is_public_api(symbol): bool (check __all__, exports)
```

### Dependencies

- `dependency_graph.py`: For tracking symbol references
- Existing element extractors: For finding definitions
- Tree-sitter queries: For finding references

## Implementation Plan

### Sprint 1: Core Detection Engine

- [ ] Create `analysis/dead_code.py` module
- [ ] Implement `DeadCodeIssue` dataclass
- [ ] Implement symbol extraction (functions, classes, imports)
- [ ] Implement reference counting
- [ ] Add basic exclusion logic (entry points, tests)
- [ ] Write unit tests (20+ tests)

### Sprint 2: Language-Specific Enhancements

- [ ] Python: `__all__` detection, `@abstractmethod` exclusion
- [ ] Java: `@Test` annotation exclusion, interface default methods
- [ ] JavaScript/TypeScript: `export` detection
- [ ] Add integration tests (10+ tests)

### Sprint 3: MCP Tool Integration

- [ ] Create `mcp/tools/dead_code_tool.py`
- [ ] Implement schema (file_pattern, exclude_tests, confidence_threshold)
- [ ] Register to ToolRegistry (analysis toolset)
- [ ] Add TOON format output
- [ ] Write tool tests (15+ tests)

## Success Criteria

- 45+ tests passing
- Detects unused functions in test projects
- Low false positive rate (<10%)
- ruff check passes, mypy --strict passes
- Integrated into MCP toolset (27 tools total)
