# Tasks: Fix Golden Master Regression

## Task Breakdown

### Phase 1: Analysis and Understanding (COMPLETED)
- [x] Identify all golden master files with incorrect titles
- [x] Analyze root cause in `table_formatter.py`
- [x] Document expected vs actual formats for each file
- [x] Review git diff to understand what changed

### Phase 2: Fix Title Generation Logic
- [ ] **Task 2.1**: Fix compact format title generation
  - Location: `table_formatter.py:_format_compact_table()`
  - Changes:
    - Remove forced "unknown" package prefix for JavaScript/TypeScript
    - Add language-specific title generation logic
    - Handle missing class names gracefully
  - Validation: Unit tests for title generation
  - Estimated effort: 30 minutes

- [ ] **Task 2.2**: Fix full format title generation
  - Location: `table_formatter.py:_format_full_table()`
  - Changes:
    - Ensure single class files use `package.ClassName` format (Java)
    - Respect language-specific conventions
    - Don't break existing structure for multi-class files
  - Validation: Compare with git history to ensure no regression
  - Estimated effort: 45 minutes

- [ ] **Task 2.3**: Add language-specific helper method
  - Location: `table_formatter.py` (new method)
  - Changes:
    - Create `_generate_title()` helper method
    - Centralize title generation logic
    - Handle each language appropriately
  - Validation: Code review, unit tests
  - Estimated effort: 30 minutes

### Phase 3: Update Golden Master Files
- [ ] **Task 3.1**: Fix Java golden masters
  - Files:
    - `tests/golden_masters/compact/java_sample_compact.md`
    - `tests/golden_masters/compact/java_userservice_compact_format.md`
    - `tests/golden_masters/full/java_bigservice_full.md`
  - Changes: Restore correct titles and format structure
  - Validation: Run golden master tests
  - Estimated effort: 20 minutes

- [ ] **Task 3.2**: Fix JavaScript/TypeScript golden masters
  - Files:
    - `tests/golden_masters/compact/javascript_class_compact.md`
    - `tests/golden_masters/compact/typescript_enum_compact.md`
  - Changes: Remove "unknown" package prefix, use appropriate titles
  - Validation: Run golden master tests
  - Estimated effort: 15 minutes

- [ ] **Task 3.3**: Fix Python golden masters
  - Files:
    - `tests/golden_masters/full/python_sample_full.md`
  - Changes: Ensure consistent format with improvements
  - Validation: Run golden master tests
  - Estimated effort: 15 minutes

### Phase 4: Testing and Validation
- [ ] **Task 4.1**: Run all golden master tests
  - Command: `pytest tests/golden_masters/ -v`
  - Expected: All tests pass
  - Estimated effort: 10 minutes

- [ ] **Task 4.2**: Run format validation tests
  - Command: `pytest tests/integration/formatters/ -v`
  - Expected: All tests pass
  - Estimated effort: 10 minutes

- [ ] **Task 4.3**: Manual verification
  - Action: Generate output for each test case and visually verify
  - Tools: Use MCP table_format tool or CLI
  - Expected: Output matches golden masters exactly
  - Estimated effort: 20 minutes

- [ ] **Task 4.4**: Cross-platform verification
  - Action: Verify on Windows (primary) and Linux (CI)
  - Expected: No platform-specific differences
  - Estimated effort: 15 minutes

### Phase 5: Documentation and Cleanup
- [ ] **Task 5.1**: Update format specifications
  - File: `docs/format_specifications.md`
  - Changes: Document title generation rules for each language
  - Estimated effort: 20 minutes

- [ ] **Task 5.2**: Add regression test
  - Location: `tests/test_table_formatter.py` or similar
  - Changes: Add specific tests for title generation logic
  - Coverage: All language types and edge cases
  - Estimated effort: 30 minutes

- [ ] **Task 5.3**: Update CHANGELOG
  - File: `CHANGELOG.md`
  - Entry: Document bug fix in appropriate section
  - Estimated effort: 5 minutes

## Task Dependencies

```
Phase 1 (Analysis) → Phase 2 (Fix Logic) → Phase 3 (Update Files) → Phase 4 (Testing) → Phase 5 (Documentation)
                                    ↓
                           Can run tests in parallel
                           with file updates
```

## Success Criteria

- [ ] All golden master tests pass
- [ ] No "unknown" package prefixes in JavaScript/TypeScript outputs
- [ ] Java files use correct `package.ClassName` format
- [ ] Python files use `Module: name` format
- [ ] Full format maintains original structure
- [ ] No regressions in other format types (CSV, JSON)
- [ ] Regression tests added to prevent future issues

## Estimated Total Effort

- Development: ~3 hours
- Testing: ~1 hour
- Documentation: ~1 hour
- **Total: ~5 hours**

## Notes

- Priority: HIGH (fixes broken tests)
- Complexity: MEDIUM (requires understanding of existing format logic)
- Risk: LOW (fixing regression, not adding new features)

