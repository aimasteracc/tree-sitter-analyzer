"""Tests for tree_sitter_analyzer.formatters.json_formatter.JSONFormatter."""

from __future__ import annotations

import json

import pytest

from tree_sitter_analyzer.formatters.json_formatter import JSONFormatter


@pytest.fixture
def fmt() -> JSONFormatter:
    return JSONFormatter()


def _doc(value_type: str = "object", child_count: int | None = None) -> dict:
    d: dict = {"element_type": "document", "value_type": value_type}
    if child_count is not None:
        d["child_count"] = child_count
    return d


def _prop(
    key: str = "name",
    value_type: str = "string",
    value: str = "hello",
    nesting_level: int = 1,
    start_line: int = 1,
    end_line: int = 1,
    child_count: int | None = None,
    name: str | None = None,
) -> dict:
    p: dict = {
        "element_type": "property",
        "value_type": value_type,
        "nesting_level": nesting_level,
        "start_line": start_line,
        "end_line": end_line,
    }
    if name is not None:
        p["name"] = name
    else:
        p["key"] = key
    if value:
        p["value"] = value
    if child_count is not None:
        p["child_count"] = child_count
    return p


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_language_attribute(self, fmt: JSONFormatter) -> None:
        assert fmt.language == "json"


# ---------------------------------------------------------------------------
# _format_json_output
# ---------------------------------------------------------------------------


class TestFormatJsonOutput:
    def test_contains_title_separator(self, fmt: JSONFormatter) -> None:
        out = fmt._format_json_output("My Title", {"k": 1})
        assert "--- My Title ---" in out

    def test_contains_valid_json(self, fmt: JSONFormatter) -> None:
        out = fmt._format_json_output("T", {"x": 42})
        body = out.split("\n", 1)[1]
        parsed = json.loads(body)
        assert parsed["x"] == 42

    def test_non_ascii_preserved(self, fmt: JSONFormatter) -> None:
        out = fmt._format_json_output("T", {"k": "日本語"})
        assert "日本語" in out


# ---------------------------------------------------------------------------
# _format_prop_row
# ---------------------------------------------------------------------------


class TestFormatPropRow:
    def test_simple_string_value(self, fmt: JSONFormatter) -> None:
        p = _prop(key="foo", value_type="string", value="bar")
        row = fmt._format_prop_row(p)
        assert "`foo`" in row
        assert "string" in row
        assert "`bar`" in row

    def test_long_value_truncated(self, fmt: JSONFormatter) -> None:
        long_val = "x" * 50
        p = _prop(key="k", value_type="string", value=long_val)
        row = fmt._format_prop_row(p)
        assert "…" in row
        # the display should use the first 40 chars
        assert "`" + "x" * 40 + "…`" in row

    def test_object_child_count_shows_props(self, fmt: JSONFormatter) -> None:
        p = _prop(key="cfg", value_type="object", value="", child_count=3)
        row = fmt._format_prop_row(p)
        assert "(3 props)" in row

    def test_array_child_count_shows_items(self, fmt: JSONFormatter) -> None:
        p = _prop(key="lst", value_type="array", value="", child_count=5)
        row = fmt._format_prop_row(p)
        assert "(5 items)" in row

    def test_no_value_empty_display(self, fmt: JSONFormatter) -> None:
        p = {
            "element_type": "property",
            "key": "k",
            "value_type": "null",
            "nesting_level": 1,
            "start_line": 1,
            "end_line": 1,
        }
        row = fmt._format_prop_row(p)
        # display column should be empty (two adjacent pipes)
        assert "| `k` | null |  |" in row

    def test_same_start_end_single_line(self, fmt: JSONFormatter) -> None:
        p = _prop(start_line=5, end_line=5)
        row = fmt._format_prop_row(p)
        assert "| 5 |" in row
        assert "5-5" not in row

    def test_different_start_end_range(self, fmt: JSONFormatter) -> None:
        p = _prop(start_line=3, end_line=7)
        row = fmt._format_prop_row(p)
        assert "3-7" in row

    def test_uses_name_key_when_key_missing(self, fmt: JSONFormatter) -> None:
        p = _prop(name="n_key", value_type="string", value="v")
        row = fmt._format_prop_row(p)
        assert "`n_key`" in row

    def test_question_mark_fallback_when_no_key_or_name(
        self, fmt: JSONFormatter
    ) -> None:
        p = {
            "element_type": "pair",
            "value_type": "string",
            "nesting_level": 1,
            "start_line": 1,
            "end_line": 1,
        }
        row = fmt._format_prop_row(p)
        assert "`?`" in row


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------


class TestFormatSummary:
    def test_with_doc_and_props(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "pkg.json",
            "elements": [
                _doc("object"),
                _prop("name", nesting_level=1),
                _prop("version", nesting_level=1),
                _prop("nested_key", nesting_level=2),
            ],
        }
        out = fmt.format_summary(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert parsed["root_type"] == "object"
        assert parsed["total_properties"] == 3
        assert parsed["top_level_keys"] == 2

    def test_no_elements_returns_unknown(self, fmt: JSONFormatter) -> None:
        result = {"file_path": "empty.json", "elements": []}
        out = fmt.format_summary(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert parsed["root_type"] == "unknown"
        assert parsed["total_properties"] == 0

    def test_pair_element_type_counts_as_prop(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [
                {
                    "element_type": "pair",
                    "value_type": "string",
                    "nesting_level": 1,
                    "key": "x",
                    "value": "y",
                },
            ],
        }
        out = fmt.format_summary(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert parsed["total_properties"] == 1

    def test_non_prop_elements_ignored(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [{"element_type": "comment", "text": "# note"}],
        }
        out = fmt.format_summary(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert parsed["total_properties"] == 0


# ---------------------------------------------------------------------------
# format_structure
# ---------------------------------------------------------------------------


class TestFormatStructure:
    def test_no_elements_returns_no_elements_message(self, fmt: JSONFormatter) -> None:
        result = {"file_path": "empty.json", "elements": []}
        out = fmt.format_structure(result)
        assert "No JSON elements found" in out

    def test_doc_only_renders_document_info(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "path/to/pkg.json",
            "elements": [_doc("object", child_count=2)],
            "line_count": 10,
        }
        out = fmt.format_structure(result)
        assert "pkg.json" in out
        assert "object" in out
        assert "properties" in out  # "Top-level properties"
        assert "Total lines" in out

    def test_array_root_uses_items_label(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "arr.json",
            "elements": [_doc("array", child_count=4)],
        }
        out = fmt.format_structure(result)
        assert "items" in out

    def test_props_shown_in_table(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [
                _doc("object"),
                _prop("alpha", value_type="string", value="a"),
                _prop("beta", value_type="number", value="42"),
            ],
        }
        out = fmt.format_structure(result)
        assert "alpha" in out
        assert "beta" in out
        assert "| Key |" in out

    def test_level_2_props_shown(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [
                _doc(),
                _prop("top", nesting_level=1),
                _prop("inner", nesting_level=2),
            ],
        }
        out = fmt.format_structure(result)
        assert "Top-level" in out
        assert "Level-2" in out

    def test_deeper_props_not_shown_but_counted(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [
                _doc(),
                _prop("l3", nesting_level=3),
                _prop("l4", nesting_level=4),
            ],
        }
        out = fmt.format_structure(result)
        assert "deeper properties not shown" in out
        assert "2 deeper" in out

    def test_line_count_from_statistics_key(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [_doc()],
            "statistics": {"total_lines": 99},
        }
        out = fmt.format_structure(result)
        assert "99" in out

    def test_no_root_children_no_label(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [{"element_type": "document", "value_type": "object"}],
        }
        out = fmt.format_structure(result)
        # child_count not present → label line absent
        assert "Top-level properties" not in out


# ---------------------------------------------------------------------------
# format_advanced
# ---------------------------------------------------------------------------


class TestFormatAdvanced:
    def test_empty_elements(self, fmt: JSONFormatter) -> None:
        result = {"file_path": "f.json", "elements": []}
        out = fmt.format_advanced(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert parsed["total_properties"] == 0
        assert parsed["max_nesting_depth"] == 0

    def test_value_type_distribution(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [
                _prop("a", value_type="string"),
                _prop("b", value_type="string"),
                _prop("c", value_type="number"),
            ],
        }
        out = fmt.format_advanced(result)
        parsed = json.loads(out.split("\n", 1)[1])
        dist = parsed["value_type_distribution"]
        assert dist["string"] == 2
        assert dist["number"] == 1

    def test_max_nesting_depth(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [
                _prop("a", nesting_level=1),
                _prop("b", nesting_level=3),
                _prop("c", nesting_level=2),
            ],
        }
        out = fmt.format_advanced(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert parsed["max_nesting_depth"] == 3

    def test_missing_value_type_classified_as_unknown(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [{"element_type": "property", "nesting_level": 1}],
        }
        out = fmt.format_advanced(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert "unknown" in parsed["value_type_distribution"]

    def test_properties_per_level_keys_are_strings(self, fmt: JSONFormatter) -> None:
        result = {
            "file_path": "f.json",
            "elements": [_prop("x", nesting_level=1)],
        }
        out = fmt.format_advanced(result)
        parsed = json.loads(out.split("\n", 1)[1])
        assert "1" in parsed["properties_per_level"]


# ---------------------------------------------------------------------------
# format_table
# ---------------------------------------------------------------------------


class TestFormatTable:
    def test_delegates_to_format_structure(self, fmt: JSONFormatter) -> None:
        result = {"file_path": "t.json", "elements": [_doc(), _prop("x")]}
        assert fmt.format_table(result) == fmt.format_structure(result)

    def test_table_type_ignored(self, fmt: JSONFormatter) -> None:
        result = {"file_path": "t.json", "elements": []}
        out = fmt.format_table(result, table_type="compact")
        assert "No JSON elements found" in out
