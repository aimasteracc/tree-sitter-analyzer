# Requirements Document: GitHub Best Practices Improvement

## Introduction

Upgrades the `.github` directory to meet enterprise-grade open-source standards. This includes enabling strict quality gate enforcement, adding missing governance files, standardizing action versions, and implementing dependency automation. The goal is to transform the CI/CD configuration from "functional" to "globally competitive".

## Terminology

- **Quality Gate**: CI job that aggregates all quality checks and blocks merge on failure
- **Reusable Workflow**: GitHub Actions pattern using `workflow_call` for DRY configuration
- **Composite Action**: Custom action bundling multiple steps into one reusable unit
- **Dependabot**: GitHub's automated dependency update service
- **CODEOWNERS**: File specifying required reviewers for code paths

## Requirements

### Requirement 1: Strict Quality Gate Enforcement

**User Story:** As a maintainer, I want CI quality checks to actually fail when issues are found, so that code quality is enforced before merge.

#### Acceptance Criteria

1. WHEN Ruff finds linting errors THEN the `reusable-quality.yml` SHALL fail the job (not use `|| true`)
2. WHEN MyPy finds type errors THEN the workflow SHALL fail the job
3. WHEN Bandit finds security issues THEN the workflow SHALL fail the job
4. WHEN any quality check fails THEN the Quality Gate SHALL block the PR from merging
5. WHEN all quality checks pass THEN the Quality Gate SHALL report success

### Requirement 2: Missing Governance Files

**User Story:** As a contributor, I want clear governance documentation, so that I understand security policies and code ownership.

#### Acceptance Criteria

1. WHEN viewing the repository THEN a `CODEOWNERS` file SHALL exist assigning reviewers for critical paths
2. WHEN viewing the repository THEN a `SECURITY.md` file SHALL exist with vulnerability reporting instructions
3. WHEN viewing issues THEN an `ISSUE_TEMPLATE/config.yml` SHALL exist with helpful links and blank issue prevention
4. WHEN creating issues THEN users SHALL see options for bug reports, feature requests, and questions

### Requirement 3: Automated Dependency Updates

**User Story:** As a maintainer, I want dependencies to be automatically updated, so that security vulnerabilities are patched promptly.

#### Acceptance Criteria

1. WHEN a new Python dependency version is available THEN Dependabot SHALL create a PR
2. WHEN a new GitHub Actions version is available THEN Dependabot SHALL create a PR
3. WHEN Dependabot creates a PR THEN it SHALL include relevant changelog information
4. WHEN grouping updates THEN minor/patch updates SHALL be grouped to reduce PR noise

### Requirement 4: Consistent Action Versions

**User Story:** As a maintainer, I want all workflows to use the same action versions, so that behavior is predictable across workflows.

#### Acceptance Criteria

1. WHEN using `astral-sh/setup-uv` THEN all workflows SHALL use the same major version (v4)
2. WHEN using `actions/checkout` THEN all workflows SHALL use v4
3. WHEN using `actions/upload-artifact` THEN all workflows SHALL use v4
4. WHEN using `actions/download-artifact` THEN all workflows SHALL use v4

### Requirement 5: Enhanced Branch Protection

**User Story:** As a maintainer, I want stronger branch protection, so that main branch integrity is guaranteed.

#### Acceptance Criteria

1. WHEN configuring main branch protection THEN `require_linear_history` SHALL be enabled
2. WHEN configuring main branch protection THEN conversation resolution SHALL be required
3. WHEN configuring main branch protection THEN commit signing verification SHOULD be recommended

### Requirement 6: Stale Issue Management

**User Story:** As a maintainer, I want stale issues to be automatically labeled and closed, so that the issue tracker stays manageable.

#### Acceptance Criteria

1. WHEN an issue has no activity for 60 days THEN it SHALL be labeled as `stale`
2. WHEN a stale issue has no activity for 7 more days THEN it SHALL be closed
3. WHEN a stale issue receives new activity THEN the `stale` label SHALL be removed
4. WHEN issues are labeled `pinned` or `security` THEN they SHALL be exempt from stale processing

### Requirement 7: Clean FUNDING.yml

**User Story:** As a visitor, I want to see clean funding options, so that I can sponsor the project without confusion.

#### Acceptance Criteria

1. WHEN viewing FUNDING.yml THEN no placeholder comments SHALL remain
2. WHEN unused funding platforms exist THEN they SHALL be removed from the file
3. WHEN viewing the Sponsor button THEN only configured platforms SHALL appear
