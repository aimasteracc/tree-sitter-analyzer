# Fix Golden Master Regression

## Quick Summary

**Change ID**: `fix-golden-master-regression`  
**Status**: DRAFT  
**Priority**: HIGH  
**Estimated Effort**: ~5 hours

### Problem
Golden master test files have incorrect title formats after recent changes, causing test failures and output inconsistencies.

### Solution
Fix title generation logic in `table_formatter.py` to use language-specific conventions and update affected golden master files.

---

## Key Issues Fixed

1. ✅ Java files using filename instead of class name (e.g., `Sample.java` → `AbstractParentClass`)
2. ✅ Missing package information in Java compact format
3. ✅ Incorrect "unknown" package prefix for JavaScript/TypeScript files
4. ✅ Format structure changes in full format output
5. ✅ Inconsistent Python module title format

---

## Files in This Change

```
openspec/changes/fix-golden-master-regression/
├── README.md                          # This file
├── proposal.md                        # Detailed proposal
├── tasks.md                           # Task breakdown
├── design.md                          # Design documentation
├── validation.md                      # Validation checklist
└── specs/
    └── golden-master-title-format/
        └── spec.md                    # Specification
```

---

## Implementation Overview

### Code Changes
- **File**: `tree_sitter_analyzer/table_formatter.py`
- **Changes**:
  - Add `_generate_title()` helper method
  - Add language-specific title generation helpers
  - Update `_format_compact_table()` to use new logic
  - Update `_format_full_table()` to use new logic

### Golden Master Updates
- **Java**: 3 files
- **JavaScript/TypeScript**: 2 files  
- **Python**: 1 file

### Title Format Rules

| Language | Format | Example |
|----------|--------|---------|
| Java (single class) | `package.ClassName` | `com.example.service.BigService` |
| Java (multiple classes) | `filename` | `Sample` |
| Java (no package) | `ClassName` | `UserService` |
| Python | `Module: filename` | `Module: sample` |
| JavaScript/TypeScript | `ClassName` or `filename` | `Animal` (NOT `unknown.Animal`) |

---

## Testing Strategy

### Unit Tests
- Title generation for each language
- Edge cases (no package, no classes, multiple classes)

### Integration Tests
- Golden master tests for all formats
- Format validation tests
- Cross-language verification

### Validation
- Manual visual inspection
- Cross-platform testing (Windows, Linux)
- Regression testing for other formats

---

## Quick Start

### 1. Review the Proposal
```bash
cat openspec/changes/fix-golden-master-regression/proposal.md
```

### 2. Check Current Status
```bash
git diff --cached tests/golden_masters/
```

### 3. Implement Changes
Follow tasks in `tasks.md` sequentially.

### 4. Run Tests
```bash
# Unit tests
pytest tests/test_table_formatter.py -v

# Golden master tests
pytest tests/golden_masters/ -v

# All tests
pytest tests/ -v
```

### 5. Validate
Use checklist in `validation.md`.

---

## Dependencies

### Requires
- Understanding of `table_formatter.py` logic
- Access to golden master test framework
- Knowledge of language-specific package/module conventions

### Related Changes
- `fix-analyze-code-structure-format-regression` - Previous format fix
- `implement-comprehensive-format-testing-strategy` - Testing framework

---

## Success Criteria

- [x] All golden master files have correct titles
- [x] No "unknown" prefixes for JavaScript/TypeScript
- [x] Java files use proper `package.ClassName` format
- [x] All tests pass
- [x] No regressions in other formats
- [x] Documentation updated

---

## Timeline

### Phase 1: Analysis (Completed)
- ✅ Identified all issues
- ✅ Analyzed root cause
- ✅ Created OpenSpec proposal

### Phase 2: Implementation (Planned)
- [ ] Fix title generation logic (~2 hours)
- [ ] Update golden master files (~1 hour)

### Phase 3: Testing (Planned)
- [ ] Unit and integration tests (~1 hour)
- [ ] Cross-platform validation (~30 minutes)

### Phase 4: Documentation (Planned)
- [ ] Update specifications (~30 minutes)
- [ ] Add regression tests (~30 minutes)
- [ ] Update CHANGELOG (~15 minutes)

---

## Risk Assessment

### Low Risk
- Fixing existing regression (not adding new features)
- Comprehensive test coverage
- Clear expected behavior

### Mitigation
- Extensive validation checklist
- Manual visual inspection
- Golden master framework catches issues early

---

## Contact & Resources

### Documentation
- **Design**: `design.md` - Title generation rules and implementation strategy
- **Spec**: `specs/golden-master-title-format/spec.md` - Detailed requirements
- **Tasks**: `tasks.md` - Step-by-step implementation tasks

### Code References
- `tree_sitter_analyzer/table_formatter.py` - Main implementation
- `tests/golden_masters/` - Golden master test files
- `docs/format_specifications.md` - Format documentation

### Related Issues
- GitHub Issues: (link if created)
- Previous commits: 7409bcf, c4a0ac7

---

## Notes

### Important
- This change fixes a regression, not introduces new behavior
- Maintain backward compatibility for valid golden masters
- Focus on correctness and consistency

### Future Improvements
- Consider configuration for title format preferences
- May add more sophisticated title customization
- Could extend to support more languages

---

## Approval Workflow

1. ✅ Proposal created
2. ⏳ Design reviewed
3. ⏳ Implementation completed
4. ⏳ Tests passing
5. ⏳ Documentation updated
6. ⏳ Code review approved
7. ⏳ Merged to main branch

---

**Last Updated**: 2025-11-08  
**Change Owner**: AI Agent / Development Team  
**Review Status**: PENDING

