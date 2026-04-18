# Design: Explicit Formatter Selection Architecture

## Overview

This document describes the architectural solution to fix command-formatter coupling that causes regressions when adding new language support.

---

## Problem Analysis

### Current Architecture (Flawed)

```
┌─────────────────┐
│  TableCommand   │
└────────┬────────┘
         │
         ├──→ create_language_formatter(lang) → formatter?
         │         ↓ YES                    ↓ NO
         │    Use New Formatter        Use Old Formatter
         │         │                         │
         ├─────────┴─────────────────────────┘
         ↓
    Format Output
```

**Problem**: Decision is implicit - "if formatter exists, use it"

### Issues with Current Design

1. **Tight Coupling**: Command决策 依赖于 LanguageFormatterFactory 的内容
2. **全局影响**: 添加新语言 → 影响所有语言的输出
3. **不可预测**: 开发者无法知道添加语言会影响什么
4. **测试脆弱**: Golden master 测试随新语言添加而失败

---

## Proposed Architecture

### New Design: Explicit Configuration

```
┌──────────────────────────────────────┐
│   LANGUAGE_FORMATTER_CONFIG          │
│   {                                  │
│     "java": {"table": "legacy"},     │
│     "sql": {"table": "new"},         │
│     ...                              │
│   }                                  │
└────────────┬─────────────────────────┘
             │
             ↓
┌─────────────────────────────────────┐
│     FormatterSelector                │
│  ┌─────────────────────────────┐   │
│  │ get_formatter(lang, type)   │   │
│  │   → Check CONFIG            │   │
│  │   → Return appropriate one  │   │
│  └─────────────────────────────┘   │
└────────────┬─────────────────────────┘
             │
             ↓
┌─────────────────────────────────────┐
│      TableCommand                    │
│  formatter = FormatterSelector       │
│    .get_formatter(lang, format_type) │
│  # No if/else needed                 │
└──────────────────────────────────────┘
```

---

## Core Components

### 1. Formatter Configuration

**File**: `tree_sitter_analyzer/formatters/formatter_config.py`

```python
"""
Formatter configuration for language-specific formatting.

This configuration determines which formatter system (legacy or new)
should be used for each language and format type combination.
"""

from typing import Literal

FormatType = Literal["table", "compact", "full", "csv", "json"]
FormatterStrategy = Literal["legacy", "new"]

# Configuration mapping: language → format_type → strategy
LANGUAGE_FORMATTER_CONFIG: dict[str, dict[FormatType, FormatterStrategy]] = {
    # Legacy languages - use original TableFormatter
    "java": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "python": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "javascript": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    "typescript": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
        "csv": "legacy",
        "json": "legacy",
    },
    
    # New languages - use language-specific formatters
    "sql": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "html": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "css": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
    "markdown": {
        "table": "new",
        "compact": "new",
        "full": "new",
        "csv": "new",
        "json": "new",
    },
}

# Default strategy for unknown languages
DEFAULT_STRATEGY: FormatterStrategy = "legacy"

def get_formatter_strategy(language: str, format_type: FormatType) -> FormatterStrategy:
    """
    Get formatter strategy for language and format type.
    
    Args:
        language: Programming language name
        format_type: Output format type
        
    Returns:
        Formatter strategy ("legacy" or "new")
    """
    lang_config = LANGUAGE_FORMATTER_CONFIG.get(language.lower(), {})
    return lang_config.get(format_type, DEFAULT_STRATEGY)
```

**Benefits**:
- ✅ Explicit: 清楚地看到每种语言用什么格式化器
- ✅ Centralized: 所有配置在一个地方
- ✅ Typed: 使用 Literal 类型确保类型安全
- ✅ Documented: 内联文档说明用途

---

### 2. FormatterSelector Service

**File**: `tree_sitter_analyzer/formatters/formatter_selector.py`

```python
"""
Formatter selector service - chooses appropriate formatter based on configuration.
"""

from typing import Any

from .formatter_config import get_formatter_strategy, FormatType, FormatterStrategy
from .language_formatter_factory import create_language_formatter
from ..table_formatter import create_table_formatter


class FormatterSelector:
    """
    Service for selecting appropriate formatter based on language and format type.
    
    This service decouples command layer from formatter layer by using explicit
    configuration instead of implicit "if formatter exists" logic.
    """
    
    @staticmethod
    def get_formatter(
        language: str,
        format_type: FormatType,
        **kwargs: Any
    ) -> Any:
        """
        Get appropriate formatter for language and format type.
        
        Args:
            language: Programming language name
            format_type: Output format type (table, compact, full, csv, json)
            **kwargs: Additional arguments for formatter (e.g., include_javadoc)
            
        Returns:
            Formatter instance (either legacy TableFormatter or new language-specific formatter)
            
        Example:
            >>> formatter = FormatterSelector.get_formatter("java", "compact")
            >>> output = formatter.format_structure(data)
        """
        strategy = get_formatter_strategy(language, format_type)
        
        if strategy == "new":
            return FormatterSelector._create_new_formatter(language, format_type, **kwargs)
        else:
            return FormatterSelector._create_legacy_formatter(language, format_type, **kwargs)
    
    @staticmethod
    def _create_new_formatter(
        language: str,
        format_type: FormatType,
        **kwargs: Any
    ) -> Any:
        """Create formatter from new system (LanguageFormatterFactory)."""
        formatter = create_language_formatter(language)
        if formatter is None:
            # Fallback to legacy if new formatter doesn't exist
            return FormatterSelector._create_legacy_formatter(language, format_type, **kwargs)
        
        # Set format type on formatter if it supports it
        if hasattr(formatter, 'format_type'):
            formatter.format_type = format_type
            
        return formatter
    
    @staticmethod
    def _create_legacy_formatter(
        language: str,
        format_type: FormatType,
        **kwargs: Any
    ) -> Any:
        """Create formatter from legacy system (TableFormatter)."""
        include_javadoc = kwargs.get('include_javadoc', False)
        return create_table_formatter(format_type, language, include_javadoc)
    
    @staticmethod
    def is_legacy_formatter(language: str, format_type: FormatType) -> bool:
        """
        Check if language uses legacy formatter for given format type.
        
        Args:
            language: Programming language name
            format_type: Output format type
            
        Returns:
            True if legacy formatter should be used, False otherwise
        """
        strategy = get_formatter_strategy(language, format_type)
        return strategy == "legacy"
    
    @staticmethod
    def get_supported_languages() -> list[str]:
        """
        Get list of all supported languages.
        
        Returns:
            List of supported language names
        """
        from .formatter_config import LANGUAGE_FORMATTER_CONFIG
        return list(LANGUAGE_FORMATTER_CONFIG.keys())
```

**Design Principles**:
1. **Single Responsibility**: Only responsible for selecting formatter
2. **Static Methods**: No state, pure service
3. **Graceful Fallback**: If new formatter doesn't exist, fallback to legacy
4. **Transparent**: Callers don't need to know about dual system

---

### 3. Updated TableCommand

**File**: `tree_sitter_analyzer/cli/commands/table_command.py`

**Before**:
```python
# Check if we have a language-specific formatter
formatter = create_language_formatter(analysis_result.language)
if formatter:
    # Use language-specific formatter
    ...
else:
    # Fallback to original implementation
    ...
```

**After**:
```python
from ...formatters.formatter_selector import FormatterSelector

# Get appropriate formatter based on configuration
table_type = getattr(self.args, "table", "full")
formatter = FormatterSelector.get_formatter(
    analysis_result.language,
    table_type,
    include_javadoc=getattr(self.args, "include_javadoc", False)
)

# Format output using selected formatter
if hasattr(formatter, 'format_analysis_result'):
    formatted_output = formatter.format_analysis_result(analysis_result, table_type)
else:
    # Convert to structure format for legacy formatters
    formatted_data = self._convert_to_structure_format(analysis_result, language)
    formatted_output = formatter.format_structure(formatted_data)

self._output_table(formatted_output)
```

**Benefits**:
- No more if/else branching based on formatter existence
- Clear and explicit formatter selection
- Configuration-driven behavior

---

### 4. Fix "unknown" Package Issue

**Current Problem** (Line 132):
```python
package_name = "unknown"  # Wrong for all languages
```

**Solution**:
```python
def _get_default_package_name(self, language: str) -> str:
    """
    Get default package name for language.
    
    Only Java-like languages have package concept.
    Other languages (JS, TS, Python) don't need package prefix.
    
    Args:
        language: Programming language name
        
    Returns:
        Default package name ("unknown" for Java-like, "" for others)
    """
    # Languages with package/namespace concept
    PACKAGED_LANGUAGES = {"java", "kotlin", "scala", "csharp", "cpp"}
    
    if language.lower() in PACKAGED_LANGUAGES:
        return "unknown"
    
    return ""  # No package for JS, TS, Python, etc.

# Usage in _convert_to_structure_format:
package_name = self._get_default_package_name(language)
```

---

## Migration Strategy

### Phase 1: Add New System (No Breaking Changes)
1. Add `formatter_config.py`
2. Add `formatter_selector.py`
3. Add tests
4. **Don't modify commands yet**

### Phase 2: Update table_command.py
1. Replace implicit check with FormatterSelector
2. Fix package name logic
3. Test thoroughly

### Phase 3: Cleanup Other Commands
1. Remove unused `_convert_to_formatter_format()` methods
2. Ensure consistency

---

## Configuration Guidelines

### Adding New Language

**Scenario 1: New language with new formatter**
```python
"newlang": {
    "table": "new",      # Use new formatter
    "compact": "new",
    "full": "new",
    "csv": "new",
    "json": "new",
}
```

**Scenario 2: New language, use legacy formatter temporarily**
```python
"newlang": {
    "table": "legacy",   # Use legacy until new formatter ready
    "compact": "legacy",
    "full": "legacy",
    "csv": "legacy",
    "json": "legacy",
}
```

**Scenario 3: Gradual migration**
```python
"existinglang": {
    "table": "new",      # Migrate table first
    "compact": "legacy",  # Keep these on legacy for now
    "full": "legacy",
    "csv": "legacy",
    "json": "legacy",
}
```

---

## Benefits

### 1. Isolation
```
添加 SQL 支持:
  LANGUAGE_FORMATTER_CONFIG["sql"] = {"table": "new", ...}
  ↓
  Java/Python/JS/TS 配置不变
  ↓
  输出不变 ✅
```

### 2. Explicit Control
```
开发者可以看到:
  - Java 用 legacy formatter
  - SQL 用 new formatter
  - 清晰明了
```

### 3. Easy Testing
```python
# Test that adding new language doesn't affect old ones
def test_add_language_isolation():
    # Record current outputs
    old_outputs = generate_all_outputs()
    
    # Add new language
    LANGUAGE_FORMATTER_CONFIG["newlang"] = {"table": "new"}
    
    # Verify old outputs unchanged
    new_outputs = generate_all_outputs()
    assert old_outputs == new_outputs  # Should pass!
```

### 4. Gradual Migration
```python
# Can migrate one format at a time
"java": {
    "table": "new",      # Migrated
    "compact": "legacy",  # Not yet
    "full": "legacy",     # Not yet
}
```

---

## Testing Strategy

### Unit Tests
```python
def test_formatter_selector_returns_legacy_for_java():
    formatter = FormatterSelector.get_formatter("java", "table")
    assert isinstance(formatter, TableFormatter)

def test_formatter_selector_returns_new_for_sql():
    formatter = FormatterSelector.get_formatter("sql", "table")
    assert isinstance(formatter, SQLFormatterWrapper)

def test_unknown_language_defaults_to_legacy():
    formatter = FormatterSelector.get_formatter("unknown", "table")
    assert isinstance(formatter, TableFormatter)
```

### Integration Tests
```python
def test_table_command_uses_formatter_selector():
    # Run table command for Java
    result = run_table_command("java_file.java")
    # Should use legacy formatter, no "unknown" prefix issues
    assert "unknown.Class" not in result
```

---

## Open Questions

1. **Q**: Should we eventually migrate all languages to new system?
   **A**: Not necessarily. Legacy system works well for Java/Python. Only migrate if there's a clear benefit.

2. **Q**: What if a language needs different formatters for different commands?
   **A**: Configuration supports this - can add command dimension if needed.

3. **Q**: Performance impact of FormatterSelector?
   **A**: Negligible - just a dictionary lookup. No runtime overhead.

---

## References

- `tree_sitter_analyzer/cli/commands/table_command.py` - Problem location
- `tree_sitter_analyzer/formatters/language_formatter_factory.py` - New system
- `tree_sitter_analyzer/table_formatter.py` - Legacy system
- OpenSpec: `improve-language-formatter-isolation` - Previous attempt

