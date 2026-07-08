"""Conftest for Claim Invariant Suite.

Every README claim must have a corresponding CI-gated test in this directory.
Tests are marked @pytest.mark.claims_benchmark and run in a dedicated CI job.

Design rules (CLAUDE.md §11):
- Assert exact values or documented relationships, never hand-waved bounds.
- Use strict=True xfail for claims that are currently not met.
- Emit measured_value so CI history provides regression visibility.
"""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "claims_benchmark: marks a test as a README claim invariant (run in dedicated CI job)",
    )
