# Test Governance Framework

## Goal

Build an enterprise-grade testing system with the following properties:

- No invalid tests (tests without clear assertions).
- Minimal duplicate tests (semantic duplicate clusters continuously reduced).
- Precise source-function to test mapping.
- Language-aligned test sharding (same strategy across supported languages).
- Continuous, machine-checkable quality gates.

## Core Principles

1. **Function-level traceability**
   - Every public source symbol should map to at least one unit test.
   - Mapping is generated automatically; no manual spreadsheet.

2. **Single responsibility test files**
   - One test file should primarily target one source module.
   - Cross-cutting tests go to explicit `*_integration.py` or `*_properties.py` files.

3. **Controlled property testing budget**
   - Property test volume must be capped to avoid test explosion.
   - Use explicit `max_examples` profiles for local/CI tiers.

4. **Continuous governance, not one-time cleanup**
   - Run governance audit in CI and locally.
   - Fail fast if duplicate/invalid threshold is exceeded.

## Directory & Naming Standard

### Source-to-test mapping standard

- Source module: `tree_sitter_analyzer/<domain>/<module>.py`
- Primary unit test: `tests/unit/<domain>/test_<module>.py`

Examples:

- `tree_sitter_analyzer/core/query_service.py` -> `tests/unit/core/test_query_service.py`
- `tree_sitter_analyzer/mcp/tools/query_tool.py` -> `tests/unit/mcp/test_query_tool.py`

### Cross-cutting tests

- Integration behavior: `tests/unit/<domain>/test_<topic>_integration.py`
- Property behavior: `tests/unit/<domain>/test_<topic>_properties.py`
- Regression bugfix: `tests/unit/<domain>/test_<topic>_regression.py`

Do not duplicate the same scenario across these categories.

## YAML and Language Sharding Policy

Current issue: YAML has many fragmented property files, inconsistent with other languages.

Target policy:

- Keep one primary plugin test file per language:
  - `test_<lang>_plugin.py`
- Keep at most **2-4** property shards per language:
  - `test_<lang>_properties_syntax.py`
  - `test_<lang>_properties_semantics.py`
  - `test_<lang>_properties_resilience.py`
  - `test_<lang>_properties_io.py` (optional)
- Avoid micro-shards (`test_yaml_xxx_properties.py`) unless they are very large and independent.

## Governance Auditor

Script: `scripts/audit_test_governance.py`

### What it checks

- Source symbols extracted from AST.
- Test cases extracted from `tests/unit/**/test_*.py`.
- Symbol -> test references (heuristic by symbol usage in test AST).
- Duplicate test clusters by AST fingerprint.
- Potentially invalid tests (no `assert`, no `pytest.raises`, no mock assertion call).
- Language sharding imbalance outliers.

### Run

```bash
uv run python scripts/audit_test_governance.py
```

### Strict gate

```bash
uv run python scripts/audit_test_governance.py --fail-on-duplicates 0 --fail-on-invalid 0
```

Generated reports:

- `comprehensive_test_results/test_governance_audit.json`
- `comprehensive_test_results/test_governance_audit.md`

## CI Gate Recommendation

Use staged thresholds:

1. Phase 1 (adoption):
   - `--fail-on-invalid 50`
   - `--fail-on-duplicates 50`
2. Phase 2 (hardening):
   - `--fail-on-invalid 10`
   - `--fail-on-duplicates 20`
3. Phase 3 (target):
   - `--fail-on-invalid 0`
   - `--fail-on-duplicates 0`

## Practical Cleanup Roadmap

1. **Merge duplicate files first**
   - Keep richer superset tests.
   - Migrate only unique scenarios.

2. **Normalize naming by module**
   - Remove `test_core_*` + `test_*` dual naming for same module.

3. **Re-shard YAML tests**
   - Consolidate fragmented files into 2-4 stable shards.

4. **Enforce function coverage gaps**
   - Use audit report `possibly_uncovered_symbols` as red list.

5. **Set property test budget**
   - Keep Hypothesis runtime under predictable CI budget.

## Definition of Done (Professional Level)

- Every supported language follows same sharding strategy.
- Every public symbol has at least one direct or behavior-level test.
- No invalid tests in governance report.
- Duplicate clusters reduced to zero (or explicitly whitelisted).
- Governance audit runs in CI and blocks regressions.

## Achieved State (2026-02-27)

All governance targets have been met:

| Metric | Baseline (prior session) | Target | Achieved |
|--------|--------------------------|--------|----------|
| Duplicate clusters | 56 | 0 | **0** ✅ |
| Invalid tests | 98 | 0 | **0** ✅ |
| Possibly uncovered symbols | 34 | 0 | **0** ✅ |
| Total test cases | ~6830 | increase | **7006** ✅ |

### What was done

1. **Cleanup (prior session)**: deleted 9 redundant test files, consolidated test logic, fixed autouse fixtures.
2. **Governance tooling**: built `scripts/audit_test_governance.py` — AST-based auditor with duplicate fingerprinting, invalid-test detection, symbol-coverage heuristics, allowlist support, and CI-gate flags.
3. **Allowlist**: `tests/governance_allowlist.json` — explicitly allowlists internal symbols (`models:dataclass_with_slots`) and confirmed no-assertion tests that are intentional.
4. **Targeted tests**: added 176 new targeted tests across 7 existing and 2 new test files to achieve 0 uncovered public symbols:
   - [tests/unit/core/test_encoding_utils.py](../tests/unit/core/test_encoding_utils.py) — `read_file_safe_async`, `clear_encoding_cache`
   - [tests/unit/core/test_models.py](../tests/unit/core/test_models.py) — `SQLTable.get_primary_key_columns/get_foreign_key_columns`
   - [tests/unit/core/test_output_manager.py](../tests/unit/core/test_output_manager.py) — `results_header`, `analysis_summary`, `language_list`, `query_list`, `extension_list`, `get_output_manager`
   - [tests/unit/core/test_project_detector.py](../tests/unit/core/test_project_detector.py) — `detect_from_cwd`
   - [tests/unit/core/test_query_loader.py](../tests/unit/core/test_query_loader.py) — `preload_languages`
   - [tests/unit/formatters/test_formatter_registry.py](../tests/unit/formatters/test_formatter_registry.py) — `register_language_formatter`, `set_default_language_formatter`, `register_builtin_formatters`
   - [tests/unit/cli/test_argument_validator.py](../tests/unit/cli/test_argument_validator.py) *(new)* — `validate_table_query_exclusivity`
   - [tests/unit/languages/test_yaml_queries.py](../tests/unit/languages/test_yaml_queries.py) *(new)* — `get_yaml_query`, `get_yaml_query_description`, `get_available_yaml_queries`

### Ongoing governance command

```bash
# Run audit (0 should mean pass — no uncovered, no duplicates, no invalid)
uv run python scripts/audit_test_governance.py --fail-on-duplicates 0 --fail-on-invalid 0
```


---

## Advanced Test Architecture (Phase 3 — Expert-Driven)

Based on industry expert analysis (Fowler / Beck / Feathers / Sridharan / Bache / Kerr / North / Winters / Troy / Majors), the following advanced testing areas close the remaining gaps to world-class quality.

### Chaos Tests (`tests/chaos/`)

Fault-injection tests that verify resilience:
- Plugin crash isolation: crash in lang A must not affect lang B
- MCP tool timeout: must return error response, not hang
- Memory pressure: 1MB input must stay within memory bounds

### Security Tests (`tests/unit/security/`)

Boundary validation against adversarial inputs:
- Path traversal: `../../etc/passwd` style inputs must raise, not read
- Memory bombs: 1000-deep YAML nesting must not stack overflow
- Fuzzing-like: Hypothesis `@given(st.text())` on all file path entrypoints

### Observability Tests

Verify structured logs contain observable fields:
- `language` field present in analysis log records
- `duration_ms` field present for performance tracking
- Error records contain `correlation_id` for traceability

### Property Test Quality Upgrade (Kerr Principle)

Replace generic `st.text()` strategies with domain-aware strategies:
- Valid YAML keys: `st.characters(whitelist_categories=("Lu", "Ll", "Nd"))`
- Idempotency: `parse(x) == parse(parse_result(x))` for all extractors
- Commutativity: order of element extraction must not affect results

### BDD Scenario Tests (North Principle)

CLI tests should express user intent via Given-When-Then structure:
- "Given a Python file, When I run analyze, Then functions appear in output"
- "Given an unsupported extension, When I run analyze, Then graceful error"

### Layer Assignment Quick Reference

| Test type | Directory | Real I/O | Parser |
|-----------|-----------|----------|--------|
| Unit (mock) | `tests/unit/` | ✗ | ✗ |
| Language integration | `tests/integration/languages/` | ✓ | ✓ |
| CLI E2E | `tests/integration/cli/` | ✓ | ✓ |
| Chaos | `tests/chaos/` | minimal | varies |
| Security | `tests/unit/security/` | ✗ | ✗ |
| Property | `tests/unit/*/test_*_properties.py` | ✗ | ✗ |
