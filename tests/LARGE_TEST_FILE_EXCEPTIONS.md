# Large Test File Exceptions

Measured on 2026-06-20. The threshold is 800 lines.

## Current Files Over Threshold

| Lines | File |
|---:|---|
| 1577 | `tests/unit/test_codegraph_context_tool.py` |
| 1553 | `tests/unit/languages/test_kotlin_plugin.py` |
| 1425 | `tests/unit/test_uml_state.py` |
| 1403 | `tests/unit/mcp/tools/test_co_change.py` |
| 1380 | `tests/unit/languages/test_cyclomatic_complexity.py` |
| 1279 | `tests/unit/test_ast_extraction.py` |
| 1194 | `tests/unit/test_uml_activity.py` |
| 1188 | `tests/unit/test_codegraph_pr_review_tool.py` |
| 1120 | `tests/unit/core/test_engine.py` |
| 1073 | `tests/unit/mcp/test_output_cost_invariants.py` |
| 885 | `tests/unit/test_ast_cache.py` |
| 839 | `tests/unit/mcp/tools/test_class_inspect_tool.py` |
| 820 | `tests/unit/mcp/test_tools/test_get_code_outline_tool.py` |

## Exception Policy

No file has a permanent size exception. These files are tolerated as existing
debt only. When a change adds new behavior to one of them, prefer extracting a
focused test file for that behavior instead of appending more cases.

Acceptable temporary reasons:

- shared golden corpus setup that would become harder to read if split;
- a single behavioral surface with many small parametrized cases;
- migration in progress with a tracked follow-up.

Unacceptable reasons:

- "the file already exists";
- adding one more unrelated regression because imports are convenient;
- preserving duplicate setup that can move into a fixture.
