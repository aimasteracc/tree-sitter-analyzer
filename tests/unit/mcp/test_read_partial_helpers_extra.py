"""Tests for mcp.tools.read_partial_helpers — schema, validation, response building."""

from tree_sitter_analyzer.mcp.tools.read_partial_helpers import (
    TOOL_SCHEMA,
    build_agent_summary,
    build_agent_summary_for_result,
    build_batch_agent_summary,
    build_read_response,
    build_validation_error,
    validate_line_range,
)


class TestToolSchema:
    def test_schema_has_required_properties(self):
        assert "properties" in TOOL_SCHEMA
        assert "file_path" in TOOL_SCHEMA["properties"]
        assert "start_line" in TOOL_SCHEMA["properties"]

    def test_schema_type_is_object(self):
        assert TOOL_SCHEMA["type"] == "object"


class TestBuildReadResponse:
    def test_basic_response(self):
        resp = build_read_response(
            "f.py", "code", 1, 5, None, None, "/abs/f.py", 5, False
        )
        assert resp["success"] is True
        assert resp["file_path"] == "f.py"
        assert resp["start_line"] == 1
        assert resp["end_line"] == 5
        assert resp["line_count"] == 5
        assert resp["truncated"] is False
        assert "start_column" not in resp

    def test_with_columns(self):
        resp = build_read_response("f.py", "code", 1, 1, 0, 10, "/abs/f.py", 1, False)
        assert resp["start_column"] == 0
        assert resp["end_column"] == 10

    def test_end_line_defaults_to_start(self):
        resp = build_read_response("f.py", "x", 3, None, None, None, "/f.py", 1, False)
        assert resp["end_line"] == 3


class TestValidateLineRange:
    def test_valid_range(self):
        assert validate_line_range(1, 10, None, None) is None

    def test_invalid_start_line_zero(self):
        assert "start_line must be a positive" in validate_line_range(0, 10, None, None)

    def test_invalid_start_line_type(self):
        assert "start_line must be a positive" in validate_line_range(
            "a", 10, None, None
        )

    def test_invalid_end_line(self):
        assert "end_line must be a positive" in validate_line_range(1, -1, None, None)

    def test_end_before_start(self):
        assert "end_line must be >= start_line" in validate_line_range(
            10, 5, None, None
        )

    def test_invalid_start_column(self):
        assert "start_column must be a non-negative" in validate_line_range(
            1, 10, -1, None
        )

    def test_invalid_end_column(self):
        assert "end_column must be a non-negative" in validate_line_range(1, 10, 0, -1)

    def test_end_column_before_start_column(self):
        assert "end_column must be >= start_column" in validate_line_range(1, 10, 10, 5)

    def test_valid_with_columns(self):
        assert validate_line_range(1, 10, 0, 5) is None

    def test_none_end_line_ok(self):
        assert validate_line_range(1, None, None, None) is None

    def test_none_columns_ok(self):
        assert validate_line_range(1, 10, None, None) is None


class TestBuildValidationError:
    def test_structure(self):
        err = build_validation_error("field_x", "bad value")
        assert err["success"] is False
        assert err["field"] == "field_x"
        assert "bad value" in err["error"]


class TestBuildAgentSummary:
    def test_low_risk(self):
        summary = build_agent_summary(
            file_path="f.py",
            start_line=1,
            end_line=10,
            start_column=None,
            end_column=None,
            content_length=100,
            lines_extracted=10,
            content_format="text",
        )
        assert summary["risk"] == "low"
        assert summary["lines_extracted"] == 10

    def test_medium_risk_lines(self):
        summary = build_agent_summary(
            file_path="f.py",
            start_line=1,
            end_line=60,
            start_column=None,
            end_column=None,
            content_length=1000,
            lines_extracted=60,
            content_format="text",
        )
        assert summary["risk"] == "medium"

    def test_high_risk_content_length(self):
        summary = build_agent_summary(
            file_path="f.py",
            start_line=1,
            end_line=300,
            start_column=None,
            end_column=None,
            content_length=25000,
            lines_extracted=300,
            content_format="text",
        )
        assert summary["risk"] == "high"

    def test_with_output_file(self):
        summary = build_agent_summary(
            file_path="f.py",
            start_line=1,
            end_line=5,
            start_column=None,
            end_column=None,
            content_length=50,
            lines_extracted=5,
            content_format="text",
            output_file="out.txt",
        )
        assert summary["output_saved"] is True

    def test_with_columns_next_step(self):
        summary = build_agent_summary(
            file_path="f.py",
            start_line=1,
            end_line=5,
            start_column=0,
            end_column=10,
            content_length=50,
            lines_extracted=5,
            content_format="text",
        )
        assert "column slice" in summary["next_step"]


class TestBuildAgentSummaryForResult:
    def test_from_result_dict(self):
        result = {
            "file_path": "f.py",
            "range": {
                "start_line": 1,
                "end_line": 5,
                "start_column": None,
                "end_column": None,
            },
            "content_length": 100,
            "lines_extracted": 5,
        }
        summary = build_agent_summary_for_result(result, "text")
        assert summary["risk"] == "low"
        assert summary["file_path"] == "f.py"


class TestBuildBatchAgentSummary:
    def test_low_risk(self):
        summary = build_batch_agent_summary(
            count_files=2, count_sections=5, truncated=False, error_count=0
        )
        assert summary["risk"] == "low"
        assert summary["mode"] == "batch"

    def test_high_risk_truncated(self):
        summary = build_batch_agent_summary(
            count_files=1, count_sections=5, truncated=True, error_count=0
        )
        assert summary["risk"] == "high"
        assert "Split" in summary["next_step"]

    def test_high_risk_errors(self):
        summary = build_batch_agent_summary(
            count_files=1, count_sections=5, truncated=False, error_count=2
        )
        assert summary["risk"] == "high"
        assert "Fix" in summary["next_step"]

    def test_medium_risk_many_sections(self):
        summary = build_batch_agent_summary(
            count_files=5, count_sections=25, truncated=False, error_count=0
        )
        assert summary["risk"] == "medium"
