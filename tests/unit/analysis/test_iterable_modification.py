"""Tests for Iterable Modification in Loop Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.iterable_modification import (
    IterableModificationAnalyzer,
)


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestIterableModificationDetect:
    """Test basic detection of collection modification during iteration."""

    def test_list_remove_in_loop(self) -> None:
        code = """
for x in items:
    items.remove(x)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.loop_variable == "items"
            assert h.method_name == "remove"
            assert h.severity == "medium"
        finally:
            path.unlink()

    def test_list_append_in_loop(self) -> None:
        code = """
for x in data:
    data.append(x)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.method_name == "append"
        finally:
            path.unlink()

    def test_dict_pop_in_loop(self) -> None:
        code = """
for key in my_dict:
    my_dict.pop(key)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.loop_variable == "my_dict"
            assert h.method_name == "pop"
        finally:
            path.unlink()

    def test_set_add_in_loop(self) -> None:
        code = """
for val in my_set:
    my_set.add(val + 1)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.method_name == "add"
        finally:
            path.unlink()

    def test_list_insert_in_loop(self) -> None:
        code = """
for item in items:
    items.insert(0, item)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].method_name == "insert"
        finally:
            path.unlink()

    def test_list_extend_in_loop(self) -> None:
        code = """
for chunk in chunks:
    chunks.extend(chunk)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].method_name == "extend"
        finally:
            path.unlink()

    def test_del_subscript_in_loop(self) -> None:
        code = """
for key in my_dict:
    del my_dict[key]
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            h = result.hotspots[0]
            assert h.method_name == "del"
            assert h.severity == "high"
        finally:
            path.unlink()

    def test_multiple_modifications(self) -> None:
        code = """
for x in items:
    items.remove(x)
    items.append(x * 2)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 2
            methods = {h.method_name for h in result.hotspots}
            assert methods == {"remove", "append"}
        finally:
            path.unlink()

    def test_dict_update_in_loop(self) -> None:
        code = """
for key in config:
    config.update({key: "new"})
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].method_name == "update"
        finally:
            path.unlink()


class TestIterableModificationExclusion:
    """Test cases that should NOT be detected."""

    def test_different_collection(self) -> None:
        code = """
for x in items:
    other.remove(x)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_non_modifying_method(self) -> None:
        code = """
for x in items:
    items.index(x)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_no_loop(self) -> None:
        code = """
items.remove(1)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_nested_loop_different_var(self) -> None:
        """Modifying 'other' while iterating 'items' in outer loop is fine."""
        code = """
for x in items:
    other.remove(x)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_safe_method_on_iterated(self) -> None:
        code = """
for x in items:
    items.sort()
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()


class TestIterableModificationNonPython:
    """Test non-Python files return empty results."""

    def test_javascript_file(self) -> None:
        code = """
for (let x of items) {
    items.push(x);
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()

    def test_nonexistent_file(self) -> None:
        result = IterableModificationAnalyzer().analyze_file("/nonexistent.py")
        assert result.total_hotspots == 0

    def test_empty_file(self) -> None:
        path = _write_tmp("")
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 0
        finally:
            path.unlink()


class TestIterableModificationStructure:
    """Test result structure and to_dict."""

    def test_result_to_dict(self) -> None:
        code = """
for x in items:
    items.remove(x)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            d = result.to_dict()
            assert "total_hotspots" in d
            assert "hotspots" in d
            assert "file_path" in d
            assert d["total_hotspots"] == 1
            h = d["hotspots"][0]
            assert "line_number" in h
            assert "loop_variable" in h
            assert "method_name" in h
            assert "severity" in h
        finally:
            path.unlink()

    def test_hotspot_frozen(self) -> None:
        code = """
for key in d:
    d.pop(key)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            h = result.hotspots[0].to_dict()
            assert isinstance(h["line_number"], int)
            assert isinstance(h["loop_variable"], str)
            assert isinstance(h["method_name"], str)
            assert isinstance(h["severity"], str)
        finally:
            path.unlink()

    def test_line_numbers_correct(self) -> None:
        code = """x = 1
for val in items:
    items.remove(val)
"""
        path = _write_tmp(code)
        try:
            result = IterableModificationAnalyzer().analyze_file(path)
            assert result.total_hotspots == 1
            assert result.hotspots[0].line_number == 3
        finally:
            path.unlink()
