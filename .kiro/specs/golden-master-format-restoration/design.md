# Golden Master Format Restoration - Design Document

## 1. Executive Summary

The formatter architecture unification inadvertently changed the output format of several language formatters,
causing golden master regression. This design document outlines the approach to restore the original format
while maintaining the architectural improvements.

## 2. Problem Analysis

### 2.1 Root Cause

The `JavaTableFormatter` and other language formatters were modified to produce a different format than
what was established in the golden masters. The key differences are:

| Aspect | Original Format | Current Format | Impact |
|--------|----------------|----------------|--------|
| Header | `# package.ClassName` | `# package.ClassName.java` | +5 chars |
| Classes section | `## Classes Overview` | `## Classes` | -9 chars |
| Per-class sections | `## ClassName (start-end)` with subsections | All merged into one section | Major structural change |
| Visibility groups | Public/Protected/Package/Private | Only Public/Private | Lost information |
| Constructors | Per-class `### Constructors` section | All merged | Lost class association |
| Inner classes | Separate sections per inner class | Merged with outer class | Lost hierarchy |
| Enum sections | `## EnumName (start-end)` | `## EnumName` with property table | Format change |
| Method table | No `Cols` column | Added `Cols` column | +8 chars per row |

### 2.2 Format Comparison

**Original Format (Correct):**
```markdown
# com.example.Sample

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
...

## AbstractParentClass (7-15)
### Package Methods
| Method | Signature | Vis | Lines | Cx | Doc |
...

## ParentClass (18-45)
### Fields
...
### Constructors
...
### Package Methods
...

## Test (72-159)
### Fields
...
### Constructors
...
### Public Methods
...
### Protected Methods
...
### Package Methods
...
### Private Methods
...

## InnerClass (83-87)
### Public Methods
...

## TestEnum (162-178)
### Fields
...
### Constructors
...
### Public Methods
...
```

**Current Format (Incorrect):**
```markdown
# com.example.Sample.java

## Classes
| Class | Type | Visibility | Lines | Methods | Fields |
...

### Fields (all merged)
...

### Constructors (all merged)
...

### Public Methods (all merged)
...

### Private Methods (missing Protected/Package)
...

## TestEnum
| Property | Value |
...
```

## 3. Design Decisions

### 3.1 Approach: Restore Original Format

**Decision**: Restore the original golden master format rather than updating golden masters to match new format.

**Rationale**:
1. Original format is more token-efficient (no unnecessary `Cols` column)
2. Original format preserves class hierarchy information
3. Original format groups methods by visibility correctly
4. Original format is more readable for humans
5. Breaking changes to established format violate backward compatibility

### 3.2 Implementation Strategy

We will modify the language formatters to produce output matching the original golden masters:

1. **Java Formatter** (`java_formatter.py`):
   - Remove `.java` extension from header
   - Restore `## Classes Overview` section name
   - Generate per-class sections with line ranges
   - Group methods by visibility (Public/Protected/Package/Private)
   - Handle inner classes separately
   - Format enums with line ranges in section header

2. **Other Language Formatters**:
   - Apply similar fixes based on their golden master differences

### 3.3 Golden Master Restoration

After fixing formatters, we will:
1. Revert all golden master files to their original state: `git checkout HEAD -- tests/golden_masters/`
2. Run tests to verify formatters produce matching output
3. Fix any remaining discrepancies

## 4. Detailed Design

### 4.1 Java Formatter Changes

#### 4.1.1 Header Format
```python
# Before (incorrect)
lines.append(f"# {package_name}.{file_name}")

# After (correct)
lines.append(f"# {package_name}.{class_name}")  # No file extension
```

#### 4.1.2 Classes Overview Section
```python
# Before (incorrect)
lines.append("## Classes")

# After (correct)
lines.append("## Classes Overview")
```

#### 4.1.3 Per-Class Sections
```python
# Generate a section for each class
for class_info in classes:
    name = class_info.get("name", "Unknown")
    line_range = class_info.get("line_range", {})
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    lines.append(f"## {name} ({lines_str})")
    
    # Get methods/fields belonging to this class
    class_methods = filter_by_line_range(data.get("methods", []), line_range)
    class_fields = filter_by_line_range(data.get("fields", []), line_range)
    
    # Format fields
    if class_fields:
        lines.append("### Fields")
        # ... format fields table
    
    # Format constructors
    class_constructors = [m for m in class_methods if m.get("is_constructor")]
    if class_constructors:
        lines.append("### Constructors")
        # ... format constructors table
    
    # Group and format methods by visibility
    for visibility in ["public", "protected", "package", "private"]:
        visibility_methods = [m for m in class_methods 
                            if not m.get("is_constructor") 
                            and m.get("visibility") == visibility]
        if visibility_methods:
            lines.append(f"### {visibility.capitalize()} Methods")
            # ... format methods table
```

#### 4.1.4 Method Table Format
```python
# Remove Cols column from method tables
# Before:
"| Method | Signature | Vis | Lines | Cols | Cx | Doc |"

# After:
"| Method | Signature | Vis | Lines | Cx | Doc |"
```

### 4.2 Affected Files

| File | Changes Required |
|------|------------------|
| `java_formatter.py` | Major rewrite of `_format_full_table` |
| `csharp_formatter.py` | Similar per-class section changes |
| `javascript_formatter.py` | Similar per-class section changes |
| `typescript_formatter.py` | Similar per-class section changes |
| `php_formatter.py` | Similar per-class section changes |
| `python_formatter.py` | Review - changes may be improvements |
| `ruby_formatter.py` | Similar per-class section changes |

## 5. Testing Strategy

1. **Unit Tests**: Verify each formatter produces expected output for sample inputs
2. **Golden Master Tests**: Restore original golden masters and verify all tests pass
3. **Regression Tests**: Ensure no other functionality is broken

## 6. Rollback Plan

If issues arise:
1. Revert formatter changes
2. Keep current golden masters
3. Document format differences for future reference

## 7. Success Metrics

1. All 47 golden master files match their original format
2. All existing tests pass
3. No new linter errors
4. Output is token-efficient

