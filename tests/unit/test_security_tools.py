"""
Tests for mcp/tools/security.py module.

TDD: Testing security scanning tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.security import SecurityScannerTool


class TestSecurityScannerTool:
    """Test SecurityScannerTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = SecurityScannerTool()
        assert tool.get_name() == "security_scan"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = SecurityScannerTool()
        assert "security" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = SecurityScannerTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "severity" in schema["properties"]
        assert "file_path" in schema["required"]

    def test_file_not_found(self) -> None:
        """Should return error for non-existent file."""
        tool = SecurityScannerTool()
        result = tool.execute({"file_path": "/nonexistent/file.py"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_detect_hardcoded_password(self) -> None:
        """Should detect hardcoded passwords."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('password = "secret123"\n')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert result["count"] >= 1
            assert any(i["type"] == "hardcoded_secret" for i in result["issues"])
        finally:
            Path(file_path).unlink()

    def test_detect_hardcoded_api_key(self) -> None:
        """Should detect hardcoded API keys."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('api_key = "abcd1234"\n')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert result["count"] >= 1
            assert any("API key" in i["description"] for i in result["issues"])
        finally:
            Path(file_path).unlink()

    def test_detect_hardcoded_token(self) -> None:
        """Should detect hardcoded tokens."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('token = "xyz789"\n')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert result["count"] >= 1
        finally:
            Path(file_path).unlink()

    def test_detect_eval_usage(self) -> None:
        """Should detect eval() usage."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('result = eval(user_input)\n')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert any(i["type"] == "dangerous_function" for i in result["issues"])
            assert any("eval" in i["description"] for i in result["issues"])
        finally:
            Path(file_path).unlink()

    def test_detect_exec_usage(self) -> None:
        """Should detect exec() usage."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('exec(code_string)\n')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert any("exec" in i["description"] for i in result["issues"])
        finally:
            Path(file_path).unlink()

    def test_clean_code_no_issues(self) -> None:
        """Should report no issues for clean code."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''
def safe_function():
    config = load_config()
    return process(config)
''')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert result["count"] == 0
        finally:
            Path(file_path).unlink()

    def test_filter_by_severity(self) -> None:
        """Should filter issues by severity."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('password = "test"\neval(x)\n')
            f.flush()
            file_path = f.name
        
        try:
            # Get all issues
            result_all = tool.execute({"file_path": file_path, "severity": "all"})
            
            # Filter by high severity
            result_high = tool.execute({"file_path": file_path, "severity": "high"})
            
            assert result_all["count"] >= result_high["count"]
            assert all(i["severity"] == "high" for i in result_high["issues"])
        finally:
            Path(file_path).unlink()

    def test_line_number_tracking(self) -> None:
        """Should track correct line numbers."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''# Line 1
# Line 2
password = "secret"  # Line 3
''')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            issue = result["issues"][0]
            assert issue["line"] == 3
        finally:
            Path(file_path).unlink()

    def test_case_insensitive_detection(self) -> None:
        """Should detect secrets case-insensitively."""
        tool = SecurityScannerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('PASSWORD = "test"\n')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"file_path": file_path})
            
            assert result["success"] is True
            assert result["count"] >= 1
        finally:
            Path(file_path).unlink()
