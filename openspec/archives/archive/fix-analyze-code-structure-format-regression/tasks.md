# Tasks: Fix analyze_code_structure Format Regression

## Overview
Restore the original v1.6.1.4 format specifications for `analyze_code_structure` tool while maintaining the FormatterRegistry architecture.

## Task List

### Phase 1: Analysis and Documentation
- [x] **T1.1**: Document exact v1.6.1.4 format specifications
  - Extract original `full` format Markdown table structure
  - Document `compact` format with complexity information
  - Document simple `csv` format structure
  - Create reference output samples

- [x] **T1.2**: Analyze current v1.9.4 implementation gaps
  - Compare FormatterRegistry vs TableFormatter outputs
  - Identify specific format violations
  - Document breaking changes in detail

### Phase 2: Format Specification Restoration
- [x] **T2.1**: Create legacy-compatible formatters
  - Implement `LegacyFullFormatter` producing Markdown tables
  - Implement `LegacyCompactFormatter` with complexity scores
  - Implement `LegacyCsvFormatter` with simple structure
  - Ensure exact v1.6.1.4 output compatibility

- [x] **T2.2**: Update FormatterRegistry integration
  - Register legacy formatters for `full`, `compact`, `csv` formats
  - Maintain backward compatibility in `TableFormatTool`
  - Ensure proper fallback mechanisms

### Phase 3: HTML Format Separation
- [x] **T3.1**: Remove HTML formats from analyze_code_structure
  - Remove `html`, `html_compact`, `html_json` from supported formats
  - Update tool schema to exclude HTML formats
  - Update validation logic

- [ ] **T3.2**: Create separate HTML analysis tool (optional) - SKIPPED
  - Design `analyze_html_structure` tool for HTML-specific analysis
  - Move HTML formatters to dedicated tool
  - Update MCP server registration

### Phase 4: Testing and Validation
- [x] **T4.1**: Create format regression tests
  - Test `full` format produces exact Markdown tables
  - Test `compact` format includes complexity information
  - Test `csv` format maintains simple structure
  - Compare outputs with v1.6.1.4 reference samples

- [x] **T4.2**: Update existing test suite
  - Fix test expectations to match v1.6.1.4 formats
  - Remove HTML format tests from analyze_code_structure
  - Add comprehensive format validation tests

### Phase 5: Documentation and Cleanup
- [x] **T5.1**: Update tool documentation
  - Correct format specifications in tool schema
  - Update MCP tool descriptions
  - Document supported formats clearly

- [x] **T5.2**: Update CHANGELOG and migration guide
  - Document format restoration in CHANGELOG
  - Provide migration guide for v1.9.4 users
  - Explain HTML format removal

## Dependencies
- T1.1 must complete before T2.1
- T2.1 must complete before T2.2
- T3.1 must complete before T4.1
- T4.1 must complete before T5.1

## Validation Criteria
1. All `full` format outputs match v1.6.1.4 Markdown table structure
2. All `compact` format outputs include complexity scores in table format
3. All `csv` format outputs use simple structure compatible with v1.6.1.4
4. HTML formats are removed from `analyze_code_structure` tool
5. All existing integration tests pass with corrected expectations
6. No breaking changes for users expecting v1.6.1.4 format behavior

## Risk Mitigation
- Maintain FormatterRegistry architecture for future extensibility
- Provide clear migration documentation for v1.9.4 format users
- Consider deprecation warnings for removed HTML formats
- Ensure backward compatibility testing covers edge cases
