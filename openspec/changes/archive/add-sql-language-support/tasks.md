# Tasks: Add SQL Language Support

**Change ID:** `add-sql-language-support`

---

## Task List

### Phase 1: Research & Preparation

- [x] **Task 1.1**: Verify tree-sitter-sql availability
  - Check PyPI for `tree-sitter-sql` package
  - Verify version compatibility with tree-sitter >=0.25.0
  - Test installation: `uv pip install tree-sitter-sql`
  - Document version requirements
  - **Dependencies**: None
  - **Estimated Time**: 30 minutes

- [x] **Task 1.2**: Analyze tree-sitter-sql grammar
  - Examine available node types
  - Test parsing sample SQL files
  - Document SQL AST structure
  - Identify element extraction patterns
  - **Dependencies**: Task 1.1
  - **Estimated Time**: 1 hour

- [x] **Task 1.3**: Review existing language plugin patterns
  - Study Python/Java plugin implementations
  - Identify common patterns to follow
  - Document SQL-specific considerations
  - **Dependencies**: None
  - **Estimated Time**: 30 minutes

---

### Phase 2: Dependency & Configuration

- [x] **Task 2.1**: Add tree-sitter-sql to pyproject.toml
  - Add to `[project.optional-dependencies]` as `sql` group
  - Add to `[project.optional-dependencies.all]`
  - Verify version constraints
  - **File**: `pyproject.toml`
  - **Dependencies**: Task 1.1
  - **Estimated Time**: 15 minutes

- [x] **Task 2.2**: Update language detector (if needed)
  - Verify `.sql` extension mapping
  - Ensure SQL is in supported languages list
  - **File**: `tree_sitter_analyzer/language_detector.py`
  - **Dependencies**: None
  - **Estimated Time**: 15 minutes

---

### Phase 3: Core Implementation

- [x] **Task 3.1**: Create SQL Element Extractor
  - Implement `SQLElementExtractor` class
  - Implement `extract_functions()` for procedures/functions/triggers
  - Implement `extract_classes()` for tables/views
  - Implement `extract_variables()` for indexes/constraints
  - Implement `extract_imports()` for schema references
  - Add helper methods for SQL-specific extraction
  - **File**: `tree_sitter_analyzer/languages/sql_plugin.py`
  - **Dependencies**: Task 1.2, Task 1.3
  - **Estimated Time**: 4 hours

- [x] **Task 3.2**: Create SQL Plugin Class
  - Implement `SQLPlugin` class extending `LanguagePlugin`
  - Implement `get_language_name()` → "sql"
  - Implement `get_file_extensions()` → [".sql"]
  - Implement `create_extractor()` → `SQLElementExtractor()`
  - Implement `get_tree_sitter_language()` → load tree-sitter-sql
  - Implement `analyze_file()` → standard analysis flow
  - Add error handling for missing tree-sitter-sql
  - **File**: `tree_sitter_analyzer/languages/sql_plugin.py`
  - **Dependencies**: Task 3.1
  - **Estimated Time**: 2 hours

- [x] **Task 3.3**: Create SQL Queries (Optional)
  - Define SQL-specific query patterns
  - Add queries for tables, procedures, functions, views
  - **File**: `tree_sitter_analyzer/queries/sql.py` (if needed)
  - **Dependencies**: Task 1.2
  - **Estimated Time**: 1 hour

---

### Phase 4: Testing

- [x] **Task 4.1**: Create unit tests for SQL plugin
  - Test plugin instantiation
  - Test language name and extensions
  - Test tree-sitter language loading
  - Test error handling (missing dependency)
  - **File**: `tests/test_languages/test_sql_plugin.py`
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 2 hours

- [x] **Task 4.2**: Create element extraction tests
  - Test table extraction
  - Test procedure extraction
  - Test function extraction
  - Test view extraction
  - Test index extraction
  - Test edge cases (empty files, invalid syntax)
  - **File**: `tests/test_languages/test_sql_plugin.py`
  - **Dependencies**: Task 3.1
  - **Estimated Time**: 3 hours

- [x] **Task 4.3**: Create integration tests
  - Test CLI integration (`analyze` command)
  - Test API integration (`analyze_file()`)
  - Test format output (Full, Compact, CSV)
  - Test MCP integration (if applicable)
  - **File**: `tests/test_languages/test_sql_plugin.py` or separate integration test file
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 2 hours

- [x] **Task 4.4**: Run full test suite
  - Execute: `pytest tests/test_languages/test_sql_plugin.py -v`
  - Verify all tests pass
  - Check test coverage (target: ≥80%)
  - **Dependencies**: Task 4.1, Task 4.2, Task 4.3
  - **Estimated Time**: 30 minutes

---

### Phase 5: Code Quality

- [x] **Task 5.1**: Run mypy type checking
  - Execute: `mypy tree_sitter_analyzer/languages/sql_plugin.py`
  - Fix all type errors
  - Ensure 100% mypy compliance
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 1 hour

- [x] **Task 5.2**: Run ruff linting
  - Execute: `ruff check tree_sitter_analyzer/languages/sql_plugin.py`
  - Fix all linting errors
  - Ensure 100% ruff compliance
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 30 minutes

- [x] **Task 5.3**: Run ruff formatting
  - Execute: `ruff format tree_sitter_analyzer/languages/sql_plugin.py`
  - Ensure code formatting compliance
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 15 minutes

- [x] **Task 5.4**: Verify no regressions
  - Run full test suite: `pytest tests/ -v`
  - Ensure all existing tests still pass
  - Check for any breaking changes
  - **Dependencies**: All previous tasks
  - **Estimated Time**: 30 minutes

---

### Phase 6: Documentation

- [x] **Task 6.1**: Update CHANGELOG.md
  - Add entry for SQL language support
  - Include version number
  - Describe new feature
  - **File**: `CHANGELOG.md`
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 15 minutes

- [x] **Task 6.2**: Update project documentation
  - Update `openspec/project.md` with SQL in supported languages
  - Update `README.md` with SQL support
  - Update language specifications if needed
  - **Files**: `openspec/project.md`, `README.md`
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 30 minutes

- [x] **Task 6.3**: Add code comments
  - Add docstrings to all public methods
  - Add inline comments for complex logic
  - Ensure comments are in English (project standard)
  - **File**: `tree_sitter_analyzer/languages/sql_plugin.py`
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 30 minutes

---

### Phase 7: Validation & Review

- [x] **Task 7.1**: Manual testing
  - Test with sample SQL files
  - Verify element extraction accuracy
  - Test all output formats
  - Test through CLI, API, MCP interfaces
  - **Dependencies**: All implementation tasks
  - **Estimated Time**: 1 hour

- [x] **Task 7.2**: Code review preparation
  - Create commit with descriptive message
  - Ensure all tests pass
  - Verify code quality checks pass
  - Prepare PR description
  - **Dependencies**: All previous tasks
  - **Estimated Time**: 30 minutes

- [x] **Task 7.3**: Final validation
  - Run complete test suite one final time
  - Verify no linting errors
  - Verify no type errors
  - Check test coverage meets target (≥80%)
  - **Dependencies**: All previous tasks
  - **Estimated Time**: 30 minutes

---

## Dependencies

### External Dependencies
- `tree-sitter-sql` package must be available on PyPI
- Compatible with `tree-sitter>=0.25.0`

### Internal Dependencies
- Existing plugin architecture (no changes needed)
- PluginManager auto-discovery mechanism
- Unified element model (Class, Function, Variable, Import)

---

## Risk Assessment

- **Risk Level**: 🟡 MEDIUM

### Risks

1. **tree-sitter-sql availability**
   - **Risk**: Package may not exist or be incompatible
   - **Mitigation**: Verify in Phase 1, Task 1.1
   - **Impact**: High - blocks implementation

2. **SQL grammar limitations**
   - **Risk**: tree-sitter-sql may not support all SQL dialects
   - **Mitigation**: Focus on standard SQL, document limitations
   - **Impact**: Medium - may limit feature completeness

3. **Element mapping complexity**
   - **Risk**: SQL concepts don't map cleanly to unified model
   - **Mitigation**: Follow design document mapping strategy
   - **Impact**: Low - design already addresses this

4. **Test coverage target**
   - **Risk**: May not reach ≥80% coverage
   - **Mitigation**: Comprehensive test suite in Phase 4
   - **Impact**: Low - can adjust target if needed

---

## Success Metrics

1. ✅ SQL plugin loads successfully via PluginManager
2. ✅ SQL files (`.sql`) are recognized and processed
3. ✅ SQL elements (tables, views, procedures, functions) are extracted correctly
4. ✅ SQL analysis works through CLI, API, and MCP interfaces
5. ✅ Format output (Full, Compact, CSV) works for SQL files
6. ✅ All tests pass (mypy, ruff, pytest)
7. ✅ Test coverage ≥80% for SQL plugin
8. ✅ No regression in existing language plugins

---

## Time Estimate

- **Total**: ~20 hours
- **Breakdown**:
  - Research & Preparation: 2 hours
  - Dependency & Configuration: 30 minutes
  - Core Implementation: 7 hours
  - Testing: 7.5 hours
  - Code Quality: 2 hours
  - Documentation: 1.25 hours
  - Validation & Review: 2 hours

---

## Notes

- Follow test-driven development (TDD) approach
- Write tests before implementation where possible
- Maintain consistency with existing plugin patterns
- Ensure all code comments are in English
- Use conservative approach for SQL dialect support (focus on standard SQL first)
- Consider future enhancements for dialect-specific features

