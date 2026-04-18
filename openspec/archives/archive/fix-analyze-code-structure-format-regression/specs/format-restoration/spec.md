# Specification: Format Restoration for analyze_code_structure

## Overview

This specification defines the requirements for restoring the original v1.6.1.4 format behavior in the `analyze_code_structure` tool while maintaining architectural improvements from v1.9.4.

## MODIFIED Requirements

### Requirement FR-001: Full Format Markdown Table Output
The `analyze_code_structure` tool MUST produce Markdown table format when `format_type="full"` is specified.

#### Scenario: Single Class Analysis
**Given** a Java file with a single class containing methods and fields  
**When** `analyze_code_structure` is called with `format_type="full"`  
**Then** the output MUST be a Markdown document with:
- Header: `# ClassName` or `# package.ClassName`
- Package section: `## Package` with backtick-wrapped package name
- Class Info table with properties (Package, Type, Visibility, Lines, Total Methods, Total Fields)
- Detailed class section with Fields and Methods tables
- All tables MUST use proper Markdown table syntax with `|` separators

#### Scenario: Multi-Class Analysis
**Given** a Java file with multiple classes  
**When** `analyze_code_structure` is called with `format_type="full"`  
**Then** the output MUST include:
- Header with filename instead of single class name
- Classes Overview table listing all classes
- Individual class detail sections for each class

### Requirement FR-002: Compact Format with Complexity Information
The `analyze_code_structure` tool MUST produce compact Markdown table format with complexity scores when `format_type="compact"` is specified.

#### Scenario: Compact Format Output
**Given** any source code file with methods and fields  
**When** `analyze_code_structure` is called with `format_type="compact"`  
**Then** the output MUST be a Markdown document with:
- Header: `# Code Structure Summary`
- Methods table including Name, Type, Visibility, Lines, Complexity, Parameters columns
- Fields table including Name, Type, Visibility, Lines columns
- Complexity scores MUST be included for all methods
- All tables MUST use proper Markdown table syntax

### Requirement FR-003: Simple CSV Format Structure
The `analyze_code_structure` tool MUST produce simple CSV format when `format_type="csv"` is specified.

#### Scenario: CSV Format Output
**Given** any source code file with code elements  
**When** `analyze_code_structure` is called with `format_type="csv"`  
**Then** the output MUST be valid CSV with:
- Header row: `Type,Name,Visibility,Lines,Complexity,Parameters`
- Data rows for each code element
- Simple parameter representation (comma-separated in quotes if multiple)
- No complex nested structures or detailed modifier breakdowns

### Requirement FR-004: Supported Format Restriction
The `analyze_code_structure` tool MUST only support the original three format types.

#### Scenario: Format Type Validation
**Given** the `analyze_code_structure` tool  
**When** the tool schema is queried  
**Then** the `format_type` enum MUST contain exactly: `["full", "compact", "csv"]`  
**And** HTML formats (`html`, `html_compact`, `html_json`) MUST NOT be supported

#### Scenario: Invalid Format Rejection
**Given** the `analyze_code_structure` tool  
**When** called with `format_type="html"` or any HTML variant  
**Then** the tool MUST raise a ValueError indicating unsupported format

### Requirement FR-005: Legacy Compatibility Preservation
The tool MUST maintain exact output compatibility with v1.6.1.4 for all supported formats.

#### Scenario: Output Format Validation
**Given** identical input files used in v1.6.1.4 testing  
**When** `analyze_code_structure` is executed with each supported format  
**Then** the output MUST match v1.6.1.4 reference outputs exactly
- Line endings MUST be consistent
- Table formatting MUST be identical
- Metadata extraction MUST produce same results

## ADDED Requirements

### Requirement FR-006: Hybrid Formatter Architecture
The implementation MUST use a hybrid approach combining legacy compatibility with registry extensibility.

#### Scenario: Format Decision Logic
**Given** the `analyze_code_structure` tool execution  
**When** a format type is specified  
**Then** the tool MUST:
- Use `LegacyTableFormatter` for `full`, `compact`, `csv` formats
- Maintain `FormatterRegistry` architecture for future extensibility
- Provide clear separation between legacy and extended formats

### Requirement FR-007: Error Handling Consistency
Error handling MUST remain consistent with v1.6.1.4 behavior while improving error messages.

#### Scenario: File Not Found Error
**Given** a non-existent file path  
**When** `analyze_code_structure` is called  
**Then** the tool MUST raise `FileNotFoundError` with clear message

#### Scenario: Invalid Format Error
**Given** an unsupported format type  
**When** `analyze_code_structure` is called  
**Then** the tool MUST raise `ValueError` listing available formats

## REMOVED Requirements

### Requirement FR-008: HTML Format Support Removal
HTML format support MUST be completely removed from `analyze_code_structure`.

#### Scenario: HTML Format Cleanup
**Given** the current v1.9.4 implementation  
**When** the format restoration is applied  
**Then** all HTML-related formatters MUST be removed from the tool
- `HtmlFormatter`, `HtmlCompactFormatter`, `HtmlJsonFormatter` MUST NOT be accessible
- Tool schema MUST NOT include HTML format options
- Error messages MUST NOT suggest HTML formats as alternatives

## Cross-References

- Related to: **Security Requirements** (path validation must be maintained)
- Related to: **Performance Requirements** (format decision overhead must be minimal)
- Related to: **Testing Requirements** (comprehensive format validation testing required)

## Validation Criteria

1. All format outputs match v1.6.1.4 reference samples exactly
2. Tool schema reflects only supported formats: `["full", "compact", "csv"]`
3. HTML formats are completely inaccessible through `analyze_code_structure`
4. Error handling maintains v1.6.1.4 compatibility
5. Performance impact of hybrid architecture is negligible
6. All existing integration tests pass with corrected format expectations
