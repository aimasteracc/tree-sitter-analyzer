# Tasks: Fix unreachable_code.py Structural Debt

## Background

`unreachable_code.py` was graded C (score 75.3) by the project health scorer:
- **549 lines** (over 500-line project limit)
- **Nesting depth 8** at L466 — inner closure `_walk_for_functions` inside
  `analyze_file_unreachable` created 6+ levels of nesting
- **3 long methods**: `_analyze_block_unreachable` 62L, `_analyze_if_statement` 75L,
  `analyze_file_unreachable` 79L

Additionally, a real bug was discovered: `_language_from_ext(ext)` was called with
just the extension string (`.py`), but the function expects a full file path.
`os.path.splitext(".py")` returns `('.py', '')` so the extension was empty and
language always resolved to `None` → every real file was treated as unknown.

## Phase 1 — TDD: write tests first (RED)

- [x] **T1** Create `tests/unit/test_unreachable_code.py` with 34 tests covering:
       `_is_false_literal`, `_is_true_literal`, `analyze_file_unreachable`,
       `analyze_project_unreachable`, dataclass schema

## Phase 2 — Refactor: eliminate structural debt (GREEN)

- [x] **R1** Fix `_language_from_ext(file_path)` bug (was passing `ext`, now passes
       full `file_path` — affects both `analyze_file_unreachable` and `analyze_project_unreachable`)
- [x] **R2** Extract inner closure `_walk_for_functions` → module-level
       `_walk_functions_in_tree(root, func_def_types, block_type, source, language, file_path, results) → int`
       with mutable `counter = [0]` to avoid nonlocal; eliminates nesting depth from 8 → ≤4
- [x] **R3** Extract `_analyze_function_body` helper (body dispatch from `_walk_functions_in_tree`)
- [x] **R4** Break up `_analyze_if_statement` (75L → ~25L) via helpers:
       `_get_if_condition`, `_get_consequence_and_alternative`, `_check_constant_condition`,
       `_find_block_in_clause`, `_analyze_alternative_clause`, `_report_dead_branch`
- [x] **R5** Extract `_report_unreachable_after_terminal` from `_analyze_block_unreachable`
- [x] **R6** Extract `_analyze_handler_block` from `_analyze_try_statement`
- [x] **R7** Extract `_find_call_func_node` from `_is_terminal_call`
- [x] **R8** Extract `_read_file_bytes` and `_parse_tree` from `analyze_file_unreachable`
- [x] **R9** Extract `_infer_js_function_name` from `_get_function_name`
- [x] **R10** Fix nested function detection: after analyzing a function body, recurse
        into its children to find nested function definitions (previously missed)

## Phase 3 — Verification

- [x] **V1** 34 new tests all pass (including nested function detection)
- [x] **V2** File grade: C (75.3) → B (83.9), deep_nesting eliminated
- [x] **V3** Full test suite: 18087 passed, 0 failed (34 new tests added)
- [x] **V4** ruff check passes
- [x] **V5** Committed on feature/code-intelligence-architecture
