# Proposal: Fix Java Annotation Method Query

**Change ID:** `fix-java-annotation-method-query`  
**Type:** Bug Fix  
**Status:** Draft  
**Created:** 2025-11-04  
**Author:** AI Assistant

---

## Problem Statement

The `method_with_annotations` query in `tree_sitter_analyzer/queries/java.py` fails to match Java methods that have annotations. The query pattern incorrectly places the `*` (zero-or-more) quantifier outside the `modifiers` node, which causes the query engine to look for multiple `modifiers` nodes rather than multiple annotations within a single `modifiers` node.

### Current Behavior
```python
# Current (broken) query pattern
"method_with_annotations": """
(method_declaration
  (modifiers (annotation) @annotation)*    # WRONG: looks for multiple modifiers nodes
  name: (identifier) @name) @method_with_annotations
"""
```

When executed against Java code with annotated methods like:
```java
@Override
public String toString() {
    return "test";
}
```

The query returns **0 results** because the tree structure has only ONE `modifiers` node containing both the annotation and the `public` keyword.

### Expected Behavior
The query should match methods with annotations and capture both the annotation(s) and the method name.

---

## Root Cause Analysis

The Java tree-sitter grammar produces the following AST structure for annotated methods:

```
method_declaration
  ├─ modifiers                    # Single modifiers node
  │  ├─ marker_annotation: @Override
  │  └─ public: public
  ├─ type_identifier: String
  ├─ identifier: toString
  ├─ formal_parameters: ()
  └─ block: { ... }
```

The current query pattern `(modifiers (annotation) @annotation)*` expects:
- Zero or more `modifiers` nodes (WRONG)
- Each containing exactly one `annotation` child

But the actual structure has:
- Exactly ONE `modifiers` node
- Containing zero or more annotations

---

## Proposed Solution

Fix the query pattern to correctly match annotations within the `modifiers` node:

```python
"method_with_annotations": """
(method_declaration
  (modifiers
    [(annotation) (marker_annotation)]+ @annotation)
  name: (identifier) @name) @method
"""
```

### Key Changes:
1. **Remove `*` from outside modifiers**: No longer looking for multiple `modifiers` nodes
2. **Add `[]` for alternation**: Match either `annotation` or `marker_annotation` node types
3. **Add `+` inside modifiers**: Require at least one annotation (methods without annotations won't match)
4. **Simplify capture name**: Change `@method_with_annotations` to `@method` for consistency

### Alternative Pattern (Optional)
If we want to match methods with OR without annotations:

```python
"method_with_annotations": """
(method_declaration
  (modifiers
    [(annotation) (marker_annotation)]* @annotation)?
  name: (identifier) @name) @method
"""
```

This makes the modifiers node optional with `?` and annotations optional with `*`.

---

## Impact Analysis

### Affected Components
- ✅ `tree_sitter_analyzer/queries/java.py` - Query definition
- ✅ Tests using `method_with_annotations` query
- ❌ No API changes
- ❌ No backward compatibility issues (query currently returns 0 results anyway)

### User Impact
- **Positive**: Users can now successfully query for annotated methods in Java code
- **No Breaking Changes**: Since the query currently doesn't work, fixing it only adds functionality

### Test Coverage
- New test cases needed for:
  - Methods with single annotation (`@Override`)
  - Methods with multiple annotations (`@SuppressWarnings` + `@Deprecated`)
  - Methods with annotation parameters (`@SuppressWarnings("unchecked")`)
  - Methods without annotations (should not match with `+` quantifier)

---

## Success Criteria

1. ✅ Query successfully matches methods with annotations
2. ✅ Query captures method name correctly
3. ✅ Query captures all annotations on a method
4. ✅ Query handles both `annotation` and `marker_annotation` node types
5. ✅ All existing tests continue to pass
6. ✅ New tests validate the fix

---

## Related Issues

- Issue reported: "アノテーションのついているmethodを抽出する時に、名前がうまく抽出できる現象を発見"
- Query type: `query_code` tool in MCP server

---

## Alternatives Considered

### Alternative 1: Keep Original Pattern, Just Fix Placement
```python
(method_declaration
  (modifiers
    (annotation) @annotation*)  # Move * inside
  name: (identifier) @name) @method
```
**Rejected**: Doesn't handle `marker_annotation` type, less clear syntax

### Alternative 2: Separate Queries
Create separate queries for `annotation` and `marker_annotation`:
```python
"method_with_marker_annotations": ...
"method_with_param_annotations": ...
```
**Rejected**: Creates maintenance burden, users want unified query

### Alternative 3: Match All Methods, Optionally Capture Annotations
```python
(method_declaration
  name: (identifier) @name) @method
```
**Rejected**: Doesn't serve the specific use case of finding annotated methods

---

## Dependencies

- None - this is a standalone query fix

---

## Timeline

- **Proposal**: 2025-11-04
- **Implementation**: < 1 hour
- **Testing**: < 1 hour  
- **Review**: < 1 day
- **Target Completion**: 2025-11-05

---

## Notes

- This fix aligns with Java tree-sitter grammar structure
- Pattern tested against real Java code with annotations
- Consider documenting common query patterns for users
