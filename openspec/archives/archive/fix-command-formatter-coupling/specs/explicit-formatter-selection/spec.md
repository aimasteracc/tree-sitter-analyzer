# Spec: Explicit Formatter Selection

## Capability
**explicit-formatter-selection**

## Overview
Implement explicit configuration-driven formatter selection to eliminate implicit coupling between command layer and formatter layer.

---

## ADDED Requirements

### Requirement: Formatter Configuration System
**Priority**: HIGH  
**Status**: ADDED

System must provide explicit configuration for which formatter to use for each language and format type.

#### Scenario: Configuration defines formatter strategy
**Given** a supported language and format type  
**When** looking up formatter strategy  
**Then** configuration returns either "legacy" or "new"  
**And** strategy is explicit, not implicit based on formatter existence

#### Scenario: Unknown language defaults safely
**Given** an unknown/unsupported language  
**When** looking up formatter strategy  
**Then** system defaults to "legacy" strategy  
**And** no errors are raised

#### Scenario: Per-language, per-format configuration
**Given** a language with mixed formatter usage  
**When** one format type uses "new" and another uses "legacy"  
**Then** each format type independently selects correct formatter  
**Example**:
```python
"java": {
    "table": "new",      # Uses new formatter
    "compact": "legacy",  # Uses legacy formatter
}
```

---

### Requirement: FormatterSelector Service
**Priority**: HIGH  
**Status**: ADDED

System must provide a service that selects appropriate formatter based on configuration.

#### Scenario: Select formatter for configured language
**Given** a language configured with strategy "legacy"  
**When** FormatterSelector.get_formatter() is called  
**Then** returns instance of legacy TableFormatter  
**And** passes through any kwargs (e.g., include_javadoc)

#### Scenario: Select new formatter for SQL
**Given** SQL is configured with strategy "new"  
**When** FormatterSelector.get_formatter("sql", "table") is called  
**Then** returns instance of SQLFormatterWrapper  
**And** formatter is ready to use

#### Scenario: Graceful fallback
**Given** a language configured with "new" strategy  
**When** new formatter doesn't exist in LanguageFormatterFactory  
**Then** falls back to legacy formatter  
**And** logs warning about fallback

---

### Requirement: Language-Specific Package Defaults
**Priority**: HIGH  
**Status**: ADDED

System must use language-appropriate defaults for package names, not universal "unknown".

#### Scenario: Java-like languages get "unknown" package
**Given** a Java/Kotlin/Scala file without package declaration  
**When** converting to structure format  
**Then** package_name is "unknown"

#### Scenario: JavaScript/TypeScript get empty package
**Given** a JavaScript or TypeScript file  
**When** converting to structure format  
**Then** package_name is "" (empty string)  
**And** output does NOT include "unknown" prefix

#### Scenario: Python gets empty package
**Given** a Python file  
**When** converting to structure format  
**Then** package_name is ""  
**And** uses "Module: filename" format instead

---

## MODIFIED Requirements

### Requirement: TableCommand Formatter Selection
**Priority**: HIGH  
**Status**: MODIFIED

TableCommand must use explicit formatter selection instead of implicit checks.

#### Scenario: Use FormatterSelector instead of implicit check
**Given** TableCommand needs to format output  
**When** executing analysis  
**Then** calls FormatterSelector.get_formatter(language, format_type)  
**And** does NOT check if formatter exists before using it  
**And** behavior is configuration-driven, not existence-driven

#### Scenario: Old behavior for Java preserved
**Given** Java is configured with "legacy" strategy  
**When** running table command on Java file  
**Then** output format is identical to previous version  
**And** no golden master tests fail

#### Scenario: New languages don't affect old ones
**Given** SQL added to configuration with "new" strategy  
**When** running table command on Java/Python/JS/TS files  
**Then** output is unchanged from before SQL was added  
**And** isolation is maintained

---

### Requirement: Remove Dead Code from Other Commands
**Priority**: MEDIUM  
**Status**: MODIFIED

Commands that don't use formatter selection must have unused code removed.

#### Scenario: AdvancedCommand cleanup
**Given** AdvancedCommand has unused _convert_to_formatter_format() method  
**When** method is removed  
**Then** all tests still pass  
**And** command functionality unchanged

#### Scenario: StructureCommand cleanup
**Given** StructureCommand has unused _convert_to_formatter_format() method  
**When** method is removed  
**Then** all tests still pass

#### Scenario: SummaryCommand cleanup
**Given** SummaryCommand has unused _convert_to_formatter_format() method  
**When** method is removed  
**Then** all tests still pass

---

## REMOVED Requirements

### Requirement: Implicit Formatter Detection
**Priority**: N/A  
**Status**: REMOVED

The pattern of "if create_language_formatter() returns formatter, use it" is removed.

#### Scenario: No more implicit checks
**Given** any command that formats output  
**When** selecting formatter  
**Then** does NOT use pattern: `if formatter: use_new() else: use_old()`  
**And** uses FormatterSelector instead

---

## Validation Criteria

### Correctness
- [ ] FormatterSelector returns correct formatter for each language
- [ ] Configuration covers all supported languages
- [ ] No "unknown" package for JavaScript/TypeScript/Python
- [ ] All golden master tests pass

### Isolation
- [ ] Adding new language to config doesn't change old language output
- [ ] Each language's formatter selection is independent
- [ ] Test: Add dummy language, verify old outputs unchanged

### Completeness
- [ ] All format types covered in configuration
- [ ] All commands updated to use FormatterSelector (or don't use formatters)
- [ ] Dead code removed

### Performance
- [ ] FormatterSelector adds negligible overhead (<1ms)
- [ ] No runtime performance degradation

---

## Dependencies

- Depends on: Existing formatter systems (both legacy and new)
- Related to: `fix-golden-master-regression` (this fixes root cause)
- Tested by: Unit tests, integration tests, golden master tests

---

## Migration Guidelines

### For Adding New Language

1. **Add to LanguageFormatterFactory** (if using new system)
2. **Add to LANGUAGE_FORMATTER_CONFIG**:
   ```python
   "newlang": {
       "table": "new",  # or "legacy"
       "compact": "new",
       "full": "new",
       "csv": "new",
       "json": "new",
   }
   ```
3. **Test**: Verify old language outputs unchanged

### For Migrating Existing Language

1. **Create new formatter** for the language
2. **Update config** gradually:
   ```python
   "java": {
       "table": "new",      # Migrate one at a time
       "compact": "legacy",
       "full": "legacy",
       ...
   }
   ```
3. **Test thoroughly** before migrating next format type

---

## References

- Implementation: `tree_sitter_analyzer/formatters/formatter_selector.py`
- Configuration: `tree_sitter_analyzer/formatters/formatter_config.py`
- Usage: `tree_sitter_analyzer/cli/commands/table_command.py`
- Tests: `tests/test_formatter_selector.py`

