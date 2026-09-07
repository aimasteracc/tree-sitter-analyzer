# Large Test File Exceptions

Measured on 2026-09-07 (auto-audited by
`tests/contracts/test_large_test_file_inventory.py` — the inventory must
match reality or CI fails). The threshold is 800 lines.

## Current Files Over Threshold (48)

| Lines | File | Note |
|---:|---|---|
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
| 1523 | `tests/unit/mcp/test_test_discovery.py` | |
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
debt only. New behavior goes into its corresponding existing behavior module.
Splitting an oversized suite requires the user-approved controlled pure-migration
exception in CLAUDE.md T-1, including a tracking issue and exact collection/AST
evidence. The 800-line warning threshold does not waive the 500-line module cap.

Acceptable temporary reasons:

## Issue #1376: Benchmark Harness Split

The 16,567-line `test_benchmark_harness.py` at
`50252c224d439b8a06e4055dee9f9a057a03fdef` is split into bounded behavior
modules and non-collected shared helpers, under the explicit #1376 migration
authorization. PR #1393 applies CLAUDE.md's **500-line hard cap** to every
migrated Python module; the 800-line inventory threshold above is a legacy
warning line, not permission to exceed 500. The size contract dynamically
discovers both harness filename prefixes rather than fixing a module count.
All paths below are under `tests/unit/`. The failed two-file WIP is not the
baseline; this review round also compares directly against `ab9cc537`.

| File | Lines |
|---|---:|
| `test_benchmark_harness.py` | 476 |
| `test_benchmark_harness_authority_host.py` | 129 |
| `test_benchmark_harness_authority_lifecycle.py` | 468 |
| `test_benchmark_harness_authority_storage.py` | 378 |
| `test_benchmark_harness_canary_evidence.py` | 388 |
| `test_benchmark_harness_canary_preflight.py` | 393 |
| `test_benchmark_harness_canary_protocol.py` | 420 |
| `test_benchmark_harness_canary_workspace.py` | 173 |
| `test_benchmark_harness_decision_service.py` | 253 |
| `test_benchmark_harness_decision_transport.py` | 263 |
| `test_benchmark_harness_experiment_integrity.py` | 390 |
| `test_benchmark_harness_experiment_registry.py` | 347 |
| `test_benchmark_harness_filesystem_evidence.py` | 352 |
| `test_benchmark_harness_gin_bundle.py` | 465 |
| `test_benchmark_harness_gin_codegraph_receipts.py` | 164 |
| `test_benchmark_harness_gin_execution.py` | 385 |
| `test_benchmark_harness_gin_index_snapshot.py` | 330 |
| `test_benchmark_harness_gin_qualification.py` | 413 |
| `test_benchmark_harness_gin_receipts.py` | 387 |
| `test_benchmark_harness_gin_tool_policy.py` | 394 |
| `test_benchmark_harness_gin_workspace.py` | 241 |
| `test_benchmark_harness_host_audit.py` | 379 |
| `test_benchmark_harness_operator_io.py` | 211 |
| `test_benchmark_harness_operator_pipeline.py` | 372 |
| `test_benchmark_harness_plan_contract.py` | 381 |
| `test_benchmark_harness_plan_oracles.py` | 271 |
| `test_benchmark_harness_platform_contract.py` | 317 |
| `test_benchmark_harness_receipt_authentication.py` | 445 |
| `test_benchmark_harness_receipt_binding.py` | 422 |
| `test_benchmark_harness_receipt_json.py` | 312 |
| `test_benchmark_harness_receipt_resource_limits.py` | 149 |
| `test_benchmark_harness_receipt_retention.py` | 107 |
| `test_benchmark_harness_receipt_transport.py` | 293 |
| `test_benchmark_harness_records.py` | 445 |
| `test_benchmark_harness_recovery_preflight.py` | 123 |
| `test_benchmark_harness_resource_bounds.py` | 446 |
| `test_benchmark_harness_service_ledger.py` | 298 |
| `test_benchmark_harness_service_runtime_schema.py` | 419 |
| `test_benchmark_harness_service_schema.py` | 376 |
| `test_benchmark_harness_setup_backend.py` | 209 |
| `test_benchmark_harness_setup_diagnostics.py` | 180 |
| `test_benchmark_harness_setup_failures.py` | 380 |
| `test_benchmark_harness_setup_manifest.py` | 459 |
| `test_benchmark_harness_setup_schedule.py` | 190 |
| `test_benchmark_harness_setup_schema.py` | 271 |
| `test_benchmark_harness_source_inventory.py` | 468 |
| `test_benchmark_harness_source_manifest.py` | 193 |
| `test_benchmark_harness_transport_recovery.py` | 229 |
| `test_benchmark_harness_verifier_ledger.py` | 245 |
| `_benchmark_harness_matrix_helpers.py` | 380 |
| `_benchmark_harness_platform.py` | 20 |
| `_benchmark_harness_qualification_helpers.py` | 315 |
| `_benchmark_harness_receipt_helpers.py` | 232 |
| `_benchmark_harness_service_helpers.py` | 456 |
| `_benchmark_harness_smoke_helpers.py` | 347 |
| `_benchmark_harness_workspace_helpers.py` | 178 |

Run the entire migrated surface with
`uv run pytest tests/unit/test_benchmark_harness*.py -q` (default four xdist
workers). The live verification command in
[`benchmarks/codegraph_compare/README.md`](../benchmarks/codegraph_compare/README.md)
uses this same glob; selecting only the old file no longer covers the harness.

Actual before/after `pytest --collect-only -m ""` retains all 702 original
nodeids, including class methods and parameter IDs. The original-case mapping
preserves everything after the first `::`; only the owning file changes.
New platform-governance cases are counted separately, with one parameter per
actual POSIX-section module, plus the independent 500-line inventory contract.

The function/method ASTs are **not claimed to be byte-identical**. The preceding
encoding-ratchet fix changed exactly 66 implicit-locale text calls to explicit
`encoding="utf-8"`; five already-explicit positional UTF-8 arguments became
same-valued keywords. This review preserves those changes without adding any
new encoding changes. No explicit encoding value or test payload was changed.
Real comments and docstrings are now Chinese; tokenizer/AST boundaries protect
test-input strings, assertion strings, and pragma/noqa/type directives.

Pairwise AST verification first recognizes true module/class/function
docstrings, then excludes their translated values, import statements, and
source positions. It does not discard arbitrary string expressions; a string
following an import is not retroactively treated as a docstring. Decorators,
test parameters, assertions, test data, and all other executable nodes remain
strictly compared. The review checks 589 function/method blocks against
`ab9cc537` and chains 588 original-source function/method blocks back to the
16,567-line baseline, normalizing only the previously authorized 66+5 UTF-8
adjustments in that older comparison. Original, current, and normalized
fingerprints are recorded separately. Seven docstring-boundary negative probes
and the ten encoding probes reject business-string/assertion/encoding changes.
Collected markers and fixture scopes match for every original case.

The original sole `tiny_repo` fixture remains function-scoped in the entry
module. There were no class/module fixtures or xunit lifecycle hooks to widen
or duplicate. Split classes retain their names and inherit only their original
non-test helpers; helper modules never import tests. All original helper
methods are defined once, even when several test modules share a helper base.

The new function-scoped `posix_module` fixture discovers every actual top-level
`_POSIX_QUALIFICATION_SECTION_START` assignment. Parameterized governance checks
exact final registration and exact platform markers for every section test,
comparing source definitions with the runtime namespace. In-memory appended-test
and missing-marker mutations must trigger assertion failures for every module.
These new governance tests precede the POSIX boundary and also run on Windows;
they copy namespaces/functions rather than mutating live test modules. The
original local and simulated-Windows tests remain, including their five
introspected cases. The original platform reason/condition are unchanged, and
the six original pre-section cases remain unmarked.

The remaining safety/cache suites were migrated separately as recorded below.
Historical benchmark reports and the benchmark tests are unchanged by that work.

## Issue #1376: Safety and Cache Splits

This controlled migration uses the published `0841669f` baseline, not the earlier
line-count report: safety was 6,123 lines and collected 332 cases; AST cache was
5,370 lines and collected 248 cases. Remote develop was checked after completing
safety and again immediately before the cache migration; it still pointed to
`0841669f`. No unpublished schema17/PR #1352 content was merged.

Every original class, test, parameter, marker and fixture scope is retained.
Safety's function-scoped autouse registry cleanup remains active in each module;
the cache suite's class-local fixtures stay inside their intact classes. Each
suite shares one non-test helper module, binding the same fixture objects rather
than re-exporting tests. No original cases were added, deleted or duplicated.

| File | Lines |
|---|---:|
| `tests/unit/mcp/test_safe_to_edit_tool.py` | 396 |
| `tests/unit/mcp/test_safe_to_edit_tool_causal_envelope.py` | 302 |
| `tests/unit/mcp/test_safe_to_edit_tool_commands.py` | 332 |
| `tests/unit/mcp/test_safe_to_edit_tool_exercising_tests.py` | 358 |
| `tests/unit/mcp/test_safe_to_edit_tool_import_resolution.py` | 474 |
| `tests/unit/mcp/test_safe_to_edit_tool_include_dependencies.py` | 386 |
| `tests/unit/mcp/test_safe_to_edit_tool_include_projection.py` | 260 |
| `tests/unit/mcp/test_safe_to_edit_tool_java_imports.py` | 247 |
| `tests/unit/mcp/test_safe_to_edit_tool_java_projection.py` | 444 |
| `tests/unit/mcp/test_safe_to_edit_tool_jsts_imports.py` | 307 |
| `tests/unit/mcp/test_safe_to_edit_tool_jsts_projection.py` | 278 |
| `tests/unit/mcp/test_safe_to_edit_tool_python_imports.py` | 257 |
| `tests/unit/mcp/test_safe_to_edit_tool_python_projection.py` | 419 |
| `tests/unit/mcp/test_safe_to_edit_tool_read_existing.py` | 271 |
| `tests/unit/mcp/test_safe_to_edit_tool_snapshot_integrity.py` | 467 |
| `tests/unit/mcp/test_safe_to_edit_tool_snapshot_routes.py` | 305 |
| `tests/unit/mcp/test_safe_to_edit_tool_stale_edges.py` | 273 |
| `tests/unit/mcp/test_safe_to_edit_tool_syntax_envelope.py` | 246 |
| `tests/unit/mcp/_safe_to_edit_tool_helpers.py` | 191 |
| `tests/unit/test_ast_cache.py` | 372 |
| `tests/unit/test_ast_cache_cache_directory.py` | 369 |
| `tests/unit/test_ast_cache_call_graph.py` | 333 |
| `tests/unit/test_ast_cache_candidate_cleanup.py` | 243 |
| `tests/unit/test_ast_cache_force_rebuild.py` | 233 |
| `tests/unit/test_ast_cache_frozen_reader.py` | 408 |
| `tests/unit/test_ast_cache_index_project.py` | 311 |
| `tests/unit/test_ast_cache_materialization.py` | 390 |
| `tests/unit/test_ast_cache_private_storage.py` | 344 |
| `tests/unit/test_ast_cache_projection_state.py` | 389 |
| `tests/unit/test_ast_cache_root_lease.py` | 341 |
| `tests/unit/test_ast_cache_scope_partition.py` | 348 |
| `tests/unit/test_ast_cache_snapshot_batches.py` | 258 |
| `tests/unit/test_ast_cache_snapshot_epoch.py` | 269 |
| `tests/unit/test_ast_cache_snapshot_validation.py` | 249 |
| `tests/unit/test_ast_cache_storage_transactions.py` | 383 |
| `tests/unit/test_ast_cache_symbols.py` | 306 |
| `tests/unit/_ast_cache_helpers.py` | 123 |

Actual before/after collection maps 332 safety cases to 332 and 248 cache cases
to 248, including every class method and parameter ID. AST evidence compares
236 safety and 162 cache top-level definition blocks, including whole classes;
module constants such as `_BACKFILL_ROUTES` are checked separately. Only imports,
source positions, true docstrings and the declared UTF-8 changes are normalized.
Safety has eight and cache has 85 implicit-locale I/O calls changed to explicit
UTF-8; no pre-existing explicit encoding values or test/assertion data changed.
Real comments/docstrings are Chinese, and executable directives are preserved.
Negative probes reject assertion, payload, parameter and explicit-encoding drift.

`pytest.ini` and its runtime contract explicitly retain every migrated cache
module in the quick gate without adding the pre-existing neighboring cache
suites. Worker, timeout, marker and comprehensive-command settings are unchanged.
The Windows trust diagnostic workflow's concrete nodeid points to the new
`test_ast_cache_force_rebuild.py` owner.

Shipping validation also integrates published develop `5ac5a68e` (#1398/#1399)
and its refreshed dependency lock. The original migration baseline and nodeid
maps remain unchanged. The Windows diagnostic retains Python 3.11/3.12/3.13,
all five cases, the dynamic `$cases.Count` check, and twenty repetitions. This
sync does not import the unmerged #1352 feature branch or change release versions.

TSA uses its existing filename/stem family rules: complete Python named families
are no longer cut to ten files, while symbol-only candidates remain bounded.
Non-Python recursive discovery keeps its original lazy ten-candidate stop;
a separate iteration-count regression guards against exhausting its iterator.
The repository's `cache/` implementation package maps to the `ast_cache` facade
family through the existing stem mapper. No parallel parser or mapping engine
was added. New policy/discovery contract cases are separate from the original
580 migrated cases, and do not manufacture coverage for those suites.
