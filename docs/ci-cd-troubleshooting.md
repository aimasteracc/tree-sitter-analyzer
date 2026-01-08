# CI/CD Troubleshooting Guide

## Introduction

This guide provides solutions to common issues encountered in the tree-sitter-analyzer CI/CD workflows. Each section includes the problem description, error messages you might see, root causes, and step-by-step resolution procedures.

## Table of Contents

1. [Test Failures](#test-failures)
2. [Quality Check Failures](#quality-check-failures)
3. [System Dependency Installation Failures](#system-dependency-installation-failures)
4. [Coverage Upload Failures](#coverage-upload-failures)
5. [Deployment Failures](#deployment-failures)
6. [Workflow Syntax Errors](#workflow-syntax-errors)
7. [Secret and Permission Issues](#secret-and-permission-issues)
8. [Performance and Timeout Issues](#performance-and-timeout-issues)
9. [Local Workflow Testing](#local-workflow-testing)

---

## Test Failures

### Symptom

Tests fail during workflow execution, preventing deployment or PR creation.

### Error Messages

```
FAILED tests/test_module.py::test_function - AssertionError: ...
```

```
❌ Tests failed. Please run 'uv run pytest tests/' locally to reproduce.
```

### Root Causes

1. Code changes introduced bugs
2. Test environment differs from local environment
3. Platform-specific issues (Windows/macOS/Linux)
4. Missing system dependencies (fd, ripgrep)
5. Race conditions in async tests

### Resolution Steps

#### Step 1: Reproduce Locally

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific failing test
uv run pytest tests/test_module.py::test_function -v

# Run with full traceback
uv run pytest tests/ -v --tb=long
```

#### Step 2: Check Platform-Specific Issues

If tests fail only on specific platforms:

```bash
# For Windows-specific issues
uv run pytest tests/ -v -m "not requires_unix"

# For macOS-specific issues
uv run pytest tests/ -v -m "not requires_linux"
```

#### Step 3: Verify System Dependencies

```bash
# Check if fd is installed
fd --version

# Check if ripgrep is installed
rg --version

# Run tests that require these tools
uv run pytest tests/ -v -m "requires_fd or requires_ripgrep"
```

#### Step 4: Check for Async Issues

```bash
# Run async tests with debugging
uv run pytest tests/ -v --log-cli-level=DEBUG -k "async"
```

#### Step 5: Fix and Verify

1. Fix the identified issue in your code
2. Run tests locally to verify the fix
3. Commit and push changes
4. Monitor workflow execution

### Prevention

- Always run `uv run pytest tests/` before pushing
- Test on multiple platforms if possible
- Use pytest markers to skip platform-specific tests appropriately
- Ensure system dependencies are documented

---

## Quality Check Failures

### Symptom

Pre-commit quality checks fail, preventing workflow from proceeding.

### Error Messages

```
mypy....................................................................Failed
- hook id: mypy
- exit code: 1

error: Incompatible types in assignment
```

```
black...................................................................Failed
- hook id: black
- exit code: 1

would reformat file.py
```

```
ruff....................................................................Failed
- hook id: ruff
- exit code: 1

file.py:10:1: F401 'module' imported but unused
```

### Root Causes

1. Code doesn't meet formatting standards
2. Type annotations are incorrect or missing
3. Unused imports or variables
4. Security vulnerabilities detected
5. Missing or incorrect docstrings

### Resolution Steps

#### Step 1: Run Quality Checks Locally

```bash
# Run all pre-commit hooks
uv run pre-commit run --all-files

# Run specific hook
uv run pre-commit run mypy --all-files
uv run pre-commit run black --all-files
uv run pre-commit run ruff --all-files
```

#### Step 2: Auto-Fix Issues

```bash
# Auto-format with black
uv run black tree_sitter_analyzer/ tests/

# Auto-fix with ruff
uv run ruff check --fix tree_sitter_analyzer/ tests/

# Auto-sort imports with isort
uv run isort tree_sitter_analyzer/ tests/
```

#### Step 3: Fix Type Issues

```bash
# Run mypy with detailed output
uv run mypy tree_sitter_analyzer/ --show-error-codes

# Fix type annotations based on errors
# Example: Add type hints to function signatures
```

#### Step 4: Fix Security Issues

```bash
# Run bandit security check
uv run bandit -r tree_sitter_analyzer/

# Review and fix security warnings
```

#### Step 5: Fix Documentation Issues

```bash
# Run pydocstyle
uv run pydocstyle tree_sitter_analyzer/

# Add or fix docstrings following Google style
```

#### Step 6: Verify and Commit

```bash
# Verify all checks pass
uv run pre-commit run --all-files

# Commit and push
git add .
git commit -m "Fix quality check issues"
git push
```

### Prevention

- Install pre-commit hooks: `pre-commit install`
- Run `pre-commit run --all-files` before committing
- Use IDE plugins for black, mypy, and ruff
- Follow project coding standards

---

## System Dependency Installation Failures

### Symptom

System dependencies (fd, ripgrep) fail to install during workflow execution.

### Error Messages

```
E: Unable to locate package fd-find
```

```
Error: The process '/usr/bin/apt-get' failed with exit code 100
```

```
Error: brew install fd failed
```

### Root Causes

1. Package manager unavailable or outdated
2. Network connectivity issues
3. Package name differences across platforms
4. Insufficient permissions

### Resolution Steps

#### Step 1: Check Platform-Specific Installation

**Linux (Ubuntu)**:
```bash
sudo apt-get update
sudo apt-get install -y fd-find ripgrep
sudo ln -sf /usr/bin/fdfind /usr/bin/fd
```

**macOS**:
```bash
brew install fd ripgrep
```

**Windows**:
```powershell
choco install fd ripgrep -y
```

#### Step 2: Verify Installation

```bash
# Check fd
fd --version

# Check ripgrep
rg --version

# Test functionality
fd "*.py" .
rg "import" .
```

#### Step 3: Update Workflow if Needed

If package names or installation methods change, update `.github/actions/setup-system/action.yml`:

```yaml
- name: Install system dependencies (Linux)
  if: runner.os == 'Linux'
  run: |
    sudo apt-get update
    sudo apt-get install -y fd-find ripgrep
    sudo ln -sf /usr/bin/fdfind /usr/bin/fd
```

#### Step 4: Retry Workflow

Re-run the failed workflow after verifying the installation steps are correct.

### Prevention

- Pin package versions when possible
- Add retry logic for network-dependent steps
- Test installation steps on all platforms
- Monitor package manager updates

---

## Coverage Upload Failures

### Symptom

Coverage reports fail to upload to Codecov, but workflow continues.

### Error Messages

```
Warning: Codecov upload failed
```

```
Error: Failed to upload coverage report
```

### Root Causes

1. Invalid or missing CODECOV_TOKEN
2. Codecov service outage
3. Network connectivity issues
4. Coverage file not generated correctly

### Resolution Steps

#### Step 1: Verify CODECOV_TOKEN

1. Go to repository Settings → Secrets and variables → Actions
2. Verify CODECOV_TOKEN exists and is correct
3. Get new token from Codecov if needed

#### Step 2: Check Coverage File Generation

```bash
# Generate coverage locally
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=xml

# Verify coverage.xml exists
ls -la coverage.xml
```

#### Step 3: Test Codecov Upload Locally

```bash
# Install codecov CLI
pip install codecov

# Upload coverage
codecov -t YOUR_TOKEN -f coverage.xml
```

#### Step 4: Check Codecov Service Status

Visit https://status.codecov.io/ to check for service outages.

#### Step 5: Update Workflow Configuration

If needed, update the codecov action configuration in `.github/workflows/reusable-test.yml`:

```yaml
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    token: ${{ secrets.CODECOV_TOKEN }}
    files: ./coverage.xml
    fail_ci_if_error: false  # Don't fail workflow on upload error
    verbose: true
```

### Prevention

- Set `fail_ci_if_error: false` to prevent workflow failures
- Monitor Codecov service status
- Keep CODECOV_TOKEN up to date
- Verify coverage generation in tests

---

## Deployment Failures

### Symptom

Package deployment to PyPI fails on release or hotfix branches.

### Error Messages

```
HTTPError: 403 Forbidden
```

```
ERROR: File already exists
```

```
twine upload failed with exit code 1
```

### Root Causes

1. Invalid or expired PYPI_API_TOKEN
2. Version number already exists on PyPI
3. Package build failures
4. Network connectivity issues
5. PyPI service outage

### Resolution Steps

#### Step 1: Verify PYPI_API_TOKEN

1. Go to repository Settings → Secrets and variables → Actions
2. Verify PYPI_API_TOKEN exists and is correct
3. Generate new token from PyPI if needed:
   - Visit https://pypi.org/manage/account/token/
   - Create new API token
   - Update GitHub secret

#### Step 2: Check Version Number

```bash
# Check current version in pyproject.toml
grep "version =" pyproject.toml

# Check if version exists on PyPI
pip index versions tree-sitter-analyzer
```

If version exists, increment version number:

```bash
# Update version in pyproject.toml
# Example: 1.6.1.4 → 1.6.1.5
```

#### Step 3: Test Build Locally

```bash
# Clean previous builds
rm -rf dist/ build/

# Build package
uv build

# Verify build artifacts
ls -la dist/
```

#### Step 4: Test Upload to Test PyPI

```bash
# Upload to Test PyPI first
uv run twine upload --repository testpypi dist/*

# Verify on Test PyPI
pip install --index-url https://test.pypi.org/simple/ tree-sitter-analyzer
```

#### Step 5: Fix and Retry

1. Fix identified issues
2. Commit version changes if needed
3. Push to trigger workflow again
4. Monitor deployment

### Prevention

- Always increment version before release
- Test builds locally before pushing
- Use Test PyPI for testing
- Keep PYPI_API_TOKEN secure and up to date
- Follow semantic versioning

---

## Workflow Syntax Errors

### Symptom

Workflow fails to start or shows syntax errors.

### Error Messages

```
Invalid workflow file: .github/workflows/develop-automation.yml
```

```
Unexpected value 'job'
```

```
YAML syntax error
```

### Root Causes

1. Invalid YAML syntax
2. Incorrect indentation
3. Missing required fields
4. Invalid job or step configuration

### Resolution Steps

#### Step 1: Validate YAML Syntax

```bash
# Install yamllint
pip install yamllint

# Validate workflow file
yamllint .github/workflows/develop-automation.yml
```

#### Step 2: Use actionlint

```bash
# Install actionlint
# On macOS:
brew install actionlint

# On Linux:
# Download from https://github.com/rhysd/actionlint/releases

# Validate workflow
actionlint .github/workflows/develop-automation.yml
```

#### Step 3: Check Common Issues

- **Indentation**: Use 2 spaces, not tabs
- **Quotes**: Use quotes for strings with special characters
- **Required Fields**: Ensure all required fields are present
- **Job Dependencies**: Verify `needs` references exist

#### Step 4: Test Workflow Locally

```bash
# Install act (GitHub Actions local runner)
# On macOS:
brew install act

# On Linux:
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run workflow locally
act -l  # List workflows
act push  # Run push event workflows
```

#### Step 5: Fix and Validate

1. Fix syntax errors
2. Validate with yamllint and actionlint
3. Commit and push
4. Verify workflow starts correctly

### Prevention

- Use YAML linting in your IDE
- Install pre-commit hooks for YAML validation
- Test workflows locally with act
- Review workflow changes carefully

---

## Secret and Permission Issues

### Symptom

Workflow fails due to missing secrets or insufficient permissions.

### Error Messages

```
Error: Input required and not supplied: token
```

```
Error: Resource not accessible by integration
```

```
403 Forbidden: Insufficient permissions
```

### Root Causes

1. Missing required secrets
2. Incorrect secret names
3. Insufficient GitHub token permissions
4. Branch protection rules blocking actions

### Resolution Steps

#### Step 1: Verify Required Secrets

Check that all required secrets exist:

1. Go to repository Settings → Secrets and variables → Actions
2. Verify these secrets exist:
   - CODECOV_TOKEN
   - PYPI_API_TOKEN (for release/hotfix workflows)

#### Step 2: Check Secret Names

Ensure secret names in workflows match repository secrets:

```yaml
# In workflow file
env:
  CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}  # Must match exactly
```

#### Step 3: Verify GitHub Token Permissions

For workflows that create PRs or interact with GitHub API:

```yaml
permissions:
  contents: write  # For pushing changes
  pull-requests: write  # For creating PRs
  issues: write  # For creating issues
```

#### Step 4: Check Branch Protection Rules

1. Go to repository Settings → Branches
2. Review branch protection rules
3. Ensure GitHub Actions has necessary permissions

#### Step 5: Use secrets: inherit

For reusable workflows, ensure secrets are passed:

```yaml
jobs:
  test:
    uses: ./.github/workflows/reusable-test.yml
    secrets: inherit  # Pass all secrets to reusable workflow
```

### Prevention

- Document all required secrets
- Use descriptive secret names
- Set appropriate workflow permissions
- Test secret access in workflows

---

## Performance and Timeout Issues

### Symptom

Workflows take too long or timeout before completion.

### Error Messages

```
Error: The operation was canceled.
```

```
Error: Job exceeded maximum execution time
```

### Root Causes

1. Tests running too slowly
2. Too many test combinations in matrix
3. Network delays
4. Resource constraints
5. Inefficient test code

### Resolution Steps

#### Step 1: Identify Slow Tests

```bash
# Run tests with duration reporting
uv run pytest tests/ -v --durations=10

# Profile specific slow tests
uv run pytest tests/test_slow.py -v --profile
```

#### Step 2: Optimize Test Matrix

Review and optimize the test matrix in workflows:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.10", "3.11", "3.12", "3.13"]
    exclude:
      # Add more exclusions to reduce combinations
      - os: windows-latest
        python-version: "3.10"
      - os: macos-latest
        python-version: "3.10"
```

#### Step 3: Use Caching

Add caching to speed up dependency installation:

```yaml
- name: Cache uv dependencies
  uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: ${{ runner.os }}-uv-${{ hashFiles('**/pyproject.toml') }}
```

#### Step 4: Parallelize Tests

```bash
# Run tests in parallel locally
uv run pytest tests/ -n auto

# Update workflow to use pytest-xdist
uv run pytest tests/ -n auto --dist loadfile
```

#### Step 5: Increase Timeout

If necessary, increase job timeout:

```yaml
jobs:
  test:
    timeout-minutes: 60  # Increase from default 360
```

### Prevention

- Write efficient tests
- Use appropriate test markers
- Monitor workflow execution times
- Optimize test matrix
- Use caching effectively

---

## Local Workflow Testing

### Overview

Testing workflows locally before pushing can save time and catch issues early.

### Using act

**act** is a tool that runs GitHub Actions locally.

#### Installation

```bash
# macOS
brew install act

# Linux
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Windows
choco install act-cli
```

#### Basic Usage

```bash
# List all workflows
act -l

# Run push event workflows
act push

# Run specific workflow
act -W .github/workflows/develop-automation.yml

# Run with secrets
act -s CODECOV_TOKEN=your_token

# Dry run (don't actually run)
act -n
```

#### Limitations

- Some GitHub-specific features may not work
- Large workflows may be slow
- Platform-specific issues may not be caught

### Using Docker

Run tests in Docker containers matching GitHub Actions environment:

```bash
# Build test container
docker build -t tree-sitter-analyzer-test .

# Run tests
docker run tree-sitter-analyzer-test pytest tests/
```

### Manual Verification

Before pushing, manually verify:

```bash
# 1. Run all tests
uv run pytest tests/ -v

# 2. Run quality checks
uv run pre-commit run --all-files

# 3. Verify system dependencies
fd --version
rg --version

# 4. Test build
uv build

# 5. Validate workflow syntax
actionlint .github/workflows/*.yml
```

---

## Getting Help

### Resources

- [CI/CD Overview](ci-cd-overview.md)
- [CI/CD Migration Guide](ci-cd-migration-guide.md)
- [Testing Guide](testing-guide.md)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

### Reporting Issues

If you encounter issues not covered in this guide:

1. Check GitHub Actions logs for detailed error messages
2. Search existing GitHub issues
3. Create a new issue with:
   - Workflow file name
   - Error message
   - Steps to reproduce
   - Relevant logs

### Community Support

- GitHub Discussions: Ask questions and share solutions
- Issue Tracker: Report bugs and request features
- Pull Requests: Contribute fixes and improvements
