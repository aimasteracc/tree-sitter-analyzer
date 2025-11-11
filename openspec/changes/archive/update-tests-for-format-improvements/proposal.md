# Proposal: Update Tests for Format Improvements

**Change ID**: update-tests-for-format-improvements  
**Type**: Test Maintenance  
**Priority**: High  
**Status**: Draft

## Problem Statement

Recent format improvements introduced by `fix-command-formatter-coupling` have broken several tests that expect the old format. These tests need to be updated to match the new, improved output formats:

### Failing Tests (10)

1. **Python Format Tests** (4 failures)
   - `test_python_language_command_consistency` - ✅ FIXED
   - `test_full_format_module_header` - Expects `# Module: utils` vs `# utils`
   - `test_full_format_fields_section` - Expects `## Fields` 
   - `test_create_compact_signature_basic` - Signature format changed

2. **Markdown Tests** (5 failures)
   - Missing `headers` field in summary
   - Missing `document_metrics` in advanced
   - Section presence checks failing
   - Text format output format changed

3. **Format Specification Compliance** (4 failures)
   - Full format: Missing `## Methods` section
   - Compact format: Missing `## Fields` section  
   - CSV format: Header mismatch
   - Cross-format compliance

## Root Cause

The format improvements changed:
1. Python titles: `# sample` → `# Module: sample`
2. Section organization for better clarity
3. CSV headers for consistency
4. Markdown-specific fields structure

These are **improvements**, not regressions. Tests need to be updated to reflect the new, better formats.

## Proposed Solution

### 1. Update Python Formatter Tests
- Update expected title formats to include `Module:` prefix
- Update section expectations for new organization
- Update signature format expectations

### 2. Update Markdown Tests  
- Fix or skip tests expecting unimplemented Markdown features
- Update section presence checks
- Adjust output format expectations

### 3. Update Format Specification Compliance Tests
- Update specifications to match improved formats
- Ensure consistency across all format types
- Document the new format standards

## Success Criteria

- [ ] All tests pass
- [ ] Test expectations match actual improved output
- [ ] No regressions in functionality
- [ ] Format specifications documented

## Estimated Effort

- Analysis: 1 hour
- Test updates: 2-3 hours
- Validation: 1 hour
- **Total**: 4-5 hours

## Priority Justification

**HIGH** - Blocking CI/CD pipeline. Must be fixed before merging format improvements.

