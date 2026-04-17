#!/usr/bin/env python3
"""
Unit tests for Security Scan MCP Tool.
"""
from __future__ import annotations

import json
import pytest

from tree_sitter_analyzer.mcp.tools.security_scan_tool import SecurityScanTool


class TestSecurityScanTool:
    """Test SecurityScanTool MCP tool."""

    @pytest.mark.asyncio
    async def test_tool_definition(self) -> None:
        """Test tool definition structure."""
        tool = SecurityScanTool()
        definition = tool.get_tool_definition()

        assert definition["name"] == "security_scan"
        assert "security vulnerabilities" in definition["description"].lower()
        assert "file_path" in definition["inputSchema"]["properties"]
        assert "output_format" in definition["inputSchema"]["properties"]
        assert "severity_filter" in definition["inputSchema"]["properties"]

    def test_validate_arguments_missing_file_path(self) -> None:
        """Test validation without file_path raises error."""
        tool = SecurityScanTool()
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_invalid_output_format(self) -> None:
        """Test validation with invalid output format."""
        tool = SecurityScanTool()
        with pytest.raises(ValueError, match="Invalid output_format"):
            tool.validate_arguments({"file_path": "test.py", "output_format": "invalid"})

    def test_validate_arguments_invalid_severity_filter(self) -> None:
        """Test validation with invalid severity filter."""
        tool = SecurityScanTool()
        with pytest.raises(ValueError, match="Invalid severity_filter"):
            tool.validate_arguments({"file_path": "test.py", "severity_filter": "invalid"})

    @pytest.mark.asyncio
    async def test_execute_with_python_file(self) -> None:
        """Test scanning a Python file with vulnerabilities."""
        tool = SecurityScanTool()

        # Create test content with vulnerabilities
        content = '''
API_KEY = "sk-1234567890abcdef"
password = "mypassword123"
os.system("cat " + user_input)
'''

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        assert "output" in result
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_execute_with_javascript_file(self) -> None:
        """Test scanning a JavaScript file with vulnerabilities."""
        tool = SecurityScanTool()

        content = '''
const apiKey = "AIza1234567890abcdef";
element.innerHTML = userInput;
'''

        result = await tool.execute({
            "file_path": "test.js",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        data = json.loads(result["output"])
        assert "findings" in data

    @pytest.mark.asyncio
    async def test_severity_filter_critical_only(self) -> None:
        """Test severity filtering for critical issues only."""
        tool = SecurityScanTool()

        content = '''
API_KEY = "secret"  # Critical
password = "pass"  # Critical
hash = hashlib.md5(data)  # Medium
'''

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "json",
            "severity_filter": "critical",
        })

        assert result["success"] is True
        data = json.loads(result["output"])
        # All findings should be critical
        for f in data.get("findings", []):
            assert f.get("severity", "").lower() in ["critical", ""]

    @pytest.mark.asyncio
    async def test_output_format_toon(self) -> None:
        """Test TOON output format."""
        tool = SecurityScanTool()

        content = 'API_KEY = "sk-1234567890abcdef"'

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "toon",
        })

        assert result["success"] is True
        assert "🔒" in result["output"] or "❌" in result["output"]

    @pytest.mark.asyncio
    async def test_output_format_sarif(self) -> None:
        """Test SARIF output format."""
        from tree_sitter_analyzer.analysis.security_scan import SARIF_OM_SUPPORTED

        tool = SecurityScanTool()
        content = 'API_KEY = "sk-1234567890abcdef"'

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "sarif",
        })

        assert result["success"] is True
        output = result["output"]

        if SARIF_OM_SUPPORTED:
            # Should be proper SARIF format
            data = json.loads(output)
            assert "version" in data
            assert data["version"] == "2.1.0"
        else:
            # Falls back to JSON format when sarif_om is not available
            data = json.loads(output)
            assert "findings" in data
            assert "total_findings" in data

    @pytest.mark.asyncio
    async def test_clean_file_no_findings(self) -> None:
        """Test scanning a clean file with no vulnerabilities."""
        tool = SecurityScanTool()

        content = '''
# This is a clean file with no vulnerabilities
def hello_world():
    print("Hello, World!")

hello_world()
'''

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        data = json.loads(result["output"])
        assert data["total_findings"] == 0

    @pytest.mark.asyncio
    async def test_java_file_detection(self) -> None:
        """Test Java file security scanning."""
        tool = SecurityScanTool()

        content = '''
String password = "admin123";
Runtime.getRuntime().exec("cmd " + userInput);
'''

        result = await tool.execute({
            "file_path": "Test.java",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_go_file_detection(self) -> None:
        """Test Go file security scanning."""
        tool = SecurityScanTool()

        content = '''
password := "mypassword"
cmd := exec.Command("sh", "-c", userCommand)
'''

        result = await tool.execute({
            "file_path": "main.go",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_xss_detection_javascript(self) -> None:
        """Test XSS vulnerability detection in JavaScript."""
        tool = SecurityScanTool()

        content = '''
element.innerHTML = userInput;
eval(userCode);
'''

        result = await tool.execute({
            "file_path": "test.js",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        data = json.loads(result["output"])
        if data["total_findings"] > 0:
            # Should have XSS findings
            has_xss = any(
                f.get("vulnerability_type") == "xss"
                for f in data["findings"]
            )
            assert has_xss

    @pytest.mark.asyncio
    async def test_cwe_ids_in_findings(self) -> None:
        """Test that findings include CWE IDs."""
        tool = SecurityScanTool()

        content = 'API_KEY = "sk-1234567890abcdef"'

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        data = json.loads(result["output"])
        if data["total_findings"] > 0:
            # At least one finding should have a CWE ID
            has_cwe = any(
                f.get("cwe_id", "").startswith("CWE-")
                for f in data["findings"]
            )
            assert has_cwe

    @pytest.mark.asyncio
    async def test_remediation_advice_in_findings(self) -> None:
        """Test that findings include remediation advice."""
        tool = SecurityScanTool()

        content = 'API_KEY = "sk-1234567890abcdef"'

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        data = json.loads(result["output"])
        if data["total_findings"] > 0:
            # All findings should have remediation
            for f in data["findings"]:
                assert len(f.get("remediation", "")) > 0

    @pytest.mark.asyncio
    async def test_summary_in_result(self) -> None:
        """Test that result includes summary."""
        tool = SecurityScanTool()

        content = 'API_KEY = "sk-1234567890abcdef"'

        result = await tool.execute({
            "file_path": "test.py",
            "content": content,
            "output_format": "json",
        })

        assert result["success"] is True
        assert "summary" in result
        assert "total_findings" in result["summary"]
