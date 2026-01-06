# Implementation Plan: Formatter Architecture Unification

## Phase 1: Enhance FormatterRegistry

- [x] 1.1 Add `get_formatter_for_language(language, format_type)` method to FormatterRegistry
- [x] 1.2 Add `register_language_formatter(language, format_type, formatter_class)` method
- [x] 1.3 Add language-to-formatter mapping data structure
- [x] 1.4 Update `register_builtin_formatters()` to register language-specific formatters
- [x] 1.5 Checkpoint - Run existing tests to ensure no regressions

## Phase 2: Consolidate TableFormatter

- [x] 2.1 Make `LegacyTableFormatter` implement `IFormatter` interface (via registry registration)
- [x] 2.2 Add `get_format_name()` static method to LegacyTableFormatter (via adapters)
- [x] 2.3 Add `format(elements: list[CodeElement])` method to LegacyTableFormatter (via adapters)
- [x] 2.4 Register LegacyTableFormatter variants in FormatterRegistry
- [x] 2.5 Checkpoint - Verify formatter output matches v1.6.1.4 spec

## Phase 3: Create Compatibility Layer

- [x] 3.1 Create `formatters/compat.py` with deprecated wrapper functions
- [x] 3.2 Add `create_table_formatter()` wrapper with deprecation warning
- [x] 3.3 Add `TableFormatterFactory` wrapper class with deprecation warning
- [x] 3.4 Add `LanguageFormatterFactory` wrapper class with deprecation warning
- [x] 3.5 Checkpoint - Verify deprecation warnings are emitted

## Phase 4: Update MCP Tools

- [x] 4.1 Update `analyze_code_structure_tool.py` to use FormatterRegistry
- [x] 4.2 Remove direct import of LegacyTableFormatter in MCP tools
- [x] 4.3 Update any other MCP tools that use formatters
- [x] 4.4 Run MCP tool tests
- [x] 4.5 Checkpoint - Verify MCP tool output unchanged

## Phase 5: Update CLI Commands

- [x] 5.1 Update `table_command.py` to use FormatterRegistry
- [x] 5.2 Remove import of FormatterSelector in CLI commands
- [x] 5.3 Update any other CLI commands that use formatters
- [x] 5.4 Run CLI command tests
- [x] 5.5 Checkpoint - Verify CLI output unchanged

## Phase 6: Delete Redundant Files (DEFERRED)

Note: File deletion is deferred to maintain backward compatibility during transition period.
The compat.py module provides deprecation warnings for old APIs.

- [ ] 6.1 Delete `tree_sitter_analyzer/table_formatter.py` (DEFERRED)
- [ ] 6.2 Delete `tree_sitter_analyzer/formatters/formatter_factory.py` (DEFERRED)
- [ ] 6.3 Delete `tree_sitter_analyzer/formatters/formatter_config.py` (DEFERRED)
- [ ] 6.4 Delete `tree_sitter_analyzer/formatters/formatter_selector.py` (DEFERRED)
- [ ] 6.5 Delete `tree_sitter_analyzer/formatters/legacy_formatter_adapters.py` (DEFERRED)
- [ ] 6.6 Checkpoint - Verify no import errors (DEFERRED)

## Phase 7: Relocate and Rename (DEFERRED)

Note: Renaming is deferred to maintain backward compatibility.

- [ ] 7.1 Move `legacy_table_formatter.py` to `formatters/table_formatter.py` (DEFERRED)
- [ ] 7.2 Rename class from `LegacyTableFormatter` to `TableFormatter` (DEFERRED)
- [ ] 7.3 Update all imports referencing the old location (DEFERRED)
- [x] 7.4 Update `formatters/__init__.py` to export unified API
- [x] 7.5 Checkpoint - Run full test suite

## Phase 8: Update Tests

- [x] 8.1 Update test imports to use new module paths (tests updated for new assertions)
- [ ] 8.2 Remove tests for deleted classes (DEFERRED - classes not yet deleted)
- [x] 8.3 Add tests for FormatterRegistry.get_formatter_for_language()
- [ ] 8.4 Add tests for deprecation warnings (OPTIONAL)
- [x] 8.5 Checkpoint - All tests pass

## Phase 9: Documentation and Cleanup

- [x] 9.1 Update `formatters/__init__.py` with proper exports
- [x] 9.2 Update docstrings to reflect unified architecture
- [x] 9.3 Remove obsolete comments referencing old architecture
- [ ] 9.4 Update any documentation files referencing old classes (OPTIONAL)
- [x] 9.5 Final checkpoint - Full test suite passes, no lint errors

## Verification Checklist

### Output Compatibility

- [ ] `full` format output matches v1.6.1.4 spec
- [ ] `compact` format output matches v1.6.1.4 spec
- [ ] `csv` format output matches v1.6.1.4 spec
- [ ] `json` format output is valid JSON
- [ ] `toon` format output is valid TOON

### API Compatibility

- [ ] `FormatterRegistry.get_formatter()` works for all formats
- [ ] `FormatterRegistry.get_formatter_for_language()` works for all languages
- [ ] Deprecated functions emit warnings but still work
- [ ] No breaking changes to public API

### Code Quality

- [ ] No duplicate code between formatter implementations
- [ ] All formatters implement IFormatter interface
- [ ] No circular import issues
- [ ] Ruff linting passes
- [ ] MyPy type checking passes

## Rollback Points

| Phase | Rollback Action |
|-------|-----------------|
| Phase 1-3 | No action needed, only additions |
| Phase 4-5 | Revert consumer changes, restore old imports |
| Phase 6 | Restore deleted files from git |
| Phase 7 | Restore old file locations, update imports |

