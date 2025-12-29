# Spec: SQL Language Support

**Change ID:** `add-sql-language-support`  
**Spec ID:** `sql-language-support`  
**Status:** Draft

---

## Overview

This specification defines the requirements for adding comprehensive SQL language support to tree-sitter-analyzer, enabling analysis of SQL files including tables, views, stored procedures, functions, triggers, and indexes.

---

## ADDED Requirements

### Requirement 1: SQL Plugin Implementation

**ID**: `SQL-001`  
**Priority**: High  
**Category**: Core Functionality

A SQL language plugin MUST be implemented following the established plugin architecture pattern.

#### Scenario: Plugin loads successfully

**Given** the SQL plugin is implemented in `tree_sitter_analyzer/languages/sql_plugin.py`

**When** the PluginManager loads plugins

**Then**:
- SQL plugin is discovered and loaded
- Plugin instance is created successfully
- Plugin is registered with language name "sql"
- No errors are raised during plugin loading

---

#### Scenario: Plugin implements LanguagePlugin interface

**Given** the SQL plugin class

**When** inspecting the plugin implementation

**Then** it MUST implement:
- `get_language_name()` → returns "sql"
- `get_file_extensions()` → returns `[".sql"]`
- `create_extractor()` → returns `SQLElementExtractor()` instance
- `get_tree_sitter_language()` → loads and returns tree-sitter-sql language
- `analyze_file()` → performs standard file analysis

---

#### Scenario: Plugin handles missing dependency gracefully

**Given** tree-sitter-sql is not installed

**When** the plugin attempts to load the language

**Then**:
- `get_tree_sitter_language()` returns `None`
- Error is logged but plugin still loads
- Analysis attempts fail with clear error message
- No exceptions crash the application

---

### Requirement 2: SQL Element Extraction

**ID**: `SQL-002`  
**Priority**: High  
**Category**: Core Functionality

SQL elements MUST be extracted and mapped to the unified element model.

#### Scenario: Extract tables from CREATE TABLE statements

**Given** a SQL file containing:
```sql
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE
);
```

**When** analyzing the file

**Then**:
- One `Class` element is extracted
- Element name is "users"
- Element type is "class"
- Start/end lines are correctly identified
- Raw text contains full CREATE TABLE statement
- Additional metadata includes column count (3)

---

#### Scenario: Extract stored procedures

**Given** a SQL file containing:
```sql
CREATE PROCEDURE get_user(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE id = user_id;
END;
```

**When** analyzing the file

**Then**:
- One `Function` element is extracted
- Element name is "get_user"
- Element type is "function"
- Start/end lines are correctly identified
- Raw text contains full procedure definition
- Parameters are captured: "IN user_id INT"

---

#### Scenario: Extract functions

**Given** a SQL file containing:
```sql
CREATE FUNCTION calculate_total(price DECIMAL, quantity INT)
RETURNS DECIMAL
BEGIN
    RETURN price * quantity;
END;
```

**When** analyzing the file

**Then**:
- One `Function` element is extracted
- Element name is "calculate_total"
- Element type is "function"
- Parameters are captured: "price DECIMAL, quantity INT"
- Return type is captured: "DECIMAL"

---

#### Scenario: Extract views

**Given** a SQL file containing:
```sql
CREATE VIEW active_users AS
SELECT * FROM users WHERE status = 'active';
```

**When** analyzing the file

**Then**:
- One `Class` element is extracted
- Element name is "active_users"
- Element type is "class"
- Raw text contains full view definition

---

#### Scenario: Extract triggers

**Given** a SQL file containing:
```sql
CREATE TRIGGER update_timestamp
BEFORE UPDATE ON users
FOR EACH ROW
BEGIN
    SET NEW.updated_at = NOW();
END;
```

**When** analyzing the file

**Then**:
- One `Function` element is extracted
- Element name is "update_timestamp"
- Element type is "function"
- Trigger event is captured: "BEFORE UPDATE"
- Target table is captured: "users"

---

#### Scenario: Extract indexes

**Given** a SQL file containing:
```sql
CREATE INDEX idx_user_email ON users(email);
```

**When** analyzing the file

**Then**:
- One `Variable` element is extracted
- Element name is "idx_user_email"
- Element type is "variable"
- Table reference is captured: "users"
- Column reference is captured: "email"

---

#### Scenario: Handle multiple SQL statements

**Given** a SQL file containing multiple CREATE statements:
```sql
CREATE TABLE users (...);
CREATE TABLE orders (...);
CREATE PROCEDURE get_user(...);
CREATE FUNCTION calculate(...);
```

**When** analyzing the file

**Then**:
- All tables are extracted as `Class` elements
- All procedures are extracted as `Function` elements
- All functions are extracted as `Function` elements
- Elements are correctly distinguished by type
- No elements are missed or duplicated

---

#### Scenario: Handle empty SQL files

**Given** an empty SQL file

**When** analyzing the file

**Then**:
- Analysis completes without errors
- Empty element list is returned
- No exceptions are raised

---

#### Scenario: Handle invalid SQL syntax

**Given** a SQL file with syntax errors:
```sql
CREATE TABLE users (
    id INT PRIMARY KEY
    -- Missing closing parenthesis
```

**When** analyzing the file

**Then**:
- Analysis attempts to parse what it can
- Valid elements are still extracted
- Errors are logged but don't crash analysis
- Partial results are returned

---

### Requirement 3: File Extension Support

**ID**: `SQL-003`  
**Priority**: High  
**Category**: Integration

SQL files MUST be recognized by file extension.

#### Scenario: .sql files are recognized

**Given** a file with `.sql` extension

**When** the language detector processes the file

**Then**:
- File is identified as SQL
- SQL plugin is selected for analysis
- Analysis proceeds with SQL plugin

---

#### Scenario: Case-insensitive extension matching

**Given** files with `.SQL`, `.Sql`, `.sql` extensions

**When** the plugin checks applicability

**Then**:
- All variations are recognized
- Plugin is applicable for all cases
- Analysis works for all variations

---

### Requirement 4: Analysis Interface Integration

**ID**: `SQL-004`  
**Priority**: High  
**Category**: Integration

SQL analysis MUST work through all analysis interfaces.

#### Scenario: CLI analysis works

**Given** a SQL file `schema.sql`

**When** running: `tree-sitter-analyzer schema.sql --advanced`

**Then**:
- Command executes successfully
- SQL elements are extracted
- Output is displayed in default format
- No errors are raised

---

#### Scenario: API analysis works

**Given** a SQL file path

**When** calling: `api.analyze_file("schema.sql")`

**Then**:
- Analysis completes successfully
- `AnalysisResult` is returned
- Result contains extracted SQL elements
- Result language is "sql"

---

#### Scenario: Format output works

**Given** a SQL file

**When** analyzing with format options:
- Full format
- Compact format
- CSV format

**Then**:
- All formats work correctly
- SQL elements are properly formatted
- Output follows format specifications
- No format-specific errors occur

---

#### Scenario: MCP integration works

**Given** MCP tools are available

**When** using MCP tools to analyze SQL files

**Then**:
- MCP tools can process SQL files
- Analysis results are returned correctly
- No MCP-specific errors occur

---

### Requirement 5: Type Safety & Code Quality

**ID**: `SQL-005`  
**Priority**: High  
**Category**: Quality Assurance

SQL plugin MUST maintain type safety and code quality standards.

#### Scenario: mypy compliance

**Given** the SQL plugin implementation

**When** running: `mypy tree_sitter_analyzer/languages/sql_plugin.py`

**Then**:
- No type errors are reported
- All functions have proper type annotations
- 100% mypy compliance is achieved

---

#### Scenario: ruff compliance

**Given** the SQL plugin implementation

**When** running: `ruff check tree_sitter_analyzer/languages/sql_plugin.py`

**Then**:
- No linting errors are reported
- Code follows project style guidelines
- 100% ruff compliance is achieved

---

#### Scenario: Code formatting

**Given** the SQL plugin implementation

**When** running: `ruff format tree_sitter_analyzer/languages/sql_plugin.py`

**Then**:
- Code is properly formatted
- Formatting matches project standards
- No formatting changes are needed

---

### Requirement 6: Test Coverage

**ID**: `SQL-006`  
**Priority**: High  
**Category**: Quality Assurance

Comprehensive tests MUST be implemented for SQL plugin.

#### Scenario: Unit tests cover plugin functionality

**Given** test file `tests/test_languages/test_sql_plugin.py`

**When** running the test suite

**Then** tests MUST cover:
- Plugin instantiation
- Language name and extensions
- Tree-sitter language loading
- Error handling (missing dependency)
- All element extraction methods
- Edge cases (empty files, invalid syntax)

---

#### Scenario: Integration tests verify interfaces

**Given** integration tests

**When** running integration tests

**Then** tests MUST verify:
- CLI integration works
- API integration works
- Format output works
- MCP integration works (if applicable)

---

#### Scenario: Test coverage meets target

**Given** the SQL plugin implementation

**When** running: `pytest --cov=tree_sitter_analyzer/languages/sql_plugin tests/test_languages/test_sql_plugin.py`

**Then**:
- Test coverage is ≥80%
- All critical paths are covered
- Edge cases are tested

---

#### Scenario: No test regressions

**Given** the full test suite

**When** running: `pytest tests/ -v`

**Then**:
- All existing tests still pass
- No regressions are introduced
- SQL plugin tests don't break other tests

---

### Requirement 7: Documentation

**ID**: `SQL-007`  
**Priority**: Medium  
**Category**: Documentation

SQL support MUST be documented appropriately.

#### Scenario: CHANGELOG entry

**Given** the CHANGELOG.md file

**When** the feature is completed

**Then** an entry MUST be added with:
- Description: "Added SQL language support"
- Details: "SQL plugin for analyzing SQL files including tables, views, procedures, functions, triggers, and indexes"
- Version number
- Feature category

---

#### Scenario: Project documentation updated

**Given** project documentation files

**When** the feature is completed

**Then** documentation MUST be updated:
- `openspec/project.md`: Add SQL to supported languages list
- `README.md`: Add SQL to language support section
- Language specifications updated if needed

---

#### Scenario: Code comments in English

**Given** the SQL plugin implementation

**When** viewing the source code

**Then**:
- All docstrings are in English
- Inline comments are in English
- Comments explain complex logic
- Comments follow project standards

---

## MODIFIED Requirements

### Requirement 8: Language Detector Support

**ID**: `SQL-008`  
**Priority**: Medium  
**Category**: Integration

Language detector MUST properly support SQL files.

#### Scenario: SQL files are detected correctly

**Given** the language detector

**When** processing a `.sql` file

**Then**:
- File is detected as SQL
- Language name "sql" is returned
- No ambiguous language detection issues

---

## Implementation Notes

### SQL Element Mapping Strategy

SQL elements are mapped to the unified element model as follows:

- **Tables** → `Class` (structural definitions)
- **Views** → `Class` (structural definitions)
- **Stored Procedures** → `Function` (executable units)
- **Functions** → `Function` (executable units)
- **Triggers** → `Function` (event-driven functions)
- **Indexes** → `Variable` (metadata)
- **Constraints** → `Variable` (metadata)
- **Schema References** → `Import` (dependencies)

### Tree-sitter SQL Grammar

The implementation relies on tree-sitter-sql grammar. Expected node types include:
- `create_statement`
- `table_definition`
- `procedure_definition`
- `function_definition`
- `trigger_definition`
- `index_definition`
- `view_definition`

### Error Handling

- Missing tree-sitter-sql: Plugin loads but analysis fails gracefully
- Invalid SQL: Partial extraction, errors logged
- Unsupported dialects: Standard SQL focus, warnings for unrecognized syntax

---

## Acceptance Criteria

✅ SQL plugin loads successfully via PluginManager  
✅ SQL files (`.sql`) are recognized and processed  
✅ SQL elements (tables, views, procedures, functions, triggers, indexes) are extracted correctly  
✅ SQL analysis works through CLI, API, and MCP interfaces  
✅ Format output (Full, Compact, CSV) works for SQL files  
✅ All tests pass (mypy, ruff, pytest)  
✅ Test coverage ≥80% for SQL plugin  
✅ No regression in existing language plugins  
✅ Documentation is updated  

---

## Related Specs

None - this is a new feature addition.

---

## References

- Tree-sitter SQL Grammar: https://github.com/tree-sitter/tree-sitter-sql (if available)
- Tree-sitter Query Syntax: https://tree-sitter.github.io/tree-sitter/using-parsers#query-syntax
- Existing Plugin Implementations: `tree_sitter_analyzer/languages/python_plugin.py`, `java_plugin.py`
- Plugin Base Classes: `tree_sitter_analyzer/plugins/base.py`

