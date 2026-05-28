# Phase 8: Code Slimming & Quality Purification

## Goal
Eliminate all mastery scan violations: 22 oversized → 0, 76 low-density → 0.

## Strategy
Split each oversized test file into focused modules (one per source module), ensuring all tests pass after each split. TDD gate: split → run tests → only proceed if green.

## Tasks (Vertical Slices — completed 2026-05-28)

### Slice 1: Split test_mcp_fd_rg_tools.py (DONE — prior commit 357cec31)
- [x] test_fd_rg_result_utils.py + related files created, original deleted

### Slice 2: Split test_route_detector.py (1516 lines → 5 files + conftest.py)
- [x] test_route_detector_python.py — Flask/FastAPI/K1 framework detection
- [x] test_route_detector_web.py — Express/Spring
- [x] test_route_detector_go.py — Go frameworks + summary/dispatch/source-walk
- [x] test_route_detector_tool.py — tool schema/execute
- [x] test_route_detector_cache.py — cache persistence, handler quality, envelope
- [x] tests/unit/conftest.py — shared fixtures (flask_project, fastapi_project, etc.)

### Slice 3: Split test_codegraph_query_tool.py (1980 lines → 6 files)
- [x] _codegraph_query_helpers.py — shared plain-function helpers
- [x] test_codegraph_query_dsl.py — DSL parser/argument helpers
- [x] test_codegraph_query_tool_core.py — schema, validation, execute basics
- [x] test_codegraph_query_tool_advanced.py — filter/fallback, batch, sort
- [x] test_codegraph_query_tool_has.py — has-step, relation cache
- [x] test_codegraph_query_internals.py — filter helpers, query state
- [x] test_codegraph_query_internals_facets.py — relation steps, file entries

### Slice 4: Split test_validator_false_positives.py (1992 lines → 6 files)
- [x] test_validator_fp_wrapper_a/b/c.py — wrapper-node groups
- [x] test_validator_fp_depth.py — depth-limit tests
- [x] test_validator_fp_multifile.py — multi-file scenarios
- [x] test_validator_fp_boundary.py — boundary/edge cases

### Slice 5: Split test_call_graph.py (1122 lines → 4 files)
- [x] test_call_graph_ast_a.py — FunctionRef, NodeText, WalkTree
- [x] test_call_graph_ast_b.py — GetFuncName, ExtractCall, FindParentClass
- [x] test_call_graph_integration.py — CallGraphBuild and integration
- [x] test_call_graph_cached.py — CachedCallGraph, FileImpact, NodeTextUtf8

### Slice 6: Split test_code_patterns_tool.py (1035 lines → 3 files)
- [x] test_code_patterns_unit.py, test_code_patterns_execute.py, test_code_patterns_regression.py

### Slice 7: Split test_universal_analyze_tool.py (891 lines → 3 files)
- [x] test_universal_analyze_tool_core.py, test_universal_analyze_tool_execute.py, test_universal_analyze_tool_metrics.py

### Slice 8: Split test_argument_parser_builder.py (869 lines → 2 files)
- [x] test_argument_parser_builder_options.py, test_argument_parser_builder_integration.py

### Slice 9: Low-density assertion files (DONE — see phase8-slice2-low-density spec)
- [x] All low-density files fixed in separate spec

### Note: test_agent_contracts.py (1486 lines — intentional exception, no split)
This is the project's architectural contract document. A single cohesive file for
48 invariant assertions is correct; splitting would fragment the audit trail.

## Gates
- [x] ruff check passes (all commits clean)
- [x] pytest full suite (18 002 tests) green
- [x] All oversized files split (exception: test_agent_contracts.py by design)
