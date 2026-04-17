#!/usr/bin/env python3
"""
Integration tests for PR Summary MCP Tool.
"""

import asyncio

import pytest

from tree_sitter_analyzer.mcp.tool_registration import register_all_tools
from tree_sitter_analyzer.mcp.tools.pr_summary_tool import PRSummaryTool


@pytest.fixture
def pr_summary_tool(project_root: str) -> PRSummaryTool:
    """Create PR Summary tool instance."""
    return PRSummaryTool(project_root)


@pytest.fixture
def sample_diff() -> str:
    """Sample git diff for testing."""
    return """diff --git a/src/main.py b/src/main.py
index abc123..def456 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,5 +1,10 @@
 def hello():
-    print("Hello")
+    print("Hello World")
+
+def greet(name):
+    return f"Hello, {name}!"

diff --git a/README.md b/README.md
index 111..222 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,5 @@
 # My Project

+## Usage
+Run with python main.py
diff --git a/tests/test_main.py b/tests/test_main.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/tests/test_main.py
@@ -0,0 +1,5 @@
+def test_hello():
+    assert True
"""


@pytest.mark.asyncio
async def test_pr_summary_basic(pr_summary_tool: PRSummaryTool, sample_diff: str) -> None:
    """Test basic PR summary generation."""
    arguments = {
        "diff_input": sample_diff,
        "output_format": "markdown",
        "semantic_analysis": False,  # Disable for faster test
    }

    result = await pr_summary_tool.execute(arguments)

    assert "content" in result
    content = result["content"][0]["text"]

    # Check for key elements
    assert "Pull Request Summary" in content
    assert "Files changed:" in content
    assert "3" in content  # 3 files changed


@pytest.mark.asyncio
async def test_pr_summary_json_format(pr_summary_tool: PRSummaryTool, sample_diff: str) -> None:
    """Test PR summary in JSON format."""
    arguments = {
        "diff_input": sample_diff,
        "output_format": "json",
        "semantic_analysis": False,
    }

    result = await pr_summary_tool.execute(arguments)

    assert "result" in result
    data = result["result"]

    # Check structure
    assert "pr_type" in data
    assert "summary" in data
    assert "categories" in data
    assert data["summary"]["files_changed"] == 3


@pytest.mark.asyncio
async def test_pr_summary_toon_format(pr_summary_tool: PRSummaryTool, sample_diff: str) -> None:
    """Test PR summary in TOON format."""
    arguments = {
        "diff_input": sample_diff,
        "output_format": "toon",
        "semantic_analysis": False,
    }

    result = await pr_summary_tool.execute(arguments)

    assert "content" in result
    content = result["content"][0]["text"]

    # Check for TOON-style formatting
    assert "📋" in content or "Pull Request" in content


@pytest.mark.asyncio
async def test_pr_summary_categorization(pr_summary_tool: PRSummaryTool, sample_diff: str) -> None:
    """Test change categorization."""
    arguments = {
        "diff_input": sample_diff,
        "output_format": "json",
        "semantic_analysis": False,
    }

    result = await pr_summary_tool.execute(arguments)
    data = result["result"]

    # Should categorize files correctly
    categories = data["categories"]
    category_names = [c["category"] for c in categories]

    # README.md should be docs
    assert any("README.md" in c["file_path"] and c["category"] in ("docs", "unknown") for c in categories)
    # tests/test_main.py should be test
    assert any("test_main.py" in c["file_path"] and c["category"] == "test" for c in categories)


@pytest.mark.asyncio
async def test_pr_summary_empty_diff(pr_summary_tool: PRSummaryTool) -> None:
    """Test handling of empty diff."""
    arguments = {
        "diff_input": "",
        "output_format": "json",
        "semantic_analysis": False,
    }

    result = await pr_summary_tool.execute(arguments)
    data = result["result"]

    # Empty diff should have 0 files
    assert data["summary"]["files_changed"] == 0
    assert data["summary"]["lines_added"] == 0
    assert data["summary"]["lines_deleted"] == 0


def test_pr_summary_validate_arguments(pr_summary_tool: PRSummaryTool) -> None:
    """Test argument validation."""
    # Valid formats
    for fmt in ("markdown", "json", "toon"):
        assert pr_summary_tool.validate_arguments({"output_format": fmt}) is True

    # Invalid format
    with pytest.raises(ValueError, match="Invalid output_format"):
        pr_summary_tool.validate_arguments({"output_format": "invalid"})


@pytest.mark.asyncio
async def test_tool_registration(project_root: str) -> None:
    """Test that PR Summary tool is properly registered."""
    register_all_tools(project_root)

    from tree_sitter_analyzer.mcp.registry import get_registry

    registry = get_registry()
    tool = registry.get_tool("pr_summary")

    assert tool is not None
    assert tool.name == "pr_summary"
    assert tool.toolset == "diagnostic"
    assert tool.category == "git-analysis"
    assert tool.emoji == "📋"


@pytest.mark.asyncio
async def test_pr_summary_lines_calculation(pr_summary_tool: PRSummaryTool) -> None:
    """Test line change calculation."""
    diff = """diff --git a/file.py b/file.py
index 111..222 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,6 @@
 def old_func():
     pass
+
+def new_func():
+    pass
"""

    arguments = {
        "diff_input": diff,
        "output_format": "json",
        "semantic_analysis": False,
    }

    result = await pr_summary_tool.execute(arguments)
    data = result["result"]

    # 2 lines added (the blank line + new_func line)
    assert data["summary"]["lines_added"] > 0
