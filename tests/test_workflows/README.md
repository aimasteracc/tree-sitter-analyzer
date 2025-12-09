# Workflow Consistency Tests

This directory contains comprehensive property-based tests for GitHub Actions workflow consistency across all branches (develop, release, hotfix, main).

## Test Files

### `test_workflow_properties.py` ⭐ NEW

**Comprehensive property-based test suite** that validates all correctness properties defined in the design document:

- **Property 1**: Test Configuration Consistency (Requirements 1.1-1.4)
- **Property 2**: All-Extras Installation Consistency (Requirements 1.5)
- **Property 3**: Quality Check Presence (Requirements 2.1)
- **Property 4**: Quality Tool Version Consistency (Requirements 2.2)
- **Property 6**: Coverage Configuration Consistency (Requirements 3.4)
- **Property 7**: System Dependencies Consistency (Requirements 3.3)
- **Property 8**: Test Matrix Consistency (Requirements 3.1, 3.2)
- **Property 9**: Test Marker Consistency (Requirements 3.5)
- **Property 11**: Reusable Workflow Behavioral Equivalence (Requirements 6.5)

This is the **primary test suite** for workflow consistency validation.

### `test_develop_workflow_consistency.py`

Property-based tests for the develop branch workflow that validate:

1. **Property 1: Test Configuration Consistency** - Verifies that the develop workflow uses the reusable test workflow with consistent configuration (Python versions, OS platforms, test matrix)

2. **Property 2: All-Extras Installation Consistency** - Ensures all dependency installation commands use the `--all-extras` flag

3. **Property 3: Quality Check Presence** - Validates that quality checks (mypy, black, ruff, isort, bandit) are present in the workflow

### `test_release_workflow_consistency.py`

Property-based tests for the release branch workflow that validate:

1. **Property 5: Deployment Dependency on Tests** - Ensures deployment only occurs after tests pass
2. **Property 10: Deployment Branch Restriction** - Verifies deployment only on release branches

### `test_hotfix_workflow_consistency.py`

Property-based tests for the hotfix branch workflow that validate:

1. **Property 5: Deployment Dependency on Tests** - Ensures deployment only occurs after tests pass
2. **Property 8: Test Matrix Consistency** - Verifies test matrix matches other workflows

### `test_ci_workflow_consistency.py`

Property-based tests for the main branch CI workflow that validate:

1. **Property 1: Test Configuration Consistency** - Verifies consistent test configuration
2. **Property 10: Deployment Branch Restriction** - Ensures no deployment on main branch

### Validation Scripts

- `validate_develop_workflow.py` - Programmatic validation for develop workflow
- `validate_release_workflow.py` - Programmatic validation for release workflow
- `validate_hotfix_workflow.py` - Programmatic validation for hotfix workflow
- `validate_ci_workflow.py` - Programmatic validation for CI workflow

## Running Tests

```bash
# Run all workflow consistency tests (recommended)
uv run pytest tests/test_workflows/ -v

# Run comprehensive property test suite
uv run pytest tests/test_workflows/test_workflow_properties.py -v

# Run specific workflow tests
uv run pytest tests/test_workflows/test_develop_workflow_consistency.py -v
uv run pytest tests/test_workflows/test_release_workflow_consistency.py -v
uv run pytest tests/test_workflows/test_hotfix_workflow_consistency.py -v
uv run pytest tests/test_workflows/test_ci_workflow_consistency.py -v

# Run validation scripts
uv run python tests/test_workflows/validate_develop_workflow.py
uv run python tests/test_workflows/validate_release_workflow.py
uv run python tests/test_workflows/validate_hotfix_workflow.py
uv run python tests/test_workflows/validate_ci_workflow.py

# Run via pre-commit hook
uv run pre-commit run workflow-consistency-tests --all-files
```

## Pre-commit Integration

The workflow consistency tests are integrated into the pre-commit hooks and run automatically when workflow files are modified:

```yaml
- repo: local
  hooks:
    - id: workflow-consistency-tests
      name: Workflow Consistency Tests
      entry: uv run pytest tests/test_workflows/test_workflow_properties.py -v --tb=short
      language: system
      pass_filenames: false
      files: ^\.github/workflows/.*\.yml$
      stages: [pre-commit]
```

This ensures workflow inconsistencies are caught before commit.

## Test Coverage

These tests validate **all requirements** (1.1-7.5) and ensure:

- ✅ Consistent test configurations across all branches
- ✅ Identical Python versions (3.10, 3.11, 3.12, 3.13)
- ✅ Identical operating systems (ubuntu-latest, windows-latest, macos-latest)
- ✅ All-extras installation flag usage
- ✅ Quality check presence and consistency
- ✅ Coverage configuration standardization
- ✅ System dependencies installation (fd, ripgrep)
- ✅ Test matrix consistency
- ✅ Pytest marker consistency
- ✅ Deployment dependency on tests
- ✅ Deployment branch restrictions
- ✅ Reusable workflow behavioral equivalence

## Implementation Notes

### YAML Parsing Issue

The tests handle a quirk where YAML parsers may convert the `on:` key to boolean `True`. The fixtures include logic to normalize this:

```python
if True in workflow and "on" not in workflow:
    workflow["on"] = workflow.pop(True)
```

### Encoding

All workflow files are read with explicit UTF-8 encoding to ensure cross-platform compatibility:

```python
with open(workflow_path, "r", encoding="utf-8") as f:
    return yaml.safe_load(f)
```

## Next Steps

After these tests pass, the next steps are:

1. Test the workflow on an actual feature branch by pushing changes
2. Verify in GitHub Actions that:
   - Test job executes using reusable-test.yml
   - All quality checks run
   - Test matrix executes on all platforms (ubuntu, windows, macos)
   - Coverage uploads successfully to Codecov
   - Build job runs after tests pass
   - PR creation job runs after build passes

## Related Files

- `.github/workflows/develop-automation.yml` - The develop branch workflow
- `.github/workflows/reusable-test.yml` - Reusable test workflow
- `.github/workflows/reusable-quality.yml` - Reusable quality check workflow
- `.github/actions/setup-system/action.yml` - Composite system setup action
