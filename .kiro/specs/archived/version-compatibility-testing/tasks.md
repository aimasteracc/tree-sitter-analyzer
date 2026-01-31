# Version Compatibility Testing - Tasks

## Overview

Implementation tasks for the version compatibility testing system.

---

## Phase 1: MCP Golden Masters

### T1.1: Create Testing Utilities Module
**Status**: `completed`  
**Priority**: High  
**Objective**: Create the foundational testing utilities for normalization and golden master handling.

**Files Created**:
- `tree_sitter_analyzer/testing/__init__.py`
- `tree_sitter_analyzer/testing/normalizer.py`
- `tree_sitter_analyzer/testing/golden_master.py`

**Acceptance Criteria**:
- [x] `MCPOutputNormalizer` class handles path normalization (Windows/Unix)
- [x] `MCPOutputNormalizer` removes volatile fields (timestamp, duration_ms, cache_hit, fd_elapsed_ms, rg_elapsed_ms)
- [x] `MCPOutputNormalizer` sorts dictionary keys for deterministic comparison
- [x] `load_golden_master()` and `save_golden_master()` utilities work
- [x] `generate_diff()` produces human-readable diffs
- [x] All functions have type hints and docstrings

---

### T1.2: Create MCP Tool Test Fixtures
**Status**: `completed`  
**Priority**: High  
**Objective**: Create standardized test inputs for each MCP tool.

**Files Created**:
- `tests/regression/mcp/conftest.py`
- `tests/regression/mcp/__init__.py`

**Test Inputs Needed**:
| Tool | Test Input |
|------|------------|
| check_code_scale | `examples/BigService.java` |
| analyze_code_structure | `examples/BigService.java` with `output_format=json` |
| extract_code_section | `examples/BigService.java` lines 93-106 |
| query_code | `examples/BigService.java` with `query_key=methods` |
| list_files | `examples/` directory |
| search_content | Pattern `class.*Service` in `examples/` |
| find_and_grep | Pattern `public` in `.java` files |
| get_supported_languages | No input needed |

**Acceptance Criteria**:
- [x] All 7 tools have defined test inputs (get_supported_languages excluded - not a separate tool)
- [x] Inputs are realistic and exercise core functionality
- [x] Fixtures are reusable across tests

---

### T1.3: Generate Initial Golden Masters
**Status**: `completed`  
**Priority**: High  
**Objective**: Capture current output of all MCP tools as golden masters.

**Files Created**:
- `tests/golden_masters/mcp/check_code_scale.json`
- `tests/golden_masters/mcp/analyze_code_structure.json`
- `tests/golden_masters/mcp/extract_code_section.json`
- `tests/golden_masters/mcp/query_code.json`
- `tests/golden_masters/mcp/list_files.json`
- `tests/golden_masters/mcp/search_content.json`
- `tests/golden_masters/mcp/find_and_grep.json`

**Acceptance Criteria**:
- [x] Each golden master contains normalized output
- [x] Files are valid JSON
- [x] Files are committed to version control
- [x] Golden masters pass validation (no volatile fields)

---

### T1.4: Create MCP Golden Master Test Suite
**Status**: `completed`  
**Priority**: High  
**Objective**: Create pytest tests that compare current output against golden masters.

**Files Created**:
- `tests/regression/mcp/test_mcp_golden_master.py`

**Acceptance Criteria**:
- [x] All 7 MCP tools are tested
- [x] Tests use individual test methods for clarity
- [x] Failed tests produce clear diffs
- [x] Tests run in < 30 seconds total
- [x] Tests pass on current develop branch (13/13 passed)

---

### T1.5: Create Golden Master Update Script
**Status**: `pending`  
**Priority**: Medium  
**Objective**: Script to regenerate golden masters after intentional changes.

**Files to Create**:
- `scripts/update_mcp_golden_masters.py`

**Usage**:
```bash
# Update all golden masters
uv run python scripts/update_mcp_golden_masters.py --all

# Update specific tool
uv run python scripts/update_mcp_golden_masters.py --tool check_code_scale
```

**Acceptance Criteria**:
- [ ] Script regenerates normalized golden masters
- [ ] Script shows diff before overwriting
- [ ] Script requires confirmation for changes
- [ ] Script logs what was updated

---

## Phase 2: Behavioral Contracts

### T2.1: Define MCP Output Contract Schema
**Status**: `pending`  
**Priority**: Medium  
**Objective**: Create YAML schema defining stable/additive/volatile fields.

**Files to Create**:
- `tests/golden_masters/contracts/mcp_output_contract.yaml`

**Acceptance Criteria**:
- [ ] All 8 tools have contract definitions
- [ ] Stable fields are clearly marked
- [ ] Additive fields are clearly marked
- [ ] Volatile fields are clearly marked
- [ ] Schema includes version number

---

### T2.2: Create Contract Validator
**Status**: `pending`  
**Priority**: Medium  
**Objective**: Validate that changes respect behavioral contracts.

**Files to Create**:
- `tree_sitter_analyzer/testing/contract_validator.py`

**Acceptance Criteria**:
- [ ] Validator loads contract from YAML
- [ ] Validator checks stable field changes (FAIL if changed)
- [ ] Validator allows additive field additions (PASS)
- [ ] Validator ignores volatile field changes (PASS)
- [ ] Clear error messages for violations

---

### T2.3: Integrate Contract Validation with Tests
**Status**: `pending`  
**Priority**: Medium  
**Objective**: Golden master tests use contract validation for smarter diffs.

**Files to Modify**:
- `tests/regression/mcp/test_mcp_golden_master.py`

**Acceptance Criteria**:
- [ ] Tests differentiate between breaking and non-breaking changes
- [ ] Breaking changes fail with clear message
- [ ] Non-breaking changes produce warnings only
- [ ] Contract violations are logged

---

## Phase 3: Cross-Version Testing

### T3.1: Create Cross-Version Comparison Script
**Status**: `pending`  
**Priority**: Low  
**Objective**: Script to compare MCP output across versions.

**Files to Create**:
- `scripts/compare_versions.py`

**Usage**:
```bash
# Compare local vs specific version
uv run python scripts/compare_versions.py --base 1.9.2 --head local

# Compare two published versions
uv run python scripts/compare_versions.py --base 1.6.1.2 --head 1.9.2
```

**Acceptance Criteria**:
- [ ] Script runs MCP tools via subprocess
- [ ] Script handles local (uv run) and published (uvx) versions
- [ ] Script normalizes outputs before comparison
- [ ] Script generates compatibility report
- [ ] Script exits with non-zero code on breaking changes

---

### T3.2: Create Version Snapshot Storage
**Status**: `pending`  
**Priority**: Low  
**Objective**: Store output snapshots for each published version.

**Files to Create**:
- `tests/golden_masters/versions/.gitkeep`
- `tests/golden_masters/versions/README.md`

**Acceptance Criteria**:
- [ ] Version snapshots are gitignored (generated locally)
- [ ] README explains snapshot generation
- [ ] Snapshot naming convention: `{version}/{tool}.json`

---

### T3.3: CI Integration for Compatibility Tests
**Status**: `pending`  
**Priority**: Low  
**Objective**: Add compatibility tests to CI workflow.

**Files to Create/Modify**:
- `.github/workflows/compatibility.yml` (new)
- OR modify existing `.github/workflows/tests.yml`

**Acceptance Criteria**:
- [ ] Golden master tests run on every PR
- [ ] Cross-version tests run on release branches
- [ ] Failing tests block merge
- [ ] Test results are visible in PR checks

---

## Dependencies

```
T1.1 ──► T1.2 ──► T1.3 ──► T1.4
              │
              └──► T1.5

T1.4 ──► T2.1 ──► T2.2 ──► T2.3

T1.4 ──► T3.1 ──► T3.2 ──► T3.3
```

## Testing Plan

### Unit Tests
- `tests/unit/testing/test_normalizer.py` - Normalizer unit tests
- `tests/unit/testing/test_golden_master.py` - Golden master utilities tests
- `tests/unit/testing/test_contract_validator.py` - Contract validator tests

### Integration Tests
- Run MCP golden master tests with actual MCP tools
- Run cross-version comparison with real versions

### Regression Tests
- MCP golden master tests ARE the regression tests

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Golden masters too strict | High | Medium | Use normalization, allow additive |
| Cross-version subprocess flaky | Medium | Low | Retry logic, timeout handling |
| CI slowdown | Low | Medium | Parallelize, cache dependencies |
| Windows path issues | Medium | Medium | Normalize paths in tests |

---

## Progress Log

| Date | Task | Status | Notes |
|------|------|--------|-------|
| 2026-01-19 | T1.1 | Pending | Design complete |
