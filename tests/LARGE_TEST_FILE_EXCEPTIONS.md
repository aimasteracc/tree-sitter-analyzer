# Large Test File Exceptions

Measured on 2026-09-07 (auto-audited by
`tests/contracts/test_large_test_file_inventory.py` — the inventory must
match reality or CI fails). The threshold is 800 lines.

## Current Files Over Threshold (50)

| Lines | File | Note |
|---:|---|---|
| 6123 | `tests/unit/mcp/test_safe_to_edit_tool.py` | tracked: #1376 |
| 5333 | `tests/unit/test_ast_cache.py` | tracked: #1376 |
| 2690 | `tests/unit/test_knowledge_graph.py` | |
| 2594 | `tests/unit/mcp/test_change_impact_tool_execute_and_mapping.py` | |
| 2253 | `tests/unit/test_incremental_sync.py` | |
| 2192 | `tests/unit/languages/test_kotlin_plugin.py` | |
| 2110 | `tests/unit/test_symbols_json_enrichment.py` | |
| 2097 | `tests/unit/test_ast_extraction.py` | |
| 2076 | `tests/unit/test_codegraph_context_tool.py` | |
| 1894 | `tests/unit/task/test_edge_evidence.py` | |
| 1878 | `tests/unit/test_uml_state.py` | |
| 1739 | `tests/unit/test_codegraph_full_index_tool.py` | |
| 1693 | `tests/unit/task/test_task_router.py` | |
| 1645 | `tests/unit/mcp/tools/test_co_change.py` | |
| 1615 | `tests/unit/languages/test_cyclomatic_complexity.py` | |
| 1575 | `tests/unit/test_uml_activity.py` | |
| 1440 | `tests/unit/mcp/test_test_discovery.py` | |
| 1403 | `tests/unit/core/test_engine.py` | |
| 1357 | `tests/unit/test_codegraph_pr_review_tool.py` | |
| 1348 | `tests/integration/formatters/test_data_manager.py` | |
| 1319 | `tests/unit/mcp/tools/test_nav_facade.py` | |
| 1120 | `tests/unit/cli/test_mcp_commands.py` | |
| 1078 | `tests/unit/mcp/tools/test_class_inspect_tool.py` | |
| 1062 | `tests/unit/languages/test_java_regression.py` | |
| 1059 | `tests/unit/test_diff_snapshot_readonly_capture.py` | |
| 1045 | `tests/unit/languages/test_cpp_plugin.py` | |
| 1036 | `tests/contracts/test_outdated_uv_qualification.py` | |
| 1022 | `tests/unit/test_index_snapshot.py` | |
| 996 | `tests/unit/test_call_graph_built_signal.py` | |
| 990 | `tests/unit/languages/test_python_plugin.py` | |
| 988 | `tests/unit/languages/test_php_plugin.py` | |
| 984 | `tests/unit/languages/test_c_plugin.py` | |
| 969 | `tests/unit/mcp/test_tools/test_get_code_outline_tool.py` | |
| 968 | `tests/unit/test_semantic_classify_tool.py` | |
| 953 | `tests/unit/mcp/tools/test_edit_facade_snapshot_routes.py` | |
| 941 | `tests/unit/test_index_source_snapshot.py` | |
| 932 | `tests/unit/mcp/tools/test_nav_facade_test_map.py` | |
| 905 | `tests/unit/test_synapse_resolution.py` | |
| 901 | `tests/unit/languages/test_html_plugin_advanced.py` | |
| 893 | `tests/unit/test_health_scorer.py` | |
| 873 | `tests/unit/mcp/test_query_symbol_search_scenarios.py` | |
| 866 | `tests/unit/languages/test_css_plugin.py` | |
| 847 | `tests/unit/test_ast_diff_scenarios.py` | |
| 847 | `tests/unit/languages/test_java_plugin.py` | |
| 833 | `tests/unit/test_codegraph_impact_tool.py` | |
| 822 | `tests/unit/test_edge_store.py` | |
| 822 | `tests/unit/cli/test_install_skills.py` | |
| 821 | `tests/unit/test_wire_owner_contract.py` | |
| 814 | `tests/unit/languages/test_java_formatter.py` | |
| 814 | `tests/unit/languages/test_csharp_plugin_elements.py` | |

## Exception Policy

No file has a permanent size exception. These files are tolerated as existing
debt only. When a change adds new behavior to one of them, prefer extracting a
focused test file for that behavior instead of appending more cases.

Acceptable temporary reasons:

## Issue #1376: Benchmark Harness Split

The 16,567-line `test_benchmark_harness.py` at
`50252c224d439b8a06e4055dee9f9a057a03fdef` is now 32 behavior-focused test
modules plus five non-collected helper modules. All paths below are under
`tests/unit/`. The failed two-file WIP is not the baseline.

| File | Lines |
|---|---:|
| `test_benchmark_harness.py` | 481 |
| `test_benchmark_harness_authority_lifecycle.py` | 576 |
| `test_benchmark_harness_authority_storage.py` | 378 |
| `test_benchmark_harness_canary_evidence.py` | 526 |
| `test_benchmark_harness_canary_preflight.py` | 556 |
| `test_benchmark_harness_canary_protocol.py` | 420 |
| `test_benchmark_harness_experiment_integrity.py` | 723 |
| `test_benchmark_harness_filesystem_evidence.py` | 352 |
| `test_benchmark_harness_gin_bundle.py` | 593 |
| `test_benchmark_harness_gin_execution.py` | 385 |
| `test_benchmark_harness_gin_qualification.py` | 413 |
| `test_benchmark_harness_gin_receipts.py` | 537 |
| `test_benchmark_harness_gin_tool_policy.py` | 394 |
| `test_benchmark_harness_gin_workspace.py` | 724 |
| `test_benchmark_harness_host_audit.py` | 379 |
| `test_benchmark_harness_operator_pipeline.py` | 559 |
| `test_benchmark_harness_plan_contract.py` | 624 |
| `test_benchmark_harness_platform_contract.py` | 179 |
| `test_benchmark_harness_receipt_authentication.py` | 522 |
| `test_benchmark_harness_receipt_binding.py` | 538 |
| `test_benchmark_harness_receipt_json.py` | 310 |
| `test_benchmark_harness_records.py` | 455 |
| `test_benchmark_harness_recovery_preflight.py` | 123 |
| `test_benchmark_harness_resource_bounds.py` | 446 |
| `test_benchmark_harness_service_ledger.py` | 750 |
| `test_benchmark_harness_service_schema.py` | 766 |
| `test_benchmark_harness_setup_backend.py` | 209 |
| `test_benchmark_harness_setup_failures.py` | 542 |
| `test_benchmark_harness_setup_manifest.py` | 632 |
| `test_benchmark_harness_setup_schema.py` | 271 |
| `test_benchmark_harness_source_inventory.py` | 643 |
| `test_benchmark_harness_transport_recovery.py` | 735 |
| `_benchmark_harness_matrix_helpers.py` | 380 |
| `_benchmark_harness_platform.py` | 20 |
| `_benchmark_harness_qualification_helpers.py` | 538 |
| `_benchmark_harness_service_helpers.py` | 456 |
| `_benchmark_harness_smoke_helpers.py` | 70 |

Run the entire migrated surface with
`uv run pytest tests/unit/test_benchmark_harness*.py -q` (default four xdist
workers). The live verification command in
[`benchmarks/codegraph_compare/README.md`](../benchmarks/codegraph_compare/README.md)
uses this same glob; selecting only the old file no longer covers the harness.

Before/after `pytest --collect-only -m ""` collected exactly 702 nodeids,
including class methods and parameter IDs. The mapping preserves everything
after the first `::`; only the owning file changes. The 609 checked AST blocks
(tests, helpers, and intact classes) are **not all identical to the original**:
the staged encoding ratchet reported 71 calls in 11 migrated files. Exactly
66 implicit-locale text calls now specify `encoding="utf-8"`. This is the only
additional behavior change beyond the split: text decoding/encoding no longer
depends on the runner's locale. Another five calls already passed `"utf-8"`
positionally; they now use the same value as an `encoding=` keyword because
the detector only recognizes keywords. Their encoding behavior is unchanged.
No pre-existing explicit encoding value or test payload was changed.

Pairwise AST verification excludes import statements and source positions,
then normalizes only an added UTF-8 keyword at an old implicit text call, or
the five exact `read_text("utf-8")` to `read_text(encoding="utf-8")` conversions.
Original, current, and normalized fingerprints are recorded separately.
Existing keyword/positional encoding changes or removals, non-UTF-8 additions,
assertion changes, payload changes, and receiver changes are rejected by ten
negative probes. Decorators, test parameters, assertions, and test/helper
docstrings are not excluded. Collected markers and fixture scopes still match
exactly. The per-file module descriptions were corrected to disclose UTF-8.

The original sole `tiny_repo` fixture remains function-scoped in the entry
module. There were no class/module fixtures or xunit lifecycle hooks to widen
or duplicate. Split classes retain their names and inherit only their original
non-test helpers; helper modules never import tests. POSIX section registration
now receives each module's namespace explicitly instead of consulting the
helper module's globals. The five tests inspected by the simulated-Windows
contract remain together with that contract, and the original platform reason
and string condition are unchanged. The six pre-section tests remain unmarked.

`test_safe_to_edit_tool.py` and `test_ast_cache.py` remain tracked above; this
split does not close all of #1376. Historical reports are unchanged.
