# CI/CD Migration Guide

## Introduction

This guide documents the migration from the old GitHub Actions workflow structure to the new reusable workflow architecture. It explains what changed, why it changed, and what developers need to know.

## Executive Summary

### What Changed

The tree-sitter-analyzer project has migrated from duplicated inline workflows to a reusable workflow architecture. This change ensures consistent testing across all branches (develop, release, hotfix, main) and eliminates the issue where tests passed on develop but failed on release/main.

### Why It Changed

**Problem**: Tests were inconsistent across branches, causing:
- Tests passing on develop but failing on release/main
- Unnecessary version increments
- Violation of GitFlow best practices
- Maintenance burden from duplicated workflow code

**Solution**: Reusable workflows that define test behavior once and are used by all branches.

### Impact on Developers

- **Positive**: More reliable CI/CD, consistent test results across branches
- **Minimal Changes**: Developer workflow remains largely the same
- **New Features**: Better error messages, improved troubleshooting

## Migration Timeline

| Phase | Date | Description |
|-------|------|-------------|
| Phase 1 | Week 1 | Created reusable workflows and composite actions |
| Phase 2 | Week 2 | Updated develop branch workflow |
| Phase 3 | Week 3 | Updated release and hotfix branch workflows |
| Phase 4 | Week 4 | Updated main branch CI workflow |
| Phase 5 | Week 5 | Documentation and monitoring |

## Detailed Changes

### 1. New Reusable Workflows

#### Reusable Test Workflow

**File**: `.github/workflows/reusable-test.yml`

**Purpose**: Defines the complete test suite used by all branches.

**Features**:
- Unified test matrix (Python 3.10-3.13, ubuntu/windows/macos)
- Consistent system dependency installation
- Standardized quality checks
- Coverage reporting
- README statistics updates

**Before**: Each branch had its own inline test configuration
**After**: All branches call this reusable workflow

#### Reusable Quality Check Workflow

**File**: `.github/workflows/reusable-quality.yml`

**Purpose**: Standardized quality gate checks.

**Features**:
- mypy type checking
- black code formatting
- ruff linting
- isort import sorting
- bandit security checks
- pydocstyle documentation checks

**Before**: Quality checks were inconsistent or missing
**After**: All branches use the same quality checks

#### Composite System Setup Action

**File**: `.github/actions/setup-system/action.yml`

**Purpose**: Consistent system dependency installation.

**Features**:
- Platform-specific installation (Linux/macOS/Windows)
- fd and ripgrep installation
- Symlink creation (Ubuntu)
- Installation verification

**Before**: Each workflow had its own installation logic
**After**: All workflows use this composite action

### 2. Updated Branch Workflows

#### Develop Branch Workflow

**File**: `.github/workflows/develop-automation.yml`

**Changes**:

```yaml
# BEFORE
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Install dependencies
        run: |
          # Inline installation logic
      - name: Run tests
        run: |
          # Inline test logic

# AFTER
jobs:
  test:
    uses: ./.github/workflows/reusable-test.yml
    secrets: inherit
```

**Key Differences**:
- Uses reusable-test.yml instead of inline configuration
- Passes secrets using `secrets: inherit`
- Maintains PR creation logic
- No deployment (as before)

#### Release Branch Workflow

**File**: `.github/workflows/release-automation.yml`

**Changes**:

```yaml
# BEFORE
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Install dependencies
        run: |
          # Different installation logic than develop
      - name: Run tests
        run: |
          # Different test configuration

  deploy:
    needs: test
    steps:
      # Deployment logic

# AFTER
jobs:
  test:
    uses: ./.github/workflows/reusable-test.yml
    secrets: inherit

  deploy:
    needs: test
    steps:
      # Same deployment logic
```

**Key Differences**:
- Uses reusable-test.yml (now identical to develop)
- Deployment still requires test success
- Maintains PyPI deployment logic
- Maintains PR creation to main

#### Hotfix Branch Workflow

**File**: `.github/workflows/hotfix-automation.yml`

**Changes**:

```yaml
# BEFORE
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Install dependencies
        run: |
          # Yet another installation variant
      - name: Run tests
        run: |
          # Yet another test configuration

  deploy:
    needs: test
    steps:
      # Deployment logic

# AFTER
jobs:
  test:
    uses: ./.github/workflows/reusable-test.yml
    secrets: inherit

  deploy:
    needs: test
    steps:
      # Same deployment logic
```

**Key Differences**:
- Uses reusable-test.yml (now identical to develop and release)
- Deployment still requires test success
- Maintains PyPI deployment logic
- Maintains PR creation to main

#### Main Branch CI Workflow

**File**: `.github/workflows/ci.yml`

**Changes**:

```yaml
# BEFORE
jobs:
  test-matrix:
    strategy:
      matrix:
        # Different matrix configuration
    steps:
      - name: Install dependencies
        run: |
          # Different installation logic
      - name: Run tests
        run: |
          # Different test configuration

# AFTER
jobs:
  test-matrix:
    strategy:
      matrix:
        # Same matrix as reusable workflow
    steps:
      - uses: ./.github/actions/setup-system
      - name: Run tests
        run: |
          # Same test configuration
```

**Key Differences**:
- Uses setup-system composite action
- Test matrix now matches other branches
- Maintains additional jobs (security, documentation, build checks)
- No deployment (as before)

### 3. Test Configuration Changes

#### Test Matrix

**Before**: Different matrices across branches

```yaml
# develop-automation.yml
matrix:
  python-version: ["3.10", "3.11", "3.12"]
  os: [ubuntu-latest]

# release-automation.yml
matrix:
  python-version: ["3.11", "3.12", "3.13"]
  os: [ubuntu-latest, windows-latest]

# ci.yml
matrix:
  python-version: ["3.10", "3.11"]
  os: [ubuntu-latest, macos-latest]
```

**After**: Unified matrix across all branches

```yaml
# All workflows use the same matrix
matrix:
  python-version: ["3.10", "3.11", "3.12", "3.13"]
  os: [ubuntu-latest, windows-latest, macos-latest]
  exclude:
    - os: windows-latest
      python-version: "3.10"
    - os: macos-latest
      python-version: "3.10"
```

#### Dependency Installation

**Before**: Inconsistent installation flags

```yaml
# develop-automation.yml
pip install -e .

# release-automation.yml
pip install -e .[dev]

# ci.yml
pip install -e .[all]
```

**After**: Consistent installation across all branches

```yaml
# All workflows use the same installation
uv sync --all-extras
```

#### System Dependencies

**Before**: Inconsistent or missing

```yaml
# develop-automation.yml
# No system dependencies installed

# release-automation.yml
apt-get install fd-find

# ci.yml
brew install ripgrep
```

**After**: Consistent across all platforms

```yaml
# All workflows use setup-system action
- uses: ./.github/actions/setup-system
  with:
    os: ${{ matrix.os }}
```

### 4. Quality Check Changes

**Before**: Inconsistent or missing quality checks

```yaml
# develop-automation.yml
# No quality checks

# release-automation.yml
# Some quality checks

# ci.yml
# Different quality checks
```

**After**: Consistent quality checks across all branches

```yaml
# All workflows run the same quality checks
- name: Run pre-commit checks
  run: uv run pre-commit run --all-files
```

Quality checks now include:
- mypy (type checking)
- black (code formatting)
- ruff (linting)
- isort (import sorting)
- bandit (security)
- pydocstyle (documentation)

## Before and After Comparison

### Workflow Execution Flow

#### Before

```
develop branch:
  → Install some dependencies
  → Run some tests
  → Create PR

release branch:
  → Install different dependencies
  → Run different tests
  → Deploy to PyPI
  → Create PR

Result: Tests pass on develop, fail on release
```

#### After

```
develop branch:
  → Call reusable-test.yml
    → Install all dependencies (--all-extras)
    → Run full test matrix
    → Run quality checks
  → Create PR

release branch:
  → Call reusable-test.yml (same as develop)
    → Install all dependencies (--all-extras)
    → Run full test matrix
    → Run quality checks
  → Deploy to PyPI (only if tests pass)
  → Create PR

Result: Tests consistent across all branches
```

### Test Coverage

#### Before

| Branch | Python Versions | OS Platforms | System Deps | Quality Checks |
|--------|----------------|--------------|-------------|----------------|
| develop | 3.10, 3.11, 3.12 | ubuntu | None | None |
| release | 3.11, 3.12, 3.13 | ubuntu, windows | fd only | Some |
| hotfix | 3.11, 3.12 | ubuntu | ripgrep only | Some |
| main | 3.10, 3.11 | ubuntu, macos | Both | Different |

#### After

| Branch | Python Versions | OS Platforms | System Deps | Quality Checks |
|--------|----------------|--------------|-------------|----------------|
| develop | 3.10, 3.11, 3.12, 3.13 | ubuntu, windows, macos | fd, ripgrep | All |
| release | 3.10, 3.11, 3.12, 3.13 | ubuntu, windows, macos | fd, ripgrep | All |
| hotfix | 3.10, 3.11, 3.12, 3.13 | ubuntu, windows, macos | fd, ripgrep | All |
| main | 3.10, 3.11, 3.12, 3.13 | ubuntu, windows, macos | fd, ripgrep | All |

## What Developers Need to Know

### No Changes Required

For most developers, **no changes are required** to your workflow:

1. Continue developing on feature branches
2. Create PRs to develop as usual
3. Tests will run automatically
4. Merge when tests pass

### What's Different

#### More Comprehensive Testing

Tests now run on more platforms and Python versions:
- **Before**: Limited testing on develop
- **After**: Full testing on all branches

**Impact**: You may discover platform-specific issues earlier.

**Action**: Test your code on multiple platforms if possible.

#### Stricter Quality Checks

All branches now enforce quality checks:
- **Before**: Quality checks were inconsistent
- **After**: All branches require passing quality checks

**Impact**: You must fix quality issues before merging.

**Action**: Run `uv run pre-commit run --all-files` before pushing.

#### Longer Workflow Times

Workflows may take longer due to comprehensive testing:
- **Before**: ~5-10 minutes on develop
- **After**: ~15-20 minutes on all branches

**Impact**: Wait longer for CI/CD results.

**Action**: Run tests locally first to catch issues early.

### Best Practices

#### Before Pushing

```bash
# 1. Run tests locally
uv run pytest tests/ -v

# 2. Run quality checks
uv run pre-commit run --all-files

# 3. Verify system dependencies work
fd --version
rg --version

# 4. Push with confidence
git push
```

#### Monitoring Workflows

1. Check GitHub Actions tab after pushing
2. Review workflow logs if tests fail
3. Fix issues and push again
4. Don't merge until all checks pass

#### Troubleshooting

If workflows fail:

1. Check the [CI/CD Troubleshooting Guide](ci-cd-troubleshooting.md)
2. Reproduce the issue locally
3. Fix and verify locally
4. Push and verify in CI/CD

## Rollback Procedures

If critical issues arise, rollback procedures are available.

### Emergency Rollback

To rollback to the old workflow structure:

```bash
# 1. Checkout the commit before migration
git checkout <commit-before-migration>

# 2. Create emergency branch
git checkout -b emergency/rollback-workflows

# 3. Copy old workflow files
git checkout <commit-before-migration> -- .github/workflows/

# 4. Commit and push
git commit -m "Emergency rollback to old workflows"
git push origin emergency/rollback-workflows

# 5. Create PR and merge immediately
```

### Partial Rollback

To rollback a specific branch workflow:

```bash
# Example: Rollback develop workflow only
git checkout <commit-before-migration> -- .github/workflows/develop-automation.yml
git commit -m "Rollback develop workflow"
git push
```

### Post-Rollback Actions

After rollback:

1. Document the issue that caused rollback
2. Create GitHub issue with details
3. Plan fix and re-migration
4. Test thoroughly before re-deploying

## Testing the Migration

### Validation Steps

Before considering migration complete:

- [x] Reusable workflows created and validated
- [x] Develop workflow updated and tested
- [x] Release workflow updated and tested
- [x] Hotfix workflow updated and tested
- [x] Main CI workflow updated and tested
- [x] Property-based tests implemented
- [x] Documentation created
- [ ] All workflows tested on real branches
- [ ] Deployment tested on test release
- [ ] Team trained on new workflows

### Test Checklist

For each branch workflow:

- [ ] Workflow triggers correctly
- [ ] System dependencies install successfully
- [ ] Tests run on all platforms
- [ ] Quality checks execute
- [ ] Coverage uploads correctly
- [ ] Deployment works (release/hotfix only)
- [ ] PR creation works
- [ ] Error messages are clear

## FAQ

### Q: Will my existing PRs be affected?

**A**: No, existing PRs will continue to use the workflow version from when they were created.

### Q: Do I need to update my local development environment?

**A**: No, local development remains the same. The changes only affect CI/CD workflows.

### Q: What if tests fail on a platform I don't have access to?

**A**: Check the workflow logs for details, then consult the [troubleshooting guide](ci-cd-troubleshooting.md). You can also ask for help in GitHub Discussions.

### Q: Can I skip certain platforms in my PR?

**A**: No, all platforms must pass. This ensures code quality across all supported environments.

### Q: How do I test workflow changes locally?

**A**: Use the `act` tool to run workflows locally. See the [troubleshooting guide](ci-cd-troubleshooting.md#local-workflow-testing) for details.

### Q: What if I need to add a new quality check?

**A**: Update `.github/workflows/reusable-quality.yml` and it will apply to all branches automatically.

### Q: How do I add a new Python version to the test matrix?

**A**: Update the matrix in `.github/workflows/reusable-test.yml` and it will apply to all branches.

### Q: What happens if Codecov is down?

**A**: The workflow will continue (coverage upload failures don't fail the workflow), but coverage won't be updated.

### Q: Can I run only specific tests in CI/CD?

**A**: No, all tests must run to ensure comprehensive coverage. Run specific tests locally for faster feedback.

## Support and Resources

### Documentation

- [CI/CD Overview](ci-cd-overview.md) - Architecture and components
- [CI/CD Troubleshooting Guide](ci-cd-troubleshooting.md) - Common issues and solutions
- [Testing Guide](testing-guide.md) - Testing best practices
- [Pre-commit Setup](pre-commit-setup.md) - Quality check setup

### Getting Help

- **GitHub Discussions**: Ask questions and share experiences
- **GitHub Issues**: Report bugs or request features
- **Team Chat**: Real-time support from team members

### Feedback

We welcome feedback on the new CI/CD system:

1. What works well?
2. What could be improved?
3. What documentation is missing?
4. What issues have you encountered?

Please share feedback in GitHub Discussions or create an issue.

## Conclusion

The migration to reusable workflows ensures consistent, reliable CI/CD across all branches. While the changes are significant internally, the impact on developer workflow is minimal. The benefits include:

- ✅ Consistent testing across all branches
- ✅ Earlier detection of platform-specific issues
- ✅ Stricter quality enforcement
- ✅ Easier maintenance and updates
- ✅ Better alignment with GitFlow practices

Thank you for your patience during this migration. If you have any questions or concerns, please don't hesitate to reach out.
