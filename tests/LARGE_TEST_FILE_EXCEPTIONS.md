# Large Test File Exceptions

Measured on 2026-09-06 (auto-audited by
`tests/contracts/test_large_test_file_inventory.py` — the inventory must
match reality or CI fails). The threshold is 800 lines.

## Current Files Over Threshold (51)

| Lines | File | Note |
|---:|---|---|
| 16567 | `tests/unit/test_benchmark_harness.py` | tracked: #1376 |
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
