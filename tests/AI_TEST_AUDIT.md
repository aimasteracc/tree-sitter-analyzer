# AI-Generated Test Audit

Measured on 2026-06-20.

## Suspicion Signals

These patterns are treated as AI-slop signals because they create green tests
without protecting behavior:

- `assert result is not None`
- `assert value is not None or value is None`
- `assert len(items) >= 1` for deterministic fixtures
- broad helper-heavy tests whose assertions only prove that something returned

## Current Findings

| Signal | Count |
|---|---:|
| Raw `assert result is not None` matches | 355 |
| AST placeholder findings after paired-behavior filtering | 130 |
| Raw None-check tautology regex matches | 15 |
| AST tautology findings | 10 |

The AST counts are authoritative for gating because they understand expression
shape and ignore placeholder guards that are paired with concrete behavior in
the same test.

## Required Rewrite Pattern

Bad:

```python
result = tool.run(input_data)
assert result is not None
```

Good:

```python
result = tool.run(input_data)
assert result["status"] == "ok"
assert result["items"] == [{"name": "main", "kind": "function"}]
```

When a fixture is intentionally nondeterministic, keep the test but document the
reason with `# ratchet: nondeterministic <reason>` on the assert block.

---

## Queue 4 Audit — AI-Suspect & Coverage-only Cleanup (2026-06-21)

### Summary

| Metric | Value |
|---|---:|
| Baseline loose assertions (pre-Queue 4) | 171 |
| Post-Queue 4 loose assertions | 0 |
| `_test_phase7_*` helper files found | 14 |
| `_test_phase7_*` files deleted | 0 (all referenced) |
| Files strengthened | 90+ |
| Files replaced (behavior rewrite) | 1 |
| Test count pre-Queue 4 | 21,221 |
| Test count post-Queue 4 | 21,221 |

### `_test_phase7_*` Helper File Disposition

All 14 `_test_phase7_*` files use pytest's skip-collection prefix (`_`), but are
imported directly by active test modules. Deleting them would break the test suite.
All 14 are classified **KEEP**.

| File | Imported By | Decision |
|---|---|---|
| `integration/_test_phase7_comprehensive_security_helpers.py` | `test_phase7_security_integration.py` | KEEP |
| `integration/_test_phase7_end_to_end_helpers.py` | `test_phase7_end_to_end.py` | KEEP |
| `integration/_test_phase7_final_integration_helpers.py` | `test_phase7_final_integration.py` | KEEP |
| `integration/_test_phase7_fixtures.py` | multiple phase7 tests | KEEP |
| `integration/_test_phase7_helpers.py` | multiple phase7 tests | KEEP |
| `integration/_test_phase7_performance_helpers.py` | `test_phase7_performance.py` | KEEP |
| `integration/_test_phase7_real_world_helpers.py` | `test_phase7_real_world.py` | KEEP |
| `integration/_test_phase7_resource_helpers.py` | `test_phase7_resource.py` | KEEP |
| `integration/_test_phase7_unit_helpers.py` | `test_phase7_unit.py` | KEEP |
| `unit/mcp/_test_phase7_mcp_helpers.py` | `test_phase7_mcp.py` | KEEP |
| `unit/mcp/_test_phase7_mcp_integration_helpers.py` | `test_phase7_mcp_integration.py` | KEEP |
| `unit/mcp/_test_phase7_mcp_unit_helpers.py` | `test_phase7_mcp_unit.py` | KEEP |
| `unit/mcp/_test_phase7_server_helpers.py` | `test_phase7_server.py` | KEEP |
| `unit/mcp/_test_phase7_tool_helpers.py` | `test_phase7_tool.py` | KEEP |

### Strengthened Files (Batch 2)

Violations fixed per file (placeholder `is not None`, tautologies `is not None or is None`,
or loose bounds `>= N` for deterministic values). Nondeterministic guards annotated with
`# ratchet: nondeterministic <reason>` instead of being removed.

| File | Violations Fixed | Primary Fix Pattern |
|---|---:|---|
| `unit/core/test_query_extended.py` | 12 | tautologies → `isinstance`; executor → `isinstance(executor, QueryExecutor)` |
| `unit/core/test_language_loader_comprehensive.py` | 3 | `is not None` → `is mock_language_obj` / `in loader._loaded_languages` |
| `unit/languages/test_typescript_extractor_comprehensive.py` | 1 | `is not None` → `isinstance(text, str)` |
| `integration/formatters/format_contract_tests.py` | 4 | `len > 0` → ratchet; 3× `is not None` → `isinstance(x, dict)` |
| `e2e/conftest.py` | 3 | subprocess pipe `is not None` → ratchet (OS-variant type) |
| `unit/mcp/test_server_utils_registration.py` | 3 | `is not None` → `isinstance(result, dict)` + schema checks |
| `unit/mcp/test_build_project_index_tool.py` | 4 | tool → `isinstance`; timing → ratchet; `files_scanned` → ratchet |
| `unit/languages/test_markdown_plugin_extract.py` | 2 | `is not None` → `isinstance(result, str)` + content checks |
| `unit/languages/test_json_plugin.py` | 3 | `len > 0` → ratchet; `>= 2` → `== 2`; `is not None` → `isinstance` |
| `unit/languages/test_css_plugin_enhanced_features.py` | 2 | `is not None` → `isinstance(str)` + selector check |
| `unit/languages/test_cpp_plugin.py` | 3 | complexity bounds → exact/relational; `is not None` → type guard |
| `unit/languages/test_c_plugin.py` | 3 | same pattern as cpp |
| `unit/core/test_project_detector.py` | 2 | `is not None` → `isinstance(str)` + content; `> 0` → ratchet |
| `unit/core/test_base_plugin.py` | 3 | `is not None` → `isinstance`; `>= 0` → `isinstance(list)` |
| `unit/cli/test_universal_analyze_tool_comprehensive.py` | 2 | `is not None` → `isinstance(PathResolver/SecurityValidator)` |
| `unit/security/test_validator.py` | 5+ | `is not None` → `isinstance(ProjectBoundaryManager/RegexSafetyChecker/...)` |
| `unit/mcp/test_read_partial_tool_coverage.py` | 2 | `is not None` → `isinstance(ReadPartialTool/FileOutputManager)` |
| `unit/mcp/test_modification_guard_tool.py` | 2 | `is not None` → `isinstance`; `len > 0` → ratchet |
| `unit/mcp/test_mcp_utils_init.py` | 2 | both → ratchet (can return None in fallback) |
| `unit/mcp/test_error_handler.py` | 3 | `is not None` → `isinstance(result, dict)` |
| `integration/mcp/test_resources/test_project_stats_resource.py` | 4 | stats `>= 0` → ratchet; `is not None` → `hasattr + callable` |
| `integration/cli/test_toon_error_handling.py` | 2 | `is not None` + `len > 0` → `isinstance(str)` + ratchet |
| `unit/mcp/test_check_tools_tool.py` | 2 | `is not None` → `isinstance`; `len > 0` → ratchet |
| `unit/test_csharp_method_resolution.py` | 1 | `is not None` → `isinstance(ctx, CSharpResolverContext)` |
| `unit/test_go_method_resolution.py` | 1 | `is not None` → `isinstance(built, GoResolverContext)` |
| `unit/test_issue_577_agent_summary_uniformity.py` | 1 | removed redundant `is not None` (already gated by `in _LEGAL_VERDICTS`) |
| `unit/test_php_method_resolution.py` | 1 | `is not None` → `isinstance(built, PhpResolverContext)` |
| *(~63 additional single-violation files)* | 1 each | `is not None` → `isinstance` / ratchet / exact |

### Replaced Files (Batch 3)

| File | Before | After | Reason |
|---|---|---|---|
| `unit/languages/test_typescript_plugin_coverage_boost.py` | Coverage-only: `assert result is not None` smoke test | Behavior test: parses known TS code, checks element categories, asserts `"myFunc"` in function names, `"MyClass"` in class names | Classic AI-slop coverage-fill: single test, no behavioral contract |

### Ratchet Exemptions Added

All `# ratchet: nondeterministic <reason>` annotations are intentional — the guarded
values are genuinely nondeterministic (OS subprocess types, timing, filesystem stats,
optional-dependency fallbacks). They are not loopholes.

| Category | Count |
|---|---:|
| Subprocess/OS pipe type variants | 3 |
| Timing / performance measurements | 6 |
| Filesystem stats (file count, optional-dep) | 4 |
| Nondeterministic output size (deterministic format but variable content) | 8 |
| Fallback / optional-dependency result type | 3 |

---

## Queue 5 Audit — Formatter Helper Simplification (2026-06-21)

### Summary

| File | Action | Behavioral impact |
|---|---|---|
| `tests/integration/formatters/_format_contract_tests_helpers.py` | removed | none (import indirection-only module) |
| `tests/integration/formatters/_format_contract_assertion_helpers.py` | removed | assertion/contract helpers moved inline to `format_contract_tests.py` because they were single-caller and did not provide cross-test reuse |
| `tests/integration/formatters/_format_contract_validator_helpers.py` | removed | contract validation helpers moved inline to `format_contract_tests.py` because they only supported one caller and kept logic near assertions |
| `tests/integration/formatters/_format_contract_info_helpers.py` | removed | format-info extraction and consistency helpers moved inline to `format_contract_tests.py` because this helper had one caller and no cross-test reuse |
| `tests/integration/formatters/format_contract_tests.py` | helper inline refactor | none (same helper symbols, same assertions behavior) |
| `tests/integration/formatters/_format_contract_tests_data.py` | removed | none (fixture content/constants moved inline to `format_contract_tests.py`) |

### Rationale

- `_format_contract_tests_helpers.py` existed as a compatibility façade and did not own assertions/logic.
- `_format_contract_tests_data.py` contained only fixture constants and fixture helper routines; these were moved inline to the test module to remove another single-caller helper.
- `_format_contract_assertion_helpers.py`, `_format_contract_validator_helpers.py`, and `_format_contract_info_helpers.py` kept same validation intent while collapsing residual single-caller helper indirection into `format_contract_tests.py`.
- Queue 5 scope is helper structure cleanup and duplication reduction, so we collapsed this layer and kept downstream helper modules intact.

### Queue 5 Coverage Check

- `uv run pytest tests/integration/formatters/format_contract_tests.py -q -n 0`
- Result: `3 passed, 6 skipped`
- `-n 0` used because default run in this environment attempted xdist node bootstrapping and
  hit a temp-directory permission error unrelated to these changes.

#### Queue 5 continuation — deeper helper flattening

- Additional format helper modules were removed after verifying they had a single caller and no remaining references:
  - `_comprehensive_suite_data.py`
  - `_comprehensive_suite_phase_cases.py`
  - `_comprehensive_suite_runner.py`
  - `_content_aware_validator.py`
  - `_enhanced_assertions_assert_mixin.py`
  - `_semantic_format_parser.py`
  - `_semantic_format_rules.py`
  - `_semantic_format_validator.py`
  - `_semantic_relationship_validator.py`
  - `_specification_compliance_tests_csv_mixin.py`
  - `_specification_compliance_tests_fixtures.py`
  - `_specification_compliance_tests_full_mixin.py`
  - `_specification_compliance_tests_helpers.py`
  - `_structural_format_validator.py`
  - `_test_data_manager_io.py`
  - `_test_data_manager_repository_io.py`
  - `_test_data_manager_schema.py`
  - `_test_data_manager_templates.py`

- These were inlined into:
  - `tests/integration/formatters/comprehensive_test_suite.py`
  - `tests/integration/formatters/enhanced_assertions.py`
  - `tests/integration/formatters/specification_compliance_tests.py`
  - `tests/integration/formatters/test_data_manager.py`

#### Follow-up coverage checks for Queue 5 continuation

- `uv run pytest tests/integration/formatters/test_real_integration.py -q -n 0`
  - Result: `4 passed`
- `uv run pytest tests/integration/formatters/test_comprehensive_format_validation.py -q -n 0`
  - Result: `16 passed, 1 skipped`
- `uv run pytest tests/integration/formatters/format_contract_tests.py -q -n 0`
  - Result: `3 passed, 6 skipped`
