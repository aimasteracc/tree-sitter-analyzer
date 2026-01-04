#!/usr/bin/env python3
"""
Tests for the List Files MCP Tool.

This module tests the ListFilesTool class which provides
file and directory listing capabilities using fd command.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return ListFilesTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".git").mkdir()

    # Create files
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")
    (tmp_path / "docs" / "guide.md").write_text("# Guide")
    (tmp_path / ".env").write_text("KEY=value")
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/")

    return tmp_path


class TestListFilesToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        """Test that initialization creates a tool instance."""
        assert tool is not None
        assert hasattr(tool, "project_root")

    def test_init_multiple_instances(self):
        """Test that multiple instances are independent."""
        tool1 = ListFilesTool()
        tool2 = ListFilesTool()
        assert tool1 is not tool2


class TestGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_tool_definition_structure(self, tool):
        """Test that tool definition has correct structure."""
        definition = tool.get_tool_definition()
        assert isinstance(definition, dict)
        assert "name" in definition
        assert "description" in definition
        assert "inputSchema" in definition

    def test_tool_definition_name(self, tool):
        """Test that tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "list_files"

    def test_tool_definition_description(self, tool):
        """Test that tool definition has description."""
        definition = tool.get_tool_definition()
        assert definition["description"] is not None
        assert isinstance(definition["description"], str)

    def test_input_schema_structure(self, tool):
        """Test that input schema has correct structure."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_required_fields(self, tool):
        """Test that required fields are correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "roots" in required
        assert len(required) == 1

    def test_roots_property(self, tool):
        """Test that roots property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "roots" in properties
        assert properties["roots"]["type"] == "array"
        assert properties["roots"]["items"]["type"] == "string"

    def test_pattern_property(self, tool):
        """Test that pattern property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "pattern" in properties
        assert properties["pattern"]["type"] == "string"

    def test_glob_property(self, tool):
        """Test that glob property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "glob" in properties
        assert properties["glob"]["type"] == "boolean"
        assert properties["glob"]["default"] is False

    def test_types_property(self, tool):
        """Test that types property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "types" in properties
        assert properties["types"]["type"] == "array"
        assert properties["types"]["items"]["type"] == "string"

    def test_extensions_property(self, tool):
        """Test that extensions property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "extensions" in properties
        assert properties["extensions"]["type"] == "array"

    def test_exclude_property(self, tool):
        """Test that exclude property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "exclude" in properties
        assert properties["exclude"]["type"] == "array"

    def test_depth_property(self, tool):
        """Test that depth property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "depth" in properties
        assert properties["depth"]["type"] == "integer"

    def test_follow_symlinks_property(self, tool):
        """Test that follow_symlinks property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "follow_symlinks" in properties
        assert properties["follow_symlinks"]["type"] == "boolean"
        assert properties["follow_symlinks"]["default"] is False

    def test_hidden_property(self, tool):
        """Test that hidden property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "hidden" in properties
        assert properties["hidden"]["type"] == "boolean"
        assert properties["hidden"]["default"] is False

    def test_no_ignore_property(self, tool):
        """Test that no_ignore property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "no_ignore" in properties
        assert properties["no_ignore"]["type"] == "boolean"
        assert properties["no_ignore"]["default"] is False

    def test_size_property(self, tool):
        """Test that size property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "size" in properties
        assert properties["size"]["type"] == "array"

    def test_changed_within_property(self, tool):
        """Test that changed_within property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "changed_within" in properties
        assert properties["changed_within"]["type"] == "string"

    def test_changed_before_property(self, tool):
        """Test that changed_before property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "changed_before" in properties
        assert properties["changed_before"]["type"] == "string"

    def test_full_path_match_property(self, tool):
        """Test that full_path_match property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "full_path_match" in properties
        assert properties["full_path_match"]["type"] == "boolean"
        assert properties["full_path_match"]["default"] is False

    def test_absolute_property(self, tool):
        """Test that absolute property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "absolute" in properties
        assert properties["absolute"]["type"] == "boolean"
        assert properties["absolute"]["default"] is True

    def test_limit_property(self, tool):
        """Test that limit property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "limit" in properties
        assert properties["limit"]["type"] == "integer"

    def test_count_only_property(self, tool):
        """Test that count_only property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "count_only" in properties
        assert properties["count_only"]["type"] == "boolean"
        assert properties["count_only"]["default"] is False

    def test_output_file_property(self, tool):
        """Test that output_file property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_file" in properties
        assert properties["output_file"]["type"] == "string"

    def test_suppress_output_property(self, tool):
        """Test that suppress_output property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "suppress_output" in properties
        assert properties["suppress_output"]["type"] == "boolean"
        assert properties["suppress_output"]["default"] is False

    def test_output_format_property(self, tool):
        """Test that output_format property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_format" in properties
        assert properties["output_format"]["type"] == "string"
        assert properties["output_format"]["enum"] == ["json", "toon"]
        assert properties["output_format"]["default"] == "toon"


class TestValidateRoots:
    """Tests for _validate_roots method."""

    def test_validate_roots_success(self, tool, sample_project_structure):
        """Test successful roots validation."""
        roots = [str(sample_project_structure)]
        validated = tool._validate_roots(roots)
        assert len(validated) == 1
        assert Path(validated[0]).is_absolute()

    def test_validate_roots_multiple(self, tool, sample_project_structure):
        """Test validation of multiple roots."""
        roots = [
            str(sample_project_structure),
            str(sample_project_structure / "src"),
        ]
        validated = tool._validate_roots(roots)
        assert len(validated) == 2

    def test_validate_roots_empty_list(self, tool):
        """Test validation fails with empty roots list."""
        roots = []
        with pytest.raises(ValueError, match="roots must be a non-empty array"):
            tool._validate_roots(roots)

    def test_validate_roots_not_a_list(self, tool):
        """Test validation fails when roots is not a list."""
        roots = "not_a_list"
        with pytest.raises(ValueError, match="roots must be a non-empty array"):
            tool._validate_roots(roots)

    def test_validate_roots_empty_string(self, tool):
        """Test validation fails when root is empty string."""
        roots = [""]
        with pytest.raises(ValueError, match="root entries must be non-empty strings"):
            tool._validate_roots(roots)

    def test_validate_roots_whitespace_string(self, tool):
        """Test validation fails when root is only whitespace."""
        roots = ["   "]
        with pytest.raises(ValueError, match="root entries must be non-empty strings"):
            tool._validate_roots(roots)

    def test_validate_roots_invalid_directory(self, tool):
        """Test validation fails when directory doesn't exist."""
        roots = ["/nonexistent/directory"]
        with pytest.raises(ValueError, match="Invalid root"):
            tool._validate_roots(roots)


class TestValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments(self, tool):
        """Test validation with valid arguments."""
        arguments = {
            "roots": ["."],
            "pattern": "*.py",
            "glob": True,
            "types": ["f"],
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_minimal_arguments(self, tool):
        """Test validation with minimal required arguments."""
        arguments = {"roots": ["."]}
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_roots(self, tool):
        """Test validation fails when roots is missing."""
        arguments = {"pattern": "*.py"}
        with pytest.raises(ValueError, match="roots is required"):
            tool.validate_arguments(arguments)

    def test_validate_roots_not_array(self, tool):
        """Test validation fails when roots is not an array."""
        arguments = {"roots": "."}
        with pytest.raises(ValueError, match="roots must be an array"):
            tool.validate_arguments(arguments)

    def test_validate_pattern_not_string(self, tool):
        """Test validation fails when pattern is not a string."""
        arguments = {"roots": ["."], "pattern": 123}
        with pytest.raises(ValueError, match="pattern must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_changed_within_not_string(self, tool):
        """Test validation fails when changed_within is not a string."""
        arguments = {"roots": ["."], "changed_within": 123}
        with pytest.raises(ValueError, match="changed_within must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_changed_before_not_string(self, tool):
        """Test validation fails when changed_before is not a string."""
        arguments = {"roots": ["."], "changed_before": 123}
        with pytest.raises(ValueError, match="changed_before must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_glob_not_boolean(self, tool):
        """Test validation fails when glob is not a boolean."""
        arguments = {"roots": ["."], "glob": "true"}
        with pytest.raises(ValueError, match="glob must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_follow_symlinks_not_boolean(self, tool):
        """Test validation fails when follow_symlinks is not a boolean."""
        arguments = {"roots": ["."], "follow_symlinks": "true"}
        with pytest.raises(ValueError, match="follow_symlinks must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_hidden_not_boolean(self, tool):
        """Test validation fails when hidden is not a boolean."""
        arguments = {"roots": ["."], "hidden": "true"}
        with pytest.raises(ValueError, match="hidden must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_no_ignore_not_boolean(self, tool):
        """Test validation fails when no_ignore is not a boolean."""
        arguments = {"roots": ["."], "no_ignore": "true"}
        with pytest.raises(ValueError, match="no_ignore must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_full_path_match_not_boolean(self, tool):
        """Test validation fails when full_path_match is not a boolean."""
        arguments = {"roots": ["."], "full_path_match": "true"}
        with pytest.raises(ValueError, match="full_path_match must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_absolute_not_boolean(self, tool):
        """Test validation fails when absolute is not a boolean."""
        arguments = {"roots": ["."], "absolute": "true"}
        with pytest.raises(ValueError, match="absolute must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_depth_not_integer(self, tool):
        """Test validation fails when depth is not an integer."""
        arguments = {"roots": ["."], "depth": "1"}
        with pytest.raises(ValueError, match="depth must be an integer"):
            tool.validate_arguments(arguments)

    def test_validate_limit_not_integer(self, tool):
        """Test validation fails when limit is not an integer."""
        arguments = {"roots": ["."], "limit": "100"}
        with pytest.raises(ValueError, match="limit must be an integer"):
            tool.validate_arguments(arguments)

    def test_validate_types_not_array(self, tool):
        """Test validation fails when types is not an array."""
        arguments = {"roots": ["."], "types": "f"}
        with pytest.raises(ValueError, match="types must be an array of strings"):
            tool.validate_arguments(arguments)

    def test_validate_extensions_not_array(self, tool):
        """Test validation fails when extensions is not an array."""
        arguments = {"roots": ["."], "extensions": "py"}
        with pytest.raises(ValueError, match="extensions must be an array of strings"):
            tool.validate_arguments(arguments)

    def test_validate_exclude_not_array(self, tool):
        """Test validation fails when exclude is not an array."""
        arguments = {"roots": ["."], "exclude": "*.pyc"}
        with pytest.raises(ValueError, match="exclude must be an array of strings"):
            tool.validate_arguments(arguments)

    def test_validate_size_not_array(self, tool):
        """Test validation fails when size is not an array."""
        arguments = {"roots": ["."], "size": "+10M"}
        with pytest.raises(ValueError, match="size must be an array of strings"):
            tool.validate_arguments(arguments)


class TestExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_fd_not_found(self, tool):
        """Test execute fails when fd command is not found."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=False,
        ):
            arguments = {"roots": ["."]}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "fd command not found" in result["error"]
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_execute_success(self, tool, sample_project_structure):
        """Test successful execution."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "pattern": "*.py",
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert "toon_content" in result
                    assert "count" in result
                    assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_execute_count_only_mode(self, tool, sample_project_structure):
        """Test execution in count_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n/path/to/file3.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "count_only": True,
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert result["count_only"] is True
                    assert "total_count" in result
                    assert result["total_count"] == 3

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, sample_project_structure):
        """Test execution with file output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.FileOutputManager"
                    ) as mock_manager_class:
                        mock_manager = MagicMock()
                        mock_manager.save_to_file.return_value = "/output/results.json"
                        mock_manager_class.return_value = mock_manager

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "output_file": "results.json",
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "output_file" in result
                        assert result["output_file"] == "/output/results.json"

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, sample_project_structure):
        """Test execution with suppress_output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.FileOutputManager"
                    ) as mock_manager_class:
                        mock_manager = MagicMock()
                        mock_manager.save_to_file.return_value = "/output/results.json"
                        mock_manager_class.return_value = mock_manager

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "output_file": "results.json",
                            "suppress_output": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "output_file" in result
                        assert "message" in result
                        # Results should not be in response when suppressed
                        assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_with_output_format_toon(
        self, tool, sample_project_structure
    ):
        """Test execution with toon output format."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.apply_toon_format_to_response"
                    ) as mock_toon:
                        mock_toon.return_value = {"toon": "formatted"}

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "output_format": "toon",
                        }

                        result = await tool.execute(arguments)

                        assert mock_toon.called
                        assert result == {"toon": "formatted"}

    @pytest.mark.asyncio
    async def test_execute_fd_command_failure(self, tool, sample_project_structure):
        """Test execution when fd command fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    1,
                    b"",
                    b"fd: error: invalid pattern",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "pattern": "*.py",
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is False
                    assert "error" in result
                    assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_extensions_auto_types(
        self, tool, sample_project_structure
    ):
        """Test that extensions parameter auto-sets types to files."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.return_value = (0, b"", b"")

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "extensions": ["py", "js"],
                        }

                        await tool.execute(arguments)

                        # Verify that types was auto-set to ['f']
                        call_kwargs = mock_build.call_args.kwargs
                        assert call_kwargs["types"] == ["f"]

    @pytest.mark.asyncio
    async def test_execute_with_gitignore_detection(
        self, tool, sample_project_structure
    ):
        """Test that .gitignore detection works."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.return_value = (0, b"", b"")

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                    ) as mock_detector:
                        mock_detector.return_value.should_use_no_ignore.return_value = (
                            True
                        )
                        mock_detector.return_value.get_detection_info.return_value = {
                            "reason": "test reason"
                        }

                        arguments = {"roots": [str(sample_project_structure)]}

                        await tool.execute(arguments)

                        # Verify that no_ignore was auto-enabled
                        call_kwargs = mock_build.call_args.kwargs
                        assert call_kwargs["no_ignore"] is True

    @pytest.mark.asyncio
    async def test_execute_limit_clamping(self, tool, sample_project_structure):
        """Test that limit is properly clamped."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.return_value = (0, b"", b"")

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                    ):
                        # Request limit higher than hard cap
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "limit": 50000,
                        }

                        await tool.execute(arguments)

                        # Verify limit was clamped
                        call_kwargs = mock_build.call_args.kwargs
                        from tree_sitter_analyzer.mcp.tools import fd_rg_utils

                        assert call_kwargs["limit"] == fd_rg_utils.MAX_RESULTS_HARD_CAP

    @pytest.mark.asyncio
    async def test_execute_truncation_defensive(self, tool, sample_project_structure):
        """Test defensive truncation even if fd doesn't truncate."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            # Simulate fd returning more than hard cap
            many_files = "\n".join(
                [f"/path/to/file{i}.py" for i in range(15000)]
            ).encode()

            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, many_files, b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {"roots": [str(sample_project_structure)]}

                    result = await tool.execute(arguments)

                    # Verify results were truncated
                    assert result["truncated"] is True
                    # In toon format, results are in toon_content
                    assert "toon_content" in result
