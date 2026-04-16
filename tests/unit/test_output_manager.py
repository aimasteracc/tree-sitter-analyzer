"""Tests for output_manager.py — increased coverage for uncovered paths."""
from __future__ import annotations

import json

from tree_sitter_analyzer.output_manager import OutputManager


class TestOutputManagerInit:
    def test_default_format(self) -> None:
        om = OutputManager()
        assert om.output_format == "json"
        assert om.quiet is False

    def test_json_output_overrides_format(self) -> None:
        om = OutputManager(json_output=True, output_format="yaml")
        assert om.output_format == "json"

    def test_quiet_mode(self) -> None:
        om = OutputManager(quiet=True)
        assert om.quiet is True


class TestOutputManagerData:
    def test_data_json_format(self, capsys: object) -> None:
        om = OutputManager(output_format="json")
        om.data({"key": "value"})
        captured = capsys.readouterr()
        assert '"key": "value"' in captured.out

    def test_data_with_toon_content(self, capsys: object) -> None:
        om = OutputManager(output_format="toon")
        toon_data = {"format": "toon", "toon_content": "cls Foo"}
        om.data(toon_data)
        captured = capsys.readouterr()
        assert "cls Foo" in captured.out

    def test_data_toon_response_json_output(self, capsys: object) -> None:
        om = OutputManager(output_format="json")
        toon_data = {"format": "toon", "toon_content": "cls Foo"}
        om.data(toon_data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["format"] == "toon"

    def test_data_string_passthrough(self, capsys: object) -> None:
        om = OutputManager(output_format="json")
        om.data("hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_data_unknown_format_fallback(self, capsys: object) -> None:
        om = OutputManager(output_format="unknown_format")
        om.data({"x": 1})
        captured = capsys.readouterr()
        assert "x: 1" in captured.out

    def test_data_list_format(self, capsys: object) -> None:
        om = OutputManager(output_format="unknown_format")
        om.data([1, 2, 3])
        captured = capsys.readouterr()
        assert "1. 1" in captured.out


class TestOutputManagerMessages:
    def test_info(self, capsys: object) -> None:
        om = OutputManager()
        om.info("test info")
        assert "test info" in capsys.readouterr().out

    def test_info_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.info("test info")
        assert capsys.readouterr().out == ""

    def test_warning(self, capsys: object) -> None:
        om = OutputManager()
        om.warning("test warn")
        assert "test warn" in capsys.readouterr().err

    def test_error(self, capsys: object) -> None:
        om = OutputManager()
        om.error("test error")
        assert "test error" in capsys.readouterr().err

    def test_success(self, capsys: object) -> None:
        om = OutputManager()
        om.success("test ok")
        assert "test ok" in capsys.readouterr().out

    def test_success_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.success("test ok")
        assert capsys.readouterr().out == ""


class TestOutputManagerAliases:
    def test_output_info(self, capsys: object) -> None:
        om = OutputManager()
        om.output_info("info msg")
        assert "info msg" in capsys.readouterr().out

    def test_output_warning(self, capsys: object) -> None:
        om = OutputManager()
        om.output_warning("warn msg")
        assert "warn msg" in capsys.readouterr().err

    def test_output_error(self, capsys: object) -> None:
        om = OutputManager()
        om.output_error("err msg")
        assert "err msg" in capsys.readouterr().err

    def test_output_success(self, capsys: object) -> None:
        om = OutputManager()
        om.output_success("ok msg")
        assert "ok msg" in capsys.readouterr().out


class TestOutputManagerStructured:
    def test_results_header(self, capsys: object) -> None:
        om = OutputManager()
        om.results_header("Test Section")
        assert "Test Section" in capsys.readouterr().out

    def test_results_header_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.results_header("Test Section")
        assert capsys.readouterr().out == ""

    def test_query_result(self, capsys: object) -> None:
        om = OutputManager()
        om.query_result(1, {
            "capture_name": "method",
            "node_type": "method_declaration",
            "start_line": 10,
            "end_line": 20,
            "content": "void foo() {}",
        })
        out = capsys.readouterr().out
        assert "method" in out
        assert "10" in out

    def test_query_result_no_content(self, capsys: object) -> None:
        om = OutputManager()
        om.query_result(2, {"capture_name": "class", "node_type": "class_decl"})
        out = capsys.readouterr().out
        assert "class" in out

    def test_analysis_summary(self, capsys: object) -> None:
        om = OutputManager()
        om.analysis_summary({"files": 5, "lines": 100})
        out = capsys.readouterr().out
        assert "files" in out
        assert "100" in out

    def test_language_list(self, capsys: object) -> None:
        om = OutputManager()
        om.language_list(["java", "python"])
        out = capsys.readouterr().out
        assert "java" in out
        assert "python" in out

    def test_language_list_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.language_list(["java"])
        assert capsys.readouterr().out == ""

    def test_query_list(self, capsys: object) -> None:
        om = OutputManager()
        om.query_list({"methods": "Find methods", "classes": "Find classes"}, "java")
        out = capsys.readouterr().out
        assert "methods" in out
        assert "Find methods" in out

    def test_query_list_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.query_list({"methods": "Find methods"}, "java")
        assert capsys.readouterr().out == ""

    def test_extension_list(self, capsys: object) -> None:
        om = OutputManager()
        om.extension_list([".py", ".java", ".js"])
        out = capsys.readouterr().out
        assert ".py" in out

    def test_extension_list_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.extension_list([".py"])
        out = capsys.readouterr().out
        assert ".py" in out

    def test_output_json(self, capsys: object) -> None:
        om = OutputManager()
        om.output_json({"key": "val"})
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["key"] == "val"

    def test_output_list_string(self, capsys: object) -> None:
        om = OutputManager()
        om.output_list("single_item", title="Items")
        out = capsys.readouterr().out
        assert "single_item" in out

    def test_output_list_with_title(self, capsys: object) -> None:
        om = OutputManager()
        om.output_list(["a", "b"], title="My List")
        out = capsys.readouterr().out
        assert "My List" in out

    def test_output_list_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.output_list(["a"], title="Title")
        out = capsys.readouterr().out
        assert out == ""

    def test_output_section(self, capsys: object) -> None:
        om = OutputManager()
        om.output_section("Section")
        assert "Section" in capsys.readouterr().out

    def test_output_section_quiet(self, capsys: object) -> None:
        om = OutputManager(quiet=True)
        om.output_section("Section")
        assert capsys.readouterr().out == ""
