# Version Compatibility Testing - Requirements

## Current State Analysis

### Existing Regression Testing Infrastructure

The project already has a solid foundation for regression testing:

| Component | Location | Coverage |
|-----------|----------|----------|
| Golden Master Tests | `tests/integration/core/test_golden_master_regression.py` | CLI output for 17 languages × 4 formats |
| API Regression Tests | `tests/regression/test_api_regression.py` | AnalysisRequest, QueryExecutor compatibility |
| CLI Regression Tests | `tests/integration/cli/test_cli_regression.py` | CLI commands and output stability |
| Format Regression Tests | `tests/regression/test_format_regression.py` | Multi-language format stability |
| Documentation | `docs/regression-testing-guide.md` | Golden Master methodology guide |

### Test Statistics
- **Total Tests**: 8,405+
- **Unit Tests**: 2,087
- **Integration Tests**: 187
- **Regression Tests**: 70
- **Property Tests**: 75
- **Benchmarks**: 20

## Problem Identification

### Gap 1: MCP Tool Regression Tests Missing

The 8 MCP tools lack dedicated golden master tests:

| MCP Tool | Has Golden Master? | Risk |
|----------|-------------------|------|
| `check_code_scale` | ❌ No | Output format changes undetected |
| `analyze_code_structure` | ❌ No | Breaking changes to structure |
| `extract_code_section` | ❌ No | Partial read inconsistencies |
| `query_code` | ❌ No | Query result format changes |
| `list_files` | ❌ No | File listing format changes |
| `search_content` | ❌ No | Search result format changes |
| `find_and_grep` | ❌ No | Combined search format changes |
| `get_supported_languages` | ❌ No | Language list changes |

### Gap 2: Cross-Version Comparison Absent

No automated mechanism to:
- Compare outputs between published versions (e.g., 1.6.1.2 vs 1.9.2 vs current)
- Detect breaking changes before release
- Validate upgrade paths

### Gap 3: Behavioral Contracts Undefined

No formal specification of:
- Which output fields MUST remain stable
- Which fields CAN be added (additive)
- Which fields MAY change (volatile)

### Gap 4: MCP Multi-Version Testing Not Leveraged

User's MCP configuration supports multiple versions side-by-side:
```json
{
  "tree-sitter-analyzer-local": { /* current */ },
  "tree-sitter-analyzer-1.6.1.2": { /* v1.6.1.2 */ },
  "tree-sitter-analyzer-1.9.2": { /* v1.9.2 */ }
}
```

This capability is not utilized for automated testing.

## Goals & Objectives

### Primary Goals

1. **MCP Golden Masters**: Create golden master tests for all 8 MCP tools
2. **Cross-Version Framework**: Automated comparison between versions
3. **Behavioral Contracts**: Define stability guarantees
4. **CI Integration**: Block breaking changes automatically

### Success Criteria

| Metric | Target |
|--------|--------|
| MCP tools with golden masters | 8/8 (100%) |
| Cross-version test automation | Fully automated |
| Breaking change detection | Before merge |
| False positive rate | < 5% |

## Non-Functional Requirements

### Performance
- Golden master tests: < 30 seconds total
- Cross-version comparison: < 2 minutes per version pair

### Maintainability
- Golden masters easily updateable via CLI command
- Clear documentation for updating after intentional changes

### Reliability
- Deterministic outputs (no flaky tests)
- Proper normalization of dynamic values (timestamps, paths, line numbers)

## Use Cases

### UC1: Developer Makes Code Change
1. Developer modifies MCP tool implementation
2. Pre-commit hook runs golden master tests
3. If output differs, test fails with diff
4. Developer reviews diff, decides if intentional
5. If intentional, updates golden master

### UC2: Pre-Release Compatibility Check
1. Before release, CI runs cross-version tests
2. Compares current branch vs latest release
3. Generates compatibility report
4. Flags breaking changes for review

### UC3: Investigate Regression Report
1. User reports regression after upgrade
2. Developer runs cross-version comparison
3. Identifies exact field/output that changed
4. Traces to specific commit

## Glossary

| Term | Definition |
|------|------------|
| Golden Master | Captured expected output used as reference |
| Breaking Change | Output change that breaks backward compatibility |
| Additive Change | New field/feature that doesn't break existing consumers |
| Behavioral Contract | Specification of what outputs must remain stable |
| Normalization | Process of removing dynamic values before comparison |
