# Requirements Document: Formatter Architecture Unification

## Introduction

Unifies the three parallel formatter systems into a single, cohesive architecture. The current codebase has accumulated technical debt with `TableFormatter`, `LegacyTableFormatter`, and `FormatterRegistry` systems coexisting, along with duplicate factory classes. This refactoring eliminates redundancy while maintaining backward compatibility for v1.6.1.4 format output.

## Terminology

- **FormatterRegistry**: The new unified registry pattern for managing all formatters
- **IFormatter**: Interface that all formatters must implement
- **BaseTableFormatter**: Abstract base class for language-specific table formatters
- **Legacy Formatter**: Original v1.6.1.4 compatible formatter implementation
- **Factory Pattern**: Design pattern for creating formatter instances

## Current Architecture Problems

### Problem 1: Three Parallel Formatter Systems

| System | File | Purpose |
|--------|------|---------|
| TableFormatter | `table_formatter.py` | Original table formatting |
| LegacyTableFormatter | `legacy_table_formatter.py` | v1.6.1.4 compatibility layer |
| FormatterRegistry | `formatters/formatter_registry.py` | New registry-based system |

### Problem 2: Duplicate Factory Classes

| Factory | File | Creates |
|---------|------|---------|
| TableFormatterFactory | `formatters/formatter_factory.py` | BaseTableFormatter subclasses |
| LanguageFormatterFactory | `formatters/language_formatter_factory.py` | BaseFormatter subclasses |

### Problem 3: Complex Strategy Selection

The `formatter_config.py` maintains a complex mapping of which languages use "legacy" vs "new" formatters, adding unnecessary complexity.

## Requirements

### Requirement 1: Unified Formatter Interface

**User Story:** As a developer, I want all formatters to implement the same interface, so that I can use them interchangeably.

#### Acceptance Criteria

1. WHEN creating a new formatter THEN it SHALL implement the `IFormatter` interface
2. WHEN using any formatter THEN the `format()` method SHALL accept CodeElement lists
3. WHEN registering a formatter THEN it SHALL be accessible via `FormatterRegistry`
4. WHEN querying available formats THEN all registered formatters SHALL be listed

### Requirement 2: Single Factory System

**User Story:** As a developer, I want one factory to create all formatters, so that formatter instantiation is consistent.

#### Acceptance Criteria

1. WHEN creating a language formatter THEN `FormatterRegistry.get_formatter()` SHALL be used
2. WHEN `TableFormatterFactory` is referenced THEN it SHALL be deprecated/removed
3. WHEN `LanguageFormatterFactory` is referenced THEN it SHALL delegate to `FormatterRegistry`
4. WHEN backward compatibility is needed THEN wrapper functions SHALL exist

### Requirement 3: Eliminate Code Duplication

**User Story:** As a maintainer, I want no duplicate formatter implementations, so that bug fixes apply everywhere.

#### Acceptance Criteria

1. WHEN comparing `TableFormatter` and `LegacyTableFormatter` THEN only ONE SHALL remain
2. WHEN common formatting logic exists THEN it SHALL be in `BaseTableFormatter`
3. WHEN CSV formatting is needed THEN the implementation SHALL exist in ONE place
4. WHEN platform newline conversion is needed THEN ONE helper method SHALL be used

### Requirement 4: Simplified Configuration

**User Story:** As a developer, I want formatter selection to be straightforward, so that I don't need complex strategy patterns.

#### Acceptance Criteria

1. WHEN selecting a formatter THEN language detection SHALL be automatic
2. WHEN `formatter_config.py` strategy mapping is used THEN it SHALL be simplified or removed
3. WHEN `FormatterSelector` is used THEN it SHALL have minimal logic
4. WHEN a language has no specific formatter THEN a sensible default SHALL be used

### Requirement 5: Backward Compatibility

**User Story:** As a user, I want existing output formats to remain unchanged, so that my integrations don't break.

#### Acceptance Criteria

1. WHEN using `full` format THEN output SHALL match v1.6.1.4 specification
2. WHEN using `compact` format THEN output SHALL match v1.6.1.4 specification
3. WHEN using `csv` format THEN output SHALL match v1.6.1.4 specification
4. WHEN MCP tools call formatters THEN existing behavior SHALL be preserved
5. WHEN CLI commands call formatters THEN existing behavior SHALL be preserved

### Requirement 6: Clean Public API

**User Story:** As an API consumer, I want a clean, documented API, so that I can easily integrate formatters.

#### Acceptance Criteria

1. WHEN importing formatters THEN `FormatterRegistry` SHALL be the primary entry point
2. WHEN deprecated classes are used THEN deprecation warnings SHALL be emitted
3. WHEN reading documentation THEN the unified architecture SHALL be explained
4. WHEN `__init__.py` exports formatters THEN only the new API SHALL be exposed

## Out of Scope

- Adding new output formats (focus is on unification, not new features)
- Changing output format specifications (v1.6.1.4 compatibility must be maintained)
- Modifying language detection logic
- Changing MCP tool interfaces

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Formatter files | 6+ | 3-4 |
| Factory classes | 2 | 1 |
| Lines of duplicate code | ~500 | 0 |
| Strategy configuration lines | 250+ | <50 |
| Test coverage | Maintained | ≥ Current |

