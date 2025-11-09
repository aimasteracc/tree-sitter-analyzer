# Design: Title Generation Rules

## Overview

This document specifies the rules for generating document titles in markdown output formats (both compact and full) for different programming languages.

## Current Problem

The existing title generation logic in `table_formatter.py` doesn't properly handle language-specific conventions, resulting in:
- Incorrect "unknown" package prefixes for JavaScript/TypeScript
- Using filename instead of class name for Java files
- Missing package information for some Java files
- Inconsistent behavior across languages

## Design Goals

1. **Language-Aware**: Respect each language's package/module conventions
2. **Consistent**: Predictable title format for each scenario
3. **Readable**: Human-friendly titles that match user expectations
4. **Maintainable**: Clear, simple logic that's easy to extend

## Title Generation Rules

### Java Files

#### Single Class File
**Format**: `package.ClassName`

**Example**:
```markdown
# com.example.service.BigService
```

**Logic**:
- If file contains exactly one class
- AND class has a name
- AND package information is available
- THEN use `{package}.{class_name}`

#### Multiple Classes File
**Format**: Use filename without extension

**Example**:
```markdown
# Sample
```

**Logic**:
- If file contains multiple classes or interfaces
- OR no clear primary class
- THEN use filename (strip `.java` extension)

#### No Package Information
**Format**: Just the class name

**Example**:
```markdown
# UserService
```

**Logic**:
- If package name is empty/null/unknown
- AND single class exists
- THEN use just `{class_name}`

### Python Files

#### Module Format
**Format**: `Module: module_name`

**Example**:
```markdown
# Module: sample
```

**Logic**:
- Always use "Module: {filename}" format for Python
- Strip `.py` extension from filename
- This matches Python's module concept

### JavaScript/TypeScript Files

#### Class-Based Files
**Format**: Just the primary class name

**Example**:
```markdown
# Animal
```

**Logic**:
- JavaScript/TypeScript don't have packages in the Java sense
- If primary class exists, use its name
- Don't add "unknown" or any package prefix

#### No Clear Class
**Format**: Use filename

**Example**:
```markdown
# utilities
```

**Logic**:
- If no clear primary class
- Use filename (strip `.js`/`.ts` extension)

## Implementation Strategy

### Proposed Helper Method

```python
def _generate_title(self, data: dict[str, Any]) -> str:
    """
    Generate document title based on language and structure.
    
    Args:
        data: Analysis result dictionary containing classes, package, file_path
        
    Returns:
        Formatted title string (without leading "# ")
    """
    language = self.language.lower()
    package_name = (data.get("package") or {}).get("name", "")
    classes = data.get("classes", []) or []
    file_path = data.get("file_path", "")
    
    # Extract filename without extension
    filename = self._extract_filename(file_path)
    
    if language == "java":
        return self._generate_java_title(package_name, classes, filename)
    elif language == "python":
        return self._generate_python_title(filename)
    elif language in ["javascript", "typescript"]:
        return self._generate_js_ts_title(classes, filename)
    else:
        # Default fallback
        return self._generate_default_title(package_name, classes, filename)
```

### Language-Specific Helpers

```python
def _generate_java_title(
    self, package_name: str, classes: list, filename: str
) -> str:
    """Generate title for Java files."""
    if len(classes) == 1:
        class_name = classes[0].get("name", "Unknown")
        if package_name and package_name != "unknown":
            return f"{package_name}.{class_name}"
        return class_name
    # Multiple classes or no classes - use filename
    return filename

def _generate_python_title(self, filename: str) -> str:
    """Generate title for Python files."""
    return f"Module: {filename}"

def _generate_js_ts_title(self, classes: list, filename: str) -> str:
    """Generate title for JavaScript/TypeScript files."""
    if classes:
        # Use primary (first) class name
        return classes[0].get("name", filename)
    return filename

def _extract_filename(self, file_path: str) -> str:
    """Extract filename without extension from file path."""
    if not file_path or file_path == "Unknown":
        return "unknown"
    
    # Get basename
    filename = file_path.split("/")[-1].split("\\")[-1]
    
    # Remove common extensions
    for ext in [".java", ".py", ".js", ".ts", ".tsx", ".jsx"]:
        if filename.endswith(ext):
            filename = filename[:-len(ext)]
            break
    
    return filename or "unknown"
```

## Migration Plan

### Step 1: Add New Helper Methods
- Add `_generate_title()` and related helpers to `TableFormatter`
- Keep existing methods unchanged initially

### Step 2: Update Compact Format
- Modify `_format_compact_table()` to use `_generate_title()`
- Test with existing golden masters

### Step 3: Update Full Format
- Modify `_format_full_table()` to use `_generate_title()`
- Ensure multi-class handling remains correct

### Step 4: Update Golden Masters
- Regenerate or manually fix golden master files
- Verify each file's title matches expected format

## Edge Cases

### Empty/Missing Data
- **No classes**: Use filename
- **No package**: Don't force "unknown" prefix (language-dependent)
- **No filename**: Use "unknown" as last resort

### Special Characters
- Package names with unusual characters: Keep as-is
- Class names with generics: Strip type parameters for title

### Nested Classes
- Use outermost class name
- Don't include nested class names in title

## Testing Strategy

### Unit Tests
```python
def test_java_title_single_class_with_package():
    """Test Java file with package and single class."""
    # Expected: com.example.UserService
    
def test_java_title_no_package():
    """Test Java file without package."""
    # Expected: UserService

def test_python_title():
    """Test Python module title."""
    # Expected: Module: sample

def test_js_title_with_class():
    """Test JavaScript file with class."""
    # Expected: Animal (not unknown.Animal)

def test_java_title_multiple_classes():
    """Test Java file with multiple classes."""
    # Expected: Sample (filename)
```

### Integration Tests
- Use existing golden master framework
- Verify all language types generate correct titles
- Test edge cases (no package, no classes, etc.)

## Compatibility Considerations

### Backward Compatibility
- Changes fix regressions, so restore previous behavior
- New behavior is more correct, not a breaking change
- Existing valid golden masters should still work

### Forward Compatibility
- Design allows easy addition of new languages
- Helper method pattern makes extension straightforward

## Open Questions

1. Should we ever show file extension in titles? 
   - **Decision**: No, extensions are noise in document titles

2. How to handle TypeScript interfaces vs classes?
   - **Decision**: Treat interfaces same as classes for title purposes

3. Should Python show class name if file has only one class?
   - **Decision**: No, stick with "Module: name" for consistency

## References

- `tree_sitter_analyzer/table_formatter.py` - Implementation location
- `tests/golden_masters/` - Expected output examples
- Language specs for package/module conventions

