# Implementation Plan

## Phase 1: Quality Gate Enforcement

- [x] 1.1 Remove `|| true` from Ruff check in `reusable-quality.yml`
- [x] 1.2 Remove `|| true` from MyPy check in `reusable-quality.yml`
- [x] 1.3 Remove `|| true` from Bandit check in `reusable-quality.yml`
- [x] 1.4 Checkpoint - Verify quality workflow syntax is valid

## Phase 2: Action Version Standardization

- [x] 2.1 Update `sql-platform-compat.yml` from `astral-sh/setup-uv@v3` to `@v4`
- [x] 2.2 Verify all workflows use `actions/checkout@v4`
- [x] 2.3 Verify all workflows use `actions/upload-artifact@v4`
- [x] 2.4 Checkpoint - Verify no version inconsistencies remain

## Phase 3: Governance Files

- [x] 3.1 Create `.github/CODEOWNERS` with maintainer assignments
- [x] 3.2 Create `.github/SECURITY.md` with vulnerability policy
- [x] 3.3 Create `.github/ISSUE_TEMPLATE/config.yml` with helpful links
- [x] 3.4 Checkpoint - Verify GitHub recognizes new files

## Phase 4: Dependency Automation

- [x] 4.1 Create `.github/dependabot.yml` for Python and GitHub Actions
- [x] 4.2 Configure dependency grouping for minor/patch updates
- [x] 4.3 Checkpoint - Verify Dependabot configuration is valid

## Phase 5: Issue Management

- [x] 5.1 Create `.github/workflows/stale.yml` for stale issue handling
- [x] 5.2 Configure exempt labels: `pinned`, `security`, `help wanted`
- [x] 5.3 Checkpoint - Verify stale workflow syntax is valid

## Phase 6: Branch Protection Enhancement

- [x] 6.1 Add `required_linear_history: true` to `branch-protection.yml`
- [x] 6.2 Add `required_conversation_resolution: true` to `branch-protection.yml`
- [x] 6.3 Checkpoint - Verify branch protection script syntax

## Phase 7: Cleanup

- [x] 7.1 Clean `FUNDING.yml` - remove placeholder comments
- [x] 7.2 Keep only active funding platforms (github, tidelift)
- [x] 7.3 Checkpoint - Verify FUNDING.yml is clean

## Phase 8: Validation

- [x] 8.1 Run YAML linting on all workflow files
- [x] 8.2 Verify no `|| true` patterns remain in quality checks
- [x] 8.3 Verify action version consistency across all workflows
- [x] 8.4 Document all changes in commit messages
- [x] 8.5 Final checkpoint - All governance files in place
