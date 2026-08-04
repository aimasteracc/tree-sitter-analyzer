"""Behavioral tests for the Windows degraded-runner classifier."""

from scripts.classify_windows_pytest_failure import classify


def test_budget_only_failures_are_retry_eligible() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "FAILED tests/unit/test_b.py::test_b - Failed: Unit test exceeded "
        "per-test budget: 9.10s > 8.0s.\n"
    )

    assert classify(output) == {
        "retry_eligible": True,
        "nodeids": ["tests/unit/test_a.py::test_a", "tests/unit/test_b.py::test_b"],
        "failure_count": 2,
        "reason": "budget_only",
    }


def test_assertion_failure_blocks_retry() -> None:
    output = "FAILED tests/unit/test_a.py::test_a - AssertionError: wrong value\n"

    assert classify(output) == {
        "retry_eligible": False,
        "nodeids": [],
        "failure_count": 1,
        "reason": "non_budget_or_unclassified",
    }


def test_mixed_failures_block_retry() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "FAILED tests/unit/test_b.py::test_b - RuntimeError: boom\n"
    )

    assert classify(output)["retry_eligible"] is False


def test_collection_error_blocks_retry() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "ERROR tests/unit/test_b.py - ImportError: missing dependency\n"
    )

    assert classify(output)["retry_eligible"] is False
