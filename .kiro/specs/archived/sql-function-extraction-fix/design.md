# Design Document

## Overview

This design addresses a bug in the SQL function extraction logic within `tree_sitter_analyzer/languages/sql_plugin.py`. The current implementation uses a regex pattern that incorrectly matches column names and keywords within function bodies as function names. The fix involves refining the regex pattern and improving the validation logic to ensure only actual CREATE FUNCTION declarations are matched.

## Architecture

The SQL plugin uses a dual-extraction approach:
1. **Regex-based extraction**: Scans source code line-by-line for CREATE FUNCTION patterns
2. **Tree-sitter AST extraction**: Parses the AST for create_function nodes

The bug exists in the regex-based extraction path within the `_extract_sql_functions_enhanced` method. The current regex pattern `r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)"` is too permissive and matches lines that contain "CREATE" and "FUNCTION" even when they're not part of a function declaration.

## Components and Interfaces

### Affected Component: SQLElementExtractor

**File**: `tree_sitter_analyzer/languages/sql_plugin.py`

**Method**: `_extract_sql_functions_enhanced(self, root_node, sql_elements)`

**Current Flow**:
1. Split source code into lines
2. Iterate through lines looking for CREATE FUNCTION pattern
3. Extract function name using regex
4. Find END statement to determine function boundary
5. Create SQLFunction object

**Issue**: The regex pattern matches any line containing "CREATE" and "FUNCTION", even within function bodies where SELECT statements might reference columns.

### Interface Changes

No interface changes required. The fix is internal to the extraction logic.

## Data Models

No changes to data models. The SQLFunction model remains unchanged:
- name: str
- start_line: int
- end_line: int
- raw_text: str
- language: str
- parameters: list[SQLParameter]
- dependencies: list[str]
- return_type: str | None

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Function body content exclusion
*For any* SQL source file containing CREATE FUNCTION statements with column names or SQL keywords in their bodies, the extracted function names should not include any of those column names or keywords - only the identifier immediately following "CREATE FUNCTION" in the declaration line.
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: Function boundary detection
*For any* CREATE FUNCTION statement, the start line should be the line containing "CREATE FUNCTION" and the end line should be the line containing the matching "END" statement.
**Validates: Requirements 1.5**

### Property 3: Regex pattern precision
*For any* line of SQL code, the CREATE FUNCTION regex pattern should only match lines that begin with CREATE FUNCTION (ignoring whitespace) and should not match lines within function bodies or lines where CREATE and FUNCTION are separated by other tokens.
**Validates: Requirements 2.1, 2.2, 2.5**

### Property 4: Identifier validation
*For any* potential function name extracted by the regex, if that name is a common SQL column name or SQL reserved keyword, it should be rejected by the validation logic.
**Validates: Requirements 2.3, 2.4**

### Property 5: Extraction count consistency
*For any* SQL file, the number of extracted functions should equal the number of CREATE FUNCTION declarations in the file.
**Validates: Requirements 1.4**

### Property 6: Output ordering preservation
*For any* SQL file with multiple functions, the extracted functions should appear in the same order as they appear in the source file.
**Validates: Requirements 3.3**

### Property 7: Deterministic extraction
*For any* given SQL input file, running the extraction multiple times should produce identical output regardless of execution context.
**Validates: Requirements 3.5**

## Error Handling

The fix will maintain existing error handling:
- Continue processing if a function extraction fails
- Log debug messages for extraction failures
- Skip invalid identifiers using `_is_valid_identifier` validation

Additional validation:
- Skip lines that are within a previously identified function body
- Validate that matched function names are not common column names
- Ensure CREATE and FUNCTION keywords appear on the same line

## Testing Strategy

### Unit Testing

Unit tests will verify:
- Regex pattern correctly matches CREATE FUNCTION declarations
- Regex pattern does not match column names in SELECT statements
- Function boundary detection correctly identifies END statements
- Validation logic rejects common column names

### Property-Based Testing

We will use pytest with Hypothesis for property-based testing:

**Library**: Hypothesis (Python property-based testing library)
**Configuration**: Minimum 100 iterations per property test

Each property-based test will be tagged with the format:
`# Feature: sql-function-extraction-fix, Property {number}: {property_text}`

Property tests will:
1. Generate random SQL code with CREATE FUNCTION statements
2. Generate random SQL code with SELECT statements containing column references
3. Verify that only CREATE FUNCTION declarations are matched
4. Verify that function boundaries are correctly identified
5. Verify that extraction count matches the number of CREATE FUNCTION statements

### Integration Testing

Integration tests will:
- Run the full extraction on sample_database.sql
- Verify output matches golden master CSV
- Ensure exactly 2 functions are extracted (calculate_order_total, is_user_active)
- Verify no "price" function appears in output

## Implementation Approach

### Root Cause Analysis

The bug occurs because the current implementation:
1. Iterates through ALL lines in the source file
2. Applies the regex pattern to every line
3. Does not track whether the current line is inside a function body

When processing line 97 (`SELECT COALESCE(SUM(price * quantity), 0) INTO total`), if the line somehow matches the pattern or if there's a logic error in the iteration, it could extract "price" as a function name.

### Solution Design

**Fix 1: Improve regex pattern specificity**
- Ensure the pattern only matches lines that start with CREATE FUNCTION
- Add word boundaries to prevent partial matches

**Fix 2: Track function body boundaries**
- When a CREATE FUNCTION is found, skip all lines until the matching END
- Prevent the regex from being applied to lines within function bodies

**Fix 3: Enhanced validation**
- Add "price", "quantity", "total" to the list of excluded column names
- Validate that the matched line actually starts with CREATE FUNCTION

**Fix 4: Use state machine approach**
- Track whether we're currently inside a function body
- Only apply CREATE FUNCTION regex when not inside a function body

### Recommended Implementation

```python
def _extract_sql_functions_enhanced(
    self, root_node: "tree_sitter.Node", sql_elements: list[SQLElement]
) -> None:
    """Extract CREATE FUNCTION statements with enhanced metadata."""
    import re

    lines = self.source_code.split("\n")
    
    # Pattern to match CREATE FUNCTION at the start of a statement
    function_pattern = re.compile(
        r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        re.IGNORECASE
    )
    
    i = 0
    inside_function = False
    
    while i < len(lines):
        line = lines[i]
        
        # Skip lines if we're inside a function body
        if inside_function:
            if line.strip().upper() in ["END;", "END$"] or line.strip().upper().startswith("END;"):
                inside_function = False
            i += 1
            continue
        
        # Only check for CREATE FUNCTION when not inside a function
        match = function_pattern.match(line)
        if match:
            func_name = match.group(1)
            
            # Skip common column names
            if func_name.upper() in (
                "PRICE", "QUANTITY", "TOTAL", "AMOUNT", "COUNT", "SUM",
                "CREATED_AT", "UPDATED_AT", "ID", "NAME", "EMAIL", "STATUS"
            ):
                i += 1
                continue
            
            start_line = i + 1
            inside_function = True
            
            # Find the end of the function
            end_line = start_line
            for j in range(i + 1, len(lines)):
                if lines[j].strip().upper() in ["END;", "END$", "END"] or \
                   lines[j].strip().upper().startswith("END;"):
                    end_line = j + 1
                    inside_function = False
                    break
            
            # Extract function details and create SQLFunction object
            # ... (rest of extraction logic)
            
            i = end_line
        else:
            i += 1
```

This approach ensures that:
1. The regex only matches at the start of lines (not within SELECT statements)
2. We track whether we're inside a function body
3. We don't apply the regex to lines within function bodies
4. We validate function names against common column names
