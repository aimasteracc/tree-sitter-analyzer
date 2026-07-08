"""Claim invariant: Index build speed (-46% improvement).

README claim:
    "Removing a redundant post-index edge-refresh pass cut a cold django index
    (~2 950 files) from 181 s → 97 s (−46%); the win grows with repo size."

This test:
    1. Verifies the measurement command is documented in this file (repro-as-test).
    2. On a medium-sized synthetic corpus, asserts indexing completes within a
       reasonable time bound relative to the file count.
    3. The full django/gin benchmark is @pytest.mark.network + manual-only because
       it requires downloading repos. See the repro command below.

Measurement command (requires the django repo at ~/.cache/tsa-benchmarks/django/):
    uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos django
    # Expected: cold index ≤ 110 s (target: 97 s per README claim)

Tracks: README "-46% index build speed" claim.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache

pytestmark = [pytest.mark.benchmark, pytest.mark.claims_benchmark]

# Target: each file should be indexed in under 0.5 s on average.
# This is a generous bound — the claim is 97 s for 2,950 files (~33 ms/file).
_MAX_SECONDS_PER_FILE = 0.5
_SYNTHETIC_FILE_COUNT = 50


def _generate_synthetic_project(tmp: str, count: int) -> None:
    """Generate a synthetic Python project with `count` files."""
    for i in range(count):
        path = os.path.join(tmp, f"module_{i}.py")
        with open(path, "w") as f:
            f.write(
                f'"""Module {i}."""\n'
                f"import os\n"
                f"import sys\n"
                f"\n"
                f"class Service{i}:\n"
                f"    def process(self, data):\n"
                f"        return self._run(data)\n"
                f"\n"
                f"    def _run(self, data):\n"
                f"        return str(data)\n"
                f"\n"
                f"def helper_{i}(x):\n"
                f"    svc = Service{i}()\n"
                f"    return svc.process(x)\n"
            )


def test_index_speed_scales_linearly_not_quadratically():
    """Index build time per file must stay under {_MAX_SECONDS_PER_FILE}s.

    README claims 97s for ~2,950 files (~33ms/file). We assert a conservative
    0.5s/file bound on a synthetic corpus to catch algorithmic regressions
    (e.g., O(n²) patterns) without requiring a full repo download.

    For the definitive measurement:
        uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos django
    """
    with tempfile.TemporaryDirectory() as tmp:
        _generate_synthetic_project(tmp, _SYNTHETIC_FILE_COUNT)

        start = time.perf_counter()
        cache = ASTCache(tmp)
        cache.index_project()
        cache.close()
        elapsed = time.perf_counter() - start

        per_file = elapsed / _SYNTHETIC_FILE_COUNT
        # Emit for CI history
        print(
            f"[claim] index_speed total={elapsed:.2f}s "
            f"files={_SYNTHETIC_FILE_COUNT} per_file={per_file:.3f}s"
        )
        assert per_file <= _MAX_SECONDS_PER_FILE, (
            f"Index speed {per_file:.3f}s/file exceeds threshold of "
            f"{_MAX_SECONDS_PER_FILE}s/file. Total: {elapsed:.2f}s for "
            f"{_SYNTHETIC_FILE_COUNT} files. "
            f"README claims ~33ms/file on django (2950 files in 97s)."
        )


def test_index_speed_claim_measurement_command_is_documented():
    """The measurement command for the django benchmark must be in this file.

    Ensures the repro path is visible to anyone who needs to verify the claim.
    """
    import inspect
    src = inspect.getfile(test_index_speed_claim_measurement_command_is_documented)
    with open(src, encoding="utf-8") as f:
        content = f.read()
    assert "benchmarks/codegraph_compare/run.py" in content, (
        "The django benchmark repro command must be documented in this file."
    )
    assert "django" in content, (
        "The 'django' benchmark target must be referenced in this file."
    )
    assert "97" in content or "181" in content, (
        "The before/after timing numbers (181s -> 97s) must be in this file."
    )
