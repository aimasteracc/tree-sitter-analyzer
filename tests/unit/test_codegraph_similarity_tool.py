"""Tests for codegraph_similarity MCP tool — AST-structural clone detection."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.code_similarity_tool import (
    CodeGraphSimilarityTool as CodeSimilarityTool,
)


@pytest.fixture
def tool():
    return CodeSimilarityTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "a.py").write_text(
        "def process(x):\n    return x * 2\n\ndef handle(x):\n    return x * 2\n"
    )
    return CodeSimilarityTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_similarity"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"all", "structural", "textual"}
        assert mode["default"] == "all"

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )


@pytest.fixture
def tool_with_clones(tmp_path):
    """Project with two structurally identical 5-line functions (guaranteed clone group).

    Each function body is >= 5 lines so it clears the default min_lines=5 threshold.
    """
    body = (
        "def process(x):\n"
        "    if x > 0:\n"
        "        y = x * 2\n"
        "        z = y + 1\n"
        "        return z\n"
        "    return 0\n"
        "\n"
        "def handle(x):\n"
        "    if x > 0:\n"
        "        y = x * 2\n"
        "        z = y + 1\n"
        "        return z\n"
        "    return 0\n"
    )
    (tmp_path / "a.py").write_text(body)
    return CodeSimilarityTool(str(tmp_path))


@pytest.mark.asyncio
class TestExecute:
    async def test_runs_on_project(self, tool_with_root):
        result = await tool_with_root.execute({"output_format": "json"})
        assert result["success"] is True

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result


class TestIncludeBodiesSchema:
    """include_bodies param is declared in the inner tool's schema."""

    def test_include_bodies_in_schema(self, tool):
        props = tool.get_tool_schema()["properties"]
        assert "include_bodies" in props, (
            "include_bodies must be declared in the tool schema "
            "so it survives _project_args projection through the facade"
        )

    def test_include_bodies_default_false(self, tool):
        prop = tool.get_tool_schema()["properties"]["include_bodies"]
        assert prop.get("default") is False

    def test_schema_description_mentions_summary(self, tool):
        """Description must state that default is summary / bodies require include_bodies."""
        desc = tool.get_tool_definition()["description"]
        assert "summary" in desc.lower() or "include_bodies" in desc, (
            "Description must mention summary-by-default or include_bodies"
        )


@pytest.mark.asyncio
class TestSummaryDefaultNoBodies:
    """Default response must NOT include code snippets in function entries."""

    async def test_default_no_snippet_in_functions(self, tool_with_clones):
        """Default: function entries must not have 'snippet' key; groups must be non-empty."""
        result = await tool_with_clones.execute({"output_format": "json"})
        assert result["success"] is True
        groups = result.get("groups", [])
        assert len(groups) > 0, (
            "Expected at least one clone group with tool_with_clones fixture"
        )
        for group in groups:
            for func in group.get("functions", []):
                assert "snippet" not in func, (
                    f"snippet must be absent by default (include_bodies not set); "
                    f"got func={func}"
                )

    async def test_include_bodies_true_has_snippet(self, tool_with_clones):
        """include_bodies=True: function entries must have 'snippet' key."""
        result = await tool_with_clones.execute(
            {"output_format": "json", "include_bodies": True}
        )
        assert result["success"] is True
        groups = result.get("groups", [])
        assert len(groups) > 0, "Expected at least one clone group"
        for group in groups:
            for func in group.get("functions", []):
                assert "snippet" in func, (
                    f"snippet must be present when include_bodies=True; got func={func}"
                )

    async def test_default_response_smaller_than_with_bodies(self, tool_with_clones):
        """Summary response (no bodies) must produce fewer bytes than include_bodies=True."""
        import json

        result_summary = await tool_with_clones.execute({"output_format": "json"})
        result_full = await tool_with_clones.execute(
            {"output_format": "json", "include_bodies": True}
        )
        summary_bytes = len(json.dumps(result_summary, ensure_ascii=False))
        full_bytes = len(json.dumps(result_full, ensure_ascii=False))
        assert summary_bytes < full_bytes, (
            f"Summary ({summary_bytes}B) must be smaller than with-bodies ({full_bytes}B)"
        )


@pytest.mark.asyncio
class TestFacadeIncludeBodiesSurvivesRouting:
    """include_bodies must survive _project_args projection through the viz facade."""

    async def test_include_bodies_survives_facade_routing(self, tmp_path):
        """via the viz facade: include_bodies=True reaches the inner tool."""
        from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

        (tmp_path / "a.py").write_text(
            "def process(x):\n"
            "    if x > 0:\n"
            "        y = x * 2\n"
            "        z = y + 1\n"
            "        return z\n"
            "    return 0\n"
            "\n"
            "def handle(x):\n"
            "    if x > 0:\n"
            "        y = x * 2\n"
            "        z = y + 1\n"
            "        return z\n"
            "    return 0\n"
        )
        facade = build_viz_facade(str(tmp_path))
        result = await facade.execute(
            {
                "action": "similarity",
                "output_format": "json",
                "include_bodies": True,
            }
        )
        assert result.get("success") is True
        groups = result.get("groups", [])
        assert len(groups) > 0, "Expected at least one clone group via facade"
        for group in groups:
            for func in group.get("functions", []):
                assert "snippet" in func, (
                    "include_bodies=True must survive facade _project_args routing"
                )

    async def test_facade_default_no_bodies(self, tmp_path):
        """via the viz facade: default (no include_bodies) must strip snippets."""
        from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

        (tmp_path / "a.py").write_text(
            "def process(x):\n"
            "    if x > 0:\n"
            "        y = x * 2\n"
            "        z = y + 1\n"
            "        return z\n"
            "    return 0\n"
            "\n"
            "def handle(x):\n"
            "    if x > 0:\n"
            "        y = x * 2\n"
            "        z = y + 1\n"
            "        return z\n"
            "    return 0\n"
        )
        facade = build_viz_facade(str(tmp_path))
        result = await facade.execute({"action": "similarity", "output_format": "json"})
        assert result.get("success") is True
        groups = result.get("groups", [])
        for group in groups:
            for func in group.get("functions", []):
                assert "snippet" not in func, (
                    "snippet must not appear in facade default (summary) response"
                )
