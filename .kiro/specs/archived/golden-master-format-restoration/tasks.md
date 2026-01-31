# Golden Master Format Restoration - Task List

## Overview

This task list implements the design for restoring golden master format compatibility.
Total estimated effort: 4-6 hours

---

## Phase 1: Preparation (30 min)

### Task 1.1: Backup Current State
- [ ] Create a backup branch of current changes
- [ ] Document current test status

### Task 1.2: Analyze Differences
- [ ] Categorize golden master differences by type (header, structure, content)
- [ ] Identify which changes are improvements vs regressions

---

## Phase 2: Java Formatter Restoration (1-2 hours)

### Task 2.1: Fix Header Format
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Remove `.java` extension from header in `_format_full_table`
- [ ] Remove `.java` extension from header in `_format_compact_table`

### Task 2.2: Fix Classes Overview Section
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Change `## Classes` to `## Classes Overview`

### Task 2.3: Implement Per-Class Sections
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Refactor `_format_full_table` to generate per-class sections
- [ ] Add `## ClassName (start-end)` section headers
- [ ] Filter fields/methods by class line range
- [ ] Generate subsections per class

### Task 2.4: Implement Visibility Grouping
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Add `### Protected Methods` section
- [ ] Add `### Package Methods` section
- [ ] Ensure correct visibility order: Constructors, Public, Protected, Package, Private

### Task 2.5: Fix Inner/Nested Class Handling
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Generate separate sections for inner classes
- [ ] Generate separate sections for static nested classes
- [ ] Ensure correct line range filtering

### Task 2.6: Fix Enum Formatting
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Change enum section header to `## EnumName (start-end)` format
- [ ] Remove property table format for enums
- [ ] Use standard field/constructor/method subsections

### Task 2.7: Remove Cols Column
**File**: `tree_sitter_analyzer/formatters/java_formatter.py`
- [ ] Remove `Cols` column from method tables
- [ ] Update `_format_method_row` to not include cols
- [ ] Remove `_format_method_row_no_cols` if redundant

---

## Phase 3: Other Language Formatters (1-2 hours)

### Task 3.1: C# Formatter
**File**: `tree_sitter_analyzer/formatters/csharp_formatter.py`
- [ ] Review golden master differences
- [ ] Apply similar fixes as Java formatter

### Task 3.2: JavaScript Formatter
**File**: `tree_sitter_analyzer/formatters/javascript_formatter.py`
- [ ] Review golden master differences
- [ ] Apply similar fixes as Java formatter

### Task 3.3: TypeScript Formatter
**File**: `tree_sitter_analyzer/formatters/typescript_formatter.py`
- [ ] Review golden master differences
- [ ] Apply similar fixes as Java formatter

### Task 3.4: PHP Formatter
**File**: `tree_sitter_analyzer/formatters/php_formatter.py`
- [ ] Review golden master differences
- [ ] Apply similar fixes as Java formatter

### Task 3.5: Python Formatter
**File**: `tree_sitter_analyzer/formatters/python_formatter.py`
- [ ] Review golden master differences
- [ ] Note: Some changes may be improvements (docstrings, module functions)
- [ ] Decide whether to keep improvements or revert

### Task 3.6: Ruby Formatter
**File**: `tree_sitter_analyzer/formatters/ruby_formatter.py`
- [ ] Review golden master differences
- [ ] Apply similar fixes as Java formatter

---

## Phase 4: Golden Master Restoration (30 min)

### Task 4.1: Revert Golden Masters
- [ ] Run: `git checkout HEAD -- tests/golden_masters/`
- [ ] Verify all golden master files are restored

### Task 4.2: Fix Trailing Newlines
- [ ] Ensure all golden master files end with newline
- [ ] Use consistent line endings (LF)

---

## Phase 5: Testing and Validation (1 hour)

### Task 5.1: Run Unit Tests
- [ ] Run: `pytest tests/unit/formatters/ -v`
- [ ] Fix any failing tests

### Task 5.2: Run Golden Master Tests
- [ ] Run: `pytest tests/ -k golden -v`
- [ ] Fix any differences

### Task 5.3: Run Full Test Suite
- [ ] Run: `pytest tests/ -v`
- [ ] Ensure all tests pass

### Task 5.4: Linting
- [ ] Run: `ruff check tree_sitter_analyzer/formatters/`
- [ ] Fix any linting errors

---

## Phase 6: Documentation and Cleanup (15 min)

### Task 6.1: Update Documentation
- [ ] Document any intentional format changes
- [ ] Update CHANGELOG if needed

### Task 6.2: Cleanup
- [ ] Remove any temporary files
- [ ] Commit changes with descriptive message

---

## Acceptance Criteria

1. [ ] All 47 golden master files match original format
2. [ ] All tests pass
3. [ ] No new linter errors
4. [ ] Output is token-efficient
5. [ ] Source code structure is accurately represented

---

## Notes

### Python Formatter Considerations
The Python formatter changes may actually be improvements:
- Added docstrings in output
- Added module-level functions

Consider keeping these improvements and updating the golden master instead of reverting.

### Priority Order
1. Java (most complex, sets pattern for others)
2. JavaScript/TypeScript (similar structure)
3. C#/PHP/Ruby (similar structure)
4. Python (may keep improvements)

