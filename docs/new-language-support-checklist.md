<!-- HISTORICAL RECORD — file paths in this document reflect early project planning. Some paths may no longer exist. -->
# New Language Support Checklist

This document outlines the steps required to add support for a new programming language to Tree-sitter Analyzer.

## 📋 Required Checklist

### 1. Implement Language Plugin

- [ ] Create `tree_sitter_analyzer/languages/{language}_plugin.py`
  - [ ] Inherit from `LanguagePlugin` class
  - [ ] Implement `get_language_name()`
  - [ ] Implement `get_file_extensions()`
  - [ ] Implement `create_extractor()`
  - [ ] Implement `get_supported_element_types()`
  - [ ] Implement `get_queries()`
  - [ ] Implement `analyze_file()`

### 2. Implement Element Extractor

- [ ] Create `{Language}ElementExtractor` class
  - [ ] Inherit from `ElementExtractor`
  - [ ] Implement language-specific extraction methods

### 3. Define Queries

- [ ] Create `tree_sitter_analyzer/queries/{language}.py`
  - [ ] Define language-specific Tree-sitter queries

### 4. Implement Formatter

- [ ] Create `tree_sitter_analyzer/formatters/{language}_formatter.py`
  - [ ] Inherit from `BaseFormatter`
  - [ ] Implement `format_summary()`
  - [ ] Implement `format_structure()`
  - [ ] Implement `format_advanced()`
  - [ ] Implement `format_table()`

### 5. Register Formatter

- [ ] Register formatter in `tree_sitter_analyzer/formatters/formatter_registry.py`

### 6. Create Sample File

- [ ] Create `examples/sample.{ext}` or `examples/Sample.{Ext}`
  - [ ] Include sample code covering major language features

### 7. Create Unit Tests

- [ ] Create `tests/test_{language}/test_{language}_plugin.py`
  - [ ] Basic plugin functionality tests
  - [ ] Element extraction tests
  - [ ] Edge case tests

### 8. ⭐ Add Golden Master Tests (Critical!)

- [ ] Create `tests/golden_masters/full/{language}_sample_{name}_full.md`
- [ ] Create `tests/golden_masters/compact/{language}_sample_{name}_compact.md` (optional)
- [ ] Create `tests/golden_masters/csv/{language}_sample_{name}_csv.csv` (optional)
- [ ] Add test cases to `tests/test_golden_master_regression.py`
  ```python
  # {Language} tests
  ("examples/sample.{ext}", "{language}_sample", "full"),
  ("examples/sample.{ext}", "{language}_sample", "compact"),
  ("examples/sample.{ext}", "{language}_sample", "csv"),
  ```

> **⚠️ Lesson Learned**: Golden master tests are crucial for preventing regressions from future changes.
> Always create golden master tests when adding a new language.

### 9. Create Property-Based Tests (Recommended)

- [ ] Create `tests/test_{language}/test_{language}_properties.py`
  - [ ] Language-specific property tests

### 10. Add Dependencies

- [ ] Add tree-sitter-{language} to `pyproject.toml`
  ```toml
  [project.optional-dependencies]
  {language} = ["tree-sitter-{language}>=x.x.x"]
  ```

### 11. Update Documentation

- [ ] Update language support table in `README.md`
- [ ] Update language support table in `README_zh.md`
- [ ] Update language support table in `README_ja.md`
- [ ] Add entry to `CHANGELOG.md`

### 12. Register Entry Points (if needed)

- [ ] Update `[project.entry-points]` section in `pyproject.toml`

## 📁 File Structure Example

```
tree_sitter_analyzer/
├── languages/
│   └── {language}_plugin.py      # Language plugin
├── formatters/
│   └── {language}_formatter.py   # Formatter
└── queries/
    └── {language}.py             # Query definitions

examples/
└── sample.{ext}                  # Sample file

tests/
├── test_{language}/
│   ├── test_{language}_plugin.py
│   ├── test_{language}_properties.py
│   └── test_{language}_golden_master.py  # Language-specific golden master tests
└── golden_masters/
    ├── full/
    │   └── {language}_sample_full.md
    ├── compact/
    │   └── {language}_sample_compact.md
    └── csv/
        └── {language}_sample_csv.csv
```

## 🔍 Test Commands

```bash
# Run language-specific tests
uv run pytest tests/test_{language}/ -v

# Run golden master tests
uv run pytest tests/test_golden_master_regression.py -v -k "{language}"

# Run all tests
uv run pytest tests/ -v
```

## 📝 Reference Implementations

Use these language implementations as references:

- **Java**: `tree_sitter_analyzer/languages/java_plugin.py` - Most complete implementation
- **Python**: `tree_sitter_analyzer/languages/python_plugin/` - Simple implementation
- **SQL**: `tree_sitter_analyzer/languages/sql_plugin/` - With dedicated formatter
- **YAML**: `tree_sitter_analyzer/languages/yaml_plugin.py` - Async parsing example
- **HTML/CSS**: `tree_sitter_analyzer/languages/html_plugin.py` - Markup language example

## ⚠️ Common Issues and Solutions

### 1. Formatter Not Used in CLI

**Problem**: Language-specific formatter not called with `--table` command

**Solution**: 
- Register formatter in `tree_sitter_analyzer/formatters/formatter_registry.py`
- Add language to `LANGUAGE_FORMATTER_CONFIG` in `cli/commands/mcp_commands.py`

### 2. Golden Master Tests Failing

**Problem**: Output differs between environments

**Solution**:
- Use `normalize_output()` function to normalize environment-dependent parts
- Standardize trailing whitespace and line endings

### 3. Tree-sitter Parser Not Found

**Problem**: `ImportError: tree-sitter-{language} not installed`

**Solution**:
- Add dependency to `pyproject.toml`
- Run `uv sync --extra {language}`

---

**Last Updated**: 2025-11-27
**Created**: As a lesson learned when golden master tests were missing during YAML language support addition
