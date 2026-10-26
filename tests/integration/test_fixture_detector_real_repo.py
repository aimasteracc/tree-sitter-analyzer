"""Whole-repository canary for the feedback_test-fixture-files incident.

``java_plugin.py`` IS a negative fixture in this repository, and the detector
must flag it UNSAFE-grade, or agents refactor it again and re-burn a session.

The unit test ``tests/unit/security/test_fixture_detector_canary.py::
TestRealRepoRegression`` pins the same behaviour on a small tree that copies
the deciding shapes. This test keeps the canary on the real repository. It
scans every test file (~7 s locally, past 30 s on a loaded macOS runner,
CI run 40255714163), so it is an integration test: outside the unit time
budget (#1779: unit tests do not scan the real repo) and with its own
timeout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.security.fixture_detector import is_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.timeout(180)
def test_real_repo_finds_java_plugin() -> None:
    target = "tree_sitter_analyzer/languages/java_plugin.py"
    fact = is_fixture(target, REPO_ROOT)
    assert fact.is_fixture is True, (
        f"Real-repo detection failed for {target}; got {fact!r}. "
        "This is the canary for feedback_test-fixture-files."
    )
    assert fact.confidence == 0.85
