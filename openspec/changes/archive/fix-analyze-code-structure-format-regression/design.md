# Design: Fix analyze_code_structure Format Regression

## Architecture Overview

This change restores the original v1.6.1.4 format specifications while maintaining the FormatterRegistry architecture introduced in v1.9.4 for future extensibility.

## Current Architecture Analysis

### v1.6.1.4 (Legacy TableFormatter)
```
TableFormatTool -> TableFormatter -> format_structure()
                                  -> _format_full_table()    # Markdown tables
                                  -> _format_compact_table() # Markdown with complexity
                                  -> _format_csv()           # Simple CSV
```

### v1.9.4 (FormatterRegistry)
```
TableFormatTool -> FormatterRegistry -> FullFormatter      # Plain text (WRONG)
                                     -> CompactFormatter    # Plain text list (WRONG)
                                     -> CsvFormatter        # Complex CSV (WRONG)
                                     -> HtmlFormatter       # Unauthorized addition
```

## Proposed Solution Architecture

### Hybrid Approach: Legacy Compatibility + Registry Extensibility

```
TableFormatTool -> Format Decision Logic
                -> Legacy Formats (full, compact, csv)
                   -> LegacyTableFormatter (restored v1.6.1.4 logic)
                -> Extended Formats (html_*, json)
                   -> FormatterRegistry -> New formatters
```

## Implementation Strategy

### 1. Legacy Format Restoration

Create `LegacyTableFormatter` class that exactly replicates v1.6.1.4 behavior:

```python
class LegacyTableFormatter:
    """Restored v1.6.1.4 TableFormatter implementation"""
    
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        if self.format_type == "full":
            return self._format_full_table(structure_data)  # Markdown tables
        elif self.format_type == "compact":
            return self._format_compact_table(structure_data)  # Markdown + complexity
        elif self.format_type == "csv":
            return self._format_csv(structure_data)  # Simple CSV
```

### 2. Format Decision Logic

Update `TableFormatTool.execute()` to use appropriate formatter:

```python
async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
    format_type = args.get("format_type", "full")
    
    # Legacy formats: use restored v1.6.1.4 implementation
    if format_type in ["full", "compact", "csv"]:
        legacy_formatter = LegacyTableFormatter(format_type)
        table_output = legacy_formatter.format_structure(structure_dict)
    
    # Extended formats: use FormatterRegistry (future extensibility)
    elif FormatterRegistry.is_format_supported(format_type):
        registry_formatter = FormatterRegistry.get_formatter(format_type)
        table_output = registry_formatter.format(structure_result.elements)
    
    else:
        raise ValueError(f"Unsupported format: {format_type}")
```

### 3. Schema Updates

Update tool schema to reflect correct supported formats:

```python
def get_tool_schema(self) -> dict[str, Any]:
    return {
        "properties": {
            "format_type": {
                "enum": ["full", "compact", "csv"],  # Remove HTML formats
                "default": "full",
            }
        }
    }
```

## Format Specifications

### Full Format (Markdown Table)
```markdown
# ClassName

## Package
`com.example.package`

## Class Info
| Property | Value |
|----------|-------|
| Package | com.example.package |
| Type | class |
| Visibility | public |
| Lines | 1-50 |
| Total Methods | 5 |
| Total Fields | 3 |

## ClassName (1-50)

### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| field1 | String | private | final | 10 | Field documentation |

### Methods
| Name | Return | Vis | Modifiers | Params | Line | Complexity | Doc |
|------|--------|-----|-----------|--------|------|------------|-----|
| method1 | void | public | | String param | 20 | 2 | Method documentation |
```

### Compact Format (Markdown Table with Complexity)
```markdown
# Code Structure Summary

## Methods
| Name | Type | Visibility | Lines | Complexity | Parameters |
|------|------|------------|-------|------------|------------|
| method1 | void | public | 20-25 | 2 | String param |

## Fields
| Name | Type | Visibility | Lines |
|------|------|------------|-------|
| field1 | String | private | 10 |
```

### CSV Format (Simple Structure)
```csv
Type,Name,Visibility,Lines,Complexity,Parameters
method,method1,public,20-25,2,"String param"
field,field1,private,10,,
```

## Migration Strategy

### Phase 1: Backward Compatibility
1. Restore v1.6.1.4 formats for `full`, `compact`, `csv`
2. Remove HTML formats from `analyze_code_structure`
3. Update tests to expect correct formats

### Phase 2: Future Extensibility
1. Keep FormatterRegistry for new format types
2. Consider separate tools for HTML analysis
3. Maintain clear separation between core and extended formats

## Risk Mitigation

### Breaking Changes
- **Risk**: Users expecting v1.9.4 plain text formats
- **Mitigation**: Provide migration guide and deprecation warnings

### Format Consistency
- **Risk**: Inconsistency between legacy and registry formatters
- **Mitigation**: Comprehensive test suite with reference outputs

### Performance Impact
- **Risk**: Dual formatter system overhead
- **Mitigation**: Minimal impact due to format decision at execution time

## Testing Strategy

### Reference Output Validation
1. Create reference output files from v1.6.1.4
2. Compare current outputs with references
3. Ensure exact format matching

### Regression Testing
1. Test all supported programming languages
2. Test edge cases (empty files, complex structures)
3. Validate metadata extraction consistency

### Integration Testing
1. Test MCP server integration
2. Test CLI compatibility
3. Test file output functionality

## Future Considerations

### HTML Format Support
- Move to separate `analyze_html_structure` tool
- Maintain HTML formatters in FormatterRegistry
- Clear separation of concerns

### Format Extensibility
- Keep FormatterRegistry for future format additions
- Define clear interface for new formatters
- Maintain backward compatibility guarantees

### Documentation
- Update tool documentation with correct format examples
- Provide migration guide for v1.9.4 users
- Document format specification clearly
