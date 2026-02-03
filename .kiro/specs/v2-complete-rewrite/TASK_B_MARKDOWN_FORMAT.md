# Task B: Optimize Markdown Format

**Status**: In Progress
**Priority**: High (本周必做)
**Estimated**: 3h
**Pain Point**: #3

## Problem Statement

Current Markdown formatter uses nested tables for methods/parameters, which:
- Reduces readability (~6/10)
- Makes output hard to scan
- Not user-friendly for quick code inspection

**Example of current problematic output:**
```markdown
| Method | Parameters | Return Type |
|--------|-----------|-------------|
| calculate | `a: int`<br>`b: int` | int |
```

The inline formatting with `<br>` tags is hard to read.

## Goals

1. **Improve Readability**: Target >8/10 readability score
2. **Remove Nested Tables**: Use cleaner formatting approach
3. **Maintain Information**: Don't lose any data
4. **Keep Compatibility**: Ensure existing tests still pass

## Design Options

### Option A: Use Lists for Nested Data
```markdown
## Methods

### `calculate(a: int, b: int) -> int`
- **Parameters**:
  - `a: int` - First number
  - `b: int` - Second number
- **Returns**: `int`
- **Complexity**: 2
```

**Pros**: Very readable, clear hierarchy
**Cons**: Longer output

### Option B: Simplified Tables
```markdown
## Methods

| Method | Signature | Complexity |
|--------|-----------|------------|
| calculate | `(a: int, b: int) -> int` | 2 |

**Parameters**:
- `a: int` - First number
- `b: int` - Second number
```

**Pros**: Clean tables, separate sections
**Cons**: Parameters not directly visible in table

### Option C: Hybrid Approach (CHOSEN)
```markdown
## Methods

### `calculate(a: int, b: int) -> int`

**Complexity**: 2
**Parameters**:
- `a` (int): First number
- `b` (int): Second number

**Returns**: int
```

**Pros**: Best of both worlds - clear hierarchy and detail
**Cons**: None significant

## Implementation Plan

### Step 1: Analyze Current Code
- [x] Read MarkdownFormatter implementation
- [x] Identify nested table sections
- [x] Find parameter formatting logic

### Step 2: Write Tests (TDD - RED)
- [ ] Create test_markdown_formatter_readable.py
- [ ] Test method formatting without nested tables
- [ ] Test parameter formatting as lists
- [ ] Test class formatting
- [ ] Run tests - should FAIL

### Step 3: Implement (TDD - GREEN)
- [ ] Modify MarkdownFormatter._format_methods()
- [ ] Modify MarkdownFormatter._format_parameters()
- [ ] Add helper method for clean signatures
- [ ] Run tests - should PASS

### Step 4: Verify (TDD - REFACTOR)
- [ ] Run all existing tests
- [ ] Manual testing with sample files
- [ ] Check coverage (target 100% on new code)
- [ ] Update documentation

### Step 5: Commit
- [ ] Stage changes
- [ ] Write commit message
- [ ] Push to repo

## Files to Modify

1. `v2/tree_sitter_analyzer_v2/formatters/markdown_formatter.py` - Main implementation
2. `v2/tests/unit/test_markdown_formatter.py` - Existing tests (update if needed)
3. `v2/tests/unit/test_markdown_readable.py` - New readability tests
4. `.kiro/specs/v2-complete-rewrite/PAINPOINTS_TRACKER.md` - Mark #3 as resolved

## Acceptance Criteria

- [ ] No nested tables with `<br>` tags
- [ ] Method signatures clearly formatted
- [ ] Parameters shown as bullet lists
- [ ] All existing tests pass
- [ ] Readability score >8/10 (manual assessment)
- [ ] 100% coverage on modified code

## Test Strategy

### Unit Tests
1. Test method formatting without tables
2. Test parameter list formatting
3. Test function formatting
4. Test class formatting
5. Test empty/edge cases

### Integration Tests
1. Analyze real Python file with complex methods
2. Analyze Java file with many parameters
3. Compare output readability

## Progress Log

### [2026-02-03 17:15] Started Task B
- Created planning document
- Ready to begin TDD workflow

### [2026-02-03 17:45] TDD RED Phase
- Created 7 readability tests in test_markdown_readable.py
- 2 tests failed as expected (parameters in tables, methods not as headings)
- 5 tests passed (baseline good formatting)

### [2026-02-03 18:00] TDD GREEN Phase
- Modified _encode_list() to detect nested structures
- Added _format_list_as_headings() for complex items (e.g., methods)
- Added _format_list_as_bullets() for structural elements (e.g., parameters)
- All 7 new tests passing ✅
- All 17 existing tests passing ✅

### [2026-02-03 18:15] Verification Complete
- Tested on real file (sample.py)
- **Before**: Nested tables with `| Name | Parameters |` inside cells
- **After**: Clean headings with bullet list parameters
  ```markdown
  ## `Calculator`
  ### Methods
  #### `__init__`
  ##### Parameters
  - self
  ```
- Readability improved from ~6/10 to ~8.5/10 ✅

## Implementation Complete

✅ No nested tables
✅ Parameters formatted as bullet lists
✅ Methods formatted as hierarchical headings
✅ All tests passing (7 new + 17 existing = 24/24)
✅ Backward compatibility maintained
✅ 83% coverage on markdown_formatter.py
