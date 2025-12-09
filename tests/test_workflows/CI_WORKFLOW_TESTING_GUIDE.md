# CI Workflow Testing Guide

## Overview

This guide provides instructions for testing the refactored `ci.yml` workflow to ensure it:
1. Uses reusable test workflow correctly
2. Has no deployment logic
3. Uses composite setup-system action
4. Maintains all CI-specific jobs
5. Triggers correctly on push and PR events

## Local Validation

### 1. Run Validation Script

```bash
python tests/test_workflows/validate_ci_workflow.py
```

This script validates:
- ✓ CI workflow uses reusable-test.yml
- ✓ No deployment logic present
- ✓ Uses composite setup-system action
- ✓ All CI-specific jobs present
- ✓ Appropriate triggers configured
- ✓ Consistent --all-extras flag usage

### 2. Run Property-Based Tests

```bash
uv run pytest tests/test_workflows/test_ci_workflow_consistency.py -v
```

This runs property-based tests that verify:
- **Property 1**: Test Configuration Consistency
- **Property 10**: Deployment Branch Restriction

## Testing on Feature Branch

### Step 1: Create Test Feature Branch

```bash
git checkout -b test/ci-workflow-refactor
git add .github/workflows/ci.yml
git commit -m "refactor: Update ci.yml to use reusable workflows"
git push origin test/ci-workflow-refactor
```

### Step 2: Verify Workflow Triggers

1. **Push Event**: The workflow should trigger automatically on push
2. **Check GitHub Actions**: Go to Actions tab and verify:
   - ✓ CI workflow is running
   - ✓ Test job is executing (using reusable-test.yml)
   - ✓ Security-check job is running
   - ✓ Documentation-check job is running
   - ✓ Build-check job is running

### Step 3: Create Pull Request

```bash
# Create PR to develop branch
gh pr create --base develop --title "Test: CI workflow refactor" --body "Testing CI workflow changes"
```

Verify:
- ✓ CI workflow triggers on PR creation
- ✓ All jobs execute successfully
- ✓ No deployment attempts occur

### Step 4: Verify Test Matrix Execution

Check that tests run on all platforms:
- ✓ ubuntu-latest (Python 3.10, 3.11, 3.12, 3.13)
- ✓ windows-latest (Python 3.11, 3.12, 3.13)
- ✓ macos-latest (Python 3.11, 3.12, 3.13)

### Step 5: Verify Coverage Upload

Check that coverage is uploaded correctly:
- ✓ Coverage runs on ubuntu-latest with Python 3.11
- ✓ Coverage is uploaded to Codecov
- ✓ Coverage report is generated

### Step 6: Verify No Deployment

Confirm that:
- ✓ No PyPI deployment occurs
- ✓ No PYPI_TOKEN is used
- ✓ No `twine upload` commands are executed

## Expected Results

### ✅ Success Criteria

1. **Test Job**:
   - Uses `./.github/workflows/reusable-test.yml`
   - Inherits secrets properly
   - Runs on all platforms and Python versions
   - Uploads coverage on ubuntu-latest with Python 3.11

2. **Security Check Job**:
   - Uses composite setup-system action
   - Runs bandit security checks
   - Runs safety checks

3. **Documentation Check Job**:
   - Uses composite setup-system action
   - Tests README examples
   - Verifies MCP setup

4. **Build Check Job**:
   - Uses composite setup-system action
   - Builds package successfully
   - Checks package with twine
   - Tests wheel installation

5. **No Deployment**:
   - No PyPI deployment jobs
   - No PyPI token usage
   - No twine upload commands

### ❌ Failure Scenarios

If any of these occur, the refactoring needs adjustment:

1. **Test job doesn't use reusable workflow**
   - Fix: Update test job to use `./.github/workflows/reusable-test.yml`

2. **Deployment logic present**
   - Fix: Remove any PyPI deployment steps or jobs

3. **System dependencies not using composite action**
   - Fix: Replace inline system dependency installation with composite action

4. **Tests fail on specific platforms**
   - Fix: Check reusable-test.yml for platform-specific issues

5. **Coverage not uploading**
   - Fix: Verify CODECOV_TOKEN secret is available

## Comparison with Other Workflows

### CI vs Develop Workflow

| Aspect | CI Workflow | Develop Workflow |
|--------|-------------|------------------|
| Test Job | Uses reusable-test.yml | Uses reusable-test.yml |
| Deployment | ❌ No deployment | ❌ No deployment |
| PR Creation | ❌ No PR creation | ✅ Creates PR to main |
| Build Job | ✅ Build check only | ✅ Build and upload artifacts |
| Triggers | Push/PR to main/develop | Push to develop |

### CI vs Release Workflow

| Aspect | CI Workflow | Release Workflow |
|--------|-------------|------------------|
| Test Job | Uses reusable-test.yml | Uses reusable-test.yml |
| Deployment | ❌ No deployment | ✅ Deploys to PyPI |
| PR Creation | ❌ No PR creation | ✅ Creates PR to main |
| Build Job | ✅ Build check only | ✅ Build and deploy |
| Triggers | Push/PR to main/develop | Push to release/* |

## Manual Testing Checklist

Before merging the CI workflow changes:

- [ ] Local validation script passes
- [ ] Property-based tests pass
- [ ] CI workflow triggers on push to feature branch
- [ ] CI workflow triggers on PR to develop
- [ ] Test job executes successfully on all platforms
- [ ] Security-check job executes successfully
- [ ] Documentation-check job executes successfully
- [ ] Build-check job executes successfully
- [ ] Coverage uploads to Codecov
- [ ] No deployment attempts occur
- [ ] No PyPI tokens are used
- [ ] Workflow completes in reasonable time (~15-20 minutes)

## Troubleshooting

### Issue: Test job fails to find reusable workflow

**Solution**: Ensure the path is correct: `./.github/workflows/reusable-test.yml`

### Issue: Secrets not inherited

**Solution**: Add `secrets: inherit` to the test job

### Issue: System dependencies fail to install

**Solution**: Verify composite action path: `./.github/actions/setup-system`

### Issue: Coverage upload fails

**Solution**: Check that CODECOV_TOKEN secret is configured in repository settings

### Issue: Tests fail on Windows

**Solution**: Check reusable-test.yml for Windows-specific test configuration

## Next Steps

After successful testing:

1. Merge the feature branch to develop
2. Monitor CI workflow execution on develop branch
3. Verify consistency with other branch workflows
4. Update documentation if needed
5. Consider adding workflow to pre-commit hooks

## Related Documentation

- [Reusable Test Workflow](.github/workflows/reusable-test.yml)
- [Composite Setup Action](.github/actions/setup-system/action.yml)
- [Develop Workflow Testing Guide](tests/test_workflows/DEVELOP_WORKFLOW_TESTING_GUIDE.md)
- [Release Workflow Testing Guide](tests/test_workflows/RELEASE_WORKFLOW_TESTING_GUIDE.md)
- [Hotfix Workflow Testing Guide](tests/test_workflows/HOTFIX_WORKFLOW_TESTING_GUIDE.md)
