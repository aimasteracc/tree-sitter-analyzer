"""Tests for Dict Merge in Loop Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.dict_merge_loop import (
    DictMergeLoopAnalyzer,
)


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestDictMergeLoopDetect:
    """Test basic detection of dict key assignment in loops."""

    def test_for_loop_subscript_assign(self) -> None:
        code = """
for k, v in items:
    d[k] = v
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.dict_variable == "d"
            assert h.loop_type == "for"
            assert h.severity == "medium"
        finally:
            path.unlink()

    def test_while_loop_subscript_assign(self) -> None:
        code = """
while cond:
    result[key] = value
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.dict_variable == "result"
            assert h.loop_type == "while"
        finally:
            path.unlink()

    def test_multiple_assigns_in_loop(self) -> None:
        code = """
for item in data:
    mapping[item.id] = item
    cache[item.name] = item.value
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 2
            vars_found = {h.dict_variable for h in result.hotspots}
            assert vars_found == {"mapping", "cache"}
        finally:
            path.unlink()

    def test_nested_loop_high_severity(self) -> None:
        code = """
for row in rows:
    for col in cols:
        matrix[row] = col
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].severity == "high"
        finally:
            path.unlink()

    def test_attribute_subscript(self) -> None:
        code = """
for item in items:
    self.data[item] = item.value
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].dict_variable == "self.data"
        finally:
            path.unlink()


class TestDictMergeLoopExclusion:
    """Test cases that should NOT be detected."""

    def test_regular_assign(self) -> None:
        code = """
for item in items:
    x = item
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_no_loop(self) -> None:
        code = """
d[key] = value
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_dict_update_call(self) -> None:
        code = """
for chunk in chunks:
    d.update(chunk)
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_augmented_assign(self) -> None:
        """Augmented assignment on dict is not subscript assign."""
        code = """
for item in items:
    d[item] += 1
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()


class TestDictMergeLoopNonPython:
    """Test non-Python files return empty results."""

    def test_javascript_file(self) -> None:
        code = """
for (let item of items) {
    d[item] = item;
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_nonexistent_file(self) -> None:
        result = DictMergeLoopAnalyzer().analyze_file("/nonexistent.py")
        assert result.total_hotspots == 0

    def test_empty_file(self) -> None:
        path = _write_tmp("")
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()


class TestDictMergeLoopStructure:
    """Test result structure and to_dict."""

    def test_result_to_dict(self) -> None:
        code = """
for k, v in items:
    d[k] = v
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            d = result.to_dict()
            assert "total_hotspots" in d
            assert "hotspots" in d
            assert "file_path" in d
            assert d["total_hotspots"] == 1
            h = d["hotspots"][0]
            assert "line_number" in h
            assert "loop_type" in h
            assert "dict_variable" in h
            assert "severity" in h
        finally:
            path.unlink()

    def test_hotspot_to_dict(self) -> None:
        code = """
for item in data:
    mapping[item] = item
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            h = result.hotspots[0].to_dict()
            assert isinstance(h["line_number"], int)
            assert isinstance(h["loop_type"], str)
            assert isinstance(h["dict_variable"], str)
            assert isinstance(h["severity"], str)
        finally:
            path.unlink()

    def test_line_numbers_correct(self) -> None:
        code = """x = 1
for item in items:
    d[item] = item.value
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].line_number == 3
        finally:
            path.unlink()

    def test_frozen_result(self) -> None:
        code = """
for k, v in items:
    d[k] = v
"""
        path = _write_tmp(code)
        try:
            result = DictMergeLoopAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            d = result.to_dict()
            assert d["total_hotspots"] == 1
        finally:
            path.unlink()
