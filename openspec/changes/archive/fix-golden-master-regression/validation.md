# Validation Checklist: Fix Golden Master Regression

## Pre-Implementation Validation

### Requirements Analysis
- [x] All affected golden master files identified
- [x] Root cause in `table_formatter.py` analyzed
- [x] Expected behavior documented for each language
- [x] Edge cases identified and documented

### Design Review
- [x] Title generation rules defined for each language
- [x] Helper method structure designed
- [x] Migration plan documented
- [x] Backward compatibility considered

---

## Implementation Validation

### Code Changes
- [ ] **Title Generation Helper Method Added**
  - [ ] `_generate_title()` method implemented
  - [ ] `_generate_java_title()` helper implemented
  - [ ] `_generate_python_title()` helper implemented
  - [ ] `_generate_js_ts_title()` helper implemented
  - [ ] `_extract_filename()` utility implemented

- [ ] **Compact Format Updated**
  - [ ] `_format_compact_table()` uses new helper
  - [ ] No hardcoded "unknown" prefix logic
  - [ ] Language-specific handling confirmed

- [ ] **Full Format Updated**
  - [ ] `_format_full_table()` uses new helper
  - [ ] Multi-class file handling preserved
  - [ ] Section structure maintained

### Golden Master Files
- [ ] **Java Files Corrected**
  - [ ] `java_sample_compact.md` - Title: `com.example.AbstractParentClass`
  - [ ] `java_userservice_compact_format.md` - Title includes package
  - [ ] `java_bigservice_full.md` - Format structure preserved

- [ ] **JavaScript/TypeScript Files Corrected**
  - [ ] `javascript_class_compact.md` - No "unknown" prefix
  - [ ] `typescript_enum_compact.md` - No "unknown" prefix

- [ ] **Python Files Corrected**
  - [ ] `python_sample_full.md` - Uses "Module: name" format

---

## Testing Validation

### Unit Tests
- [ ] **Title Generation Tests**
  ```python
  test_generate_java_title_with_package()
  test_generate_java_title_without_package()
  test_generate_java_title_multiple_classes()
  test_generate_python_title()
  test_generate_js_title_no_unknown_prefix()
  test_generate_ts_title_no_unknown_prefix()
  test_extract_filename_various_paths()
  ```

- [ ] **All tests pass**: `pytest tests/test_table_formatter.py -v`

### Golden Master Tests
- [ ] **Compact Format Tests**
  ```bash
  pytest tests/golden_masters/test_compact_format.py -v
  ```
  - [ ] All Java compact tests pass
  - [ ] All JavaScript compact tests pass
  - [ ] All TypeScript compact tests pass

- [ ] **Full Format Tests**
  ```bash
  pytest tests/golden_masters/test_full_format.py -v
  ```
  - [ ] All Java full tests pass
  - [ ] All Python full tests pass

### Integration Tests
- [ ] **Format Testing Suite**
  ```bash
  pytest tests/integration/formatters/ -v
  ```
  - [ ] All format validation tests pass
  - [ ] No regressions in other formats (CSV, JSON)

### Manual Testing
- [ ] **Visual Inspection**
  - [ ] Generate output for each test case
  - [ ] Compare with golden master files
  - [ ] Verify titles are human-readable and correct

- [ ] **Cross-Language Verification**
  - [ ] Test with real Java files
  - [ ] Test with real Python files
  - [ ] Test with real JavaScript/TypeScript files

---

## Quality Validation

### Code Quality
- [ ] **MyPy Type Checking**
  ```bash
  uv run mypy tree_sitter_analyzer/table_formatter.py
  ```
  - [ ] Zero type errors
  - [ ] All helper methods properly typed

- [ ] **Linting**
  ```bash
  uv run ruff check tree_sitter_analyzer/table_formatter.py
  uv run black --check tree_sitter_analyzer/table_formatter.py
  ```
  - [ ] No linting errors
  - [ ] Code style compliant

- [ ] **Code Coverage**
  ```bash
  pytest --cov=tree_sitter_analyzer.table_formatter tests/
  ```
  - [ ] Coverage > 85% for modified code
  - [ ] New helper methods covered

### Documentation
- [ ] **Code Comments**
  - [ ] All helper methods have docstrings
  - [ ] Complex logic explained with comments
  - [ ] Examples provided where helpful

- [ ] **External Documentation**
  - [ ] `docs/format_specifications.md` updated
  - [ ] Title generation rules documented
  - [ ] Examples for each language provided

---

## Regression Validation

### No Breaking Changes
- [ ] **CSV Format**
  - [ ] CSV output unchanged
  - [ ] CSV tests still pass

- [ ] **JSON Format**
  - [ ] JSON output unchanged
  - [ ] JSON tests still pass

- [ ] **Other Languages**
  - [ ] HTML/CSS formatters unaffected
  - [ ] SQL formatters unaffected (if applicable)

### Platform Compatibility
- [ ] **Windows**
  - [ ] Tests pass on Windows
  - [ ] Line endings correct

- [ ] **Linux (CI)**
  - [ ] Tests pass in CI environment
  - [ ] No platform-specific issues

---

## Deployment Validation

### Pre-Commit Checks
- [ ] All tests pass locally
- [ ] No linter errors
- [ ] Type checking passes
- [ ] Coverage threshold met

### CI/CD Pipeline
- [ ] GitHub Actions tests pass
- [ ] All platform tests pass (Windows, macOS, Linux)
- [ ] All Python version tests pass (3.10-3.13)

### Version Control
- [ ] Meaningful commit messages
- [ ] Changes properly staged
- [ ] No unintended file modifications

---

## Post-Deployment Validation

### Smoke Tests
- [ ] Generate output for sample files
- [ ] Verify titles are correct
- [ ] No error messages or warnings

### Monitoring
- [ ] Check CI test results after merge
- [ ] Monitor for any reported issues
- [ ] Verify no downstream breakage

---

## Validation Summary

### Critical Path Items
1. ✅ Title generation logic fixed
2. ✅ Golden master files corrected
3. ✅ All tests pass
4. ✅ No regressions introduced

### Sign-Off Criteria
- [ ] All checklist items completed
- [ ] No known issues remaining
- [ ] Documentation updated
- [ ] Tests comprehensive and passing

### Approval
- [ ] **Code Review**: _______________ (Date: _______)
- [ ] **QA Review**: _______________ (Date: _______)
- [ ] **Ready for Merge**: YES / NO

---

## Notes

### Known Issues
- None expected (this is a bug fix)

### Future Improvements
- Consider adding more comprehensive title customization options
- May want to add configuration for title format preferences

### References
- Related change: `fix-analyze-code-structure-format-regression`
- OpenSpec proposal: `openspec/changes/fix-golden-master-regression/proposal.md`

