"""Cover uncovered branches in error_recovery.py (70.83% -> 100%).

Uncovered lines: 68-71 (pattern match body), 81 (suggested_tool conditional).
Each hint pattern is exercised to hit the for-loop body at least once.
"""


from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
    build_agent_friendly_error,
)


class TestBuildAgentFriendlyError:
    def test_file_not_found_pattern(self):
        err = FileNotFoundError("file not found at /tmp/missing.js")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["success"] is False
        assert result["error_category"] == "file_not_found"
        assert "list_files" in result["suggested_tool"]
        assert result["error_type"] == "FileNotFoundError"

    def test_unsupported_language_pattern(self):
        err = ValueError("unsupported language: .xyz")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["error_category"] == "language_unsupported"
        assert "suggested_tool" not in result

    def test_project_root_pattern(self):
        err = RuntimeError("project root has not been configured")
        result = build_agent_friendly_error("analyze_dependencies", err)
        assert result["error_category"] == "project_not_set"
        assert result["suggested_tool"] == "set_project_path"

    def test_outside_boundary_pattern(self):
        err = PermissionError("outside project boundary detected")
        result = build_agent_friendly_error("read_file", err)
        assert result["error_category"] == "security_violation"
        assert "suggested_tool" not in result

    def test_missing_parameter_pattern(self):
        err = TypeError("file_path is required")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["error_category"] == "missing_parameter"
        assert "suggested_tool" not in result

    def test_validation_error_pattern(self):
        err = ValueError("format must be one of: full, compact")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["error_category"] == "validation_error"

    def test_resource_exhausted_pattern(self):
        err = MemoryError("out of memory during analysis")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["error_category"] == "resource_exhausted"
        assert "suppress_output" in result["recovery_hint"]

    def test_timeout_pattern(self):
        err = TimeoutError("operation timed out after 30s")
        result = build_agent_friendly_error("search_content", err)
        assert result["error_category"] == "timeout"
        assert "scope" in result["recovery_hint"]

    def test_unknown_error_category(self):
        err = RuntimeError("something completely unexpected")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["error_category"] == "unknown"
        assert "Review the error message" in result["recovery_hint"]
        assert "suggested_tool" not in result

    def test_error_message_preserved(self):
        # SEC-2: absolute paths are redacted to <external-path>, but the
        # rest of the message + the exception class name are preserved so
        # the agent can still reason about the failure.
        err = FileNotFoundError("file not found: /tmp/test.py")
        result = build_agent_friendly_error("analyze_file", err)
        assert "FileNotFoundError" in result["error"]
        assert "file not found" in result["error"]
        assert "/tmp/test.py" not in result["error"]
        assert "<external-path>" in result["error"]

    def test_error_type_preserved(self):
        err = MemoryError("out of memory")
        result = build_agent_friendly_error("analyze_file", err)
        assert result["error_type"] == "MemoryError"

    def test_suggested_tool_with_file_not_found(self):
        err = FileNotFoundError("not found: missing.py")
        result = build_agent_friendly_error("analyze_file", err)
        assert "suggested_tool" in result
        assert result["suggested_tool"] == "list_files"
