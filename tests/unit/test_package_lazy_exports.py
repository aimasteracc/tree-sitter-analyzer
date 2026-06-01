"""Top-level package lazy-export contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_top_level_import_does_not_preload_heavy_analysis_modules() -> None:
    script = (
        "import sys, tree_sitter_analyzer; "
        "print('tree_sitter_analyzer.core.analysis_engine' in sys.modules); "
        "print('tree_sitter_analyzer.output_manager' in sys.modules)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )

    assert result.stdout.splitlines() == ["False", "False"]


def test_lazy_export_resolves_and_caches_public_name() -> None:
    import tree_sitter_analyzer as tsa

    tsa.__dict__.pop("Function", None)

    function_cls = tsa.Function

    assert function_cls.__name__ == "Function"
    assert tsa.__dict__["Function"] is function_cls


def test_lazy_export_unknown_name_raises_attribute_error() -> None:
    import tree_sitter_analyzer as tsa

    missing = "DefinitelyMissing"
    with pytest.raises(AttributeError, match="DefinitelyMissing"):
        getattr(tsa, missing)
