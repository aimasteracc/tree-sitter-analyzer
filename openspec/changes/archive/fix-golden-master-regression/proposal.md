# Proposal: Fix Golden Master Regression

## Change ID
`fix-golden-master-regression`

## Status
DRAFT

## Problem Statement

Golden master test data files have incorrect header formats and inconsistent package/class name representations after recent changes. This creates test failures and mismatches between expected and actual output formats.

### Specific Issues

1. **java_sample_compact.md**
   - Current (Wrong): `# com.example.Sample.java`
   - Expected: `# com.example.AbstractParentClass`
   - Issue: Using filename instead of actual class name

2. **java_userservice_compact_format.md**
   - Current (Wrong): `# UserService`
   - Expected: `# com.example.service.UserService` (or appropriate package.class format)
   - Issue: Missing package information

3. **javascript_class_compact.md**
   - Current (Wrong): `# unknown.Animal`
   - Issue: Using "unknown" as package name for JavaScript files

4. **typescript_enum_compact.md**
   - Current (Wrong): `# unknown.Color`
   - Issue: Using "unknown" as package name for TypeScript files

5. **java_bigservice_full.md**
   - Issue: Format structure was changed, breaking compatibility
   - Expected: Maintain original format structure

6. **python_sample_full.md**
   - Issue: Specification improvements made but inconsistent with existing format

## Root Cause Analysis

The issue stems from the title generation logic in `table_formatter.py`:

### Compact Format (Lines 454-465)
```python
def _format_compact_table(self, data: dict[str, Any]) -> str:
    """Compact table format"""
    lines = []
    
    # Header
    package_name = (data.get("package") or {}).get("name", "unknown")
    classes = data.get("classes", [])
    if classes is None:
        classes = []
    class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
    lines.append(f"# {package_name}.{class_name}")
```

**Problems:**
- Always uses `package_name.class_name` format, even when inappropriate
- Defaults to "unknown" for missing package names
- Doesn't handle multiple classes or special cases properly
- JavaScript/TypeScript files shouldn't use package notation

### Full Format (Lines 60-102)
```python
def _format_full_table(self, data: dict[str, Any]) -> str:
    """Full table format - organized by class"""
    lines = []
    
    # Header - use package.class format for single class, filename for multi-class files
    classes = data.get("classes", [])
    # ... complex logic ...
```

**Problems:**
- Complex conditional logic that doesn't cover all cases
- Inconsistent handling of different languages
- Recent changes broke existing behavior

## Proposed Solution

Fix the title generation logic in `table_formatter.py` to:

1. **Respect language-specific conventions**
   - Java: Use `package.ClassName` for single class files
   - Python: Use `Module: filename` format
   - JavaScript/TypeScript: Use just `ClassName` without package prefix
   
2. **Handle edge cases properly**
   - Multiple classes: Use filename
   - No classes: Use filename or appropriate fallback
   - Missing package: Don't force "unknown" prefix

3. **Maintain backward compatibility**
   - Keep existing format structures for full format
   - Preserve section headings and organization

4. **Update golden master files**
   - Restore correct titles based on actual class/module names
   - Ensure consistency across all test files

## Impact Assessment

### Benefits
- ✅ Fixes broken golden master tests
- ✅ Improves output format consistency
- ✅ Better handles multi-language scenarios
- ✅ More maintainable title generation logic

### Risks
- ⚠️ May require updating other test files if format changes
- ⚠️ Need to verify all golden master files are correct

### Scope
- **Modified Components**: `table_formatter.py`, golden master test files
- **Test Coverage**: Existing golden master tests, format validation tests
- **Breaking Changes**: None (fixing regression, not introducing new behavior)

## Success Criteria

1. All golden master test files have correct titles matching their content
2. Title generation logic handles all supported languages appropriately
3. No "unknown" package prefixes for JavaScript/TypeScript files
4. Full format maintains original structure and organization
5. All existing tests pass with updated golden masters

## Dependencies

- Requires understanding of current golden master test framework
- May need to coordinate with format testing strategy changes

## Related Changes

- Related to: `fix-analyze-code-structure-format-regression`
- Related to: `implement-comprehensive-format-testing-strategy`

## References

- `tests/golden_masters/compact/` - Compact format golden masters
- `tests/golden_masters/full/` - Full format golden masters
- `tree_sitter_analyzer/table_formatter.py` - Title generation logic

