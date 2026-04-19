"""Tests for Concurrency Safety Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.concurrency_safety import (
    ISSUE_CHECK_THEN_ACT,
    ISSUE_MISSING_SYNC,
    ISSUE_SHARED_MUTABLE,
    ConcurrencySafetyAnalyzer,
)

ANALYZER = ConcurrencySafetyAnalyzer()


class TestPythonConcurrency:
    def test_missing_sync(self, tmp_path: Path) -> None:
        code = (
            "from threading import Thread\n"
            "\n"
            "def worker():\n"
            "    pass\n"
            "\n"
            "Thread(target=worker).start()\n"
        )
        f = tmp_path / "nosync.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_MISSING_SYNC for i in result.issues)

    def test_check_then_act(self, tmp_path: Path) -> None:
        code = (
            "if cache == None:\n"
            "    cache = {}\n"
        )
        f = tmp_path / "race.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_CHECK_THEN_ACT for i in result.issues)

    def test_clean_code(self, tmp_path: Path) -> None:
        code = (
            "def compute(x, y):\n"
            "    return x + y\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestJavaConcurrency:
    def test_shared_mutable_java(self, tmp_path: Path) -> None:
        code = (
            "public class Worker implements Runnable {\n"
            "  private List<String> items = new ArrayList<>();\n"
            "  public void run() {\n"
            "    items.add(\"hello\");\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Worker.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_SHARED_MUTABLE for i in result.issues)
