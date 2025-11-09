# Tasks: Redesign SQL Output Format

**Change ID:** `redesign-sql-output-format`

---

## Task List

### Phase 1: Analysis & Design

- [x] **Task 1.1**: Analyze current SQL output format issues
  - Identify inappropriate terminology (class, public, etc.)
  - Document missing SQL elements (procedures, functions, triggers, indexes)
  - Review current formatter architecture
  - **Dependencies**: None
  - **Estimated Time**: 1 hour

- [x] **Task 1.2**: Design SQL-specific output format
  - Create comprehensive format specification
  - Define terminology mapping (table, view, procedure, function, trigger, index)
  - Design full, compact, and CSV format layouts
  - **Dependencies**: Task 1.1
  - **Estimated Time**: 2 hours

---

### Phase 2: Core Implementation

- [x] **Task 2.1**: Create SQL-specific element models
  - Extend base element models with SQL-specific metadata
  - Add column information, constraints, dependencies
  - Implement SQL element type hierarchy
  - **File**: `tree_sitter_analyzer/models.py`
  - **Dependencies**: Task 1.2
  - **Estimated Time**: 3 hours
  - **Status**: ✅ COMPLETED

- [x] **Task 2.2**: Enhance SQL element extraction
  - Extract column information from CREATE TABLE statements
  - Extract parameter information from procedures/functions
  - Extract dependency information (foreign keys, references)
  - Extract constraint information (primary keys, unique, etc.)
  - **File**: `tree_sitter_analyzer/languages/sql_plugin.py`
  - **Dependencies**: Task 2.1
  - **Estimated Time**: 4 hours
  - **Status**: ✅ COMPLETED

- [x] **Task 2.3**: Create SQL-specific formatters
  - Implement `SQLFullFormatter` class
  - Implement `SQLCompactFormatter` class
  - Implement `SQLCSVFormatter` class
  - **File**: `tree_sitter_analyzer/formatters/sql_formatters.py`
  - **Dependencies**: Task 2.1, Task 2.2
  - **Estimated Time**: 4 hours
  - **Status**: ✅ COMPLETED

---

### Phase 3: Integration

- [x] **Task 3.1**: Integrate SQL formatters with output system
  - Modify CLI output logic to use SQL-specific formatters
  - Update MCP tools to use SQL-specific formatters
  - Ensure format selection works correctly for SQL files
  - **Files**: CLI and MCP tool files
  - **Dependencies**: Task 2.3
  - **Estimated Time**: 2 hours
  - **Status**: ✅ COMPLETED

- [x] **Task 3.2**: Update element extraction pipeline
  - Ensure all SQL elements are properly extracted
  - Fix missing procedures, functions, triggers, indexes
  - Validate extraction accuracy with sample_database.sql
  - **CRITICAL FIX**: Fixed line number calculation for SQL procedures and functions
    - `get_user_orders` procedure: corrected from 58-58 to 58-68
    - `calculate_order_total` function: corrected from 89-100 to 89-101
    - Implemented regex-based line number calculation as primary method
    - Added fallback to tree-sitter parsing for robustness
  - **File**: `tree_sitter_analyzer/languages/sql_plugin.py`
  - **Dependencies**: Task 2.2
  - **Estimated Time**: 3 hours
  - **Status**: ✅ COMPLETED

---

### Phase 4: Testing

- [x] **Task 4.1**: Create comprehensive SQL format tests
  - Test full format output with sample_database.sql
  - Test compact format output
  - Test CSV format output
  - Test edge cases (empty files, syntax errors)
  - **File**: `tests/test_sql_formatters.py`
  - **Dependencies**: Task 3.1, Task 3.2
  - **Estimated Time**: 3 hours

- [x] **Task 4.2**: Update existing SQL tests
  - Update `tests/test_languages/test_sql_plugin.py`
  - Add tests for enhanced element extraction
  - Add tests for SQL-specific metadata
  - **File**: `tests/test_languages/test_sql_plugin.py`
  - **Dependencies**: Task 3.2
  - **Estimated Time**: 2 hours

- [x] **Task 4.3**: Update golden master files
  - Regenerate SQL golden masters with new format
  - Verify output quality and accuracy
  - Update format testing strategy if needed
  - **Files**: `tests/golden_masters/*/sql_*`
  - **Dependencies**: Task 4.1, Task 4.2
  - **Estimated Time**: 1 hour

---

### Phase 5: Quality Assurance

- [x] **Task 5.1**: Run comprehensive test suite
  - Execute all SQL-related tests
  - Verify no regressions in other language plugins
  - Check format consistency across all output types
  - **Dependencies**: Task 4.3
  - **Estimated Time**: 1 hour

- [x] **Task 5.2**: Code quality checks
  - Run mypy type checking
  - Run ruff linting and formatting
  - Ensure 100% test coverage for new code
  - **Dependencies**: Task 5.1
  - **Estimated Time**: 30 minutes

- [x] **Task 5.3**: Performance validation
  - Test with large SQL files
  - Verify no performance degradation
  - Check memory usage with complex schemas
  - **Dependencies**: Task 5.1
  - **Estimated Time**: 1 hour

---

### Phase 6: Documentation

- [x] **Task 6.1**: Update documentation
  - Update README.md with SQL format examples
  - Update CHANGELOG.md with format changes
  - Document new SQL-specific features
  - **Files**: `README.md`, `CHANGELOG.md`
  - **Dependencies**: Task 5.3
  - **Estimated Time**: 1 hour

- [x] **Task 6.2**: Create SQL format documentation
  - Document SQL-specific output format
  - Provide examples for each format type
  - Document SQL element types and metadata
  - **File**: `docs/sql-format-guide.md`
  - **Dependencies**: Task 6.1
  - **Estimated Time**: 2 hours

---

### Phase 6.5: SQL Query System Enhancement

- [x] **Task 6.5.1**: Design and implement SQL query library
  - Create comprehensive SQL Tree-sitter query definitions
  - Support all SQL elements (tables, views, procedures, functions, triggers, indexes)
  - Include advanced SQL features (CTEs, window functions, subqueries)
  - Include error handling for tree-sitter-sql ERROR nodes
  - **File**: `tree_sitter_analyzer/queries/sql.py`
  - **Dependencies**: Task 1.2
  - **Estimated Time**: 3 hours
  - **Status**: ✅ COMPLETED

- [x] **Task 6.5.2**: Create comprehensive SQL query tests
  - Test all SQL query definitions and functionality
  - Test integration with QueryService
  - Test compatibility with generic query interface
  - Validate query patterns with sample SQL files
  - **File**: `tests/test_queries_sql.py`
  - **Dependencies**: Task 6.5.1
  - **Estimated Time**: 2 hours
  - **Status**: ✅ COMPLETED

- [x] **Task 6.5.3**: Integrate SQL queries with query loader system
  - Add SQL to supported languages list
  - Update query loader to recognize SQL queries
  - Update documentation to include SQL support
  - Verify SQL query system works end-to-end
  - **Files**: `tree_sitter_analyzer/query_loader.py`, `tree_sitter_analyzer/queries/__init__.py`
  - **Dependencies**: Task 6.5.2
  - **Estimated Time**: 1 hour
  - **Status**: ✅ COMPLETED

---

### Phase 7: Final Validation

- [x] **Task 7.1**: End-to-end testing
  - Test CLI with various SQL files
  - Test MCP tools with SQL analysis
  - Verify format output in real-world scenarios
  - **Dependencies**: Task 6.2
  - **Estimated Time**: 2 hours
  - **Status**: ✅ COMPLETED

- [x] **Task 7.2**: User acceptance validation
  - Verify output meets professional database documentation standards
  - Ensure terminology is appropriate for SQL domain
  - Validate completeness of extracted information
  - **Dependencies**: Task 7.1
  - **Estimated Time**: 1 hour
  - **Status**: ✅ COMPLETED

---

### Phase 8: Final Validation and Completion

- [x] **Task 8.1**: Golden master test validation
  - All SQL golden master tests pass (16/16)
  - SQL compact format issues resolved
  - Enum members extraction issues resolved
  - **Status**: ✅ COMPLETED

- [x] **Task 8.2**: Test suite fixes
  - Fixed table format tool test failures
  - Resolved CSV format assertion issues
  - **Status**: ✅ COMPLETED

- [x] **Task 8.3**: OpenSpec change completion
  - All tasks completed successfully
  - SQL output format redesign fully implemented
  - Professional database terminology in use
  - **Status**: ✅ COMPLETED

---

## Dependencies

### External Dependencies
- Completion of `add-sql-language-support` change
- `tree-sitter-sql` package availability
- Existing formatter architecture

### Internal Dependencies
- SQL element extraction must be working correctly
- Base formatter classes must support extension
- Test infrastructure must support new format types

---

## Risk Assessment

- **Risk Level**: 🟡 MEDIUM

### Risks

1. **Format breaking changes**
   - **Risk**: Existing SQL output consumers may break
   - **Mitigation**: Comprehensive testing and clear documentation
   - **Impact**: Medium - affects SQL output only

2. **Performance impact**
   - **Risk**: Enhanced metadata extraction may slow down analysis
   - **Mitigation**: Performance testing and optimization
   - **Impact**: Low - SQL files are typically smaller

3. **Complexity of SQL metadata extraction**
   - **Risk**: Extracting columns, constraints, dependencies may be complex
   - **Mitigation**: Incremental implementation and thorough testing
   - **Impact**: Medium - may require multiple iterations

---

## Success Metrics

1. ✅ SQL files display database-appropriate terminology
2. ✅ All SQL elements (tables, views, procedures, functions, triggers, indexes) are shown
3. ✅ Meaningful metadata is extracted and displayed (columns, constraints, dependencies)
4. ✅ Output is professional and suitable for database documentation
5. ✅ All tests pass with updated golden masters
6. ✅ No performance degradation compared to current implementation
7. ✅ Format is consistent across full, compact, and CSV outputs

---

## Time Estimate

- **Total**: ~38 hours
- **Breakdown**:
  - Analysis & Design: 3 hours
  - Core Implementation: 11 hours
  - Integration: 5 hours
  - Testing: 6 hours
  - Quality Assurance: 2.5 hours
  - Documentation: 3 hours
  - SQL Query System Enhancement: 6 hours ✅ COMPLETED
  - Final Validation: 3 hours

---

## Notes

- Prioritize accuracy of element extraction over advanced metadata initially
- Consider SQL dialect differences (MySQL, PostgreSQL, SQLite) for future enhancements
- Maintain backward compatibility where possible
- Focus on professional database documentation standards
- Ensure format is suitable for both human reading and automated processing
