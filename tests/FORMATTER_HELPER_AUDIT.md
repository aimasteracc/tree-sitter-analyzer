# Formatter Helper Audit

Measured on 2026-06-20 under `tests/integration/formatters`.

| Surface | Count |
|---|---:|
| Helper files | 48 |
| Helper lines | 7972 |
| Test files | 6 |
| Test lines | 2181 |

## Policy

Formatter helpers are acceptable only when they remove real duplication across
multiple tests or isolate unavoidable compatibility setup. A helper that only
wraps one assertion or hides one fixture should be inlined into the test.

## Cleanup Order

1. Identify helpers imported by exactly one test file.
2. Inline helpers that merely call a formatter and return the result.
3. Keep helpers that build shared golden data or normalize cross-version output.
4. Move behavior assertions out of helpers and into test bodies so failures
   point at the behavior being protected.

## Review Rule

New formatter helpers must include at least two call sites or a comment that
names the compatibility concern they isolate.

## Queue 5 Audit — Formatter Helper Simplification (2026-06-21)

### Purpose

Collapse a compatibility-only helper façade to reduce helper indirection in
`tests/integration/formatters`.

### Baseline snapshot (targeted)

| File | Caller count (before) | Classification |
|---|---:|---|
| `tests/integration/formatters/_format_contract_tests_helpers.py` | 1 (`format_contract_tests.py`) | `single-caller` |
| `tests/integration/formatters/_format_contract_assertion_helpers.py` | 1 (`_format_contract_tests_helpers.py`) | `single-caller` |
| `tests/integration/formatters/_format_contract_info_helpers.py` | 1 (`_format_contract_tests_helpers.py`) | `single-caller` |
| `tests/integration/formatters/_format_contract_validator_helpers.py` | 1 (`_format_contract_tests_helpers.py`) | `single-caller` |
| `tests/integration/formatters/_format_contract_tests_data.py` | 1 (`_format_contract_tests_helpers.py`) | `single-caller` |

### Queue 5 changes

| File | Action | Replaced with / Rationale |
|---|---|---|
| `tests/integration/formatters/_format_contract_tests_helpers.py` | **removed** | Facade layer with no logic; direct imports now in `format_contract_tests.py` |
| `tests/integration/formatters/_format_contract_tests_data.py` | **removed** | Fixture content and constants were moved inline into `format_contract_tests.py` because the helper had one call site |
| `tests/integration/formatters/format_contract_tests.py` | updated helper implementation | Helper logic was moved inline and call paths now point directly at the test module |
| `tests/integration/formatters/_format_contract_assertion_helpers.py` | **removed** | Assertion helpers were inlined into `format_contract_tests.py` because single-caller import-only indirection remained after queue pass |
| `tests/integration/formatters/_format_contract_validator_helpers.py` | **removed** | Validator helpers were inlined into `format_contract_tests.py` because the module only served this single test file |
| `tests/integration/formatters/_format_contract_info_helpers.py` | **removed** | Info extraction and consistency helpers were inlined into `format_contract_tests.py` because this helper had one call site |

### Result snapshot (targeted)

| File | Caller count (after) | Classification |
|---|---:|---|
| `tests/integration/formatters/_format_contract_info_helpers.py` | 0 | `removed` |
| `tests/integration/formatters/_format_contract_tests_data.py` | 0 | `removed` |

### Queue 5 continuation (2026-06-21)

Additional single-caller formatter helpers were consolidated into active modules and removed after the initial contract-suite pass:

| File | Caller count (before) | Classification (after) |
|---|---:|---|
| `tests/integration/formatters/_comprehensive_suite_data.py` | 1 (`_comprehensive_suite_phases.py`) | `removed` |
| `tests/integration/formatters/_comprehensive_suite_phase_cases.py` | 1 (`_comprehensive_suite_phases.py`) | `removed` |
| `tests/integration/formatters/_comprehensive_suite_runner.py` | 1 (`comprehensive_test_suite.py`) | `removed` |
| `tests/integration/formatters/_content_aware_validator.py` | 1 (`enhanced_assertions.py`) | `removed` |
| `tests/integration/formatters/_enhanced_assertions_assert_mixin.py` | 1 (`enhanced_assertions.py`) | `removed` |
| `tests/integration/formatters/_semantic_format_parser.py` | 1 (`enhanced_assertions.py` after inline) | `removed` |
| `tests/integration/formatters/_semantic_format_rules.py` | 1 (`enhanced_assertions.py` after inline) | `removed` |
| `tests/integration/formatters/_semantic_format_validator.py` | 1 (`enhanced_assertions.py` after inline) | `removed` |
| `tests/integration/formatters/_semantic_relationship_validator.py` | 1 (`enhanced_assertions.py` after inline) | `removed` |
| `tests/integration/formatters/_specification_compliance_tests_csv_mixin.py` | 1 (`specification_compliance_tests.py`) | `removed` |
| `tests/integration/formatters/_specification_compliance_tests_fixtures.py` | 1 (`specification_compliance_tests.py`) | `removed` |
| `tests/integration/formatters/_specification_compliance_tests_full_mixin.py` | 1 (`specification_compliance_tests.py`) | `removed` |
| `tests/integration/formatters/_specification_compliance_tests_helpers.py` | 1 (`specification_compliance_tests.py`) | `removed` |
| `tests/integration/formatters/_structural_format_validator.py` | 1 (`enhanced_assertions.py`) | `removed` |
| `tests/integration/formatters/_test_data_manager_io.py` | 1 (`test_data_manager.py`) | `removed` |
| `tests/integration/formatters/_test_data_manager_repository_io.py` | 1 (`test_data_manager.py`) | `removed` |
| `tests/integration/formatters/_test_data_manager_schema.py` | 1 (`test_data_manager.py`) | `removed` |
| `tests/integration/formatters/_test_data_manager_templates.py` | 1 (`test_data_manager.py`) | `removed` |

### Notes

- No behavior in production or assertions was changed; this change is a pure
  import-graph simplification.
- No helper behavior was removed from execution paths; this was an import-graph and
  placement cleanup.
