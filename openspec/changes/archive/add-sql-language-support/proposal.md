# Proposal: Add SQL Language Support

**Change ID:** `add-sql-language-support`  
**Type:** Feature Addition  
**Status:** Draft  
**Created:** 2025-11-07  
**Author:** AI Assistant

---

## Problem Statement

Tree-sitter Analyzer currently supports 7 languages (Python, Java, JavaScript, TypeScript, HTML, CSS, Markdown) but lacks support for SQL, a critical language for database-related code analysis. SQL files are commonly found in enterprise codebases for:

- Database schema definitions (CREATE TABLE, ALTER TABLE)
- Stored procedures and functions
- Views and triggers
- Migration scripts
- Query files

The `language_detector.py` already recognizes `.sql` files but there is no corresponding plugin implementation to extract SQL elements like tables, views, procedures, functions, and queries.

### Current Behavior

- SQL files are detected by extension (`.sql`) but mapped to ambiguous language list: `["sql", "plsql", "mysql"]`
- No SQL plugin exists in `tree_sitter_analyzer/languages/`
- SQL files cannot be analyzed through the analyzer API
- MCP tools cannot process SQL files
- No SQL-specific element extraction (tables, views, procedures, etc.)

### Expected Behavior

After implementation:
- SQL files (`.sql`) are fully supported with dedicated plugin
- SQL elements are extracted: tables, views, stored procedures, functions, triggers, indexes
- SQL analysis works through all interfaces: CLI, API, MCP
- SQL-specific queries are available (e.g., `find_tables`, `find_procedures`)
- Format output (Full, Compact, CSV) works for SQL files

---

## Root Cause Analysis

### Missing Components

1. **No SQL Plugin**: `tree_sitter_analyzer/languages/sql_plugin.py` does not exist
2. **No SQL Extractor**: No `SQLElementExtractor` class to parse SQL AST
3. **No tree-sitter-sql Dependency**: `pyproject.toml` doesn't include `tree-sitter-sql`
4. **No SQL Queries**: `tree_sitter_analyzer/queries/` lacks SQL query definitions
5. **No SQL Tests**: Test suite has no SQL-specific test cases

### Architecture Alignment

The project uses a plugin-based architecture where:
- Each language has a `*_plugin.py` file in `languages/` directory
- Plugins implement `LanguagePlugin` interface
- Element extractors implement `ElementExtractor` interface
- Plugins are auto-discovered by `PluginManager`
- Tree-sitter languages are loaded via `get_tree_sitter_language()`

SQL support requires implementing this same pattern.

---

## Proposed Solution

Implement comprehensive SQL language support following the existing plugin architecture pattern, maintaining consistency with other language plugins.

### Key Components

1. **SQL Plugin** (`sql_plugin.py`)
   - Implements `LanguagePlugin` interface
   - Supports `.sql` file extension
   - Loads `tree-sitter-sql` language
   - Provides SQL-specific element extraction

2. **SQL Element Extractor** (`SQLElementExtractor`)
   - Extracts SQL tables (CREATE TABLE statements)
   - Extracts views (CREATE VIEW statements)
   - Extracts stored procedures (CREATE PROCEDURE)
   - Extracts functions (CREATE FUNCTION)
   - Extracts triggers (CREATE TRIGGER)
   - Extracts indexes (CREATE INDEX)
   - Maps SQL elements to unified element model (Class, Function, Variable, Import)

3. **SQL Queries** (`queries/sql.py`)
   - Query definitions for common SQL patterns
   - Table discovery queries
   - Procedure/function discovery queries
   - View discovery queries

4. **Dependencies**
   - Add `tree-sitter-sql` to `pyproject.toml`
   - Add SQL to optional dependencies group

5. **Tests**
   - Unit tests for SQL plugin
   - Integration tests for SQL analysis
   - Test SQL element extraction
   - Test format output for SQL

### Design Principles

- **Consistency**: Follow existing plugin patterns (Python, Java, JavaScript)
- **Type Safety**: Full mypy compliance with proper type hints
- **Code Quality**: Ruff compliance, no linting errors
- **Test Coverage**: >80% coverage for SQL plugin
- **Backward Compatibility**: No breaking changes to existing APIs

---

## Impact Analysis

### Affected Components

- ✅ `tree_sitter_analyzer/languages/sql_plugin.py` - New file
- ✅ `tree_sitter_analyzer/queries/sql.py` - New file (if needed)
- ✅ `pyproject.toml` - Add tree-sitter-sql dependency
- ✅ `tests/test_languages/test_sql_plugin.py` - New test file
- ❌ No breaking changes to existing code
- ❌ No API changes required

### User Impact

- **Positive**: Users can now analyze SQL files
- **Positive**: SQL elements are extractable through all interfaces
- **Positive**: MCP tools can process SQL files
- **No Breaking Changes**: Existing functionality remains unchanged

### Dependencies

- **External**: `tree-sitter-sql` Python package (must be available on PyPI)
- **Internal**: Existing plugin architecture (no changes needed)

---

## Success Criteria

1. ✅ SQL plugin loads successfully via PluginManager
2. ✅ SQL files (`.sql`) are recognized and processed
3. ✅ SQL elements (tables, views, procedures, functions) are extracted correctly
4. ✅ SQL analysis works through CLI, API, and MCP interfaces
5. ✅ Format output (Full, Compact, CSV) works for SQL files
6. ✅ All tests pass (mypy, ruff, pytest)
7. ✅ Test coverage ≥80% for SQL plugin
8. ✅ No regression in existing language plugins

---

## Related Issues

- Language detection already recognizes `.sql` but lacks plugin
- Similar pattern to existing language plugins (Python, Java, etc.)
- Follows established plugin architecture

---

## Alternatives Considered

### Alternative 1: Generic SQL Parser
Use a generic SQL parser library instead of tree-sitter-sql.

**Rejected**: 
- Inconsistent with project architecture (all languages use tree-sitter)
- Would require different integration approach
- Breaks consistency principle

### Alternative 2: Minimal SQL Support
Only support basic SQL statements without full element extraction.

**Rejected**:
- Doesn't meet user needs for comprehensive SQL analysis
- Inconsistent with other language plugins' feature completeness
- Would require future expansion anyway

### Alternative 3: External Plugin
Create SQL support as external plugin via entry points.

**Rejected**:
- Core language support should be built-in
- Better integration with existing codebase
- Easier maintenance and testing

---

## Dependencies

- **tree-sitter-sql**: Must be available on PyPI and compatible with tree-sitter >=0.25.0
- **Verification**: Need to confirm tree-sitter-sql package availability and version compatibility

---

## Timeline

- **Proposal**: 2025-11-07
- **Design Review**: 1 day
- **Implementation**: 2-3 days
- **Testing**: 1-2 days
- **Review**: 1 day
- **Target Completion**: 2025-11-12

---

## Notes

- SQL is a complex language with many dialects (MySQL, PostgreSQL, SQL Server, etc.)
- tree-sitter-sql may have limitations on dialect-specific features
- Initial implementation focuses on standard SQL (ANSI SQL) elements
- Future enhancements could add dialect-specific support
- Consider SQL query complexity analysis (similar to cyclomatic complexity for code)

