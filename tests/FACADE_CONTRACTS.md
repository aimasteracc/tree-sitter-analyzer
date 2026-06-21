# FACADE_CONTRACTS.md

Last updated: 2026-06-21 (Queue 3)

## Measurement Snapshot (post-Queue-3)

| Metric | Count |
|--------|------:|
| Facade test files (`tests/unit/mcp/tools/*.py`) | 10 |
| Total test functions (facade files) | 274 |
| Contract invariant tests (`test_facade_envelope_contract.py`) | 32 |
| Governance test violations baseline (`KNOWN_EXISTING_VIOLATIONS`) | 29 |

## 8 Production Facades

| Facade | Builder Function | Module |
|--------|-----------------|--------|
| Edit | `build_edit_facade` | `tree_sitter_analyzer.mcp.tools.edit_facade` |
| Health | `build_health_facade` | `tree_sitter_analyzer.mcp.tools.health_facade` |
| Index | `build_index_facade` | `tree_sitter_analyzer.mcp.tools.index_facade` |
| Nav | `build_nav_facade` | `tree_sitter_analyzer.mcp.tools.nav_facade` |
| Project | `build_project_facade` | `tree_sitter_analyzer.mcp.tools.project_facade` |
| Search | `build_search_facade` | `tree_sitter_analyzer.mcp.tools.search_facade` |
| Structure | `build_structure_facade` | `tree_sitter_analyzer.mcp.tools.structure_facade` |
| Viz | `build_viz_facade` | `tree_sitter_analyzer.mcp.tools.viz_facade` |

Note: `search` uses the standard FacadeTool action-map protocol (action=symbol/query/content/grep/batch)
and is included in the parametrized contract tests. The `content` action is a bespoke F5 route
(returns `dict | int`) but the facade's error-envelope invariants still apply to it.

## 4 Common Invariants — Canonical Location

All 4 invariants below are parametrized over all 8 production facades in:
`tests/unit/mcp/test_facade_envelope_contract.py`

| # | Invariant | Test function |
|---|-----------|--------------|
| 1 | Envelope preserved | `test_envelope_preserved` |
| 2 | Arg projection (action key stripped) | `test_arg_projection_strips_action` |
| 3 | Missing action → error envelope | `test_missing_action_returns_error_envelope` |
| 4 | Unknown action → error envelope with available_actions | `test_unknown_action_returns_error_envelope` |

## Facade-Specific Boundary Contracts (per-file)

Each facade test file in `tests/unit/mcp/tools/` retains:
- Bespoke routing logic (e.g., R3 normalize, specific action dispatch)
- Schema shape validation
- File-specific edge cases
- Integration-level tests using real builder with `tmp_path`

See the INVARIANT DELEGATION NOTICE comment block at the top of each file for details.

## Governance Ratchet

File: `tests/unit/mcp/test_facade_contract_governance.py`

Scans `tests/unit/mcp/tools/*.py` for new functions matching:
- `test_*envelope_preserved*`
- `test_*arg_projection_strips_action*`
- `test_*missing_action_returns_error*`
- `test_*unknown_action_returns_error*`

Any match NOT in `KNOWN_EXISTING_VIOLATIONS` causes test failure.
This prevents re-introduction of the duplicate boilerplate patterns.

Ratchet baseline: 29 pre-existing violations (discovered 2026-06-21, before Queue 3).
The baseline only shrinks — Queue 4+ will remove existing duplicates and remove
them from `KNOWN_EXISTING_VIOLATIONS` at the same time.

## Prohibited Patterns

Do NOT add new functions to `tests/unit/mcp/tools/` that duplicate the 4 invariants above.
The governance test will catch and fail on any new additions.

Queue 4+ will remove the existing `KNOWN_EXISTING_VIOLATIONS` entries and shrink the baseline.

---

## History

### Pre-Queue-3 (measured 2026-06-20)

| Surface | Count |
|---|---:|
| `tests/unit/mcp` Python files | 219 |
| Facade-named files in `tests/unit/mcp` | 11 |

### Queue 3 (2026-06-21)

Added:
- `tests/unit/mcp/test_facade_envelope_contract.py` — 32 parametrized contract tests
  (8 facades × 4 invariants)
- `tests/unit/mcp/test_facade_contract_governance.py` — governance ratchet test

Modified (INVARIANT DELEGATION NOTICE added to 10 files):
- `tests/unit/mcp/tools/test_edit_facade.py`
- `tests/unit/mcp/tools/test_health_facade.py`
- `tests/unit/mcp/tools/test_facade_tool.py`
- `tests/unit/mcp/tools/test_index_facade.py`
- `tests/unit/mcp/tools/test_nav_facade.py`
- `tests/unit/mcp/tools/test_nav_facade_test_map.py`
- `tests/unit/mcp/tools/test_project_facade.py`
- `tests/unit/mcp/tools/test_structure_facade.py`
- `tests/unit/mcp/tools/test_viz_facade.py`
- `tests/unit/mcp/tools/test_viz_facade_uml_p1.py`

No existing test functions deleted; all 226 facade tests continue to pass.
