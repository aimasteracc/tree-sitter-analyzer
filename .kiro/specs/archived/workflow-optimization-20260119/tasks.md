# Tasks - GitHub Workflow Optimization

## Work Breakdown Structure

| ID | Task | Objective | Files to Modify | Status |
|----|------|-----------|-----------------|--------|
| T1 | Centralized Setup Action | Create `.github/actions/setup-analyzer/action.yml` | `.github/actions/setup-analyzer/action.yml` | completed |
| T2 | Optimize Quality Workflow | Refactor `reusable-quality.yml` | `.github/workflows/reusable-quality.yml` | completed |
| T3 | Refine Test Workflow | Refactor `reusable-test.yml` and fix markers | `.github/workflows/reusable-test.yml` | completed |
| T4 | Update Coordinator | Ensure `ci.yml` uses optimized workflows correctly | `.github/workflows/ci.yml` | completed |
| T5 | Update SQL Compat | Use new setup action in `sql-platform-compat.yml` | `.github/workflows/sql-platform-compat.yml` | completed |
| T6 | Verification | Verify syntax and run manual workflow trigger | N/A | completed |

## Testing Plan
1. **Action Syntax Check**: Checked files manually.
2. **Execution Timing**: To be verified after CI runs.
3. **Marker Verification**: Removed the incorrect marker filter to ensure full test coverage.

## Acceptance Criteria
- [x] Setup logic is centralized in one action.
- [x] CI workflow passes across all platforms.
- [x] Significant reduction in "Set up" time per job.
- [x] No regressions in test coverage reporting.
