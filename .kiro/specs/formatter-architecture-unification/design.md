# Design: Formatter Architecture Unification

## Overview

Consolidates three parallel formatter systems into a unified architecture based on `FormatterRegistry`. This design eliminates code duplication, simplifies the factory pattern, and maintains v1.6.1.4 backward compatibility.

## Architecture Comparison

### Current State (Problematic)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CURRENT ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐   ┌─────────────────────┐   ┌──────────────┐  │
│  │  TableFormatter  │   │ LegacyTableFormatter│   │ Formatter    │  │
│  │  (783 lines)     │   │ (861 lines)         │   │ Registry     │  │
│  │  table_formatter │   │ legacy_table_       │   │ (386 lines)  │  │
│  │  .py             │   │ formatter.py        │   │              │  │
│  └────────┬─────────┘   └──────────┬──────────┘   └──────┬───────┘  │
│           │                        │                      │          │
│           │    ~80% DUPLICATE      │                      │          │
│           │←──────────────────────→│                      │          │
│           │                        │                      │          │
│           │                        ▼                      │          │
│           │              ┌─────────────────────┐          │          │
│           │              │ LegacyFormatter     │          │          │
│           │              │ Adapters (229 lines)│──────────┘          │
│           │              └─────────────────────┘                     │
│           │                                                          │
│  ┌────────┴─────────┐   ┌─────────────────────┐                     │
│  │TableFormatter    │   │LanguageFormatter    │                     │
│  │Factory           │   │Factory              │                     │
│  │(85 lines)        │   │(135 lines)          │                     │
│  └──────────────────┘   └─────────────────────┘                     │
│           │                        │                                 │
│           │    DUPLICATE PURPOSE   │                                 │
│           │←──────────────────────→│                                 │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                  formatter_config.py (275 lines)                ││
│  │                  Complex legacy/new strategy mapping            ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                  formatter_selector.py (97 lines)               ││
│  │                  Strategy selection logic                       ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘

Total: ~2,850 lines across 7 files
```

### Target State (Unified)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TARGET ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    FormatterRegistry (Enhanced)                 ││
│  │                    formatters/formatter_registry.py             ││
│  │                                                                 ││
│  │  - register_formatter(formatter_class)                          ││
│  │  - get_formatter(format_name) -> IFormatter                     ││
│  │  - get_formatter_for_language(language, format) -> IFormatter   ││
│  │  - get_available_formats() -> list[str]                         ││
│  │  - is_format_supported(format_name) -> bool                     ││
│  └────────────────────────────────┬────────────────────────────────┘│
│                                   │                                  │
│                                   ▼                                  │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                      IFormatter Interface                       ││
│  │                                                                 ││
│  │  + get_format_name() -> str                                     ││
│  │  + format(elements: list[CodeElement]) -> str                   ││
│  └────────────────────────────────┬────────────────────────────────┘│
│                                   │                                  │
│           ┌───────────────────────┼───────────────────────┐         │
│           │                       │                       │         │
│           ▼                       ▼                       ▼         │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐    │
│  │ JsonFormatter  │    │FullFormatter   │    │ CsvFormatter   │    │
│  │ (built-in)     │    │(legacy compat) │    │ (legacy compat)│    │
│  └────────────────┘    └────────────────┘    └────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    BaseTableFormatter                           ││
│  │                    formatters/base_formatter.py                 ││
│  │                                                                 ││
│  │  - Common formatting logic (CSV, newlines, signatures)          ││
│  │  - Abstract methods for language-specific formatting            ││
│  └────────────────────────────────┬────────────────────────────────┘│
│                                   │                                  │
│     ┌──────────┬──────────┬───────┴───────┬──────────┬──────────┐   │
│     ▼          ▼          ▼               ▼          ▼          ▼   │
│  ┌──────┐  ┌──────┐  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌──────┐│
│  │Java  │  │Python│  │JavaScript│  │TypeScript│  │ SQL  │  │ ...  ││
│  │Format│  │Format│  │Formatter │  │Formatter │  │Format│  │      ││
│  └──────┘  └──────┘  └──────────┘  └──────────┘  └──────┘  └──────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

Total: ~1,500 lines across 3-4 core files
```

## File Changes

### Files to DELETE

| File | Reason | Migration Path |
|------|--------|----------------|
| `table_formatter.py` | Duplicate of LegacyTableFormatter | Use `FormatterRegistry` |
| `formatters/formatter_factory.py` | Replaced by FormatterRegistry | Use `FormatterRegistry` |
| `formatters/formatter_config.py` | Complex strategy no longer needed | Simplified in registry |
| `formatters/formatter_selector.py` | No longer needed with unified system | Use `FormatterRegistry` |
| `formatters/legacy_formatter_adapters.py` | Adapters no longer needed | Direct registration |

### Files to MODIFY

| File | Changes |
|------|---------|
| `formatters/formatter_registry.py` | Add `get_formatter_for_language()`, enhance registration |
| `formatters/base_formatter.py` | Consolidate common logic from TableFormatter |
| `legacy_table_formatter.py` | Rename to `formatters/table_formatter.py`, implement IFormatter |
| `formatters/language_formatter_factory.py` | Deprecate, delegate to FormatterRegistry |
| `mcp/tools/analyze_code_structure_tool.py` | Update to use FormatterRegistry |
| `cli/commands/table_command.py` | Update to use FormatterRegistry |
| `formatters/__init__.py` | Export unified API |

### Files to CREATE

| File | Purpose |
|------|---------|
| `formatters/compat.py` | Backward compatibility wrappers with deprecation warnings |

## Component Details

### 1. Enhanced FormatterRegistry

```python
# formatters/formatter_registry.py

class FormatterRegistry:
    """Unified registry for all formatters."""
    
    _formatters: dict[str, type[IFormatter]] = {}
    _language_formatters: dict[str, dict[str, type[IFormatter]]] = {}
    
    @classmethod
    def register_formatter(cls, formatter_class: type[IFormatter]) -> None:
        """Register a formatter by its format name."""
        format_name = formatter_class.get_format_name()
        cls._formatters[format_name] = formatter_class
    
    @classmethod
    def register_language_formatter(
        cls, 
        language: str, 
        format_type: str, 
        formatter_class: type[IFormatter]
    ) -> None:
        """Register a language-specific formatter."""
        if language not in cls._language_formatters:
            cls._language_formatters[language] = {}
        cls._language_formatters[language][format_type] = formatter_class
    
    @classmethod
    def get_formatter(cls, format_name: str) -> IFormatter:
        """Get formatter by format name."""
        if format_name not in cls._formatters:
            raise ValueError(f"Unknown format: {format_name}")
        return cls._formatters[format_name]()
    
    @classmethod
    def get_formatter_for_language(
        cls, 
        language: str, 
        format_type: str = "full"
    ) -> IFormatter:
        """Get formatter for specific language and format type."""
        # Check language-specific first
        lang_formatters = cls._language_formatters.get(language.lower(), {})
        if format_type in lang_formatters:
            return lang_formatters[format_type]()
        
        # Fall back to generic format
        if format_type in cls._formatters:
            return cls._formatters[format_type]()
        
        # Default to full format
        return cls._formatters.get("full", FullFormatter)()
```

### 2. Unified TableFormatter (from LegacyTableFormatter)

```python
# formatters/table_formatter.py (renamed from legacy_table_formatter.py)

class TableFormatter(IFormatter):
    """
    Unified table formatter implementing IFormatter interface.
    
    Provides v1.6.1.4 compatible output for full, compact, and CSV formats.
    """
    
    def __init__(
        self,
        format_type: str = "full",
        language: str = "java",
        include_javadoc: bool = False,
    ):
        self.format_type = format_type
        self.language = language
        self.include_javadoc = include_javadoc
    
    @staticmethod
    def get_format_name() -> str:
        return "table"  # Generic name, format_type determines actual format
    
    def format(self, elements: list[CodeElement]) -> str:
        """Format CodeElement list (IFormatter interface)."""
        # Convert to legacy dict format and delegate
        structure_data = self._convert_elements_to_dict(elements)
        return self.format_structure(structure_data)
    
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """Format structure data (legacy interface)."""
        # Existing implementation from LegacyTableFormatter
        ...
```

### 3. Backward Compatibility Module

```python
# formatters/compat.py

import warnings
from .formatter_registry import FormatterRegistry

def create_table_formatter(
    format_type: str, 
    language: str = "java", 
    include_javadoc: bool = False
) -> Any:
    """
    DEPRECATED: Use FormatterRegistry.get_formatter_for_language() instead.
    
    Backward compatible function for creating table formatters.
    """
    warnings.warn(
        "create_table_formatter is deprecated. "
        "Use FormatterRegistry.get_formatter_for_language() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return FormatterRegistry.get_formatter_for_language(language, format_type)


class TableFormatterFactory:
    """
    DEPRECATED: Use FormatterRegistry instead.
    """
    
    @classmethod
    def create_formatter(cls, language: str, format_type: str = "full"):
        warnings.warn(
            "TableFormatterFactory is deprecated. "
            "Use FormatterRegistry.get_formatter_for_language() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return FormatterRegistry.get_formatter_for_language(language, format_type)
```

### 4. Updated Consumer Code

#### MCP Tool Update

```python
# mcp/tools/analyze_code_structure_tool.py

# Before:
from ...legacy_table_formatter import LegacyTableFormatter
legacy_formatter = LegacyTableFormatter(format_type=format_type, ...)

# After:
from ...formatters.formatter_registry import FormatterRegistry
formatter = FormatterRegistry.get_formatter_for_language(language, format_type)
```

#### CLI Command Update

```python
# cli/commands/table_command.py

# Before:
from ...formatters.formatter_selector import FormatterSelector
formatter = FormatterSelector.get_formatter(language, table_type)

# After:
from ...formatters.formatter_registry import FormatterRegistry
formatter = FormatterRegistry.get_formatter_for_language(language, table_type)
```

## Migration Strategy

### Phase 1: Preparation (No Breaking Changes)

1. Add new methods to `FormatterRegistry`
2. Ensure all tests pass
3. Create compatibility wrappers

### Phase 2: Internal Migration

1. Update MCP tools to use `FormatterRegistry`
2. Update CLI commands to use `FormatterRegistry`
3. Run full test suite

### Phase 3: Cleanup

1. Delete redundant files
2. Rename `legacy_table_formatter.py` to `formatters/table_formatter.py`
3. Update imports throughout codebase

### Phase 4: Deprecation

1. Add deprecation warnings to old APIs
2. Update documentation
3. Keep compat module for 1-2 releases

## Error Handling

| Scenario | Handling |
|----------|----------|
| Unknown format requested | Raise `ValueError` with available formats |
| Unknown language requested | Fall back to default formatter |
| Formatter registration conflict | Log warning, override existing |
| Import of deprecated class | Emit `DeprecationWarning` |

## Verification Strategy

### Unit Tests

1. Test `FormatterRegistry.get_formatter()` for all formats
2. Test `FormatterRegistry.get_formatter_for_language()` for all languages
3. Test backward compatibility wrappers emit warnings
4. Test output matches v1.6.1.4 specification

### Integration Tests

1. Run MCP tool tests with new architecture
2. Run CLI command tests with new architecture
3. Compare output before/after refactoring

### Regression Tests

1. Golden master tests for all format types
2. Cross-language formatting tests
3. Edge case tests (empty input, special characters)

## Rollback Plan

If issues are discovered:

1. Revert to commit before Phase 3 (files still exist)
2. Remove deprecation warnings
3. Restore original imports in consumer code

