# Hotfix Workflow Testing Guide

## Overview

This guide provides instructions for testing the refactored hotfix workflow to ensure it works correctly in production.

## Automated Validation

### Local Validation

Run the validation script to check workflow configuration:

```bash
uv run python tests/test_workflows/validate_hotfix_workflow.py
```

This validates:
- ✅ Test job uses reusable workflow
- ✅ Deployment depends on tests
- ✅ PR creation depends on both test and deployment
- ✅ Workflow triggers on hotfix/* branches
- ✅ Configuration matches release workflow

### Property-Based Tests

Run the property-based tests:

```bash
uv run pytest tests/test_workflows/test_hotfix_workflow_consistency.py -v
```

This validates:
- **Property 5**: Deployment Dependency on Tests
- **Property 8**: Test Matrix Consistency

## Manual Testing on GitHub

### Prerequisites

1. Access to the repository with push permissions
2. PyPI API token configured in repository secrets
3. Codecov token configured in repository secrets

### Test Procedure

#### Step 1: Create Test Hotfix Branch

```bash
# Create a test hotfix branch
git checkout -b hotfix/test-workflow-v0.0.0

# Make a small change (e.g., update a comment)
echo "# Test hotfix workflow" >> tests/test_workflows/HOTFIX_WORKFLOW_TESTING_GUIDE.md

# Commit and push
git add .
git commit -m "test: Validate hotfix workflow"
git push origin hotfix/test-workflow-v0.0.0
```

#### Step 2: Monitor Workflow Execution

1. Go to GitHub Actions tab
2. Find the "Hotfix Branch Automation" workflow run
3. Monitor the execution

#### Step 3: Verify Test Job

Check that the test job:
- ✅ Uses reusable-test.yml workflow
- ✅ Runs on multiple OS platforms (ubuntu, windows, macos)
- ✅ Tests Python 3.10, 3.11, 3.12, 3.13
- ✅ Installs system dependencies (fd, ripgrep)
- ✅ Runs quality checks on ubuntu-latest with Python 3.11
- ✅ Uploads coverage to Codecov
- ✅ Updates README statistics

#### Step 4: Verify Deployment Job

Check that the deployment job:
- ✅ Only runs after test job succeeds
- ✅ Builds the package
- ✅ Checks the package with twine
- ✅ Uploads to PyPI (or test PyPI)

**Note**: For testing purposes, you may want to:
- Use test PyPI instead of production PyPI
- Modify the workflow temporarily to skip actual deployment
- Use a test version number (e.g., v0.0.0-test)

#### Step 5: Verify PR Creation

Check that the PR creation job:
- ✅ Only runs after both test and deployment succeed
- ✅ Creates a PR to main branch
- ✅ Uses "hotfix-to-main" as the PR branch
- ✅ Includes proper title and description
- ✅ Has correct labels and metadata

#### Step 6: Verify Workflow Consistency

Compare the hotfix workflow execution with a recent release workflow execution:
- ✅ Same test matrix (Python versions and OS)
- ✅ Same quality checks
- ✅ Same system dependencies
- ✅ Same deployment process
- ✅ Same PR creation process

### Expected Results

#### Successful Execution

```
✅ Test Job (reusable-test.yml)
   ├─ Test Matrix (ubuntu-latest, Python 3.10) - PASSED
   ├─ Test Matrix (ubuntu-latest, Python 3.11) - PASSED (with coverage)
   ├─ Test Matrix (ubuntu-latest, Python 3.12) - PASSED
   ├─ Test Matrix (ubuntu-latest, Python 3.13) - PASSED
   ├─ Test Matrix (windows-latest, Python 3.11) - PASSED
   ├─ Test Matrix (windows-latest, Python 3.12) - PASSED
   ├─ Test Matrix (windows-latest, Python 3.13) - PASSED
   ├─ Test Matrix (macos-13, Python 3.11) - PASSED
   ├─ Test Matrix (macos-13, Python 3.12) - PASSED
   └─ Test Matrix (macos-13, Python 3.13) - PASSED

✅ Build and Deploy Job
   ├─ Build package - PASSED
   ├─ Check package - PASSED
   └─ Deploy to PyPI - PASSED

✅ Create Main PR Job
   └─ Create PR to main - PASSED
```

#### Failure Scenarios

If tests fail:
```
❌ Test Job - FAILED
⏭️  Build and Deploy Job - SKIPPED
⏭️  Create Main PR Job - SKIPPED
```

If deployment fails:
```
✅ Test Job - PASSED
❌ Build and Deploy Job - FAILED
⏭️  Create Main PR Job - SKIPPED
```

## Troubleshooting

### Test Job Fails

**Symptom**: Test job fails in reusable workflow

**Possible Causes**:
1. Test failures in the code
2. System dependencies not installed correctly
3. Quality checks failing

**Resolution**:
1. Check test logs for specific failures
2. Run tests locally: `uv run pytest tests/ -v`
3. Run quality checks: `uv run python check_quality.py --new-code-only`
4. Verify system dependencies are installed

### Deployment Job Fails

**Symptom**: Deployment job fails after tests pass

**Possible Causes**:
1. PyPI credentials not configured
2. Package version already exists
3. Package build errors

**Resolution**:
1. Verify PYPI_API_TOKEN secret is set
2. Check package version in pyproject.toml
3. Run build locally: `uv run python -m build`
4. Check package: `uv run twine check dist/*`

### PR Creation Fails

**Symptom**: PR creation job fails after deployment

**Possible Causes**:
1. GITHUB_TOKEN permissions insufficient
2. Branch already exists
3. PR already exists

**Resolution**:
1. Verify workflow has `contents: write` and `pull-requests: write` permissions
2. Delete existing "hotfix-to-main" branch if it exists
3. Close existing PR if it exists

### Workflow Not Triggering

**Symptom**: Workflow doesn't run when pushing to hotfix branch

**Possible Causes**:
1. Branch name doesn't match pattern
2. Workflow file has syntax errors
3. Workflow is disabled

**Resolution**:
1. Ensure branch name starts with `hotfix/`
2. Validate workflow syntax: `actionlint .github/workflows/hotfix-automation.yml`
3. Check workflow is enabled in GitHub Actions settings

## Cleanup

After testing, clean up the test resources:

```bash
# Delete the test branch locally
git branch -D hotfix/test-workflow-v0.0.0

# Delete the test branch remotely
git push origin --delete hotfix/test-workflow-v0.0.0

# Close the test PR on GitHub (if created)
# Delete the hotfix-to-main branch (if created)
```

## Comparison with Release Workflow

The hotfix workflow should be identical to the release workflow except for:

| Aspect | Hotfix Workflow | Release Workflow |
|--------|----------------|------------------|
| Trigger branches | `hotfix/*` | `release/v*` |
| PR branch name | `hotfix-to-main` | `release-to-main` |
| PR title prefix | "🚨 Hotfix:" | "🚀 Release to Main:" |
| PR body emphasis | Critical bug fix | Version release |

All other aspects (test matrix, quality checks, deployment, etc.) should be identical.

## Success Criteria

The hotfix workflow is considered successfully tested when:

- ✅ All automated validations pass
- ✅ All property-based tests pass
- ✅ Workflow triggers correctly on hotfix/* branches
- ✅ Test job executes with full matrix
- ✅ Deployment only occurs after tests pass
- ✅ PR creation only occurs after deployment succeeds
- ✅ Configuration matches release workflow
- ✅ No regressions in existing functionality

## Next Steps

After successful testing:

1. Document any issues encountered and their resolutions
2. Update this guide with any new findings
3. Proceed to task 5: Update main branch CI workflow
4. Monitor production hotfix workflows for any issues

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [GitFlow Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow)
- Design Document: `.kiro/specs/github-actions-consistency/design.md`
- Requirements Document: `.kiro/specs/github-actions-consistency/requirements.md`
