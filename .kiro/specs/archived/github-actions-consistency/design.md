# Design Document: GitHub Actions Consistency

## Overview

This design addresses the critical issue of testing inconsistency across different branches in the tree-sitter-analyzer project's CI/CD pipeline. The current implementation causes tests to pass on the develop branch but fail on release/main branches, leading to unnecessary version increments and violating GitFlow best practices.

The solution implements a unified testing strategy using reusable GitHub Actions workflows, ensuring that all branches (develop, release, hotfix, main) execute identical test suites, quality checks, and system dependency installations.

## Architecture

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
2. **Separation of Concerns**: Testing logic separate from deployment logic
3. **Fail-Fast**: Tests must pass before deployment can occur
4. **Consistency**: Identical test execution across all branches
5. **Maintainability**: Changes to test logic update all branches automatically

## Components and Interfaces

### 1. Reusable Test Workflow

**File**: `.github/workflows/reusable-test.yml`

**Purpose**: Defines the complete test suite that all branches must execute

**Interface**:
```yaml
inputs:
  python-version:
    description: 'Python version for quality checks'
    required: false
    default: '3.11'
    type: string
  
  upload-coverage:
    description: 'Whether to upload coverage to Codecov'
    required: false
    default: true
    type: boolean

secrets:
  CODECOV_TOKEN:
    required: true
```

**Responsibilities**:
- Install system dependencies (fd, ripgrep)
- Set up Python environment with uv
- Install all project dependencies using `--all-extras`
- Run pre-commit quality checks
- Execute full test matrix (Python 3.10-3.13, ubuntu/windows/macos)
- Generate and upload coverage reports
- Update README statistics

### 2. Reusable Quality Check Workflow

**File**: `.github/workflows/reusable-quality.yml`

**Purpose**: Standardized quality gate checks

**Interface**:
```yaml
inputs:
  python-version:
    description: 'Python version for quality checks'
    required: false
    default: '3.11'
    type: string
```

**Responsibilities**:
- Run mypy type checking
- Run black code formatting check
- Run ruff linting
- Run isort import sorting check
- Run bandit security checks
- Run pydocstyle documentation checks

### 3. Composite System Setup Action

**File**: `.github/actions/setup-system/action.yml`

**Purpose**: Consistent system dependency installation

**Interface**:
```yaml
inputs:
  os:
    description: 'Operating system (ubuntu-latest, windows-latest, macos-13)'
    required: true
```

**Responsibilities**:
- Install fd and ripgrep on Linux (apt-get)
- Install fd and ripgrep on macOS (brew)
- Install fd and ripgrep on Windows (choco)
- Create symlinks where necessary (fdfind → fd on Ubuntu)
- Verify installation success

### 4. Branch-Specific Workflows

Each branch workflow (develop, release, hotfix, main) will:
- Call the reusable test workflow
- Conditionally execute deployment (only release/hotfix)
- Create appropriate pull requests
- Maintain branch-specific metadata

## Data Models

### Workflow Configuration Model

```yaml
WorkflowConfig:
  name: string
  triggers:
    - push:
        branches: [string]
    - pull_request:
        branches: [string]
    - workflow_dispatch: {}
  
  jobs:
    test:
      uses: ./.github/workflows/reusable-test.yml
      secrets: inherit
    
    deploy:
      needs: [test]
      if: condition
      steps: [...]
```

### Test Matrix Model

```yaml
TestMatrix:
  os: [ubuntu-latest, windows-latest, macos-13]
  python-version: ["3.10", "3.11", "3.12", "3.13"]
  exclude:
    - os: windows-latest
      python-version: "3.10"
    - os: macos-13
      python-version: "3.10"
```

### System Dependencies Model

```yaml
SystemDependencies:
  linux:
    package_manager: apt-get
    packages: [fd-find, ripgrep]
    post_install:
      - sudo ln -sf /usr/bin/fdfind /usr/bin/fd
  
  macos:
    package_manager: brew
    packages: [fd, ripgrep]
  
  windows:
    package_manager: choco
    packages: [fd, ripgrep]
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Test Configuration Consistency

*For any* pair of branch workflows (develop, release, hotfix, main), the test job configurations should be identical in terms of:
- Python versions tested
- Operating systems tested
- System dependencies installed
- Test commands executed
- Quality checks performed
- Dependency installation flags (`--all-extras`)

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

### Property 2: All-Extras Installation Consistency

*For any* test job in any branch workflow, the dependency installation command should include the `--all-extras` flag

**Validates: Requirements 1.5**

### Property 3: Quality Check Presence

*For any* branch workflow, there should exist a quality check job or step that runs pre-commit hooks including mypy, black, ruff, isort, and bandit

**Validates: Requirements 2.1**

### Property 4: Quality Tool Version Consistency

*For any* pair of branch workflows, the quality check tool versions and configurations should be identical

**Validates: Requirements 2.2**

### Property 5: Deployment Dependency on Tests

*For any* workflow that contains a deployment job, that deployment job should have a `needs` dependency on the test job, ensuring tests must pass before deployment

**Validates: Requirements 2.3, 5.1, 5.2, 5.3**

### Property 6: Coverage Configuration Consistency

*For any* branch workflow that uploads coverage, the coverage configuration (OS: ubuntu-latest, Python: 3.11) should be identical

**Validates: Requirements 3.4**

### Property 7: System Dependencies Consistency

*For any* test job in any branch workflow, the system dependency installation steps should install fd and ripgrep using the appropriate package manager for the target OS

**Validates: Requirements 3.3**

### Property 8: Test Matrix Consistency

*For any* pair of branch workflows, the test matrix (Python versions and operating systems) should be identical

**Validates: Requirements 3.1, 3.2**

### Property 9: Test Marker Consistency

*For any* test execution command in any branch workflow, the pytest markers should be identical (e.g., `-m "not requires_ripgrep or not requires_fd"`)

**Validates: Requirements 3.5**

### Property 10: Deployment Branch Restriction

*For any* workflow, PyPI deployment jobs should only exist in release/* and hotfix/* branch workflows, and should not exist in develop or main workflows

**Validates: Requirements 5.4, 5.5**

### Property 11: Reusable Workflow Behavioral Equivalence

*For any* reusable workflow, the effective behavior (commands executed, dependencies installed, checks performed) should be equivalent to the original inline workflow implementation

**Validates: Requirements 6.5**

## Error Handling

### Workflow Failure Scenarios

1. **Test Failure**
   - **Detection**: pytest exit code != 0
   - **Handling**: Fail the workflow, prevent deployment, notify via GitHub status checks
   - **Recovery**: Developer fixes tests, pushes new commit

2. **Quality Check Failure**
   - **Detection**: pre-commit exit code != 0
   - **Handling**: Fail the workflow, provide detailed error output
   - **Recovery**: Developer runs `pre-commit run --all-files` locally, fixes issues

3. **System Dependency Installation Failure**
   - **Detection**: apt-get/brew/choco exit code != 0
   - **Handling**: Fail the workflow with clear error message
   - **Recovery**: Retry workflow, check package availability

4. **Coverage Upload Failure**
   - **Detection**: codecov action fails
   - **Handling**: Log warning but don't fail workflow (use `fail_ci_if_error: false`)
   - **Recovery**: Check Codecov service status, retry

5. **Deployment Failure**
   - **Detection**: twine upload exit code != 0
   - **Handling**: Fail the workflow, prevent PR creation
   - **Recovery**: Check PyPI credentials, verify package version

### Error Messages

All workflows should include descriptive error messages:

```yaml
- name: Run tests
  run: |
    uv run pytest tests/ -v --tb=short || {
      echo "❌ Tests failed. Please run 'uv run pytest tests/' locally to reproduce."
      exit 1
    }
```

## Testing Strategy

### Unit Testing

Since this is a CI/CD configuration change, traditional unit tests don't apply. Instead, we use:

1. **Workflow Syntax Validation**
   - Use `actionlint` to validate YAML syntax
   - Verify workflow file structure

2. **Local Workflow Testing**
   - Use `act` tool to run workflows locally
   - Test on different operating systems

### Property-Based Testing

We will use Python with PyYAML to implement property-based tests that verify workflow consistency:

**Testing Framework**: pytest with Hypothesis

**Test Strategy**:
1. Parse all workflow YAML files
2. Extract test job configurations
3. Generate test cases that verify properties hold across all workflows
4. Run tests as part of pre-commit hooks

**Example Test Structure**:
```python
from hypothesis import given, strategies as st
import yaml
from pathlib import Path

def load_workflow(workflow_path):
    """Load and parse a GitHub Actions workflow file"""
    with open(workflow_path) as f:
        return yaml.safe_load(f)

def extract_test_config(workflow):
    """Extract test configuration from workflow"""
    # Extract matrix, dependencies, commands, etc.
    pass

@given(st.sampled_from(['develop', 'release', 'hotfix', 'main']))
def test_workflow_consistency(branch_name):
    """Property: All workflows have consistent test configurations"""
    workflow = load_workflow(f'.github/workflows/{branch_name}-automation.yml')
    config = extract_test_config(workflow)
    
    # Verify consistency properties
    assert config['python_versions'] == ['3.10', '3.11', '3.12', '3.13']
    assert config['os'] == ['ubuntu-latest', 'windows-latest', 'macos-13']
    assert '--all-extras' in config['install_command']
```

### Integration Testing

1. **Branch Protection Testing**
   - Create test branches
   - Push code that should fail quality checks
   - Verify workflow prevents merge

2. **End-to-End Testing**
   - Create test release branch
   - Verify tests run
   - Verify deployment occurs only after tests pass
   - Verify PR creation

3. **Cross-Platform Testing**
   - Verify workflows run successfully on all OS platforms
   - Verify system dependencies install correctly

### Manual Testing Checklist

Before merging workflow changes:

- [ ] Test develop branch workflow
- [ ] Test release branch workflow
- [ ] Test hotfix branch workflow
- [ ] Test main branch workflow
- [ ] Verify quality checks run on all branches
- [ ] Verify test matrix is identical across branches
- [ ] Verify system dependencies install on all platforms
- [ ] Verify deployment only occurs on release/hotfix
- [ ] Verify coverage uploads correctly
- [ ] Verify README stats update

## Implementation Phases

### Phase 1: Create Reusable Workflows
1. Create `.github/workflows/reusable-test.yml`
2. Create `.github/workflows/reusable-quality.yml`
3. Create `.github/actions/setup-system/action.yml`
4. Validate syntax with actionlint

### Phase 2: Update Branch Workflows
1. Update `develop-automation.yml` to use reusable workflows
2. Update `release-automation.yml` to use reusable workflows
3. Update `hotfix-automation.yml` to use reusable workflows
4. Update `ci.yml` to use reusable workflows

### Phase 3: Testing and Validation
1. Implement property-based tests for workflow consistency
2. Test workflows on all branches
3. Verify deployment logic
4. Update documentation

### Phase 4: Deployment and Monitoring
1. Merge changes to develop
2. Monitor CI/CD execution
3. Create release branch to test full flow
4. Document any issues and resolutions

## Migration Strategy

### Backward Compatibility

- Existing workflows will continue to work during migration
- Changes will be rolled out branch by branch
- Rollback plan: revert to previous workflow versions

### Rollout Plan

1. **Week 1**: Create and test reusable workflows on feature branch
2. **Week 2**: Update develop branch, monitor for issues
3. **Week 3**: Update release and hotfix branches
4. **Week 4**: Update main branch and ci.yml

### Monitoring

- Monitor GitHub Actions execution times
- Track test failure rates
- Monitor deployment success rates
- Collect feedback from developers

## Documentation Requirements

### Developer Documentation

1. **CI/CD Overview**: Explain the new workflow structure
2. **Troubleshooting Guide**: Common issues and solutions
3. **Local Testing Guide**: How to test workflows locally
4. **Migration Guide**: Changes from old to new workflows

### Workflow Documentation

Each workflow file should include:
- Purpose and trigger conditions
- Job dependencies
- Required secrets
- Expected behavior

### Example Documentation

```yaml
# .github/workflows/develop-automation.yml
#
# Purpose: Automated testing and validation for develop branch
# Triggers: Push to develop branch, manual dispatch
# Jobs:
#   - test: Runs comprehensive test suite (reusable workflow)
#   - create-pr: Creates PR to main after successful tests
# Secrets Required:
#   - CODECOV_TOKEN: For coverage upload
#   - GITHUB_TOKEN: For PR creation
```

## Security Considerations

1. **Secret Management**
   - Use GitHub secrets for sensitive data
   - Never log secrets in workflow output
   - Use `secrets: inherit` for reusable workflows

2. **Dependency Security**
   - Pin action versions (e.g., `actions/checkout@v4`)
   - Use dependabot to keep actions updated
   - Verify action sources

3. **Branch Protection**
   - Require status checks to pass before merging
   - Require pull request reviews
   - Restrict who can push to protected branches

## Performance Considerations

1. **Workflow Execution Time**
   - Current: ~15-20 minutes per workflow
   - Target: Maintain or improve execution time
   - Strategy: Parallel job execution, caching

2. **Resource Usage**
   - Use matrix strategy to parallelize tests
   - Cache dependencies where possible
   - Use `fail-fast: false` to see all failures

3. **Cost Optimization**
   - Reduce matrix size where appropriate
   - Use self-hosted runners for frequent builds (future consideration)
   - Monitor GitHub Actions minutes usage

## Future Enhancements

1. **Caching Strategy**
   - Cache uv dependencies
   - Cache tree-sitter parsers
   - Cache test results for unchanged code

2. **Notification System**
   - Slack notifications for deployment
   - Email notifications for test failures
   - GitHub status badges

3. **Advanced Testing**
   - Mutation testing
   - Performance regression testing
   - Security scanning integration

4. **Workflow Optimization**
   - Conditional test execution (only affected tests)
   - Incremental testing
   - Parallel test execution optimization
