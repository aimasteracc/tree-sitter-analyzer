# Requirements - GitHub Workflow Consolidation

## Current State Analysis
The project has many overlapping workflows. For example, a push to the `develop` branch triggers:
1. `ci.yml` (Tests + Build)
2. `develop-automation.yml` (Build + PR creation)
3. `test-coverage.yml` (Tests with coverage)
4. `regression-tests.yml` (Regression tests)
5. `benchmarks.yml` (Benchmarks)
6. `sql-platform-compat.yml` (SQL tests + profiling)

## Problem Identification
- **Extreme Redundancy**: The same test suite and build process are executed up to 4 times for a single push.
- **Resource Waste**: Significant GitHub Actions minutes are wasted.
- **Slow Feedback**: Developers have to wait for multiple redundant runs to finish.
- **Maintenance Complexity**: Setup logic is scattered across 10+ files.

## Goals & Objectives
- Achieve "Single Path of Execution" for core quality checks.
- Consolidate advanced reporting (coverage, trends) into reusable workflows.
- Eliminate duplicate `test` and `build` jobs across automation workflows.
- Strategically exclude slow tests (benchmarks) from the fast feedback loop.

## Non-functional Requirements
- **Efficiency**: Reduce total CI minutes by 50%+.
- **Reliability**: Ensure specialized automation (PR creation, Publishing) still works correctly.
- **Standardization**: Use the unified `setup-analyzer` action everywhere.
