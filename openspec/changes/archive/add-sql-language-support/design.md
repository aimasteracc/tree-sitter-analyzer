# Design: SQL Language Support

## Architecture Overview

This design document describes the architecture for adding SQL language support to tree-sitter-analyzer, following the established plugin pattern used by other language plugins.

## Design Principles

1. **Consistency**: Follow existing plugin architecture patterns
2. **Type Safety**: Full mypy compliance with proper type annotations
3. **Code Quality**: Ruff compliance, no linting errors
4. **Testability**: Comprehensive test coverage (>80%)
5. **Maintainability**: Clear code structure following project conventions
6. **Extensibility**: Support for future SQL dialect-specific features

## Architecture Alignment

### Current Plugin Pattern

All language plugins follow this structure:

```
tree_sitter_analyzer/languages/
├── {language}_plugin.py
    ├── {Language}ElementExtractor(ElementExtractor)
    │   ├── extract_functions()
    │   ├── extract_classes()
    │   ├── extract_variables()
    │   └── extract_imports()
    └── {Language}Plugin(LanguagePlugin)
        ├── get_language_name()
        ├── get_file_extensions()
        ├── create_extractor()
        ├── get_tree_sitter_language()
        └── analyze_file()
```

### SQL Plugin Structure

SQL plugin will follow the same pattern:

```
tree_sitter_analyzer/languages/
└── sql_plugin.py
    ├── SQLElementExtractor(ElementExtractor)
    │   ├── extract_functions() → stored procedures, functions
    │   ├── extract_classes() → tables, views
    │   ├── extract_variables() → indexes, constraints
    │   └── extract_imports() → schema references
    └── SQLPlugin(LanguagePlugin)
        ├── get_language_name() → "sql"
        ├── get_file_extensions() → [".sql"]
        ├── create_extractor() → SQLElementExtractor()
        ├── get_tree_sitter_language() → tree-sitter-sql
        └── analyze_file() → standard analysis flow
```

## SQL Element Mapping

### SQL → Unified Element Model

SQL has different concepts than programming languages, so we map SQL elements to the unified element model:

| SQL Element | Maps To | Rationale |
|------------|---------|-----------|
| CREATE TABLE | Class | Tables are structural definitions (like classes) |
| CREATE VIEW | Class | Views are structural definitions |
| CREATE PROCEDURE | Function | Procedures are executable units |
| CREATE FUNCTION | Function | Functions are executable units |
| CREATE TRIGGER | Function | Triggers are event-driven functions |
| CREATE INDEX | Variable | Indexes are metadata (like variables) |
| ALTER TABLE | Variable | Schema changes are modifications |
| Schema references | Import | Cross-schema dependencies |

### Element Extraction Strategy

#### Tables (extract_classes)

```sql
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);
```

**Extraction**:
- Element Type: `Class`
- Name: `users`
- Start/End Line: From CREATE TABLE statement
- Raw Text: Full CREATE TABLE statement
- Additional: Column count, constraint count

#### Stored Procedures (extract_functions)

```sql
CREATE PROCEDURE get_user(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE id = user_id;
END;
```

**Extraction**:
- Element Type: `Function`
- Name: `get_user`
- Start/End Line: From CREATE PROCEDURE statement
- Raw Text: Full procedure definition
- Parameters: `IN user_id INT`
- Additional: Complexity analysis (nested queries, conditionals)

#### Views (extract_classes)

```sql
CREATE VIEW active_users AS
SELECT * FROM users WHERE status = 'active';
```

**Extraction**:
- Element Type: `Class`
- Name: `active_users`
- Start/End Line: From CREATE VIEW statement
- Raw Text: Full view definition
- Additional: Base table references

#### Functions (extract_functions)

```sql
CREATE FUNCTION calculate_total(price DECIMAL, quantity INT)
RETURNS DECIMAL
BEGIN
    RETURN price * quantity;
END;
```

**Extraction**:
- Element Type: `Function`
- Name: `calculate_total`
- Start/End Line: From CREATE FUNCTION statement
- Raw Text: Full function definition
- Parameters: `price DECIMAL, quantity INT`
- Return Type: `DECIMAL`

#### Indexes (extract_variables)

```sql
CREATE INDEX idx_user_email ON users(email);
```

**Extraction**:
- Element Type: `Variable`
- Name: `idx_user_email`
- Start/End Line: From CREATE INDEX statement
- Raw Text: Full index definition
- Additional: Table reference, column reference

## Tree-sitter SQL Grammar

### Node Types (Expected)

Based on tree-sitter-sql grammar, we expect these node types:

- `create_statement` - CREATE TABLE, VIEW, etc.
- `table_definition` - Table structure
- `column_definition` - Column definitions
- `procedure_definition` - Stored procedures
- `function_definition` - Functions
- `trigger_definition` - Triggers
- `index_definition` - Indexes
- `select_statement` - SELECT queries
- `insert_statement` - INSERT statements
- `update_statement` - UPDATE statements
- `delete_statement` - DELETE statements

### Query Patterns

SQL-specific queries for common patterns:

```python
# Find all tables
"tables": """
(create_statement
  (table_definition
    name: (identifier) @name)) @table
"""

# Find all procedures
"procedures": """
(create_statement
  (procedure_definition
    name: (identifier) @name)) @procedure
"""

# Find all functions
"functions": """
(create_statement
  (function_definition
    name: (identifier) @name)) @function
"""
```

## Implementation Details

### SQL Plugin Class

```python
class SQLPlugin(LanguagePlugin):
    """SQL language plugin implementation"""
    
    def __init__(self) -> None:
        super().__init__()
        self.extractor = SQLElementExtractor()
        self.language = "sql"
        self.supported_extensions = [".sql"]
        self._cached_language: Any | None = None
    
    def get_language_name(self) -> str:
        return "sql"
    
    def get_file_extensions(self) -> list[str]:
        return [".sql"]
    
    def create_extractor(self) -> ElementExtractor:
        return SQLElementExtractor()
    
    def get_tree_sitter_language(self) -> Any | None:
        """Load tree-sitter-sql language"""
        if self._cached_language is not None:
            return self._cached_language
        
        try:
            import tree_sitter
            import tree_sitter_sql
            
            lang = tree_sitter_sql.language()
            if hasattr(lang, "__class__") and "Language" in str(type(lang)):
                self._cached_language = lang
            else:
                self._cached_language = tree_sitter.Language(lang)
            
            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-sql not available: {e}")
            return None
```

### SQL Element Extractor

```python
class SQLElementExtractor(ElementExtractor):
    """SQL-specific element extractor"""
    
    def __init__(self) -> None:
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[int, str] = {}
    
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract stored procedures and functions"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        
        functions: list[Function] = []
        
        if tree is not None and tree.root_node is not None:
            # Extract procedures
            self._extract_procedures(tree.root_node, functions)
            # Extract functions
            self._extract_sql_functions(tree.root_node, functions)
            # Extract triggers
            self._extract_triggers(tree.root_node, functions)
        
        return functions
    
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract tables and views"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        
        classes: list[Class] = []
        
        if tree is not None and tree.root_node is not None:
            # Extract tables
            self._extract_tables(tree.root_node, classes)
            # Extract views
            self._extract_views(tree.root_node, classes)
        
        return classes
    
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract indexes and constraints"""
        # Implementation similar to above
        pass
    
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract schema references and dependencies"""
        # Implementation similar to above
        pass
```

## Error Handling

### Missing tree-sitter-sql

If `tree-sitter-sql` is not installed:
- Plugin should load but return `None` from `get_tree_sitter_language()`
- Analysis should fail gracefully with clear error message
- Tests should handle optional dependency

### Unsupported SQL Dialect

- Focus on standard SQL (ANSI SQL)
- Dialect-specific features may not parse correctly
- Log warnings for unrecognized syntax
- Don't fail entire analysis for partial failures

## Testing Strategy

### Unit Tests

1. **Plugin Loading**
   - Test plugin instantiation
   - Test language name and extensions
   - Test tree-sitter language loading

2. **Element Extraction**
   - Test table extraction
   - Test procedure extraction
   - Test function extraction
   - Test view extraction
   - Test index extraction

3. **Edge Cases**
   - Empty SQL files
   - Invalid SQL syntax
   - Mixed SQL dialects
   - Large SQL files

### Integration Tests

1. **CLI Integration**
   - Test `analyze` command with SQL file
   - Test format output (Full, Compact, CSV)

2. **API Integration**
   - Test `analyze_file()` with SQL
   - Test element extraction results

3. **MCP Integration**
   - Test MCP tools with SQL files
   - Test query execution

## Performance Considerations

- SQL files can be very large (migration scripts, schema dumps)
- Use streaming file reading (already implemented in analysis engine)
- Cache parsed AST for repeated analysis
- Optimize element extraction for large files

## Future Enhancements

1. **Dialect-Specific Support**
   - MySQL-specific features
   - PostgreSQL-specific features
   - SQL Server-specific features

2. **Query Analysis**
   - Extract SELECT queries
   - Analyze query complexity
   - Identify query patterns

3. **Schema Analysis**
   - Cross-table relationships
   - Foreign key analysis
   - Dependency graphs

## Dependencies

### Required

- `tree-sitter-sql`: SQL grammar for tree-sitter
- `tree-sitter>=0.25.0`: Core tree-sitter library (already required)

### Optional

- Add SQL to optional dependencies group in `pyproject.toml`
- Allow installation with: `pip install tree-sitter-analyzer[sql]`

## Migration Path

No migration needed - this is a new feature addition with no breaking changes.

