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
        assert len(groups) == 2  # tool_with_clones fixture: exactly 2 groups
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
        assert len(groups) == 2  # tool_with_clones fixture: exactly 2 groups
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
        assert len(groups) == 2  # same fixture via facade: exactly 2 groups
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


# ---------------------------------------------------------------------------
# Issue #801 — bounding params + compact cap + type coercion
# ---------------------------------------------------------------------------


def _large_group_fixture_body() -> str:
    """Generate 15 structurally identical 5-line functions for cap tests."""
    parts = []
    for i in range(15):
        parts.append(
            f"def func_{i:02d}(x):\n"
            "    if x > 0:\n"
            "        y = x * 2\n"
            "        z = y + 1\n"
            "        return z\n"
            "    return 0\n\n"
        )
    return "".join(parts)


@pytest.fixture
def tool_with_large_group(tmp_path):
    """Project with 15 structurally identical functions in one file."""
    (tmp_path / "large.py").write_text(_large_group_fixture_body())
    return CodeSimilarityTool(str(tmp_path))


@pytest.mark.asyncio
class TestBoundingParams801:
    """Issue #801 — max_groups / functions-cap / type coercion."""

    async def test_max_groups_limits_output(self, tool_with_clones):
        """max_groups=1 must limit the groups list to exactly 1 entry."""
        result = await tool_with_clones.execute(
            {"output_format": "json", "max_groups": 1}
        )
        assert result["success"] is True
        assert len(result["groups"]) == 1

    async def test_max_groups_string_coercion(self, tool_with_clones):
        """max_groups passed as a string (MCP transport) must be coerced to int."""
        result = await tool_with_clones.execute(
            {"output_format": "json", "max_groups": "1"}
        )
        assert result["success"] is True
        assert len(result["groups"]) == 1

    async def test_min_lines_string_coercion(self, tool_with_clones):
        """min_lines passed as string must not crash — coerced to int."""
        result = await tool_with_clones.execute(
            {"output_format": "json", "min_lines": "5"}
        )
        assert result["success"] is True

    async def test_min_group_size_string_coercion(self, tool_with_clones):
        """min_group_size passed as string must not crash — coerced to int."""
        result = await tool_with_clones.execute(
            {"output_format": "json", "min_group_size": "2"}
        )
        assert result["success"] is True

    async def test_compact_large_group_capped_at_10(self, tool_with_large_group):
        """Compact mode (include_bodies=False) must cap functions[] to 10 entries."""
        result = await tool_with_large_group.execute({"output_format": "json"})
        assert result["success"] is True
        groups = result["groups"]
        assert len(groups) == 1  # 15 identical funcs → exactly 1 clone group
        for group in groups:
            funcs = group["functions"]
            assert len(funcs) == 10, (
                f"Expected exactly 10 functions (capped); got {len(funcs)}"
            )
            assert group.get("truncated") is True, (
                "truncated flag must be True when functions[] was capped"
            )

    async def test_include_bodies_true_not_capped(self, tool_with_large_group):
        """include_bodies=True must NOT cap functions[] — all 15 returned."""
        result = await tool_with_large_group.execute(
            {"output_format": "json", "include_bodies": True}
        )
        assert result["success"] is True
        groups = result["groups"]
        assert len(groups) == 1  # 15 identical funcs → exactly 1 clone group
        max_funcs = max(len(g["functions"]) for g in groups)
        assert max_funcs == 15, (
            f"include_bodies=True should return all 15 functions; got max={max_funcs}"
        )

    async def test_no_truncated_flag_when_under_10(self, tool_with_clones):
        """When group has <= 10 functions, truncated flag must be absent or False."""
        result = await tool_with_clones.execute({"output_format": "json"})
        assert result["success"] is True
        for group in result["groups"]:
            assert not group.get("truncated"), (
                "truncated must not be set when functions count <= 10"
            )


class TestFacadeSchemaExposesSimilarityParams801:
    """Issue #801 — similarity bounding params must be discoverable in the viz facade schema."""

    def test_viz_facade_schema_exposes_max_groups(self):
        """max_groups must appear in the viz facade's public schema."""
        from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

        facade = build_viz_facade(project_root=None)
        schema = facade.get_tool_schema()
        assert "max_groups" in schema["properties"], (
            "max_groups must be in viz facade schema for agent discoverability"
        )

    def test_viz_facade_schema_exposes_min_lines(self):
        """min_lines must appear in the viz facade's public schema."""
        from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

        facade = build_viz_facade(project_root=None)
        schema = facade.get_tool_schema()
        assert "min_lines" in schema["properties"], (
            "min_lines must be in viz facade schema for agent discoverability"
        )

    def test_viz_facade_schema_exposes_min_group_size(self):
        """min_group_size must appear in the viz facade's public schema."""
        from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

        facade = build_viz_facade(project_root=None)
        schema = facade.get_tool_schema()
        assert "min_group_size" in schema["properties"], (
            "min_group_size must be in viz facade schema for agent discoverability"
        )


@pytest.mark.asyncio
class TestFacadeRoutesSimilarityParams801:
    """Issue #801 — similarity params must route through the viz facade correctly."""

    async def test_max_groups_via_facade(self, tmp_path):
        """max_groups=1 passed via viz facade must limit groups to exactly 1."""
        from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

        (tmp_path / "a.py").write_text(_large_group_fixture_body())
        facade = build_viz_facade(str(tmp_path))
        result = await facade.execute(
            {"action": "similarity", "output_format": "json", "max_groups": 1}
        )
        assert result["success"] is True
        assert len(result["groups"]) == 1
