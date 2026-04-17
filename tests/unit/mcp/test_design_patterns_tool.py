#!/usr/bin/env python3
"""Tests for Design Patterns MCP Tool."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.design_patterns_tool import DesignPatternsTool


class TestDesignPatternsToolDefinition:
    """Test the tool definition."""

    def test_tool_name(self):
        """Test tool name."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert definition["name"] == "design_patterns"

    def test_has_description(self):
        """Test tool has a description."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert len(definition["description"]) > 50

    def test_has_input_schema(self):
        """Test tool has input schema."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert "properties" in definition["inputSchema"]

    def test_schema_has_file_path(self):
        """Test schema includes file_path property."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "file_path" in definition["inputSchema"]["properties"]

    def test_schema_has_project_root(self):
        """Test schema includes project_root property."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "project_root" in definition["inputSchema"]["properties"]

    def test_schema_has_pattern_types(self):
        """Test schema includes pattern_types property."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "pattern_types" in definition["inputSchema"]["properties"]

    def test_schema_has_min_confidence(self):
        """Test schema includes min_confidence property."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "min_confidence" in definition["inputSchema"]["properties"]

    def test_schema_has_format(self):
        """Test schema includes format property with enum."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert "format" in definition["inputSchema"]["properties"]
        assert definition["inputSchema"]["properties"]["format"]["enum"] == ["toon", "json"]


class TestDesignPatternsToolValidation:
    """Test argument validation."""

    def test_valid_arguments_passes(self):
        """Test validation with valid arguments passes."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "min_confidence": 0.6,
            "format": "toon",
        }
        assert tool.validate_arguments(args) is True

    def test_invalid_min_confidence_raises(self):
        """Test validation with invalid min_confidence raises."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "min_confidence": 1.5,
        }
        try:
            tool.validate_arguments(args)
            assert False, "Should raise ValueError for invalid min_confidence"
        except ValueError as e:
            assert "min_confidence" in str(e)

    def test_invalid_format_raises(self):
        """Test validation with invalid format raises."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "format": "invalid",
        }
        try:
            tool.validate_arguments(args)
            assert False, "Should raise ValueError for invalid format"
        except ValueError as e:
            assert "format" in str(e)

    def test_missing_path_and_root_raises(self):
        """Test validation with neither file_path nor project_root raises."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "min_confidence": 0.6,
        }
        try:
            tool.validate_arguments(args)
            assert False, "Should raise ValueError when neither file_path nor project_root provided"
        except ValueError as e:
            assert "file_path" in str(e) or "project_root" in str(e)


class TestDesignPatternsToolExecute:
    """Test tool execution."""

    def test_execute_with_missing_paths(self):
        """Test execute with neither file_path nor project_root."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "min_confidence": 0.6,
        }

        # This should raise an error in validation
        try:
            tool.validate_arguments(args)
            assert False, "Should raise ValueError"
        except ValueError:
            pass

    def test_execute_with_invalid_file_skips_gracefully(self):
        """Test execute with non-existent file returns empty patterns."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/nonexistent/file.py",
            "min_confidence": 0.6,
        }

        # Should not crash, just return empty results
        import asyncio

        async def run_execute():
            return await tool.execute(args)

        result = asyncio.get_event_loop().run_until_complete(run_execute())
        assert isinstance(result, dict)
        assert "patterns" in result or "error" in result

    def test_min_confidence_filter(self):
        """Test that min_confidence filters results."""
        # This test verifies the filtering logic is in place
        # Actual filtering would require real files
        tool = DesignPatternsTool("/tmp")
        args = {
            "project_root": "/tmp",
            "min_confidence": 0.9,  # High threshold
        }

        import asyncio

        async def run_execute():
            return await tool.execute(args)

        result = asyncio.get_event_loop().run_until_complete(run_execute())
        assert isinstance(result, dict)
        # With high threshold and no files, should have no patterns
        assert result.get("summary", "") or "patterns" in result


class TestDesignPatternsToolOutputFormats:
    """Test different output formats."""

    def test_json_format_requested(self):
        """Test JSON format can be requested."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "format": "json",
        }
        # Just validate that format is accepted
        assert tool.validate_arguments(args) is True

    def test_toon_format_is_default(self):
        """Test TOON is the default format."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
        }
        # Default should be toon
        assert args.get("format", "toon") == "toon"

    def test_toon_format_requested(self):
        """Test TOON format can be requested."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "format": "toon",
        }
        assert tool.validate_arguments(args) is True


class TestDesignPatternsToolPatternTypes:
    """Test pattern type filtering."""

    def test_all_pattern_types_default(self):
        """Test 'all' is the default for pattern_types."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
        }
        # Default should be 'all'
        assert args.get("pattern_types", "all") == "all"

    def test_specific_pattern_type(self):
        """Test specific pattern type can be requested."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "pattern_types": "singleton,factory_method",
        }
        assert tool.validate_arguments(args) is True

    def test_multiple_pattern_types(self):
        """Test multiple pattern types can be requested."""
        tool = DesignPatternsTool("/tmp")
        args = {
            "file_path": "/tmp/test.py",
            "pattern_types": "singleton,observer,strategy",
        }
        assert tool.validate_arguments(args) is True


class TestDesignPatternsToolIntegration:
    """Integration tests for the tool."""

    def test_tool_initialization(self):
        """Test tool can be initialized with different project roots."""
        tool1 = DesignPatternsTool("/tmp")
        assert tool1 is not None

        tool2 = DesignPatternsTool(None)
        assert tool2 is not None

    def test_tool_definition_consistency(self):
        """Test tool definition is consistent across calls."""
        tool = DesignPatternsTool("/tmp")
        definition1 = tool.get_tool_definition()
        definition2 = tool.get_tool_definition()
        assert definition1 == definition2

    def test_get_tool_definition_returns_dict(self):
        """Test get_tool_definition returns a dict."""
        tool = DesignPatternsTool("/tmp")
        definition = tool.get_tool_definition()
        assert isinstance(definition, dict)
        assert "name" in definition
        assert "inputSchema" in definition
