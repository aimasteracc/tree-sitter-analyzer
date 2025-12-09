# CI/CD Overview

## Introduction

This document provides a comprehensive overview of the tree-sitter-analyzer project's Continuous Integration and Continuous Deployment (CI/CD) infrastructure. The CI/CD system is built on GitHub Actions and follows GitFlow branching practices to ensure code quality, consistency, and reliable deployments.

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Branch Workflows                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ develop  │  │ release  │  │  hotfix  │  │   main   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │              │             │          │
│       └─────────────┴──────────────┴─────────────┘          │
│                          │                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Reusable Workflow Components                    │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Test Workflow │  │ Quality Check  │  │ System Setup │  │
│  │                │  │   Workflow     │  │    Action    │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Deployment Logic                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Conditional: Only on release/* and hotfix/* branches  │ │
│  │  Requires: All tests passed                            │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Single Source of Truth**: Reusable workflows define test behavior once
2. **Separation of Concerns**: Testing logic is separate from deployment logic
3. **Fail-Fast**: Tests must pass before deployment can occur
4. **Consistency**: Identical test execution across all branches
5. **Maintainability**: Changes to test logic update all branches automatically

## Workflow Components

### 1. Reusable Test Workflow

**File**: `.github/workflows/reusable-test.yml`

**Purpose**: Defines the complete test suite that all branches must execute.

**Key Features**:
- Installs system dependencies (fd, ripgrep)
- Sets up Python environment with uv
- Installs all project dependencies using `--all-extras`
- Runs pre-commit quality checks
- Executes full test matrix (Python 3.10-3.13, ubuntu/windows/macos)
- Generates and uploads coverage reports
- Updates README statistics

**Inputs**:
```yaml
python-version: '3.11'  # Python version for quality checks
upload-coverage: true    # Whether to upload coverage to Codecov
```

**Test Matrix**:
- **Python Versions**: 3.10, 3.11, 3.12, 3.13
- **Operating Systems**: ubuntu-latest, windows-latest, macos-latest
- **Exclusions**: Windows and macOS skip Python 3.10 for optimization

### 2. Reusable Quality Check Workflow

**File**: `.github/workflows/reusable-quality.yml`

**Purpose**: Standardized quality gate checks.

**Quality Tools**:
- **mypy**: Type checking
- **black**: Code formatting check
- **ruff**: Linting
- **isort**: Import sorting check
- **bandit**: Security checks
- **pydocstyle**: Documentation checks

**Configuration**:
- Uses Python 3.11 for all quality checks
- Fail-fast behavior for quality issues

### 3. Composite System Setup Action

**File**: `.github/actions/setup-system/action.yml`

**Purpose**: Consistent system dependency installation across all platforms.

**Responsibilities**:
- Installs fd and ripgrep on Linux (apt-get)
- Installs fd and ripgrep on macOS (brew)
- Installs fd and ripgrep on Windows (choco)
- Creates symlinks where necessary (fdfind → fd on Ubuntu)
- Verifies installation success

## Branch-Specific Workflows

### Develop Branch Workflow

**File**: `.github/workflows/develop-automation.yml`

**Triggers**:
- Push to `develop` branch
- Manual dispatch

**Jobs**:
1. **test**: Runs comprehensive test suite (calls reusable-test.yml)
2. **create-pr**: Creates PR to main after successful tests

**Deployment**: None (develop branch does not deploy)

### Release Branch Workflow

**File**: `.github/workflows/release-automation.yml`

**Triggers**:
- Push to `release/*` branches
- Manual dispatch

**Jobs**:
1. **test**: Runs comprehensive test suite (calls reusable-test.yml)
2. **deploy**: Builds and deploys to PyPI (only after tests pass)
3. **create-pr**: Creates PR to main after successful deployment

**Deployment**: PyPI deployment occurs only after all tests pass

### Hotfix Branch Workflow

**File**: `.github/workflows/hotfix-automation.yml`

**Triggers**:
- Push to `hotfix/*` branches
- Manual dispatch

**Jobs**:
1. **test**: Runs comprehensive test suite (calls reusable-test.yml)
2. **deploy**: Builds and deploys to PyPI (only after tests pass)
3. **create-pr**: Creates PR to main after successful deployment

**Deployment**: PyPI deployment occurs only after all tests pass

### Main Branch CI Workflow

**File**: `.github/workflows/ci.yml`

**Triggers**:
- Push to `main` branch
- Pull requests to `main`
- Manual dispatch

**Jobs**:
1. **test-matrix**: Runs comprehensive test suite
2. **quality-check**: Runs quality gates
3. **security-check**: Runs security scans
4. **documentation-check**: Validates documentation
5. **build-check**: Verifies package builds correctly

**Deployment**: None (main branch does not deploy)

## Workflow Execution Flow

### Development Flow (develop branch)

```
Developer Push → develop branch
    ↓
Trigger develop-automation.yml
    ↓
Run reusable-test.yml
    ├─ Install system dependencies
    ├─ Setup Python environment
    ├─ Install project dependencies (--all-extras)
    ├─ Run quality checks (mypy, black, ruff, etc.)
    ├─ Run test matrix (Python 3.10-3.13, ubuntu/windows/macos)
    ├─ Upload coverage to Codecov
    └─ Update README stats
    ↓
Tests Pass? ──No──> Workflow Fails, Notify Developer
    │
   Yes
    ↓
Create PR to main
    ↓
Workflow Complete
```

### Release Flow (release/* branch)

```
Release Branch Created → release/* branch
    ↓
Trigger release-automation.yml
    ↓
Run reusable-test.yml
    ├─ Install system dependencies
    ├─ Setup Python environment
    ├─ Install project dependencies (--all-extras)
    ├─ Run quality checks
    ├─ Run test matrix
    ├─ Upload coverage
    └─ Update README stats
    ↓
Tests Pass? ──No──> Workflow Fails, No Deployment
    │
   Yes
    ↓
Build Package
    ↓
Deploy to PyPI
    ↓
Deployment Success? ──No──> Workflow Fails, Notify Team
    │
   Yes
    ↓
Create PR to main
    ↓
Workflow Complete
```

### Hotfix Flow (hotfix/* branch)

```
Hotfix Branch Created → hotfix/* branch
    ↓
Trigger hotfix-automation.yml
    ↓
Run reusable-test.yml (same as release)
    ↓
Tests Pass? ──No──> Workflow Fails, No Deployment
    │
   Yes
    ↓
Build Package
    ↓
Deploy to PyPI
    ↓
Deployment Success? ──No──> Workflow Fails, Notify Team
    │
   Yes
    ↓
Create PR to main
    ↓
Workflow Complete
```

### Main Branch Flow (main branch)

```
PR Merged → main branch
    ↓
Trigger ci.yml
    ↓
Run test-matrix job
    ├─ Install system dependencies
    ├─ Setup Python environment
    ├─ Install project dependencies (--all-extras)
    └─ Run test matrix
    ↓
Run quality-check job
    └─ Run all quality tools
    ↓
Run security-check job
    └─ Run security scans
    ↓
Run documentation-check job
    └─ Validate documentation
    ↓
Run build-check job
    └─ Verify package builds
    ↓
All Checks Pass? ──No──> Workflow Fails, Investigate
    │
   Yes
    ↓
Workflow Complete (No Deployment)
```

## Test Configuration

### Test Matrix

All branch workflows use the same test matrix to ensure consistency:

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.10", "3.11", "3.12", "3.13"]
    exclude:
      - os: windows-latest
        python-version: "3.10"
      - os: macos-latest
        python-version: "3.10"
```

### System Dependencies

All workflows install the same system dependencies:

- **fd**: Fast file finder (Rust-based)
- **ripgrep**: Fast text search (Rust-based)

Platform-specific installation:
- **Linux**: `apt-get install fd-find ripgrep` + symlink creation
- **macOS**: `brew install fd ripgrep`
- **Windows**: `choco install fd ripgrep`

### Quality Checks

All workflows run the same quality checks:

```bash
uv run pre-commit run --all-files
```

This includes:
- mypy (type checking)
- black (code formatting)
- ruff (linting)
- isort (import sorting)
- bandit (security)
- pydocstyle (documentation)

### Coverage Configuration

Coverage is uploaded from a single configuration:
- **OS**: ubuntu-latest
- **Python**: 3.11
- **Service**: Codecov

## Secrets and Environment Variables

### Required Secrets

All workflows require the following GitHub secrets:

1. **CODECOV_TOKEN**: For uploading coverage reports to Codecov
2. **GITHUB_TOKEN**: Automatically provided by GitHub Actions for PR creation
3. **PYPI_API_TOKEN**: For deploying packages to PyPI (release and hotfix only)

### Setting Up Secrets

Secrets are configured in GitHub repository settings:

1. Navigate to: `Settings → Secrets and variables → Actions`
2. Click "New repository secret"
3. Add each required secret with its value

### Environment Variables

Workflows use the following environment variables:

- **PYTHON_VERSION**: Python version for quality checks (default: 3.11)
- **UV_SYSTEM_PYTHON**: Set to 1 for uv to use system Python

## Performance Considerations

### Workflow Execution Time

- **Typical Duration**: 15-20 minutes per workflow
- **Parallel Execution**: Test matrix runs in parallel across OS/Python combinations
- **Optimization**: Exclusions reduce unnecessary test combinations

### Resource Usage

- **GitHub Actions Minutes**: Monitored to stay within limits
- **Concurrent Jobs**: Multiple jobs run in parallel when possible
- **Caching**: Dependencies are cached by uv for faster subsequent runs

## Monitoring and Maintenance

### Workflow Status

Monitor workflow status through:

1. **GitHub Actions Tab**: View all workflow runs
2. **Branch Protection**: Status checks required before merging
3. **Codecov Dashboard**: Track coverage trends
4. **PyPI Releases**: Verify successful deployments

### Regular Maintenance

- **Dependency Updates**: Use dependabot for action version updates
- **Python Version Updates**: Add new Python versions to matrix as released
- **Tool Version Updates**: Keep quality tools up to date
- **Documentation Updates**: Keep this document synchronized with actual workflows

## Best Practices

### For Developers

1. **Run Tests Locally**: Use `uv run pytest tests/` before pushing
2. **Run Quality Checks**: Use `uv run pre-commit run --all-files` before pushing
3. **Check Workflow Status**: Monitor GitHub Actions after pushing
4. **Fix Failures Quickly**: Address workflow failures promptly

### For Maintainers

1. **Review Workflow Changes**: Carefully review any workflow modifications
2. **Test on Feature Branches**: Test workflow changes before merging
3. **Monitor Performance**: Track workflow execution times
4. **Update Documentation**: Keep documentation synchronized with workflows

## Troubleshooting

For detailed troubleshooting guidance, see [CI/CD Troubleshooting Guide](ci-cd-troubleshooting.md).

Common issues:

- **Test Failures**: Check test output in workflow logs
- **Quality Check Failures**: Run `pre-commit run --all-files` locally
- **Deployment Failures**: Verify PyPI credentials and package version
- **System Dependency Failures**: Check package manager availability

## Related Documentation

- [CI/CD Troubleshooting Guide](ci-cd-troubleshooting.md)
- [CI/CD Migration Guide](ci-cd-migration-guide.md)
- [Testing Guide](testing-guide.md)
- [Pre-commit Setup](pre-commit-setup.md)
- [Developer Guide](developer_guide.md)
