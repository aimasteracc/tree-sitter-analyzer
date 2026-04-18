# Spec: Java Query Fix

**Change ID:** `fix-java-annotation-method-query`  
**Spec ID:** `java-query-fix`  
**Status:** Draft

---

## Overview

This specification defines the requirements for fixing the `method_with_annotations` query in the Java plugin to correctly match and extract annotated methods.

---

## MODIFIED Requirements

### Requirement 1: Query Pattern Structure

**ID**: `JQF-001`  
**Priority**: High  
**Category**: Correctness

The `method_with_annotations` query MUST use the correct tree-sitter query pattern that aligns with the Java grammar's AST structure.

#### Scenario: Query matches methods with single annotation

**Given** a Java source file containing:
```java
public class Example {
    @Override
    public String toString() {
        return "example";
    }
}
```

**When** executing the `method_with_annotations` query

**Then**:
- Query returns exactly 1 match
- Match captures `name` as "toString"
- Match captures `annotation` as "@Override"
- Match captures `method` as the entire method declaration

---

#### Scenario: Query matches methods with multiple annotations

**Given** a Java source file containing:
```java
public class Example {
    @SuppressWarnings("unchecked")
    @Deprecated
    public void oldMethod() {
        // deprecated code
    }
}
```

**When** executing the `method_with_annotations` query

**Then**:
- Query returns exactly 1 match
- Match captures `name` as "oldMethod"  
- Match captures `annotation` for BOTH annotations
- All annotation texts are accessible

---

#### Scenario: Query handles annotation with parameters

**Given** a Java source file containing:
```java
public class Example {
    @SuppressWarnings("unchecked")
    public List getRawList() {
        return new ArrayList();
    }
}
```

**When** executing the `method_with_annotations` query

**Then**:
- Query returns exactly 1 match
- Match captures `name` as "getRawList"
- Match captures `annotation` as '@SuppressWarnings("unchecked")'
- Annotation parameters are preserved

---

#### Scenario: Query distinguishes annotation from marker_annotation

**Given** Java tree-sitter grammar has two annotation node types:
- `marker_annotation`: Annotations without parameters (e.g., `@Override`)
- `annotation`: Annotations with parameters (e.g., `@SuppressWarnings("unchecked")`)

**When** the query pattern is defined

**Then**:
- Pattern MUST match BOTH `annotation` AND `marker_annotation` node types
- Pattern uses alternation syntax: `[(annotation) (marker_annotation)]`
- Both types are captured with the same capture name `@annotation`

---

### Requirement 2: Query Result Format

**ID**: `JQF-002`  
**Priority**: High  
**Category**: API Consistency

The query results MUST follow the standard format used by the tree-sitter analyzer framework.

#### Scenario: Result structure contains required fields

**Given** a successful query execution

**When** inspecting the query result

**Then** each result MUST contain:
- `text`: Full matched text
- `start_line`: Starting line number (1-indexed)
- `end_line`: Ending line number (1-indexed)
- `start_column`: Starting column (0-indexed)
- `end_column`: Ending column (0-indexed)
- `captures`: Dictionary of captured nodes

---

#### Scenario: Captures contain expected nodes

**Given** a result from `method_with_annotations` query

**When** examining the `captures` dictionary

**Then** it MUST contain:
- `name`: Dictionary with method name details
  - `text`: Method identifier string
  - `start_line`, `end_line`, `start_column`, `end_column`
- `annotation`: Dictionary (or list of dictionaries) with annotation details
  - `text`: Full annotation text including @
  - Position information
- `method`: Dictionary with full method declaration details

---

### Requirement 3: Backward Compatibility

**ID**: `JQF-003`  
**Priority**: Medium  
**Category**: Compatibility

Changes MUST NOT break existing code that uses the `method_with_annotations` query.

#### Scenario: Query name remains unchanged

**Given** existing code using `api.execute_query(file, "method_with_annotations")`

**When** the fix is applied

**Then**:
- Query name "method_with_annotations" is still valid
- No code changes required for users
- Query can be called through all interfaces (API, CLI, MCP)

---

#### Scenario: Empty result for methods without annotations

**Given** a Java method without annotations:
```java
public void regularMethod() {
    // no annotations
}
```

**When** executing the `method_with_annotations` query

**Then**:
- Method is NOT matched (query uses `+` quantifier requiring at least 1 annotation)
- Empty results list is returned
- No errors are raised

---

### Requirement 4: Test Coverage

**ID**: `JQF-004`  
**Priority**: High  
**Category**: Quality Assurance

Comprehensive test cases MUST be added to verify the fix.

#### Scenario: Unit tests cover all annotation scenarios

**Given** a new test file for Java queries

**When** running the test suite

**Then** tests MUST cover:
1. ✅ Single marker annotation (`@Override`)
2. ✅ Single annotation with parameters (`@SuppressWarnings("unchecked")`)
3. ✅ Multiple annotations on one method
4. ✅ Methods without annotations (verify no match)
5. ✅ Mixed methods (some with, some without annotations)
6. ✅ Edge cases (annotations on constructors, static methods, etc.)

---

#### Scenario: Integration tests verify all interfaces

**Given** the fixed query

**When** running integration tests

**Then** query MUST work correctly via:
1. ✅ Python API: `api.execute_query()`
2. ✅ CLI: `python -m tree_sitter_analyzer.cli query`
3. ✅ MCP Server: `execute_query` tool
4. ✅ Direct query service

---

### Requirement 5: Documentation

**ID**: `JQF-005`  
**Priority**: Low  
**Category**: Documentation

The fix MUST be documented appropriately.

#### Scenario: CHANGELOG entry describes the fix

**Given** the CHANGELOG.md file

**When** the fix is merged

**Then** an entry MUST be added with:
- Description: "Fixed `method_with_annotations` query for Java"
- Details: "Query now correctly matches methods with annotations"
- Issue reference (if applicable)
- Version number

---

#### Scenario: Code comments explain the pattern

**Given** the query definition in `java.py`

**When** viewing the source code

**Then** comments MUST explain:
- What the query matches
- Why alternation `[(annotation) (marker_annotation)]` is used
- That `+` requires at least one annotation

---

## Implementation Notes

### Query Pattern Syntax

```python
"method_with_annotations": """
(method_declaration
  (modifiers
    [(annotation) (marker_annotation)]+ @annotation)
  name: (identifier) @name) @method
"""
```

**Key Points**:
- `[]` creates alternation (match either type)
- `+` requires one or more (methods without annotations won't match)
- `@annotation` captures all matched annotations
- `@name` captures the method identifier
- `@method` captures the full method declaration

### Alternative: Optional Annotations

If we want to match ALL methods and optionally capture annotations:

```python
"method_with_annotations": """
(method_declaration
  (modifiers
    [(annotation) (marker_annotation)]* @annotation)?
  name: (identifier) @name) @method
"""
```

- `*` allows zero or more annotations
- `?` makes the modifiers node optional
- This would match methods without annotations too

**Decision**: Use `+` quantifier (at least one annotation required) to maintain semantic clarity of the query name "method_with_annotations".

---

## Acceptance Criteria

✅ Query successfully matches all annotated methods  
✅ Method names are correctly extracted  
✅ Annotations are correctly captured  
✅ Both `annotation` and `marker_annotation` types work  
✅ Test coverage ≥ 90%  
✅ No existing tests break  
✅ Documentation is updated  

---

## Related Specs

None - this is a standalone fix.

---

## References

- Tree-sitter Java Grammar: https://github.com/tree-sitter/tree-sitter-java
- Tree-sitter Query Syntax: https://tree-sitter.github.io/tree-sitter/using-parsers#query-syntax
- Current Implementation: `tree_sitter_analyzer/queries/java.py`
