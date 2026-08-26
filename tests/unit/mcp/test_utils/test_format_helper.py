#!/usr/bin/env python3
"""Unit tests for format_helper.py — JSON output paths only (TOON removed)."""

from tree_sitter_analyzer.mcp.utils.format_helper import (
    JsonFormatter,
    apply_output_format,
    apply_output_format_to_response,
    attach_toon_content_to_response,
    format_as_json,
    format_for_file_output,
    format_output,
    get_formatter,
    preformat_diff_snapshot_publish_errors,
)


class TestFormatOutput:
    def test_format_output_json(self):
        data = {"key": "value", "number": 42}
        result = format_output(data, "json")
        assert isinstance(result, str)
        assert '"key": "value"' in result
        assert '"number": 42' in result

    def test_format_output_default_format(self):
        data = {"key": "value"}
        result = format_output(data)
        assert isinstance(result, str)
        assert '"key": "value"' in result

    def test_format_output_empty_dict(self):
        result = format_output({}, "json")
        assert result == "{}"

    def test_format_output_nested_dict(self):
        data = {"outer": {"inner": {"deep": "value"}}}
        result = format_output(data, "json")
        assert '"outer"' in result
        assert '"deep": "value"' in result


class TestFormatAsJson:
    def test_format_as_json_simple(self):
        result = format_as_json({"key": "value"})
        assert result == '{\n  "key": "value"\n}'

    def test_format_as_json_with_numbers(self):
        result = format_as_json({"int": 42, "float": 3.14})
        assert '"int": 42' in result
        assert '"float": 3.14' in result

    def test_format_as_json_with_unicode(self):
        result = format_as_json({"text": "日本語テスト"})
        assert "日本語テスト" in result


class TestGetFormatter:
    def test_get_formatter_json(self):
        assert isinstance(get_formatter("json"), JsonFormatter)

    def test_get_formatter_default(self):
        assert isinstance(get_formatter(), JsonFormatter)


class TestJsonFormatter:
    def test_format_dict(self):
        result = JsonFormatter().format({"key": "value", "n": 42})
        assert '"key": "value"' in result
        assert '"n": 42' in result

    def test_format_list(self):
        result = JsonFormatter().format([1, 2, 3])
        assert result == "[\n  1,\n  2,\n  3\n]"


class TestApplyOutputFormat:
    def test_return_dict(self):
        d = {"key": "value"}
        assert apply_output_format(d, "json", False) == d

    def test_return_json_string(self):
        result = apply_output_format({"key": "value"}, "json", True)
        assert isinstance(result, str)
        assert '"key": "value"' in result

    def test_default_params(self):
        d = {"key": "value"}
        assert apply_output_format(d) == d


class TestFormatForFileOutput:
    def test_json_extension(self):
        content, ext = format_for_file_output({"key": "value"}, "json")
        assert ext == ".json"
        assert '"key": "value"' in content

    def test_default_is_json(self):
        content, ext = format_for_file_output({"key": "value"})
        assert ext == ".json"
        assert isinstance(content, str)


class TestApplyToonFormatToResponse:
    def test_json_format_passthrough(self):
        result = {"key": "value", "number": 42}
        response = apply_output_format_to_response(result, "json")
        assert response == result
        assert "toon_content" not in response


class TestAttachToonContentToResponse:
    def test_passthrough(self):
        result = {"key": "value"}
        response = attach_toon_content_to_response(result)
        assert "key" in response
        assert response["key"] == "value"


def test_preformat_diff_snapshot_publish_errors_json() -> None:
    errors, _generic = preformat_diff_snapshot_publish_errors(
        "json", apply_output_format_to_response
    )
    assert "DIFF_SNAPSHOT_UNSUPPORTED_FILTER" in errors
    err = errors["DIFF_SNAPSHOT_UNSUPPORTED_FILTER"]
    assert err["success"] is False
    assert err["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_FILTER"
