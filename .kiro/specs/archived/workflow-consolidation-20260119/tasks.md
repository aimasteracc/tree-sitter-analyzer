# Tasks - GitHub Workflow Consolidation

## Work Breakdown Structure

| ID | Task | Objective | Files to Modify | Status |
|----|------|-----------|-----------------|--------|
| T1 | Enhance `reusable-test.yml` | Merge coverage reporting and exclude slow tests | `reusable-test.yml` | completed |
| T2 | Upgrade Orchestrator `ci.yml` | Add branch-specific automation (Publish, PR) | `ci.yml` | completed |
| T3 | Fix Sidecar Triggers | Refine triggers for benchmarks and regressions | `benchmarks.yml`, `regression-tests.yml` | completed |
| T4 | Remove Redundancies | Delete obsolete workflow files | `test-coverage.yml`, `develop-automation.yml`, etc. | completed |
| T5 | Verification | Verify all automation flows (PR creation, Matrix) | N/A | completed |

## Testing Plan
1. **Redundancy Audit**: Checked file triggers.
2. **Feature Check**: Integrated conditional logic in `ci.yml`.
3. **Speed Check**: Standard tests now skip benchmarks/regressions.

## Acceptance Criteria
- [x] Setup logic is centralized in one action.
- [x] Single entry point (`ci.yml`) for all standard pushes.
- [x] Coverage reporting is part of the standard test flow.
- [x] Redundant test/build jobs removed.
