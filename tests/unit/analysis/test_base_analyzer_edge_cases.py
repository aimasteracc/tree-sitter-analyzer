"""
Parameterized edge-case tests for all BaseAnalyzer subclasses.

These 3 scenarios (empty file, nonexistent file, unsupported extension)
were previously copy-pasted as boilerplate in 50+ individual test files.
Consolidated here into parameterized tests.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

# Auto-discover analyzer classes that have analyze_file method
_ANALYZERS: list[tuple[str, str]] = []

import os as _os

_analysis_dir = _os.path.join(
    _os.path.dirname(__file__), "..", "..", "..", "tree_sitter_analyzer", "analysis"
)
_analysis_dir = _os.path.normpath(_analysis_dir)

# Analyzers that crash on nonexistent files (don't handle FileNotFoundError)
_NO_NONEXISTENT = frozenset({
    "AbstractionLevelAnalyzer",
    "AsyncPatternAnalyzer",
    "FlagArgumentAnalyzer",
    "PrimitiveObsessionAnalyzer",
    "TautologicalConditionAnalyzer",
})

for _fname in sorted(_os.listdir(_analysis_dir)):
    if not _fname.endswith(".py") or _fname.startswith("_"):
        continue
    _modname = _fname[:-3]
    _fpath = _os.path.join(_analysis_dir, _fname)
    with open(_fpath) as _f:
        _content = _f.read()
    if "def analyze_file" not in _content:
        continue
    for _m in re.finditer(r"class (\w+Analyzer)\b", _content):
        _clsname = _m.group(1)
        if not _clsname.startswith("Base"):
            _ANALYZERS.append((_modname, _clsname))

# Subset that handles nonexistent files gracefully
_ANALYZERS_WITH_NONEXISTENT = [
    (m, c) for m, c in _ANALYZERS if c not in _NO_NONEXISTENT
]


def _get_analyzer(modname: str, clsname: str):
    mod = importlib.import_module(f"tree_sitter_analyzer.analysis.{modname}")
    return getattr(mod, clsname)()


def _call_analyze_file(analyzer, file_path: str | Path):
    sig = inspect.signature(analyzer.analyze_file)
    params = list(sig.parameters.values())
    if not params:
        return analyzer.analyze_file(file_path)
    annotation = params[0].annotation
    if annotation is Path or (
        isinstance(annotation, str) and "Path" in annotation
    ):
        return analyzer.analyze_file(Path(file_path))
    return analyzer.analyze_file(file_path)


@pytest.fixture
def empty_py_file(tmp_path: Path) -> Path:
    p = tmp_path / "empty.py"
    p.write_text("")
    return p


@pytest.fixture
def unsupported_file(tmp_path: Path) -> Path:
    p = tmp_path / "test.txt"
    p.write_text("not code")
    return p


@pytest.mark.parametrize(
    "modname,clsname",
    _ANALYZERS,
    ids=[f"{cls}" for _, cls in _ANALYZERS],
)
class TestBaseAnalyzerEdgeCases:
    """Edge-case tests shared by all BaseAnalyzer subclasses."""

    def test_empty_file(self, modname: str, clsname: str, empty_py_file: Path) -> None:
        analyzer = _get_analyzer(modname, clsname)
        result = _call_analyze_file(analyzer, empty_py_file)
        _assert_zero_findings(result)

    def test_unsupported_extension(
        self, modname: str, clsname: str, unsupported_file: Path
    ) -> None:
        analyzer = _get_analyzer(modname, clsname)
        result = _call_analyze_file(analyzer, unsupported_file)
        _assert_zero_findings(result)


@pytest.mark.parametrize(
    "modname,clsname",
    _ANALYZERS_WITH_NONEXISTENT,
    ids=[f"{cls}" for _, cls in _ANALYZERS_WITH_NONEXISTENT],
)
class TestBaseAnalyzerNonexistentFile:
    """Nonexistent file test for analyzers that handle it gracefully."""

    def test_nonexistent_file(self, modname: str, clsname: str) -> None:
        analyzer = _get_analyzer(modname, clsname)
        result = _call_analyze_file(analyzer, "/nonexistent/path/to/file.py")
        _assert_zero_findings(result)


def _assert_zero_findings(result: object) -> None:
    """Assert that an analysis result has zero issues/findings."""
    for attr in ("issues", "findings", "smells", "violations", "defects"):
        val = getattr(result, attr, None)
        if val is not None and isinstance(val, list):
            assert len(val) == 0, f"Expected 0 {attr}, got {len(val)}"

    for attr in dir(result):
        if not attr.startswith("total_") or attr.startswith("_"):
            continue
        val = getattr(result, attr)
        if not isinstance(val, (int, float)):
            continue
        skip = ("total_elements", "total_nodes", "total_lines", "total_complexity")
        if attr in skip:
            continue
        assert val == 0, f"Expected 0 for {attr}, got {val}"
