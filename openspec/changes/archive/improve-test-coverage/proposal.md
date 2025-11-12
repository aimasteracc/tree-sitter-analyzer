# Improve Test Coverage

**Change ID**: improve-test-coverage  
**Status**: In Progress  
**Created**: 2025-11-11  
**Last Updated**: 2025-11-11  
**Priority**: High  
**Impact**: Quality, Maintainability

---

## Progress Summary

### Completed Tasks (2/23)
- ✅ Task 1.1: CLI Entry Point Tests - **100% coverage** (0% → 100%)
- ✅ Task 1.2: Exception Coverage Tests - **89.13% coverage** (50.4% → 89.13%)

### Impact
- **69 new tests** added
- **2 critical files** improved significantly
- **1 file** at 100% coverage (quality standard met)
- **Bugs fixed**: 6 exception class initialization bugs discovered and fixed

---

## Overview

This change addresses the current test coverage gaps in the tree-sitter-analyzer project. Analysis shows 20 files with coverage below 80%, with some critical components having coverage as low as 0-40%. This proposal outlines a systematic approach to improve test coverage to meet the project's quality standard of >80% coverage.

---

## Problem Statement

### Current Coverage Analysis

Based on the latest coverage report, the following critical files have insufficient test coverage:

**Critical (0-50% coverage)**:
- `cli/__main__.py` (0.0%) - CLI entry point
- `utils/__init__.py` (22.2%) - Utility module initialization
- `utils/tree_sitter_compat.py` (34.0%) - Tree-sitter compatibility layer
- `formatters/java_formatter.py` (39.9%) - Java output formatting
- `interfaces/mcp_server.py` (40.8%) - MCP server interface
- `mcp/tools/universal_analyze_tool.py` (44.9%) - Universal analysis tool
- `exceptions.py` (50.4%) - Exception handling

**Medium Priority (50-70% coverage)**:
- `utils.py` (52.0%) - Core utilities
- `cli/commands/summary_command.py` (59.5%) - Summary command
- `queries/html.py` (59.5%) - HTML queries
- `queries/css.py` (61.5%) - CSS queries
- `core/engine.py` (62.3%) - Core analysis engine
- `core/query.py` (63.4%) - Query execution
- `cli/commands/find_and_grep_cli.py` (65.8%) - Find and grep CLI
- `formatters/markdown_formatter.py` (66.4%) - Markdown formatter
- `language_loader.py` (66.7%) - Language loader
- `cli/commands/list_files_cli.py` (68.2%) - List files CLI
- `cli/commands/search_content_cli.py` (68.5%) - Search content CLI
- `formatters/base_formatter.py` (68.5%) - Base formatter
- `languages/markdown_plugin.py` (68.6%) - Markdown plugin

### Impact

Low test coverage in these areas creates several risks:
1. **Regression Risk**: Changes may break functionality without detection
2. **Maintenance Difficulty**: Harder to refactor with confidence
3. **Quality Standard Violation**: Below the project's 80% coverage target
4. **CI/CD Risk**: Lower confidence in automated releases

---

## Goals

### Primary Goals
1. Achieve >80% test coverage across all core modules
2. Ensure 100% coverage for critical paths (CLI entry points, exception handling)
3. Add comprehensive tests for MCP server interface
4. Improve formatter test coverage to >85%

### Secondary Goals
1. Document complex test scenarios
2. Add integration tests for end-to-end workflows
3. Create test utilities to simplify future test development
4. Establish coverage monitoring in CI/CD

---

## Proposed Solution

### Phase 1: Critical Components (0-50% coverage)

**Priority 1A: Entry Points and Core Infrastructure**
- `cli/__main__.py`: Add tests for CLI initialization and error handling
- `exceptions.py`: Test all exception types and error scenarios
- `interfaces/mcp_server.py`: Add comprehensive MCP server interface tests

**Priority 1B: Compatibility and Tools**
- `utils/tree_sitter_compat.py`: Test compatibility layer across tree-sitter versions
- `mcp/tools/universal_analyze_tool.py`: Add tool invocation and validation tests
- `utils/__init__.py`: Test utility module initialization and exports

**Priority 1C: Formatters**
- `formatters/java_formatter.py`: Add Java-specific formatting tests

### Phase 2: Medium Priority Components (50-70% coverage)

**Priority 2A: Core Engine**
- `core/engine.py`: Add edge case and error handling tests
- `core/query.py`: Test query execution with various parameters
- `utils.py`: Complete utility function coverage

**Priority 2B: Query Modules**
- `queries/html.py`: Add HTML query pattern tests
- `queries/css.py`: Add CSS selector and property query tests

**Priority 2C: CLI Commands**
- `cli/commands/summary_command.py`: Add summary generation tests
- `cli/commands/find_and_grep_cli.py`: Add find/grep functionality tests
- `cli/commands/list_files_cli.py`: Add file listing tests
- `cli/commands/search_content_cli.py`: Add content search tests

**Priority 2D: Formatters and Plugins**
- `formatters/base_formatter.py`: Add base formatter tests
- `formatters/markdown_formatter.py`: Add Markdown formatting tests
- `languages/markdown_plugin.py`: Add plugin behavior tests
- `language_loader.py`: Add language loading and fallback tests

### Phase 3: Infrastructure and Monitoring

**Test Infrastructure**
- Create test fixtures for common scenarios
- Add test data generators for large-scale testing
- Implement coverage monitoring in GitHub Actions

**Documentation**
- Document testing patterns and best practices
- Create test writing guide for contributors
- Add coverage badge to README

---

## Design Considerations

### Test Strategy

**Unit Tests**
- Focus on individual function/method behavior
- Use mocking for external dependencies
- Aim for high code path coverage

**Integration Tests**
- Test component interactions
- Verify CLI command end-to-end flows
- Test MCP server request/response cycles

**Edge Cases and Error Handling**
- Test all exception paths
- Verify error messages and codes
- Test resource cleanup on failures

### Test Organization

```
tests/
├── unit/
│   ├── test_cli_main.py           # NEW: CLI entry point tests
│   ├── test_exceptions.py          # ENHANCED: Complete exception coverage
│   ├── test_utils_init.py          # NEW: Utils module tests
│   └── test_tree_sitter_compat.py  # NEW: Compatibility tests
├── integration/
│   ├── test_mcp_server_interface.py  # NEW: MCP interface tests
│   └── test_cli_workflows.py         # NEW: E2E CLI tests
├── formatters/
│   ├── test_java_formatter.py        # ENHANCED: Java formatter tests
│   └── test_base_formatter.py        # ENHANCED: Base formatter tests
└── fixtures/
    └── coverage_helpers.py           # NEW: Test utilities
```

### Success Metrics

**Coverage Targets**
- Overall coverage: >80% (currently ~75%)
- Critical modules: 100% (entry points, exceptions)
- Core modules: >85% (engine, query, formatters)
- Plugin modules: >80% (language plugins)

**Quality Metrics**
- All new tests pass 100%
- No reduction in existing test pass rate
- CI/CD pipeline execution time increase <20%

---

## Implementation Plan

See `tasks.md` for detailed task breakdown.

### Timeline
- **Phase 1**: 2-3 weeks (Critical components)
- **Phase 2**: 3-4 weeks (Medium priority components)
- **Phase 3**: 1-2 weeks (Infrastructure and monitoring)
- **Total**: 6-9 weeks

### Resources
- 1 developer (primary)
- Code review from maintainer
- CI/CD resources for automated testing

---

## Risks and Mitigation

### Risks

1. **Time Investment**: Comprehensive test coverage requires significant time
   - *Mitigation*: Phased approach, prioritize critical components first

2. **Test Maintenance**: More tests = more maintenance burden
   - *Mitigation*: Write clear, focused tests; use test utilities to reduce duplication

3. **False Confidence**: High coverage doesn't guarantee bug-free code
   - *Mitigation*: Focus on meaningful tests, not just coverage percentage

4. **CI/CD Performance**: More tests may slow down pipeline
   - *Mitigation*: Optimize test execution, use parallel testing where possible

### Backward Compatibility

This change is fully backward compatible:
- No API changes
- No breaking changes to existing functionality
- Only test additions and improvements

---

## Related Changes

- Quality Management Plan (`docs/ja/project-management/03_品質管理計画.md`)
- Test Strategy (`docs/ja/test-management/00_テスト戦略.md`)
- CI/CD workflows (`.github/workflows/`)

---

## Open Questions

1. Should we establish coverage requirements per module type (e.g., 100% for core, 80% for plugins)?
2. Should coverage checks be enforced in CI/CD (fail build if coverage drops)?
3. Are there specific test scenarios requested by users or identified in issue tracker?

---

## References

- Current coverage report: `coverage.json`
- Existing test suite: `tests/`
- Project quality standards: `openspec/project.md`
- pytest configuration: `pytest.ini`, `pyproject.toml`
