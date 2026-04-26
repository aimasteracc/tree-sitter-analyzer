"""Tests for Null Safety Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.null_safety import (
    ISSUE_DICT_UNSAFE_ACCESS,
    ISSUE_UNCHECKED_ACCESS,
    NullSafetyAnalyzer,
)

ANALYZER = NullSafetyAnalyzer()


class TestPythonNullSafety:
    def test_unchecked_none_access(self, tmp_path: Path) -> None:
        code = (
            "def process():\n"
            "    data = None\n"
            "    result = data.strip()\n"
        )
        f = tmp_path / "none.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues >= 1
        assert any(i.issue_type == ISSUE_UNCHECKED_ACCESS for i in result.issues)

    def test_dict_unsafe_access(self, tmp_path: Path) -> None:
        code = (
            "def process(config):\n"
            "    val = config['key']\n"
            "    return val\n"
        )
        f = tmp_path / "dict.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_DICT_UNSAFE_ACCESS for i in result.issues)

    def test_safe_none_check(self, tmp_path: Path) -> None:
        code = (
            "def process():\n"
            "    data = None\n"
            "    if data is not None:\n"
            "        result = data.strip()\n"
        )
        f = tmp_path / "safe.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert not any(i.issue_type == ISSUE_UNCHECKED_ACCESS for i in result.issues)

    def test_clean_code(self, tmp_path: Path) -> None:
        code = (
            "def greet(name: str) -> str:\n"
            "    return f'Hello {name}'\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0
