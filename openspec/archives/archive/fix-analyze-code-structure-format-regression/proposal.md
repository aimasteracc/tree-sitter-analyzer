# Fix analyze_code_structure Format Regression

## Overview

The `analyze_code_structure` tool has experienced significant format regression between v1.6.1.4 and v1.9.4, breaking backward compatibility and violating the original specification.

## Problem Statement

### Version Comparison

**v1.6.1.4 (Correct Implementation)**:
- `full`: Markdown table format with proper structure
- `compact`: Markdown table format with complexity information
- `csv`: Simple CSV structure
- Supported formats: `["full", "compact", "csv"]`

**v1.9.4 (Broken Implementation)**:
- `full`: Plain text format (specification violation)
- `compact`: Plain text list format without complexity information
- `csv`: Complex CSV structure with detailed parameters/modifiers
- Supported formats: `["html_compact", "html_json", "full", "compact", "csv", "json", "html"]`

### Specific Issues

1. **Full Format Complete Breakdown**
   - v1.6.1.4: Proper Markdown table format
   - v1.9.4: Plain text format with `=` separators (specification violation)

2. **Compact Format Inconsistency**
   - v1.6.1.4: Markdown table with complexity scores
   - v1.9.4: Plain text list without complexity information

3. **CSV Format Structure Change**
   - v1.6.1.4: Simple CSV structure
   - v1.9.4: Complex CSV with detailed parameter/modifier breakdown

4. **Unauthorized Format Addition**
   - HTML formats (`html`, `html_compact`, `html_json`) were added without specification
   - These formats are not part of the original `analyze_code_structure` specification

## Root Cause

The introduction of `FormatterRegistry` in v1.9.4 replaced the legacy `TableFormatter` implementation, but the new formatters produce completely different output formats that violate the original specification.

## Impact

- **Breaking Change**: Existing integrations expecting Markdown table format will fail
- **Specification Violation**: Tool no longer produces documented output formats
- **Feature Regression**: Loss of complexity information in compact format
- **Compatibility Issues**: CSV structure changes break parsing logic

## Proposed Solution

Restore the original v1.6.1.4 format specifications while maintaining the new FormatterRegistry architecture for extensibility.

## Success Criteria

1. `full` format produces Markdown tables identical to v1.6.1.4
2. `compact` format includes complexity information in Markdown table format
3. `csv` format maintains simple structure compatible with v1.6.1.4
4. HTML formats are moved to separate tools or clearly marked as experimental
5. All existing tests pass with corrected format expectations

## Related Issues

- Backward compatibility with existing MCP integrations
- Documentation updates required for format specifications
- Test suite updates to reflect correct format expectations
