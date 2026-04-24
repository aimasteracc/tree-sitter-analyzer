"""Tests for Encapsulation Break Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.encapsulation_break import (
    EncapsulationBreakAnalyzer,
    ISSUE_PRIVATE_STATE_EXPOSURE,
    ISSUE_STATE_EXPOSURE,
)


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestPythonStateExposure:
    """Test Python encapsulation break detection."""

    def test_return_list_field(self) -> None:
        code = """
class Cache:
    def __init__(self):
        self.items = []

    def get_items(self):
        return self.items
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            issue = result.issues[0]
            assert issue.issue_type == ISSUE_STATE_EXPOSURE
            assert issue.method_name == "get_items"
            assert issue.field_name == "self.items"
            assert issue.severity == "medium"
        finally:
            path.unlink()

    def test_return_dict_field(self) -> None:
        code = """
class Config:
    def __init__(self):
        self.data = {}

    def get_data(self):
        return self.data
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            assert result.issues[0].field_name == "self.data"
        finally:
            path.unlink()

    def test_return_set_field(self) -> None:
        code = """
class Registry:
    def __init__(self):
        self.entries = set()

    def get_entries(self):
        return self.entries
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            assert result.issues[0].field_name == "self.entries"
        finally:
            path.unlink()

    def test_return_private_field(self) -> None:
        code = """
class Store:
    def __init__(self):
        self._cache = {}

    def cache(self):
        return self._cache
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            issue = result.issues[0]
            assert issue.issue_type == ISSUE_PRIVATE_STATE_EXPOSURE
            assert issue.severity == "low"
        finally:
            path.unlink()

    def test_return_list_constructor(self) -> None:
        code = """
class Queue:
    def __init__(self):
        self.pending = list()

    def get_pending(self):
        return self.pending
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
        finally:
            path.unlink()

    def test_return_comprehension_field(self) -> None:
        code = """
class Filter:
    def __init__(self):
        self.active = [x for x in range(10)]

    def get_active(self):
        return self.active
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
        finally:
            path.unlink()

    def test_no_exposure_immutable_field(self) -> None:
        code = """
class User:
    def __init__(self):
        self.name = "Alice"

    def get_name(self):
        return self.name
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()

    def test_no_exposure_tuple_field(self) -> None:
        code = """
class Point:
    def __init__(self):
        self.coords = (0, 0)

    def get_coords(self):
        return self.coords
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()

    def test_no_exposure_no_return(self) -> None:
        code = """
class Counter:
    def __init__(self):
        self.counts = {}

    def increment(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()

    def test_no_exposure_nonexistent_file(self) -> None:
        result = EncapsulationBreakAnalyzer().analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_field_assigned_in_method(self) -> None:
        code = """
class Service:
    def setup(self):
        self._buffers = []

    def get_buffers(self):
        return self._buffers
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            assert result.issues[0].field_name == "self._buffers"
        finally:
            path.unlink()

    def test_bytearray_field(self) -> None:
        code = """
class Buffer:
    def __init__(self):
        self.data = bytearray()

    def get_data(self):
        return self.data
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
        finally:
            path.unlink()

    def test_dict_comprehension_field(self) -> None:
        code = """
class Lookup:
    def __init__(self):
        self.mapping = {k: v for k, v in [("a", 1)]}

    def get_mapping(self):
        return self.mapping
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
        finally:
            path.unlink()


class TestJSStateExposure:
    """Test JavaScript/TypeScript encapsulation break detection."""

    def test_return_array_field_js(self) -> None:
        code = """
class Cache {
    constructor() {
        this.items = [];
    }
    getItems() {
        return this.items;
    }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            assert result.issues[0].field_name == "this.items"
        finally:
            path.unlink()

    def test_return_map_field_ts(self) -> None:
        code = """
class Store {
    constructor() {
        this._data = new Map();
    }
    getData() {
        return this._data;
    }
}
"""
        path = _write_tmp(code, suffix=".ts")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            assert result.issues[0].field_name == "this._data"
        finally:
            path.unlink()

    def test_no_exposure_string_field(self) -> None:
        code = """
class User {
    constructor() {
        this.name = "Alice";
    }
    getName() {
        return this.name;
    }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()

    def test_return_object_field(self) -> None:
        code = """
class Config {
    constructor() {
        this.settings = {};
    }
    getSettings() {
        return this.settings;
    }
}
"""
        path = _write_tmp(code, suffix=".js")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
        finally:
            path.unlink()


class TestJavaStateExposure:
    """Test Java encapsulation break detection."""

    def test_return_arraylist_field(self) -> None:
        code = """
import java.util.ArrayList;

public class Service {
    private ArrayList<String> items = new ArrayList<>();

    public ArrayList<String> getItems() {
        return this.items;
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            assert result.issues[0].field_name == "this.items"
        finally:
            path.unlink()

    def test_return_hashmap_field(self) -> None:
        code = """
import java.util.HashMap;

public class Config {
    private HashMap<String, String> data = new HashMap<>();

    public HashMap<String, String> getData() {
        return this.data;
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
        finally:
            path.unlink()

    def test_no_exposure_string_field(self) -> None:
        code = """
public class User {
    private String name = "Alice";

    public String getName() {
        return this.name;
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()


class TestEdgeCases:
    """Test edge cases for encapsulation break detection."""

    def test_no_class(self) -> None:
        code = """
def hello():
    return "world"
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()

    def test_unsupported_extension(self) -> None:
        code = "x = 1"
        path = _write_tmp(code, suffix=".rs")
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            path.unlink()

    def test_to_dict(self) -> None:
        code = """
class Cache:
    def __init__(self):
        self.items = []
    def get_items(self):
        return self.items
"""
        path = _write_tmp(code)
        try:
            result = EncapsulationBreakAnalyzer().analyze_file(path)
            assert result.total_issues == 1
            d = result.to_dict()
            assert d["total_issues"] == 1
            assert d["issues"][0]["method_name"] == "get_items"
        finally:
            path.unlink()
