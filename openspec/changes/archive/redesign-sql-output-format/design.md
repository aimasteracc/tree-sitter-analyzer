# Design: Redesign SQL Output Format

**Change ID:** `redesign-sql-output-format`

---

## Architecture Overview

This change introduces SQL-specific output formatting to replace the current generic class-based format with database-appropriate terminology and comprehensive element representation.

---

## Current Architecture Analysis

### Current Flow
```
SQL File → SQLPlugin → Generic Element Models → Generic Formatters → Inappropriate Output
```

### Current Issues
1. **Generic Element Models**: SQL elements forced into Class/Function/Variable categories
2. **Generic Formatters**: Java/Python terminology applied to SQL elements
3. **Missing Elements**: Procedures, functions, triggers, indexes not displayed
4. **Inappropriate Metadata**: "public visibility", "methods", "fields" for database elements

---

## Proposed Architecture

### New Flow
```
SQL File → Enhanced SQLPlugin → SQL-Specific Models → SQL Formatters → Professional SQL Output
```

### Component Design

#### 1. Enhanced Element Models

**Base SQL Element Model**
```python
@dataclass
class SQLElement:
    name: str
    element_type: SQLElementType  # TABLE, VIEW, PROCEDURE, FUNCTION, TRIGGER, INDEX
    start_line: int
    end_line: int
    raw_text: str
    language: str = "sql"
    
    # SQL-specific metadata
    columns: List[SQLColumn] = field(default_factory=list)
    parameters: List[SQLParameter] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    constraints: List[SQLConstraint] = field(default_factory=list)
```

**SQL-Specific Element Types**
```python
class SQLElementType(Enum):
    TABLE = "table"
    VIEW = "view"
    PROCEDURE = "procedure"
    FUNCTION = "function"
    TRIGGER = "trigger"
    INDEX = "index"

@dataclass
class SQLColumn:
    name: str
    data_type: str
    nullable: bool = True
    default_value: Optional[str] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_reference: Optional[str] = None

@dataclass
class SQLParameter:
    name: str
    data_type: str
    direction: str = "IN"  # IN, OUT, INOUT

@dataclass
class SQLConstraint:
    name: Optional[str]
    constraint_type: str  # PRIMARY_KEY, FOREIGN_KEY, UNIQUE, CHECK
    columns: List[str]
    reference_table: Optional[str] = None
    reference_columns: Optional[List[str]] = None
```

#### 2. Enhanced SQL Element Extraction

**Metadata Extraction Strategy**
```python
class EnhancedSQLElementExtractor(SQLElementExtractor):
    def extract_table_metadata(self, node: Node) -> SQLElement:
        """Extract comprehensive table information"""
        # Extract columns with data types
        # Extract constraints (PK, FK, UNIQUE)
        # Extract dependencies
        
    def extract_view_metadata(self, node: Node) -> SQLElement:
        """Extract view information"""
        # Extract source tables
        # Extract column mappings
        
    def extract_procedure_metadata(self, node: Node) -> SQLElement:
        """Extract procedure information"""
        # Extract parameters with types and directions
        # Extract dependencies on tables/views
        
    def extract_function_metadata(self, node: Node) -> SQLElement:
        """Extract function information"""
        # Extract parameters and return type
        # Extract dependencies
        
    def extract_trigger_metadata(self, node: Node) -> SQLElement:
        """Extract trigger information"""
        # Extract event type (INSERT, UPDATE, DELETE)
        # Extract target table
        # Extract timing (BEFORE, AFTER)
        
    def extract_index_metadata(self, node: Node) -> SQLElement:
        """Extract index information"""
        # Extract target table
        # Extract indexed columns
        # Extract index type
```

#### 3. SQL-Specific Formatters

**Formatter Architecture**
```python
class SQLFormatterBase:
    """Base class for SQL-specific formatters"""
    
    def format_elements(self, elements: List[SQLElement]) -> str:
        """Format SQL elements with appropriate terminology"""
        
    def group_elements_by_type(self, elements: List[SQLElement]) -> Dict[SQLElementType, List[SQLElement]]:
        """Group elements by SQL type"""
        
    def format_element_overview(self, elements: List[SQLElement]) -> str:
        """Create overview table with SQL terminology"""

class SQLFullFormatter(SQLFormatterBase):
    """Comprehensive SQL format with detailed metadata"""
    
    def format_table_section(self, tables: List[SQLElement]) -> str:
        """Format tables with columns, constraints, dependencies"""
        
    def format_view_section(self, views: List[SQLElement]) -> str:
        """Format views with source information"""
        
    def format_procedure_section(self, procedures: List[SQLElement]) -> str:
        """Format procedures with parameters and dependencies"""

class SQLCompactFormatter(SQLFormatterBase):
    """Compact SQL format for quick overview"""
    
    def format_compact_table(self, elements: List[SQLElement]) -> str:
        """Single table with essential SQL information"""

class SQLCSVFormatter(SQLFormatterBase):
    """CSV format for data processing"""
    
    def format_csv_rows(self, elements: List[SQLElement]) -> str:
        """CSV rows with SQL-specific columns"""
```

---

## Implementation Strategy

### Phase 1: Foundation
1. **Create SQL-specific element models** with comprehensive metadata support
2. **Enhance extraction logic** to gather SQL-specific information
3. **Implement basic SQL formatters** with appropriate terminology

### Phase 2: Metadata Enhancement
1. **Column extraction** from CREATE TABLE statements
2. **Constraint extraction** (PRIMARY KEY, FOREIGN KEY, UNIQUE)
3. **Dependency analysis** (table references, view sources)
4. **Parameter extraction** from procedures and functions

### Phase 3: Advanced Features
1. **Trigger event analysis** (timing, events, target tables)
2. **Index metadata** (target table, columns, type)
3. **Cross-reference analysis** (which elements depend on which)
4. **Schema validation** (detect missing dependencies)

---

## Data Flow Design

### Element Extraction Flow
```
SQL AST Node → Element Type Detection → Metadata Extraction → SQLElement Creation
```

### Formatting Flow
```
List[SQLElement] → Type Grouping → Format Selection → SQL-Specific Rendering → Output
```

### Integration Points
```
CLI Tool → Language Detection → SQL Plugin → Enhanced Extraction → SQL Formatter → Output
MCP Tool → File Analysis → SQL Plugin → Enhanced Extraction → SQL Formatter → Response
```

---

## Format Specifications

### Full Format Structure
```markdown
# filename.sql

## Database Schema Overview
[Comprehensive table with all elements]

## Tables
[Detailed table information with columns, constraints]

## Views
[View information with sources and columns]

## Procedures
[Procedure information with parameters]

## Functions
[Function information with parameters and return types]

## Triggers
[Trigger information with events and targets]

## Indexes
[Index information with tables and columns]
```

### Compact Format Structure
```markdown
# filename.sql

[Single comprehensive table with essential information]
```

### CSV Format Structure
```csv
Element,Type,Lines,Columns_Parameters,Dependencies
[One row per element with essential metadata]
```

---

## Error Handling Strategy

### Extraction Errors
- **Graceful degradation**: If metadata extraction fails, fall back to basic element information
- **Partial extraction**: Extract what's possible, mark missing information
- **Error logging**: Log extraction issues for debugging

### Formatting Errors
- **Safe defaults**: Use generic formatting if SQL-specific formatting fails
- **Validation**: Validate element data before formatting
- **Fallback**: Maintain compatibility with existing formatter interface

---

## Performance Considerations

### Extraction Performance
- **Lazy evaluation**: Extract metadata only when needed for formatting
- **Caching**: Cache extracted metadata to avoid re-parsing
- **Incremental parsing**: Parse only relevant AST sections for metadata

### Memory Usage
- **Efficient data structures**: Use minimal memory for metadata storage
- **Streaming**: Process large SQL files in chunks if needed
- **Cleanup**: Properly dispose of AST resources after extraction

---

## Testing Strategy

### Unit Tests
- **Element extraction**: Test each SQL element type extraction
- **Metadata extraction**: Test column, constraint, dependency extraction
- **Formatter output**: Test each format type with known inputs

### Integration Tests
- **End-to-end**: Test complete flow from SQL file to formatted output
- **Real-world files**: Test with actual database schema files
- **Edge cases**: Test with malformed SQL, empty files, large schemas

### Golden Master Tests
- **Format validation**: Ensure output matches expected format
- **Regression prevention**: Detect unintended format changes
- **Cross-platform**: Validate consistent output across platforms

---

## Migration Strategy

### Backward Compatibility
- **API compatibility**: Maintain existing plugin interface
- **Gradual rollout**: SQL-specific formatting only for SQL files
- **Fallback support**: Fall back to generic formatting if SQL formatting fails

### Golden Master Updates
- **Regeneration**: Update all SQL golden masters with new format
- **Validation**: Manually review new golden masters for accuracy
- **Documentation**: Document format changes in CHANGELOG

---

## Future Enhancements

### SQL Dialect Support
- **MySQL-specific**: Support MySQL-specific syntax and features
- **PostgreSQL-specific**: Support PostgreSQL-specific syntax
- **SQLite-specific**: Support SQLite-specific features
- **Configurable**: Allow dialect selection for enhanced accuracy

### Advanced Analysis
- **Schema validation**: Detect missing foreign key targets
- **Dependency graphs**: Visualize table dependencies
- **Performance analysis**: Identify potential performance issues
- **Documentation generation**: Generate comprehensive schema documentation

---

## Success Criteria

### Functional Requirements
1. ✅ SQL elements use appropriate database terminology
2. ✅ All SQL element types are displayed (tables, views, procedures, functions, triggers, indexes)
3. ✅ Meaningful metadata is extracted and displayed
4. ✅ Output is professional and suitable for database documentation

### Quality Requirements
1. ✅ No performance degradation compared to current implementation
2. ✅ 100% test coverage for new functionality
3. ✅ All existing tests continue to pass
4. ✅ Format is consistent across all output types

### User Experience Requirements
1. ✅ Output is immediately understandable to database professionals
2. ✅ Format is suitable for both human reading and automated processing
3. ✅ Information density is appropriate for each format type
4. ✅ Error messages are clear and actionable
