"""Probe test: always-failing baseline (RFC-0029 item 5, BASELINE_NOT_GREEN).

This test always fails, so any probe using it as the test node id must return
unknown / BASELINE_NOT_GREEN because the baseline run is not green.
"""


def test_always_fails() -> None:
    assert 1 == 2  # noqa: PLR0133
