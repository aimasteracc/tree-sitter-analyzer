# Release Workflow Testing Guide

This guide provides instructions for testing the refactored release workflow on a test release branch.

## Prerequisites

- All property tests must pass: `uv run pytest tests/test_workflows/test_release_workflow_consistency.py -v`
- Validation script must pass: `uv run python tests/test_workflows/validate_release_workflow.py`
- You must have push access to the repository

## Testing Steps

### 1. Local Validation

Before creating a test branch, validate the workflow locally:

```bash
# Run property tests
uv run pytest tests/test_workflows/test_release_workflow_consistency.py -v

# Run validation script
uv run python tests/test_workflows/validate_release_workflow.py
```

Both should pass with no errors.

### 2. Create Test Release Branch

Create a test release branch with a test version number:

```bash
# Ensure you're on the latest develop or feature branch
git checkout develop  # or your feature branch
git pull

# Create test release branch
git checkout -b release/v0.0.0-test

# Push to remote
git push origin release/v0.0.0-test
```

### 3. Monitor Workflow Execution

1. Go to GitHub Actions: `https://github.com/your-org/tree-sitter-analyzer/actions`
2. Find the "Release Branch Automation" workflow run
3. Monitor the execution in real-time

### 4. Verify Test Job

The test job should:

- ✅ Use the reusable-test.yml workflow
- ✅ Run tests across multiple Python versions (3.10, 3.11, 3.12, 3.13)
- ✅ Run tests across multiple OS platforms (ubuntu-latest, windows-latest, macos-13)
- ✅ Install system dependencies (fd, ripgrep)
- ✅ Run pre-commit quality checks
- ✅ Upload coverage to Codecov
- ✅ Update README statistics

**Expected Duration**: 10-15 minutes

**How to Verify**:
- Check that the test job shows "uses: ./.github/workflows/reusable-test.yml"
- Verify all matrix combinations execute
- Check that coverage is uploaded successfully
- Ensure no test failures occur

### 5. Verify Build and Deploy Job

The build-and-deploy job should:

- ✅ Wait for test job to complete successfully
- ✅ Only run after tests pass
- ✅ Build the Python package
- ✅ Check the package with twine
- ✅ Attempt to deploy to PyPI (will fail with test version, which is expected)

**Expected Duration**: 2-3 minutes

**How to Verify**:
- Check that build-and-deploy job has `needs: test` dependency
- Verify package build completes successfully
- Verify twine check passes
- Note: PyPI upload may fail with test version - this is expected and acceptable

**Important**: For a real test, you may want to:
- Use Test PyPI instead: `https://test.pypi.org/`
- Modify the workflow temporarily to use Test PyPI
- Or skip the actual upload step and just verify the build

### 6. Verify PR Creation Job

The create-main-pr job should:

- ✅ Wait for both test and build-and-deploy jobs to complete
- ✅ Create a pull request to the main branch
- ✅ Include comprehensive PR description
- ✅ Set appropriate PR title and labels

**Expected Duration**: 1 minute

**How to Verify**:
- Check that create-main-pr job has `needs: [test, build-and-deploy]` dependency
- Verify a PR is created to main branch
- Check PR title: "🚀 Release to Main: release/v0.0.0-test"
- Verify PR description includes test results and deployment status

### 7. Verify Workflow Consistency

Compare the release workflow execution with develop workflow:

- ✅ Same test matrix (Python versions, OS platforms)
- ✅ Same system dependencies installed
- ✅ Same quality checks executed
- ✅ Same test commands used
- ✅ Same coverage configuration

**How to Verify**:
- Run property tests: `uv run pytest tests/test_workflows/test_release_workflow_consistency.py::TestReleaseWorkflowConsistency::test_release_workflow_test_configuration_matches_develop -v`
- Compare workflow logs between develop and release branches
- Verify test execution times are similar

## Expected Results

### Success Criteria

All of the following must be true:

1. ✅ Test job completes successfully
2. ✅ All tests pass across all platforms
3. ✅ Quality checks pass
4. ✅ Coverage is uploaded
5. ✅ Build-and-deploy job runs after tests
6. ✅ Package builds successfully
7. ✅ PR to main is created
8. ✅ No workflow syntax errors
9. ✅ Workflow uses reusable components correctly
10. ✅ Test configuration matches develop workflow

### Known Issues / Expected Failures

The following are expected and acceptable:

- ⚠️ PyPI upload may fail with test version (v0.0.0-test)
  - This is expected because test versions are not valid for PyPI
  - Solution: Use Test PyPI or skip upload verification

- ⚠️ Some platform-specific tests may be skipped
  - This is expected and configured in the test matrix
  - Windows and macOS may skip Python 3.10 tests

## Troubleshooting

### Test Job Fails

**Problem**: Test job fails with errors

**Solutions**:
1. Check test logs for specific failures
2. Run tests locally: `uv run pytest tests/ -v`
3. Verify system dependencies are installed correctly
4. Check for platform-specific issues

### Build Job Fails

**Problem**: Build-and-deploy job fails

**Solutions**:
1. Verify package builds locally: `uv run python -m build`
2. Check twine validation: `uv run twine check dist/*`
3. Verify all dependencies are installed

### PyPI Upload Fails

**Problem**: PyPI upload fails with authentication or version errors

**Solutions**:
1. For test branches, this is expected - skip this verification
2. For real releases, verify PYPI_API_TOKEN secret is configured
3. Consider using Test PyPI for testing: `https://test.pypi.org/`

### PR Creation Fails

**Problem**: PR to main is not created

**Solutions**:
1. Verify GITHUB_TOKEN has correct permissions
2. Check that main branch exists
3. Verify peter-evans/create-pull-request action version is correct

## Cleanup

After testing is complete:

```bash
# Delete the test release branch locally
git checkout develop
git branch -D release/v0.0.0-test

# Delete the test release branch remotely
git push origin --delete release/v0.0.0-test

# Close the test PR on GitHub (if created)
# Go to the PR and click "Close pull request"
```

## Next Steps

Once testing is successful:

1. ✅ Mark task 3.3 as complete
2. ✅ Document any issues or improvements needed
3. ✅ Proceed to task 4: Update hotfix branch workflow
4. ✅ Consider creating a similar test for hotfix workflow

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [PyPI Publishing](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [Test PyPI](https://test.pypi.org/)

## Validation Checklist

Use this checklist to verify the release workflow:

- [ ] Local property tests pass
- [ ] Local validation script passes
- [ ] Test release branch created
- [ ] Workflow triggers on push
- [ ] Test job uses reusable workflow
- [ ] Tests run across all platforms
- [ ] Quality checks execute
- [ ] Coverage uploads successfully
- [ ] Build-and-deploy waits for tests
- [ ] Package builds successfully
- [ ] Twine check passes
- [ ] PR to main is created
- [ ] PR has correct title and description
- [ ] Test configuration matches develop
- [ ] No workflow syntax errors
- [ ] Cleanup completed

---

**Note**: This is a test workflow execution. For production releases, ensure all secrets are properly configured and version numbers are valid.
