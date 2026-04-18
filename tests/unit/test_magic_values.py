"""Unit tests for magic value detection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.magic_values import (
    MagicValueDetector,
    MagicValueResult,
    MagicValueUsage,
    _classify_number,
    _classify_string,
    _extract_string_content,
)


@pytest.fixture
def detector() -> MagicValueDetector:
    return MagicValueDetector("python")


@pytest.fixture
def tmp_py() -> Path:
    content = b'''"""Module docstring."""
import os

MAX_RETRIES = 3
TIMEOUT = 30

def fetch(url):
    """Fetch data from URL."""
    result = connect("https://api.example.com/v1/data")
    for i in range(10):
        process(42, "hello world")
    if x > 100:
        return "#ff0000"
    return "#abc"
'''
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(content)
        return Path(f.name)


def test_classify_number_safe() -> None:
    assert _classify_number("0") is None
    assert _classify_number("1") is None
    assert _classify_number("-1") is None
    assert _classify_number("2") is None


def test_classify_number_magic() -> None:
    assert _classify_number("42") == "magic_number"
    assert _classify_number("100") == "magic_number"
    assert _classify_number("3.14") == "magic_number"
    assert _classify_number("-99") == "magic_number"


def test_classify_string_safe() -> None:
    assert _classify_string("") is None
    assert _classify_string("ab") is None


def test_classify_string_magic() -> None:
    assert _classify_string("hello world") == "magic_string"
    assert _classify_string("api.example.com/data") == "magic_string"


def test_classify_string_url() -> None:
    assert _classify_string("https://api.example.com") == "hardcoded_url"
    assert _classify_string("http://localhost:8080") == "hardcoded_url"
    assert _classify_string("ftp://files.example.com") == "hardcoded_url"


def test_classify_string_path() -> None:
    assert _classify_string("/usr/local/bin") == "hardcoded_path"
    assert _classify_string("./config/settings") == "hardcoded_path"
    assert _classify_string("../parent/dir") == "hardcoded_path"


def test_classify_string_color() -> None:
    assert _classify_string("#ff0000") == "hardcoded_color"
    assert _classify_string("#abc") == "hardcoded_color"
    assert _classify_string("#aabbccdd") == "hardcoded_color"


def test_extract_string_content() -> None:
    assert _extract_string_content('"hello"') == "hello"
    assert _extract_string_content("'world'") == "world"
    assert _extract_string_content('"""doc"""') == "doc"
    assert _extract_string_content("f\"{x}\"") == "{x}"
    assert _extract_string_content("r'\\n'") == "\\n"


def test_detect_single_file(detector: MagicValueDetector, tmp_py: Path) -> None:
    result = detector.detect(tmp_py)
    assert isinstance(result, MagicValueResult)
    assert result.total_count > 0
    categories = {r.category for r in result.references}
    assert "magic_number" in categories
    assert "hardcoded_url" in categories or "magic_string" in categories


def test_detect_finds_magic_numbers(detector: MagicValueDetector) -> None:
    code = b"x = 42\ny = 100\nz = 0\n"
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(code)
        p = Path(f.name)
    result = detector.detect(p)
    nums = [r for r in result.references if r.category == "magic_number"]
    values = {r.value for r in nums}
    assert "42" in values
    assert "100" in values


def test_detect_finds_urls(detector: MagicValueDetector) -> None:
    code = b'url = "https://api.example.com/v2"\n'
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(code)
        p = Path(f.name)
    result = detector.detect(p)
    urls = [r for r in result.references if r.category == "hardcoded_url"]
    assert len(urls) >= 1
    assert "https://api.example.com/v2" in urls[0].value


def test_detect_finds_colors(detector: MagicValueDetector) -> None:
    code = b'color = "#ff5500"\n'
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(code)
        p = Path(f.name)
    result = detector.detect(p)
    colors = [r for r in result.references if r.category == "hardcoded_color"]
    assert len(colors) >= 1
    assert colors[0].value == "#ff5500"


def test_group_by_value(detector: MagicValueDetector) -> None:
    code = b"x = 42\ny = 42\n"
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(code)
        p = Path(f.name)
    results = [detector.detect(p)]
    usages = detector.group_by_value(results)
    assert isinstance(usages, list)
    found_42 = [u for u in usages if u.value == "42"]
    assert len(found_42) == 1
    assert found_42[0].total_refs >= 2


def test_filter_by_category(detector: MagicValueDetector, tmp_py: Path) -> None:
    results = [detector.detect(tmp_py)]
    filtered = detector.filter_by_category(results, {"magic_number"})
    for r in filtered:
        for ref in r.references:
            assert ref.category == "magic_number"


def test_to_dict_result(detector: MagicValueDetector) -> None:
    code = b"x = 42\n"
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(code)
        p = Path(f.name)
    result = detector.detect(p)
    d = result.to_dict()
    assert "file_path" in d
    assert "total_count" in d
    assert "references" in d


def test_to_dict_usage() -> None:
    from tree_sitter_analyzer.analysis.magic_values import MagicValueReference

    ref = MagicValueReference(
        value="42",
        file_path="test.py",
        line=1,
        column=4,
        value_type="number",
        context="x = 42",
        category="magic_number",
    )
    usage = MagicValueUsage(
        value="42",
        references=(ref,),
        file_count=1,
        total_refs=1,
        category="magic_number",
    )
    d = usage.to_dict()
    assert d["value"] == "42"
    assert d["total_refs"] == 1
    assert len(d["references"]) == 1
