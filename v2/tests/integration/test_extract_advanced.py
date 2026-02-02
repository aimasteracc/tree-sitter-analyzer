"""
Integration tests for advanced extract_code_section features.

Tests batch mode, token protection, and safety limits.
"""

import pytest


@pytest.fixture
def sample_files(tmp_path):
    """Create multiple sample files for batch testing."""
    # File 1: Python
    file1 = tmp_path / "main.py"
    file1.write_text(
        """def hello():
    print("Hello")

def world():
    print("World")

class MyClass:
    def method(self):
        pass
""",
        encoding="utf-8",
    )

    # File 2: JavaScript
    file2 = tmp_path / "app.js"
    file2.write_text(
        """function greet() {
    console.log("Hello");
}

function farewell() {
    console.log("Goodbye");
}

class App {
    constructor() {
        this.name = "App";
    }
}
""",
        encoding="utf-8",
    )

    return {"file1": file1, "file2": file2}


class TestBatchMode:
    """Tests for batch mode extraction."""

    def test_batch_single_file_multiple_sections(self, sample_files):
        """Test extracting multiple sections from one file."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(sample_files["file1"]),
                        "sections": [
                            {"start_line": 1, "end_line": 2, "label": "hello function"},
                            {"start_line": 4, "end_line": 5, "label": "world function"},
                        ],
                    }
                ]
            }
        )

        assert result["success"] is True
        assert result["count_files"] == 1
        assert result["count_sections"] == 2
        assert len(result["results"]) == 1
        assert len(result["results"][0]["sections"]) == 2

        # Check first section
        sec1 = result["results"][0]["sections"][0]
        assert sec1["label"] == "hello function"
        assert "def hello():" in sec1["content"]

        # Check second section
        sec2 = result["results"][0]["sections"][1]
        assert sec2["label"] == "world function"
        assert "def world():" in sec2["content"]

    def test_batch_multiple_files(self, sample_files):
        """Test extracting from multiple files."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(sample_files["file1"]),
                        "sections": [{"start_line": 1, "end_line": 2, "label": "python hello"}],
                    },
                    {
                        "file_path": str(sample_files["file2"]),
                        "sections": [{"start_line": 1, "end_line": 3, "label": "js greet"}],
                    },
                ]
            }
        )

        assert result["success"] is True
        assert result["count_files"] == 2
        assert result["count_sections"] == 2

        # Check Python file section
        assert "def hello():" in result["results"][0]["sections"][0]["content"]

        # Check JavaScript file section
        assert "function greet()" in result["results"][1]["sections"][0]["content"]

    def test_batch_with_errors_partial_success(self, sample_files):
        """Test batch mode with some errors (partial success)."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(sample_files["file1"]),
                        "sections": [{"start_line": 1, "end_line": 2, "label": "valid section"}],
                    },
                    {
                        "file_path": "/nonexistent/file.py",
                        "sections": [{"start_line": 1, "end_line": 10}],
                    },
                ],
                "fail_fast": False,
            }
        )

        assert result["success"] is True  # Partial success
        assert result["count_sections"] == 1  # Only one succeeded
        assert result["errors_summary"]["errors"] == 1

    def test_batch_fail_fast(self, sample_files):
        """Test batch mode with fail_fast=True."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {"file_path": "/nonexistent/file.py", "sections": [{"start_line": 1}]}
                ],
                "fail_fast": True,
            }
        )

        assert result["success"] is False
        assert "error" in result


class TestTokenProtection:
    """Tests for token explosion protection."""

    def test_suppress_content(self, sample_files):
        """Test suppress_content to save tokens."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "file_path": str(sample_files["file1"]),
                "start_line": 1,
                "end_line": 5,
                "suppress_content": True,
            }
        )

        assert result["success"] is True
        assert "content" not in result
        assert result["content_suppressed"] is True
        assert result["content_length"] > 0  # Metadata still present
        assert result["lines_extracted"] == 5

    def test_max_content_length_truncation(self, tmp_path):
        """Test max_content_length truncates long content."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        # Create file with long content
        large_file = tmp_path / "large.py"
        content = "# " + ("x" * 1000) + "\n" * 50
        large_file.write_text(content, encoding="utf-8")

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {"file_path": str(large_file), "start_line": 1, "max_content_length": 100}
        )

        assert result["success"] is True
        assert result["truncated"] is True
        assert result["truncated_length"] == 100 + len("\n... [truncated]")
        assert result["content_length"] > 100  # Original length
        assert "[truncated]" in result["content"]


class TestSafetyLimits:
    """Tests for batch mode safety limits."""

    def test_max_files_limit_with_truncate(self, tmp_path):
        """Test max_files limit with allow_truncate."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import BATCH_LIMITS, ExtractCodeSectionTool

        # Create many small files
        files = []
        for i in range(BATCH_LIMITS["max_files"] + 5):
            f = tmp_path / f"file{i}.py"
            f.write_text(f"# File {i}\n", encoding="utf-8")
            files.append(f)

        tool = ExtractCodeSectionTool()

        # With allow_truncate, should succeed but truncate
        result = tool.execute(
            {
                "requests": [{"file_path": str(f), "sections": [{"start_line": 1}]} for f in files],
                "allow_truncate": True,
            }
        )

        assert result["success"] is True
        assert result["truncated"] is True
        assert result["count_files"] == BATCH_LIMITS["max_files"]

    def test_max_files_limit_without_truncate(self, tmp_path):
        """Test max_files limit fails without allow_truncate."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import BATCH_LIMITS, ExtractCodeSectionTool

        # Create many small files
        files = []
        for i in range(BATCH_LIMITS["max_files"] + 5):
            f = tmp_path / f"file{i}.py"
            f.write_text(f"# File {i}\n", encoding="utf-8")
            files.append(f)

        tool = ExtractCodeSectionTool()

        # Without allow_truncate, should fail
        result = tool.execute(
            {
                "requests": [{"file_path": str(f), "sections": [{"start_line": 1}]} for f in files],
                "allow_truncate": False,
            }
        )

        assert result["success"] is False
        assert "Too many files" in result["error"]

    def test_batch_limits_in_response(self, sample_files):
        """Test that batch response includes limits information."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(sample_files["file1"]),
                        "sections": [{"start_line": 1, "end_line": 2}],
                    }
                ]
            }
        )

        assert result["success"] is True
        assert "limits" in result
        assert result["limits"]["max_files"] == 20
        assert result["limits"]["max_sections_per_file"] == 50
        assert result["limits"]["max_total_bytes"] == 1024 * 1024


class TestBackwardCompatibility:
    """Tests to ensure single mode still works (backward compatibility)."""

    def test_single_mode_still_works(self, sample_files):
        """Test that original single mode still functions correctly."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {"file_path": str(sample_files["file1"]), "start_line": 1, "end_line": 2}
        )

        assert result["success"] is True
        assert "content" in result
        assert "def hello():" in result["content"]
        # Should NOT have batch mode fields
        assert "count_files" not in result
        assert "count_sections" not in result

    def test_mutual_exclusion_single_batch(self, sample_files):
        """Test that single and batch mode parameters are mutually exclusive."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "file_path": str(sample_files["file1"]),
                "start_line": 1,
                "requests": [
                    {"file_path": str(sample_files["file2"]), "sections": [{"start_line": 1}]}
                ],
            }
        )

        assert result["success"] is False
        assert "mutually exclusive" in result["error"]
