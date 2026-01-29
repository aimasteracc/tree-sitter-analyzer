# Tasks - Plugin Contract Alignment

## Work Breakdown Structure

| ID | Task | Objective | Files to Modify | Status |
|----|------|-----------|-----------------|--------|
| T1 | Extract Base Contract | Identify standard methods in `LanguagePlugin` | `plugins/base.py` | completed |
| T2 | Audit Plugins | Compare all plugins against the base contract | `languages/*.py` | completed |
| T3 | Implement Missing Methods | Batch add `get_queries`, `execute_query_strategy`, etc. | `languages/*.py` | completed |
| T4 | Format Alignment | Ensure correct indentation and UTF-8 encoding | `languages/*.py` | completed |
| T5 | Verification | Verify with TOON map and unit tests | N/A | completed |

## Testing Plan
1. **Structural Verification**: `uv run tree-sitter-analyzer --table toon` on modified plugins.
2. **Unit Testing**: `uv run pytest tests/unit/core/test_query_service.py` to ensure contract usage works.
3. **Integration Testing**: Run all core unit tests.

## Acceptance Criteria
- [x] All language plugins implement `execute_query_strategy`.
- [x] All language plugins implement `get_element_categories`.
- [x] Files are correctly formatted (no mixed line endings, valid UTF-8).
