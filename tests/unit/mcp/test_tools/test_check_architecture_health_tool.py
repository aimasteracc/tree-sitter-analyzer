#!/usr/bin/env python3
"""Tests for check_architecture_health MCP tool."""

import pytest

from tree_sitter_analyzer.mcp.tools.check_architecture_health_tool import (
    CheckArchitectureHealthTool,
)


@pytest.fixture
def tool():
    return CheckArchitectureHealthTool(project_root="/tmp/test")


class TestCheckArchitectureHealthToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "check_architecture_health"

    def test_path_required(self, tool):
        assert "path" in tool.get_tool_definition()["inputSchema"]["required"]

    def test_has_checks_param(self, tool):
        schema = tool.get_tool_definition()["inputSchema"]
        assert "checks" in schema["properties"]


class TestCheckArchitectureHealthToolValidation:
    def test_valid_args(self, tool):
        assert tool.validate_arguments({"path": "src/"})

    def test_missing_path(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({})


class TestCheckArchitectureHealthToolExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_dict(self, tool):
        result = await tool.execute({"path": "src/"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_has_score(self, tool):
        result = await tool.execute({"path": "src/"})
        assert "data" in result
        assert "score" in result["data"]


class TestValidChecksContainsNewChecks:
    """Verify VALID_CHECKS includes stability_metrics and hotspots."""

    def test_stability_metrics_in_valid_checks(self, tool):
        schema_str = str(tool.get_tool_definition())
        assert "stability_metrics" in schema_str

    def test_hotspots_in_valid_checks(self, tool):
        schema_str = str(tool.get_tool_definition())
        assert "hotspots" in schema_str


class TestLayerRulesValidation:
    """layer_rules format validation and documentation - Bug 3."""

    def test_layer_rules_invalid_type_raises(self, tool):
        """layer_rules must be a dict, not a list."""
        with pytest.raises(ValueError, match="layer_rules"):
            tool.validate_arguments(
                {"path": "src/", "layer_rules": ["services", "models"]}
            )

    def test_layer_rules_invalid_inner_structure_raises(self, tool):
        """Each layer value must have 'allowed_deps' key."""
        with pytest.raises(ValueError, match="allowed_deps"):
            tool.validate_arguments(
                {"path": "src/", "layer_rules": {"services": ["models"]}}
            )

    def test_layer_rules_valid_format_accepted(self, tool):
        """Correct format must pass validation without raising."""
        result = tool.validate_arguments({
            "path": "src/",
            "layer_rules": {
                "services": {"allowed_deps": ["models", "utils"]},
                "models": {"allowed_deps": ["utils"]},
            },
        })
        assert result is True

    def test_layer_rules_schema_description_contains_example(self, tool):
        """Tool schema must document layer_rules format with an example."""
        defn = tool.get_tool_definition()
        layer_rules_schema = (
            defn.get("inputSchema", {})
            .get("properties", {})
            .get("layer_rules", {})
        )
        description = layer_rules_schema.get("description", "")
        assert "allowed_deps" in description
        assert "example" in description.lower() or "{" in description
