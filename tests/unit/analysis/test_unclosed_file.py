"""Tests for Unclosed File Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.unclosed_file import (
    UnclosedFileAnalyzer,
)


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestUnclosedFileDetect:
    """Test basic detection of open() without with."""

    def test_simple_open(self) -> None:
        code = """
f = open("file.txt")
data = f.read()
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.variable == "f"
            assert h.severity == "medium"
        finally:
            path.unlink()

    def test_open_with_mode(self) -> None:
        code = """
log = open("log.txt", "w")
log.write("hello")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].variable == "log"
        finally:
            path.unlink()

    def test_multiple_opens(self) -> None:
        code = """
f1 = open("a.txt")
f2 = open("b.txt")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 2
            vars_found = {h.variable for h in result.hotspots}
            assert vars_found == {"f1", "f2"}
        finally:
            path.unlink()

    def test_open_in_function(self) -> None:
        code = """
def read_config():
    config = open("config.yaml")
    return config.read()
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].variable == "config"
        finally:
            path.unlink()


class TestUnclosedFileExclusion:
    """Test cases that should NOT be detected."""

    def test_with_statement(self) -> None:
        code = """
with open("file.txt") as f:
    data = f.read()
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_non_open_call(self) -> None:
        code = """
f = SomeClass("file.txt")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_open_not_assigned(self) -> None:
        """open() without assignment is a different issue (unused result)."""
        code = """
open("file.txt")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_open_in_with_clause(self) -> None:
        code = """
with open("a.txt") as f1, open("b.txt") as f2:
    pass
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()


class TestUnclosedFileNonPython:
    """Test non-Python files return empty results."""

    def test_javascript_file(self) -> None:
        code = """
const f = fs.openSync("file.txt");
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_nonexistent_file(self) -> None:
        result = UnclosedFileAnalyzer().analyze_file("/nonexistent.py")
        assert result.total_hotspots == 0

    def test_empty_file(self) -> None:
        path = _write_tmp("")
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()


class TestUnclosedFileStructure:
    """Test result structure and to_dict."""

    def test_result_to_dict(self) -> None:
        code = """
f = open("file.txt")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            d = result.to_dict()
            assert "total_hotspots" in d
            assert "hotspots" in d
            assert "file_path" in d
            assert d["total_hotspots"] == 1
            h = d["hotspots"][0]
            assert "line_number" in h
            assert "variable" in h
            assert "severity" in h
        finally:
            path.unlink()

    def test_hotspot_frozen(self) -> None:
        code = """
f = open("data.json")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            h = result.hotspots[0].to_dict()
            assert isinstance(h["line_number"], int)
            assert isinstance(h["variable"], str)
            assert isinstance(h["severity"], str)
        finally:
            path.unlink()

    def test_line_numbers_correct(self) -> None:
        code = """x = 1
y = 2
f = open("file.txt")
"""
        path = _write_tmp(code)
        try:
            result = UnclosedFileAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].line_number == 3
        finally:
            path.unlink()
