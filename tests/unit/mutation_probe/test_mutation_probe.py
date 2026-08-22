#!/usr/bin/env python3
"""Tests for the mutation probe subsystem (RFC-0029).

Test-plan coverage (11 items):
  1. Hoist mutation → does_not_constrain (return value unchanged)
  2. Location-sensitive: same test, different code location → different verdict
  3. Positive controls: at least 3 paths that return constrains
  4. Non-assertion crash → unknown / MUTATED_RUN_CRASHED (not constrains)
  5. Each fail-closed subcode forced: BASELINE_NOT_GREEN, NO_INVERTIBLE_BRANCH,
     NOT_ISOLABLE, MUTATED_RUN_CRASHED, TIMEOUT
  6. Deselected / uncollected node → unknown / NOT_ISOLABLE
  7. Working tree unmodified after any probe call (byte-identical digest)
  8. Relative imports survive mutation (no ImportError → not MUTATED_RUN_CRASHED)
  9. Structural: no os.fork, no mutmut references in the package
 10. False-negative profile: documented defect kinds NOT detected by the 5-mutation set
 11. Latency budget: completes within 60 s; response carries timing fields
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from tree_sitter_analyzer.mutation_probe import probe
from tree_sitter_analyzer.mutation_probe.engine import (
    apply_mutation,
)
from tree_sitter_analyzer.mutation_probe.runner import (
    _classify,
    _parse_exception_type,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_PROJECT_ROOT = str(Path(__file__).parents[3])


def _loc(fixture_file: str, lineno: int) -> str:
    """Build a code_location string relative to project root (forward slashes)."""
    return f"tests/unit/mutation_probe/fixtures/{fixture_file}:{lineno}"


def _nid(probe_file: str, test_name: str) -> str:
    """Build a pytest node id (forward slashes — works on all platforms)."""
    return f"tests/unit/mutation_probe/fixtures/{probe_file}::{test_name}"


# ---------------------------------------------------------------------------
# Engine unit tests (fast, no subprocess)
# ---------------------------------------------------------------------------


def test_engine_hoist_mutation_applied() -> None:
    src = (
        b"def f():\n"
        b"    class _C:\n"
        b"        def __enter__(self): return self\n"
        b"        def __exit__(self, *a): return False\n"
        b"    with _C():\n"
        b"        x = 1\n"
        b"        y = 2\n"
        b"    return x\n"
    )
    result = apply_mutation(src, lineno=5)
    assert result is not None
    assert "hoist" in result.description.lower()
    assert result.mutation_kind == "_HoistMutator"


def test_engine_invert_condition_applied() -> None:
    src = b"def f(x):\n    if x > 0:\n        return 1\n    return 0\n"
    result = apply_mutation(src, lineno=2)
    assert result is not None
    assert result.mutation_kind == "_InvertConditionMutator"
    assert b"not" in result.mutated_bytes


def test_engine_flip_comparison_applied() -> None:
    # A Compare node with no surrounding If (bare expression); the
    # _FlipComparisonMutator fires on Compare nodes, not If nodes.
    src = b"x = 1\ny = x == 0\n"
    result = apply_mutation(src, lineno=2)
    assert result is not None
    assert result.mutation_kind == "_FlipComparisonMutator"
    assert b"!=" in result.mutated_bytes


def test_engine_negate_boolean_return_applied() -> None:
    src = b"def f():\n    return True\n"
    result = apply_mutation(src, lineno=2)
    assert result is not None
    assert result.mutation_kind == "_NegateBooleanReturnMutator"
    assert b"False" in result.mutated_bytes


def test_engine_drop_kwarg_applied() -> None:
    src = b"def f():\n    open('x', newline='')\n"
    result = apply_mutation(src, lineno=2)
    assert result is not None
    assert result.mutation_kind == "_DropKeywordArgMutator"
    assert b"newline" not in result.mutated_bytes


def test_engine_returns_none_when_no_mutation_applicable() -> None:
    # A plain assignment has no applicable mutation.
    src = b"x = 42\n"
    result = apply_mutation(src, lineno=1)
    assert result is None


def test_engine_mutated_bytes_are_valid_python() -> None:
    src = b"def f(x):\n    if x > 0:\n        return True\n    return False\n"
    result = apply_mutation(src, lineno=2)
    assert result is not None
    decoded = result.mutated_bytes.decode("utf-8")
    # compile() raises SyntaxError on invalid Python; this is the primary check.
    compile(decoded, "<test>", "exec")
    # Mutation must produce bytes that differ from the original source.
    assert result.mutated_bytes != src


# ---------------------------------------------------------------------------
# Runner unit tests (test output parsing, no subprocess)
# ---------------------------------------------------------------------------


def test_runner_exit_0_is_none() -> None:
    assert _classify(0, "") == "NONE"


def test_runner_exit_4_is_not_run() -> None:
    assert _classify(4, "") == "NOT_RUN"


def test_runner_exit_5_is_not_run() -> None:
    assert _classify(5, "") == "NOT_RUN"


def test_runner_assertion_error_in_output_is_assertion() -> None:
    output = "FAILED test_x\nE   AssertionError: expected 1, got 2\n"
    assert _parse_exception_type(output) == "ASSERTION"


def test_runner_failed_in_output_is_assertion() -> None:
    # pytest.fail() raises _pytest.outcomes.Failed, shown as "Failed"
    output = "FAILED test_x\nE   Failed: assert True\n"
    assert _parse_exception_type(output) == "ASSERTION"


def test_runner_rewritten_assert_is_assertion() -> None:
    # pytest assertion rewriting shows "E   assert X == Y" (no "AssertionError:")
    output = "FAILED test_x\nE   assert 0 == 10\nE    +  where 0 = _private(5)\n"
    assert _parse_exception_type(output) == "ASSERTION"


def test_runner_name_error_in_output_is_non_assertion() -> None:
    output = "FAILED test_x\nE   NameError: name 'x' is not defined\n"
    assert _parse_exception_type(output) == "NON_ASSERTION"


def test_runner_import_error_in_output_is_non_assertion() -> None:
    output = "FAILED test_x\nE   ImportError: cannot import name 'foo'\n"
    assert _parse_exception_type(output) == "NON_ASSERTION"


def test_runner_exit_2_is_non_assertion() -> None:
    # Exit code 2 = pytest internal error / collection error → non-assertion crash
    assert _classify(2, "") == "NON_ASSERTION"


# ---------------------------------------------------------------------------
# Item 1: Hoist mutation → does_not_constrain
#
# The hoist moves `value = _work()` before `with tracker:`.  The function
# still returns 42, so `assert compute() == 42` passes → does_not_constrain.
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_1_hoist_does_not_constrain() -> None:
    result = probe(
        test_node_id=_nid("_probe_hoist.py", "test_compute_returns_42"),
        code_location=_loc("hoist_target.py", 21),  # the `with tracker:` line
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "does_not_constrain"
    assert result.reason == "MUTATED_RUN_PASSED"
    assert result.baseline_failure == "NONE"
    assert result.mutated_failure == "NONE"


# ---------------------------------------------------------------------------
# Item 2: Location-sensitive
#
# test_private_returns_double calls _private(5) directly.
# - Probing _private's condition (line 11) → constrains
# - Probing public_dispatch's condition (line 17) → does_not_constrain
#   because public_dispatch is never called by the test.
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_2a_private_location_constrains() -> None:
    result = probe(
        test_node_id=_nid("_probe_dispatch.py", "test_private_returns_double"),
        code_location=_loc("dispatch_target.py", 11),  # `if x == 0:` in _private
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "constrains"
    assert result.reason is None
    assert result.mutated_failure == "ASSERTION"


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_2b_dispatch_location_does_not_constrain() -> None:
    result = probe(
        test_node_id=_nid("_probe_dispatch.py", "test_private_returns_double"),
        code_location=_loc("dispatch_target.py", 17),  # `if x > 0:` in public_dispatch
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "does_not_constrain"
    assert result.reason == "MUTATED_RUN_PASSED"


# ---------------------------------------------------------------------------
# Item 3: Positive controls (at least 3 paths → constrains)
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_3a_negate_return_constrains() -> None:
    # `return True` → `return False`; is_positive(5) returns False.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_is_positive_true"),
        code_location=_loc("bool_target.py", 10),  # `return True`
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "constrains"
    assert result.mutated_failure == "ASSERTION"


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_3b_invert_condition_constrains() -> None:
    # `if x > 0:` → `if not (x > 0):`; is_positive(-1) returns True instead of False.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_is_positive_false"),
        code_location=_loc("bool_target.py", 9),  # `if x > 0:`
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "constrains"
    assert result.mutated_failure == "ASSERTION"


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_3c_invert_zero_check_constrains() -> None:
    # `if b == 0:` → `if not (b == 0):`; divide(10,2) returns None instead of 5.0.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 15),  # `if b == 0:`
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "constrains"
    assert result.mutated_failure == "ASSERTION"


# ---------------------------------------------------------------------------
# Item 4: Non-assertion crash → unknown / MUTATED_RUN_CRASHED
#
# Hoist moves `path = _make(name)` before `with _Ctx() as name:`, causing
# NameError.  A crash is not detection — verdict must be unknown, not constrains.
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_4_non_assertion_crash_is_not_constrains() -> None:
    result = probe(
        test_node_id=_nid("_probe_crash.py", "test_get_bound_is_str"),
        code_location=_loc("crash_target.py", 18),  # `with _Ctx() as name:`
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "MUTATED_RUN_CRASHED"
    assert result.mutated_failure == "NON_ASSERTION"


# ---------------------------------------------------------------------------
# Item 5: Each fail-closed subcode forced
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_5_baseline_not_green() -> None:
    result = probe(
        test_node_id=_nid("_probe_always_fails.py", "test_always_fails"),
        code_location=_loc("bool_target.py", 9),  # valid mutation location
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "BASELINE_NOT_GREEN"
    assert result.baseline_failure == "ASSERTION"


def test_plan_5_no_invertible_branch() -> None:
    # `return a / b` at line 17 is a BinOp return — no mutation in the closed
    # set applies (not boolean, no comparison, no With/Try, no keyword arg).
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 17),  # `return a / b`
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "NO_INVERTIBLE_BRANCH"


@pytest.mark.slow_ok  # spawns 1 pytest subprocess (~10-15 s on Windows)
@pytest.mark.timeout(30)
def test_plan_5_not_isolable_nonexistent_node() -> None:
    # A non-existent test node id causes pytest exit code 5 → NOT_RUN → NOT_ISOLABLE.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_does_not_exist_xyz"),
        code_location=_loc("bool_target.py", 9),  # valid mutation location
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "NOT_ISOLABLE"
    assert result.baseline_failure == "NOT_RUN"


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_5_mutated_run_crashed_is_unknown() -> None:
    # Duplicate path already covered by item 4; assert the subcode explicitly.
    result = probe(
        test_node_id=_nid("_probe_crash.py", "test_get_bound_is_str"),
        code_location=_loc("crash_target.py", 18),
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "MUTATED_RUN_CRASHED"


def test_plan_5_timeout_returns_unknown() -> None:
    # timeout=0.001 s forces TimeoutExpired on the baseline subprocess call.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 9),
        project_root=_PROJECT_ROOT,
        timeout=0.001,
    )
    assert result.verdict == "unknown"
    assert result.reason == "TIMEOUT"


# ---------------------------------------------------------------------------
# Item 6: Uncollected node returns NOT_ISOLABLE
#
# Specifying a node id that does not exist is the primary NOT_ISOLABLE path.
# The "collected count == 1" invariant is satisfied for any successful probe
# call that returns a definitive verdict (constrains / does_not_constrain) —
# pytest only returns a definitive outcome when exactly one test ran.
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 1 pytest subprocess (~10-15 s on Windows)
@pytest.mark.timeout(30)
def test_plan_6_uncollected_node_is_not_isolable() -> None:
    result = probe(
        test_node_id="tests/unit/mutation_probe/fixtures/_probe_bool.py::no_such_test",
        code_location=_loc("bool_target.py", 9),
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "NOT_ISOLABLE"


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_6_valid_node_yields_definitive_verdict() -> None:
    # A good node id produces a definitive result, proving exactly 1 test ran.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 15),
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict in ("constrains", "does_not_constrain")


# ---------------------------------------------------------------------------
# Item 7: Working tree is byte-identical after a probe call
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_7_working_tree_unmodified() -> None:
    target = _FIXTURE_DIR / "hoist_target.py"
    before_digest = hashlib.md5(target.read_bytes()).hexdigest()

    probe(
        test_node_id=_nid("_probe_hoist.py", "test_compute_returns_42"),
        code_location=_loc("hoist_target.py", 21),
        project_root=_PROJECT_ROOT,
    )

    after_digest = hashlib.md5(target.read_bytes()).hexdigest()
    assert before_digest == after_digest


# ---------------------------------------------------------------------------
# Item 8: Relative imports survive mutation (no ImportError)
#
# rel_import_target.py uses `from . import rel_import_helper`.  After
# mutation and ast.unparse(), the relative import must still resolve.
# If it raised ImportError, the result would be MUTATED_RUN_CRASHED — but
# the probe must return ``constrains`` because the InvertCondition mutation
# changes compute(2)'s return value from 42 to 0.
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_8_relative_imports_survive_mutation() -> None:
    result = probe(
        test_node_id=_nid("_probe_rel_import.py", "test_compute_rel_import"),
        code_location=_loc("rel_import_target.py", 11),  # `if x > 0:`
        project_root=_PROJECT_ROOT,
    )
    # Must be constrains — if relative import broke, result would be MUTATED_RUN_CRASHED.
    assert result.verdict == "constrains"
    assert result.mutated_failure == "ASSERTION"


# ---------------------------------------------------------------------------
# Item 9: Structural — no os.fork, no mutmut references (all-OS requirement)
# ---------------------------------------------------------------------------


def test_plan_9_no_os_fork_in_package() -> None:
    # Check for actual call site usage, not documentation mentions.
    # "os.fork(" is a function call; a comment saying "no os.fork" is fine.
    pkg_dir = Path(_PROJECT_ROOT) / "tree_sitter_analyzer" / "mutation_probe"
    for py_file in sorted(pkg_dir.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        assert "os.fork(" not in source, f"os.fork() call found in {py_file.name}"


def test_plan_9_no_mutmut_in_package() -> None:
    # Verify mutmut is not imported or used as a dependency.
    # Check at the AST level: no import of mutmut as a module.
    pkg_dir = Path(_PROJECT_ROOT) / "tree_sitter_analyzer" / "mutation_probe"
    for py_file in sorted(pkg_dir.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "mutmut", f"import mutmut in {py_file.name}"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "mutmut", (
                    f"from mutmut import in {py_file.name}"
                )


# ---------------------------------------------------------------------------
# Item 10: False-negative profile
#
# The 5-mutation closed set cannot detect every defect category.  This test
# documents which defect kinds are NOT detected by asserting NO_INVERTIBLE_BRANCH
# for lines that only contain undetectable constructs.
# ---------------------------------------------------------------------------


def test_plan_10_arithmetic_magnitude_not_detected() -> None:
    # `return a / b` at line 17: no member of the 5-mutation set applies.
    # Arithmetic magnitude changes (+1, -1, *2, /2) are false negatives.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 17),  # `return a / b`
        project_root=_PROJECT_ROOT,
    )
    assert result.verdict == "unknown"
    assert result.reason == "NO_INVERTIBLE_BRANCH"


def test_plan_10_wrong_variable_not_detected() -> None:
    # A plain variable assignment has no applicable mutation in the closed set.
    # Wrong-variable substitutions (a vs b) are false negatives.
    src = b"x = 1\ny = x\n"
    mutation_result = apply_mutation(src, lineno=2)
    # Verify the engine itself returns None (no mutation applicable)
    assert mutation_result is None


# ---------------------------------------------------------------------------
# Item 11: Latency budget — completes within 60 s; carries timing fields
# ---------------------------------------------------------------------------


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_11_timing_fields_are_floats() -> None:
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 15),
        project_root=_PROJECT_ROOT,
    )
    assert isinstance(result.baseline_ms, float)
    assert isinstance(result.mutated_ms, float)
    assert isinstance(result.overhead_ms, float)


@pytest.mark.slow_ok  # spawns 2 pytest subprocesses (~15-30 s each on Windows)
@pytest.mark.timeout(120)
def test_plan_11_both_runs_within_60s_budget() -> None:
    # RFC-0029 SLA: each individual run is at most 60 s.
    result = probe(
        test_node_id=_nid("_probe_bool.py", "test_divide_basic"),
        code_location=_loc("bool_target.py", 15),
        project_root=_PROJECT_ROOT,
    )
    assert result.baseline_ms < 60000.0
    assert result.mutated_ms < 60000.0
