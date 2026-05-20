"""Unit tests for output_manager — OutputManager class and convenience functions."""

import json

from tree_sitter_analyzer.output_manager import (
    OutputManager,
    get_output_manager,
    output_data,
    output_info,
    output_json,
    set_output_mode,
)


class TestOutputManagerInit:
    """Tests for OutputManager initialization."""

    def test_default_format(self):
        om = OutputManager()
        assert om.output_format == "json"
        assert om.quiet is False
        assert om.json_output is False

    def test_json_output_forces_format(self):
        om = OutputManager(json_output=True)
        assert om.output_format == "json"

    def test_custom_format(self):
        om = OutputManager(output_format="yaml")
        assert om.output_format == "yaml"

    def test_quiet_mode(self):
        om = OutputManager(quiet=True)
        assert om.quiet is True


class TestOutputManagerInfo:
    """Tests for info/warning/success/error methods."""

    def test_info_prints_to_stdout(self, capsys):
        om = OutputManager()
        om.info("hello")
        assert capsys.readouterr().out.strip() == "hello"

    def test_info_suppressed_in_quiet(self, capsys):
        om = OutputManager(quiet=True)
        om.info("hello")
        assert capsys.readouterr().out == ""

    def test_error_always_prints(self, capsys):
        om = OutputManager(quiet=True)
        om.error("bad")
        assert "bad" in capsys.readouterr().err

    def test_warning_prints_to_stderr(self, capsys):
        om = OutputManager()
        om.warning("caution")
        assert "WARNING" in capsys.readouterr().err

    def test_warning_suppressed_in_quiet(self, capsys):
        om = OutputManager(quiet=True)
        om.warning("caution")
        err = capsys.readouterr().err
        assert err == ""

    def test_success_prints_checkmark(self, capsys):
        om = OutputManager()
        om.success("done")
        assert "✓" in capsys.readouterr().out


class TestOutputManagerData:
    """Tests for data() method — format routing."""

    def test_json_output(self, capsys):
        om = OutputManager()
        om.data({"key": "value"})
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["key"] == "value"

    def test_json_string_passthrough(self, capsys):
        om = OutputManager()
        om.data("plain text")
        assert capsys.readouterr().out.strip() == '"plain text"'

    def test_toon_mcp_response_passthrough(self, capsys):
        om = OutputManager(output_format="toon")
        om.data({"format": "toon", "toon_content": "TABLE DATA"})
        assert "TABLE DATA" in capsys.readouterr().out

    def test_toon_response_as_json_when_json_format(self, capsys):
        om = OutputManager(json_output=True)
        om.data({"format": "toon", "toon_content": "TABLE"})
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["format"] == "toon"

    def test_json_output_flag_overrides_format(self, capsys):
        om = OutputManager(json_output=True, output_format="yaml")
        om.data({"x": 1})
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["x"] == 1


class TestOutputManagerFormatData:
    """Tests for _format_data fallback."""

    def test_dict_formatting(self, capsys):
        om = OutputManager()
        om._format_data({"name": "test", "value": 42})
        out = capsys.readouterr().out
        assert "name" in out
        assert "test" in out

    def test_list_formatting(self, capsys):
        om = OutputManager()
        om._format_data(["a", "b", "c"])
        out = capsys.readouterr().out
        assert "1. a" in out
        assert "3. c" in out

    def test_string_formatting(self, capsys):
        om = OutputManager()
        om._format_data("just text")
        assert capsys.readouterr().out.strip() == "just text"


class TestOutputManagerResultsHeader:
    """Tests for results_header / output_section."""

    def test_results_header(self, capsys):
        om = OutputManager()
        om.results_header("Query Results")
        assert "Query Results" in capsys.readouterr().out

    def test_results_header_suppressed_quiet(self, capsys):
        om = OutputManager(quiet=True)
        om.results_header("Title")
        assert capsys.readouterr().out == ""


class TestOutputManagerQueryResult:
    """Tests for query_result method."""

    def test_displays_result(self, capsys):
        om = OutputManager()
        om.query_result(1, {
            "capture_name": "function",
            "node_type": "function_definition",
            "start_line": 5,
            "end_line": 10,
            "content": "def foo(): pass",
        })
        out = capsys.readouterr().out
        assert "function" in out
        assert "5-10" in out

    def test_quiet_suppresses_query_result(self, capsys):
        om = OutputManager(quiet=True)
        om.query_result(1, {"capture_name": "x", "node_type": "y"})
        assert capsys.readouterr().out == ""


class TestOutputManagerList:
    """Tests for output_list method."""

    def test_list_with_title(self, capsys):
        om = OutputManager()
        om.output_list(["a", "b"], title="Items")
        out = capsys.readouterr().out
        assert "Items" in out
        assert "a" in out

    def test_string_input_becomes_single_item(self, capsys):
        om = OutputManager()
        om.output_list("only_one")
        out = capsys.readouterr().out
        assert "only_one" in out

    def test_quiet_suppresses_list(self, capsys):
        om = OutputManager(quiet=True)
        om.output_list(["a"], title="Hidden")
        assert capsys.readouterr().out == ""


class TestOutputManagerExtensions:
    """Tests for extension_list method."""

    def test_shows_extensions(self, capsys):
        om = OutputManager()
        om.extension_list([".py", ".js", ".ts"])
        out = capsys.readouterr().out
        assert ".py" in out
        assert "3 extensions" in out


class TestGlobalFunctions:
    """Tests for module-level convenience functions."""

    def test_set_output_mode_creates_new_manager(self):
        old = get_output_manager()
        set_output_mode(quiet=True, json_output=True)
        new = get_output_manager()
        assert new is not old
        assert new.quiet is True
        # Restore
        set_output_mode(quiet=False, json_output=False)

    def test_output_info_delegates(self, capsys):
        set_output_mode(quiet=False, json_output=False)
        output_info("test message")
        assert "test message" in capsys.readouterr().out

    def test_output_json_delegates(self, capsys):
        output_json({"key": "val"})
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["key"] == "val"

    def test_output_data_delegates(self, capsys):
        output_data({"x": 1}, format_type="json")
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["x"] == 1
