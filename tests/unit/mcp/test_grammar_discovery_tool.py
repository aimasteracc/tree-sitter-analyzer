"""
Unit tests for GrammarDiscoveryTool.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.grammar_discovery_tool import GrammarDiscoveryTool


class TestGrammarDiscoveryTool:
    """Test GrammarDiscoveryTool class."""

    @pytest.fixture
    def tool(self) -> GrammarDiscoveryTool:
        """Get GrammarDiscoveryTool instance."""
        return GrammarDiscoveryTool()

    def test_name(self, tool: GrammarDiscoveryTool) -> None:
        """Test tool name."""
        assert tool.name == "grammar_discovery"

    def test_description_exists(self, tool: GrammarDiscoveryTool) -> None:
        """Test that description exists in schema."""
        schema = tool.get_schema()
        assert schema.get("description", "")
        assert "introspection" in schema.get("description", "").lower()

    def test_get_schema_returns_dict(self, tool: GrammarDiscoveryTool) -> None:
        """Test that get_schema returns a dictionary."""
        schema = tool.get_schema()
        assert isinstance(schema, dict)

    def test_get_schema_contains_required_properties(
        self, tool: GrammarDiscoveryTool,
    ) -> None:
        """Test that schema contains required properties."""
        schema = tool.get_schema()
        assert "properties" in schema
        assert "required" in schema

        required_props = schema["required"]
        assert "project_root" in required_props
        assert "language" in required_props
        assert "operation" in required_props

    def test_get_schema_operation_enum(self, tool: GrammarDiscoveryTool) -> None:
        """Test that operation property has correct enum values."""
        schema = tool.get_schema()
        operation_prop = schema["properties"]["operation"]
        assert operation_prop["type"] == "string"
        assert "enum" in operation_prop

        enum_values = operation_prop["enum"]
        expected = ["summary", "node_types", "fields", "wrappers", "paths"]
        for val in expected:
            assert val in enum_values

    def test_get_schema_output_format_enum(self, tool: GrammarDiscoveryTool) -> None:
        """Test that output_format property has correct enum values."""
        schema = tool.get_schema()
        format_prop = schema["properties"]["output_format"]
        assert format_prop["type"] == "string"
        assert "enum" in format_prop

        enum_values = format_prop["enum"]
        assert "toon" in enum_values
        assert "json" in enum_values

    @patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.PluginRegistry")
    def test_execute_unsupported_language(
        self, mock_registry: MagicMock, tool: GrammarDiscoveryTool,
    ) -> None:
        """Test execute with unsupported language."""
        mock_instance = MagicMock()
        mock_registry.return_value = mock_instance
        mock_instance.discover.return_value = mock_instance
        mock_instance.load.side_effect = ValueError("Unsupported language: xyz")

        result = tool._execute_sync(
            project_root="/tmp/test",
            language="xyz",
            operation="summary",
        )

        assert result["success"] is False
        assert "error" in result

    @patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.PluginRegistry")
    def test_execute_summary_operation(
        self, mock_registry: MagicMock, tool: GrammarDiscoveryTool,
    ) -> None:
        """Test execute with summary operation."""
        mock_lang = MagicMock()
        mock_instance = MagicMock()
        mock_registry.return_value = mock_instance
        mock_instance.discover.return_value = mock_instance
        mock_instance.load.return_value = mock_lang

        # Mock introspector
        with patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.GrammarIntrospector") as mock_intro:
            mock_intro_instance = MagicMock()
            mock_intro.return_value = mock_intro_instance
            mock_intro_instance.get_summary.return_value = {
                "total_node_types": 275,
                "total_fields": 31,
                "wrapper_candidates": 5,
            }

            result = tool._execute_sync(
                project_root="/tmp/test",
                language="python",
                operation="summary",
            )

            assert result["success"] is True
            assert "summary" in result
            assert result["language"] == "python"

    @patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.PluginRegistry")
    def test_execute_node_types_operation(
        self, mock_registry: MagicMock, tool: GrammarDiscoveryTool,
    ) -> None:
        """Test execute with node_types operation."""
        mock_lang = MagicMock()
        mock_instance = MagicMock()
        mock_registry.return_value = mock_instance
        mock_instance.discover.return_value = mock_instance
        mock_instance.load.return_value = mock_lang

        with patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.GrammarIntrospector") as mock_intro:
            mock_intro_instance = MagicMock()
            mock_intro.return_value = mock_intro_instance
            mock_node_type = MagicMock()
            mock_node_type.to_dict.return_value = {
                "kind_id": 1,
                "kind_name": "function_definition",
            }
            mock_intro_instance.enumerate_node_types.return_value = [mock_node_type]

            result = tool._execute_sync(
                project_root="/tmp/test",
                language="python",
                operation="node_types",
            )

            assert result["success"] is True
            assert "node_types" in result
            assert result["total_count"] == 1

    @patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.PluginRegistry")
    def test_execute_wrappers_operation(
        self, mock_registry: MagicMock, tool: GrammarDiscoveryTool,
    ) -> None:
        """Test execute with wrappers operation."""
        mock_lang = MagicMock()
        mock_instance = MagicMock()
        mock_registry.return_value = mock_instance
        mock_instance.discover.return_value = mock_instance
        mock_instance.load.return_value = mock_lang

        with patch("tree_sitter_analyzer.mcp.tools.grammar_discovery_tool.GrammarIntrospector") as mock_intro:
            mock_intro_instance = MagicMock()
            mock_intro.return_value = mock_intro_instance
            mock_wrapper = MagicMock()
            mock_wrapper.to_dict.return_value = {
                "node_type": "decorated_definition",
                "confidence": 50,
            }
            mock_intro_instance.heuristic_wrapper_detection.return_value = [mock_wrapper]

            result = tool._execute_sync(
                project_root="/tmp/test",
                language="python",
                operation="wrappers",
            )

            assert result["success"] is True
            assert "wrappers" in result
            assert result["total_count"] == 1

    def test_format_toon_with_summary(self, tool: GrammarDiscoveryTool) -> None:
        """Test TOON formatting with summary."""
        result = {
            "language": "python",
            "operation": "summary",
            "summary": {
                "total_node_types": 275,
                "total_fields": 31,
                "wrapper_candidates": 5,
            },
        }

        toon = tool.format_toon(result)

        assert "Grammar Discovery" in toon
        assert "Operation: summary" in toon
        assert "275" in toon

    def test_format_toon_with_node_types(self, tool: GrammarDiscoveryTool) -> None:
        """Test TOON formatting with node types."""
        result = {
            "language": "python",
            "operation": "node_types",
            "total_count": 2,
            "node_types": [
                {"kind_name": "function_definition", "kind_id": 1},
                {"kind_name": "class_definition", "kind_id": 2},
            ],
        }

        toon = tool.format_toon(result)

        assert "Node Types" in toon
        assert "Total: 2" in toon
        assert "function_definition" in toon
        assert "class_definition" in toon

    def test_format_toon_with_wrappers(self, tool: GrammarDiscoveryTool) -> None:
        """Test TOON formatting with wrappers."""
        result = {
            "language": "python",
            "operation": "wrappers",
            "total_count": 1,
            "wrappers": [
                {"node_type": "decorated_definition", "confidence": 50},
            ],
        }

        toon = tool.format_toon(result)

        assert "Wrapper Candidates" in toon
        assert "Total: 1" in toon
        assert "decorated_definition" in toon

    def test_format_toon_with_error(self, tool: GrammarDiscoveryTool) -> None:
        """Test TOON formatting with error."""
        result = {
            "language": "xyz",
            "operation": "summary",
            "success": False,
            "error": "Unsupported language: xyz",
        }

        toon = tool.format_toon(result)

        assert "Error" in toon
        assert "Unsupported language" in toon

    def test_find_code_files_python(self, tool: GrammarDiscoveryTool, tmp_path: str) -> None:
        """Test _find_code_files for Python."""
        from pathlib import Path

        # Create test Python files
        test_dir = Path(tmp_path) / "test_project"
        test_dir.mkdir()
        (test_dir / "test1.py").touch()
        (test_dir / "test2.py").touch()
        (test_dir / "readme.txt").touch()

        files = tool._find_code_files(test_dir, "python")

        assert len(files) == 2
        assert all(f.suffix == ".py" for f in files)

    def test_find_code_files_javascript(self, tool: GrammarDiscoveryTool, tmp_path: str) -> None:
        """Test _find_code_files for JavaScript."""
        from pathlib import Path

        test_dir = Path(tmp_path) / "test_project"
        test_dir.mkdir()
        (test_dir / "test.js").touch()
        (test_dir / "test.jsx").touch()
        (test_dir / "readme.txt").touch()

        files = tool._find_code_files(test_dir, "javascript")

        assert len(files) == 2

    def test_find_code_files_unsupported_language(self, tool: GrammarDiscoveryTool, tmp_path: str) -> None:
        """Test _find_code_files for unsupported language."""
        from pathlib import Path

        test_dir = Path(tmp_path) / "test_project"
        test_dir.mkdir()
        (test_dir / "test.xyz").touch()

        files = tool._find_code_files(test_dir, "xyz")

        assert len(files) == 0

    def test_find_code_files_recursive(self, tool: GrammarDiscoveryTool, tmp_path: str) -> None:
        """Test that _find_code_files searches recursively."""
        from pathlib import Path

        test_dir = Path(tmp_path) / "test_project"
        subdir = test_dir / "subdir"
        subdir.mkdir(parents=True)
        (subdir / "test.py").touch()

        files = tool._find_code_files(test_dir, "python")

        assert len(files) == 1
        assert "subdir" in str(files[0])
