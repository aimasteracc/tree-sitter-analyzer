# Requirements - GitHub Workflow Optimization

## Current State Analysis
The project has multiple GitHub workflows for CI, testing, quality checks, and automation. Currently, these workflows have significant redundancy in setup logic and could be optimized for speed and reliability.

## Problem Identification
- **Redundant Setup**: Every job in `reusable-quality.yml` and `reusable-test.yml` manually installs `uv` and Python.
- **Suboptimal Caching**: `uv` cache is enabled in some places but not globally consistent or shared effectively.
- **Slow Test Matrix**: `reusable-test.yml` runs a full matrix (3 OS x 4 Python versions = 12 combinations, with some exclusions) on every push to common branches.
- **Maintenance Overhead**: Changes to the setup logic must be applied in multiple places.
- **Suspect Marker Logic**: The marker `-m "not requires_ripgrep or not requires_fd"` in tests might be incorrectly skipping integration tests that require both.

## Goals & Objectives
- Centralize setup logic into a single composite action.
- Reduce CI execution time by improving caching and reducing redundant steps.
- Optimize the test matrix to balance coverage and speed.
- Ensure all tests (especially those requiring system dependencies) are correctly run in CI.

## Non-functional Requirements
- **Performance**: CI should be at least 20% faster.
- **Consistency**: All workflows should use the same setup mechanism.
- **Robustness**: Better error reporting in CI summaries.
