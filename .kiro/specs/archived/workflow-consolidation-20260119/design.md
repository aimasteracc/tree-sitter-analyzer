# Design - GitHub Workflow Consolidation

## Technology Choices
- **Centralized Coordinator**: `ci.yml`.
- **Enhanced Reusable Workflows**: `reusable-test.yml` and `reusable-quality.yml`.
- **Conditional Job Execution**: Using GitHub Actions `if` expressions.

## Consolidated Architecture

### 1. `reusable-test.yml` (The Core Engine)
- **New Feature**: Advanced coverage reporting (summary, low coverage check, trend) moved here from `test-coverage.yml`.
- **Exclusion**: Always exclude `-m "benchmark"` and `-m "regression"` to keep it fast.
- **Trigger**: Run on all PRs and pushes to main/develop.

### 2. `ci.yml` (The Orchestrator)
- Will remain the main gatekeeper.
- On `develop` branch: Added a `post-ci` job that handles PR creation to `main` (merging logic from `develop-automation.yml`).
- On `release/*` and `hotfix/*`: Added a `deploy` job that handles PyPI publishing (merging logic from `release-automation.yml` and `hotfix-automation.yml`).

### 3. Specialized Workflows (The Sidecar)
- `benchmarks.yml`: Only triggers on `schedule`, `workflow_dispatch`, or `push` to `main`. Excludes standard tests.
- `regression-tests.yml`: Triggers on PR and `push` to `main`/`develop`. Only runs `-m "regression"`.
- `sql-platform-compat.yml`: Triggers on `push` to `main`/`develop`.

### 4. Deletions
- `test-coverage.yml`: Logic merged into `reusable-test.yml`.
- `develop-automation.yml`: Logic merged into `ci.yml`.
- `release-automation.yml`: Logic merged into `ci.yml`.
- `hotfix-automation.yml`: Logic merged into `ci.yml`.

## Implementation Strategy
1. Upgrade `reusable-test.yml`.
2. Upgrade `ci.yml` with branch-specific logic.
3. Fix triggers in sidecar workflows.
4. Delete redundant files.
