# Tasks: Fix Java Annotation Method Query

**Change ID:** `fix-java-annotation-method-query`

---

## Task List

### Phase 1: Investigation & Validation ✅ COMPLETED

- [x] **Task 1.1**: Reproduce the issue
  - Create test Java file with annotated methods
  - Verify that `method_with_annotations` query returns 0 results
  - Document the current behavior
  - **Status**: ✅ Completed - Issue confirmed, query returns 0 results

- [x] **Task 1.2**: Analyze tree structure
  - Parse Java code with tree-sitter
  - Examine AST structure of annotated methods
  - Identify correct node hierarchy
  - **Status**: ✅ Completed - Structure documented in proposal

- [x] **Task 1.3**: Test query patterns
  - Test original broken pattern
  - Test various fix alternatives
  - Identify optimal pattern
  - **Status**: ✅ Completed - Pattern selected

---

### Phase 2: Implementation ✅ COMPLETED

- [x] **Task 2.1**: Update query definition
  - **File**: `tree_sitter_analyzer/queries/java.py`
  - **Action**: Replace broken query pattern
  - **Lines**: 105-118
  - **Validation**: Pattern syntax is valid
  - **Status**: ✅ Completed - Query fixed with `[(annotation) (marker_annotation)]+ @annotation`

- [x] **Task 2.2**: Add comprehensive test cases
  - **File**: `tests/test_queries/test_java_annotation_query.py` (created)
  - **Tests added**:
    1. Method with single marker annotation (`@Override`)
    2. Method with annotation with parameters (`@SuppressWarnings("unchecked")`)
    3. Method with multiple annotations
    4. Class with mix of annotated and non-annotated methods
    5. Capture structure validation
  - **Status**: ✅ Completed - 5 test cases created
  - **Note**: Tests currently fail due to API limitation (execute_query doesn't support custom queries)

- [ ] **Task 2.3**: Update test file used for reproduction
  - **File**: `test_annotation_issue.java` (root level, created for testing)
  - **Action**: Move to examples directory or remove
  - **Decision needed**: Keep as example or remove after testing
  - **Estimated Time**: 2 minutes

---

### Phase 3: Testing & Validation ⚠️ BLOCKED

**Note**: Manual testing with tree-sitter directly confirms the query fix works correctly. However, integration testing through the API is blocked by a separate issue where `api.execute_query()` doesn't properly execute custom queries.

- [x] **Task 3.1**: Manual validation with tree-sitter
  - Tested query pattern directly against Java AST
  - ✅ Verified: Query successfully matches annotated methods
  - ✅ Verified: Method names correctly extracted (`toString`, `testMethod`, `multiAnnotationMethod`)
  - ✅ Verified: Annotations correctly captured (`@Override`, `@Test`, `@SuppressWarnings`, `@Deprecated`)
  - ✅ Verified: Multiple annotations on one method work correctly (10 captures for 3 methods)
  - **Status**: ✅ Completed - Query fix validated

- [ ] **Task 3.2**: Run unit tests (BLOCKED)
  - Execute: `pytest tests/test_queries/test_java_annotation_query.py -v`
  - **Status**: ⚠️ Tests created but fail due to API limitation
  - **Blocker**: `api.execute_query()` doesn't execute custom queries like `method_with_annotations`
  - **Root Cause**: API only executes default queries (class, method, field)
  - **Workaround**: Manual tree-sitter testing confirms query works

- [ ] **Task 3.3**: Run integration tests (BLOCKED)
  - Test with MCP server: `execute_query` tool
  - Test with CLI: `python -m tree_sitter_analyzer.cli`
  - Test with API: `api.execute_query(...)`
  - **Status**: ⚠️ Blocked by same API limitation
  - **Acceptance**: All interfaces work correctly (after API fix)

- [ ] **Task 3.4**: Regression testing
  - Run full test suite: `pytest tests/ -v`
  - Ensure no existing tests break
  - **Status**: TODO - Can be done independently
  - **Acceptance**: No regressions

---

### Phase 4: Documentation & Cleanup 🔜 TODO

- [ ] **Task 4.1**: Update CHANGELOG
  - **File**: `CHANGELOG.md`
  - **Section**: Add entry under appropriate version
  - **Content**: Describe bug fix
  - **Estimated Time**: 5 minutes

- [ ] **Task 4.2**: Update documentation (if needed)
  - Check if `method_with_annotations` is documented
  - Update examples if they exist
  - **Files**: Check `docs/` directory
  - **Estimated Time**: 10 minutes

- [ ] **Task 4.3**: Clean up test files
  - Decision on `test_annotation_issue.java`
  - Remove temporary files
  - **Estimated Time**: 2 minutes

---

### Phase 5: Review & Merge 🔜 TODO

- [ ] **Task 5.1**: Code review
  - Create Pull Request
  - Request review from team
  - Address feedback
  - **Acceptance**: Approved by reviewer

- [ ] **Task 5.2**: Final validation
  - Run all tests one more time
  - Verify changes are complete
  - **Acceptance**: All tests pass, no warnings

- [ ] **Task 5.3**: Merge
  - Merge to develop branch (following Gitflow)
  - Tag if needed
  - **Acceptance**: Successfully merged

---

## Dependencies

- **No blocking dependencies** - all investigation completed
- Ready to proceed with implementation

---

## Risk Assessment

- **Risk Level**: 🟢 LOW
- **Reasons**:
  - Query currently doesn't work (returns 0 results)
  - Fix only adds functionality, no breaking changes
  - Well-defined solution with tested pattern
  - Limited scope (single query definition)

---

## Success Metrics

1. ✅ Query returns non-zero results for annotated methods (validated manually)
2. ✅ Method names correctly extracted (validated manually)
3. ✅ Annotations correctly captured (validated manually)
4. ⚠️ Test coverage ≥ 90% for new code (tests created but blocked by API issue)
5. ⏳ No regression in existing tests (pending verification)

---

## Current Status Summary

### ✅ Completed Work:
1. **Query Fix**: Successfully updated `method_with_annotations` query pattern
2. **Manual Validation**: Confirmed query works correctly with direct tree-sitter testing
3. **Test Creation**: Created comprehensive test suite (5 test cases)
4. **Documentation**: Created OpenSpec proposal and tasks

### ⚠️ Blocked Items:
- **API Integration Testing**: `api.execute_query()` doesn't properly execute custom queries
- **Unit Tests**: Tests fail due to API limitation, not query issue
- **Root Cause**: API's `analyze_file()` ignores the `queries` parameter

### 📋 Remaining Tasks:
1. Clean up `test_annotation_issue.java` file
2. Update CHANGELOG
3. Run regression tests
4. Create PR for review

### 🔧 Follow-up Issue:
- Consider creating a separate OpenSpec change to fix `api.execute_query()` to support custom queries
- This would allow the test suite to run properly

---

## Time Estimate

- **Total**: ~2 hours
- **Breakdown**:
  - Implementation: 30 minutes
  - Testing: 45 minutes
  - Documentation: 15 minutes
  - Review: 30 minutes

---

## Notes

- Test file `test_annotation_issue.java` created at project root during investigation
- Pattern tested successfully against tree-sitter Java grammar
- Considered multiple alternatives, selected most robust solution
