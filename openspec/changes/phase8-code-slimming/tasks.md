# Phase 8: Code Slimming & Quality Purification

## Goal
Eliminate all mastery scan violations: 22 oversized → 0, 76 low-density → 0.

## Strategy
Split each oversized test file into focused modules (one per source module), ensuring all tests pass after each split. TDD gate: split → run tests → only proceed if green.

## Tasks (Vertical Slices — one OpenSpec change at a time)

### Slice 1: Split test_mcp_fd_rg_tools.py (5633 lines → 4 files)
- [ ] Read source modules: fd_rg_utils.py, list_files_tool.py, search_content_tool.py, find_and_grep_tool.py
- [ ] Create test_fd_rg_utils.py with fd_rg_utils tests
- [ ] Create test_list_files_tool.py with ListFilesTool tests
- [ ] Create test_search_content_tool.py with SearchContentTool tests
- [ ] Create test_find_and_grep_tool.py with FindAndGrepTool tests
- [ ] Verify all tests pass
- [ ] Remove oversized test_mcp_fd_rg_tools.py
- [ ] Run mastery scan — confirm oversized count decreases

### Slice 2-5: Split remaining oversized test files (4 batches of ~5 files each)
- [ ] Batch A: formatters (3 files: 1385 + 1308 + 1271 lines)
- [ ] Batch B: cli (3 files: 1306 + 1061 + 1058 + 1048 lines)
- [ ] Batch C: integration (4 files: 1284 + 1276 + 1194 + 1110 lines)
- [ ] Batch D: unit (5 files: 1704 + 1556 + 1504 + 1220 + 1011 lines)

### Slice 6: Fix low-density assertion files (76 files)
- [ ] Enhance tests/unit/core/* files (8 files)
- [ ] Enhance tests/unit/security/* files (2 files)
- [ ] Enhance remaining files (66 files)

### Gates
- [ ] test_mastery_scan.py --gates exits 0
- [ ] ruff check passes
- [ ] pytest full suite passes
