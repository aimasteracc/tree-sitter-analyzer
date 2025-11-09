# Proposal: Fix Command-Formatter Coupling

## Change ID
`fix-command-formatter-coupling`

## Status
DRAFT

## Problem Statement

The CLI command layer has a design flaw that causes regressions when adding new language support. The root cause is improper coupling between command layer and formatter layer, with inconsistent fallback behavior.

### Specific Issues

1. **table_command.py (Line 46-63): Problematic Fallback Logic**
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
   **Problem**: Adding a new language to `LanguageFormatterFactory` automatically switches ALL commands to use the new formatter, even if it's not fully compatible with the old format.

2. **table_command.py (Line 132): Hardcoded "unknown" Package**
   ```python
   package_name = "unknown"
   ```
   **Problem**: This is the source of "unknown.Animal" and "unknown.Color" in JavaScript/TypeScript outputs. Languages without packages should not have any package prefix.

3. **Dual Formatter System Confusion**
   - `create_language_formatter()` → New system (BaseFormatter)
   - `create_table_formatter()` → Old system (TableFormatter)
   - Commands don't know which one to use consistently

4. **Other Commands Have Same Pattern**
   - `advanced_command.py`: Has unused `_convert_to_formatter_format()` method
   - `structure_command.py`: Has unused `_convert_to_formatter_format()` method  
   - `summary_command.py`: Has unused `_convert_to_formatter_format()` method
   - All suggest incomplete migration from old to new formatter system

### Impact

When adding SQL language support:
- SQL added to `LanguageFormatterFactory`
- **Unintended side effect**: All existing languages (Java, Python, JS, TS) switch to new formatter path
- New formatter has different title generation logic
- Result: Golden master tests fail for unrelated languages

## Root Cause Analysis

### Design Flaw: Implicit Migration

The code assumes that adding a language to `LanguageFormatterFactory` means it's ready for production use across ALL commands. This is false because:

1. **Different formatters have different capabilities**
   - Old `TableFormatter`: Supports JavaDoc, detailed Java features
   - New formatters: May not support all old features

2. **No explicit compatibility declaration**
   - No way to say "this formatter is ready for compact format but not full format"
   - No way to say "this formatter is for table command only, not other commands"

3. **Commands make independent decisions**
   - Each command checks `create_language_formatter()` independently
   - No central configuration of which formatter to use for which language

### The Real Problem

```
添加 SQL 支持 → LanguageFormatterFactory._formatters["sql"] = SQLFormatterWrapper
                ↓
        table_command.py 检测到 formatter 存在
                ↓
        尝试使用新的格式化路径
                ↓
        新路径的标题生成逻辑不同
                ↓
        Java/Python/JS/TS 的输出格式改变
                ↓
        Golden Master 测试失败 ❌
```

## Proposed Solution

### Principle: Explicit Formatter Selection

Instead of implicit "if formatter exists, use it", use explicit configuration:

```python
# Each language explicitly declares which formatter to use for which format
LANGUAGE_FORMATTER_CONFIG = {
    "java": {
        "table": "legacy",      # Use TableFormatter
        "compact": "legacy",
        "full": "legacy",
    },
    "python": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
    },
    "javascript": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
    },
    "typescript": {
        "table": "legacy",
        "compact": "legacy",
        "full": "legacy",
    },
    "sql": {
        "table": "new",         # Use SQLFormatterWrapper
        "compact": "new",
        "full": "new",
    },
}
```

### Implementation Strategy

1. **Create FormatterSelector Service**
   ```python
   class FormatterSelector:
       """Selects appropriate formatter based on language and format type"""
       
       @staticmethod
       def get_formatter(language: str, format_type: str):
           config = LANGUAGE_FORMATTER_CONFIG.get(language, {})
           strategy = config.get(format_type, "legacy")
           
           if strategy == "new":
               return create_language_formatter(language)
           else:
               return create_table_formatter(format_type, language)
   ```

2. **Update table_command.py**
   - Remove implicit `if formatter:` check
   - Use `FormatterSelector.get_formatter(language, format_type)`
   - Consistent behavior across all languages

3. **Fix "unknown" Package Issue**
   - Don't default to "unknown" for all languages
   - Use language-specific logic:
     ```python
     if language in ["java"]:
         package_name = "unknown"  # Java needs package
     else:
         package_name = ""  # Other languages don't
     ```

4. **Remove Dead Code**
   - Remove unused `_convert_to_formatter_format()` from other commands
   - These methods were added but never properly integrated

## Impact Assessment

### Benefits
- ✅ **Isolation**: Adding new language support won't affect existing languages
- ✅ **Explicit**: Clear which formatter is used for each language/format
- ✅ **Testable**: Can test formatters independently
- ✅ **Maintainable**: Easy to understand and modify
- ✅ **Backward Compatible**: Existing languages keep using old formatter

### Risks
- ⚠️ Need to update all commands consistently
- ⚠️ Need to ensure configuration is complete

### Scope
- **Modified Files**: 
  - `table_command.py` (primary fix)
  - `advanced_command.py` (cleanup)
  - `structure_command.py` (cleanup)
  - `summary_command.py` (cleanup)
- **New Files**:
  - `formatters/formatter_selector.py` (new service)
- **Configuration**:
  - Add `LANGUAGE_FORMATTER_CONFIG` constant

## Success Criteria

1. Adding SQL to `LanguageFormatterFactory` does NOT change Java/Python/JS/TS output
2. No "unknown" package prefix for JavaScript/TypeScript
3. All golden master tests pass
4. Clear documentation of which formatter is used for each language
5. Easy to add new languages without breaking existing ones

## Dependencies

- Related to: `fix-golden-master-regression` (fixes the symptom)
- Related to: `improve-language-formatter-isolation` (previous attempt)
- Requires: Understanding of both formatter systems

## Migration Path

### Phase 1: Add FormatterSelector (No Breaking Changes)
- Create FormatterSelector service
- Add configuration
- Don't change command code yet

### Phase 2: Update table_command.py
- Replace implicit check with explicit selector
- Test thoroughly

### Phase 3: Cleanup Other Commands  
- Remove unused `_convert_to_formatter_format()` methods
- Ensure consistency

### Phase 4: Fix Package Name Logic
- Remove hardcoded "unknown"
- Add language-specific logic

## Alternative Approaches

### Alternative 1: Single Unified Formatter System
**Pros**: Clean, no dual system  
**Cons**: Requires migrating all existing code, high risk

### Alternative 2: Separate Command Classes
**Pros**: Complete isolation  
**Cons**: Code duplication, harder to maintain

### Alternative 3: Feature Flags per Formatter
**Pros**: Gradual migration  
**Cons**: Complex, harder to understand

**Chosen**: Explicit Configuration (Current Proposal)  
**Reason**: Minimal changes, explicit, maintainable, backward compatible

## References

- `tree_sitter_analyzer/cli/commands/table_command.py` - Main problem
- `tree_sitter_analyzer/formatters/language_formatter_factory.py` - New system
- `tree_sitter_analyzer/table_formatter.py` - Old system
- `openspec/changes/improve-language-formatter-isolation/` - Previous attempt

