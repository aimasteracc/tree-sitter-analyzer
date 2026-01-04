#!/usr/bin/env python3
"""
Tests for Find and Grep MCP Tool.

This module tests FindAndGrepTool class which provides
two-stage search functionality using fd and ripgrep.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import (
    FindAndGrepTool,
)


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return FindAndGrepTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()

    # Create files
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")
    (tmp_path / "docs" / "guide.md").write_text("# Guide")

    return tmp_path


class TestFindAndGrepToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        """Test that initialization creates a tool instance."""
        assert tool is not None
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        """Test initialization with project root."""
        tool = FindAndGrepTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_init_multiple_instances(self):
        """Test that multiple instances are independent."""
        tool1 = FindAndGrepTool()
        tool2 = FindAndGrepTool()
        assert tool1 is not tool2


class TestSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_all_components(self, tool):
        """Test that set_project_path updates all components."""
        new_path = "/new/project/path"
        tool.set_project_path(new_path)
        assert tool.project_root == new_path

    def test_set_project_path_recreates_file_manager(self, tool):
        """Test that set_project_path recreates file manager."""
        old_manager = tool.file_output_manager
        tool.set_project_path("/new/path")
        assert tool.file_output_manager is not old_manager


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
        assert definition["name"] == "find_and_grep"

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
        assert "query" in required
        assert len(required) == 2

    def test_file_stage_parameters(self, tool):
        """Test that file stage parameters are defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})

        # File stage parameters
        assert "roots" in properties
        assert "pattern" in properties
        assert "glob" in properties
        assert "types" in properties
        assert "extensions" in properties
        assert "exclude" in properties
        assert "depth" in properties
        assert "follow_symlinks" in properties
        assert "hidden" in properties
        assert "no_ignore" in properties
        assert "size" in properties
        assert "changed_within" in properties
        assert "changed_before" in properties
        assert "full_path_match" in properties
        assert "file_limit" in properties
        assert "sort" in properties

    def test_content_stage_parameters(self, tool):
        """Test that content stage parameters are defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})

        # Content stage parameters
        assert "query" in properties
        assert "case" in properties
        assert "fixed_strings" in properties
        assert "word" in properties
        assert "multiline" in properties
        assert "include_globs" in properties
        assert "exclude_globs" in properties
        assert "max_filesize" in properties
        assert "context_before" in properties
        assert "context_after" in properties
        assert "encoding" in properties
        assert "max_count" in properties
        assert "timeout_ms" in properties

    def test_output_format_parameters(self, tool):
        """Test that output format parameters are defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})

        # Output format parameters
        assert "count_only_matches" in properties
        assert "summary_only" in properties
        assert "optimize_paths" in properties
        assert "group_by_file" in properties
        assert "total_only" in properties
        assert "output_file" in properties
        assert "suppress_output" in properties
        assert "output_format" in properties

    def test_sort_enum_values(self, tool):
        """Test that sort parameter has correct enum values."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert properties["sort"]["enum"] == ["path", "mtime", "size"]

    def test_case_enum_values(self, tool):
        """Test that case parameter has correct enum values."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert properties["case"]["enum"] == ["smart", "insensitive", "sensitive"]
        assert properties["case"]["default"] == "smart"

    def test_output_format_enum_values(self, tool):
        """Test that output_format parameter has correct enum values."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
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
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_roots(self, tool):
        """Test validation fails when roots is missing."""
        arguments = {"query": "test"}
        with pytest.raises(ValueError, match="roots is required"):
            tool.validate_arguments(arguments)

    def test_validate_roots_not_array(self, tool):
        """Test validation fails when roots is not an array."""
        arguments = {"roots": ".", "query": "test"}
        with pytest.raises(ValueError, match="roots is required and must be an array"):
            tool.validate_arguments(arguments)

    def test_validate_missing_query(self, tool):
        """Test validation fails when query is missing."""
        arguments = {"roots": ["."]}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_query_not_string(self, tool):
        """Test validation fails when query is not a string."""
        arguments = {"roots": ["."], "query": 123}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_empty_query(self, tool):
        """Test validation fails when query is empty."""
        arguments = {"roots": ["."], "query": ""}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_whitespace_query(self, tool):
        """Test validation fails when query is only whitespace."""
        arguments = {"roots": ["."], "query": "   "}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_file_limit_type(self, tool):
        """Test validation fails when file_limit is not an integer."""
        arguments = {"roots": ["."], "query": "test", "file_limit": "100"}
        with pytest.raises(ValueError, match="file_limit must be an integer"):
            tool.validate_arguments(arguments)


class TestExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_missing_commands(self, tool):
        """Test execute fails when fd or rg commands are not found."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=["fd", "rg"],
        ):
            arguments = {"roots": ["."], "query": "test"}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "Required commands not found" in result["error"]
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_execute_fd_failure(self, tool, sample_project_structure):
        """Test execute when fd command fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (1, b"", b"fd: error")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is False
                assert "error" in result
                assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_execute_no_files_found(self, tool, sample_project_structure):
        """Test execute when no files are found."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                # fd returns no files
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["count"] == 0
                assert result["results"] == []

    @pytest.mark.asyncio
    async def test_execute_total_only_mode(self, tool, sample_project_structure):
        """Test execute in total_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                # fd returns files
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n/path/to/file2.py\n", b""),
                    (0, b"42", b""),  # rg returns count
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_count_output",
                    return_value={"__total__": 42},
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "total_only": True,
                    }

                    result = await tool.execute(arguments)

                    # total_only returns just the number
                    assert result == 42

    @pytest.mark.asyncio
    async def test_execute_count_only_matches_mode(
        self, tool, sample_project_structure
    ):
        """Test execute in count_only_matches mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n/path/to/file2.py\n", b""),
                    (0, b"10\n5\n", b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_count_output",
                    return_value={"__total__": 15, "file1.py": 10, "file2.py": 5},
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "count_only_matches": True,
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert result["count_only"] is True
                    assert result["total_matches"] == 15
                    assert "file_counts" in result

    @pytest.mark.asyncio
    async def test_execute_group_by_file_mode(self, tool, sample_project_structure):
        """Test execute in group_by_file mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n/path/to/file2.py\n", b""),
                    (0, b'{"path": "file1.py"}\n{"path": "file2.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[
                        {"path": "file1.py", "line": 1, "content": "test"},
                        {"path": "file2.py", "line": 2, "content": "test"},
                    ],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.group_matches_by_file",
                        return_value={
                            "success": True,
                            "count": 2,
                            "files": [
                                {"path": "file1.py", "matches": 1},
                                {"path": "file2.py", "matches": 1},
                            ],
                        },
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "group_by_file": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "files" in result

    @pytest.mark.asyncio
    async def test_execute_summary_only_mode(self, tool, sample_project_structure):
        """Test execute in summary_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.summarize_search_results",
                        return_value={"top_files": ["file1.py"], "total_count": 1},
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "summary_only": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert result["summary_only"] is True
                        assert "summary" in result

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, sample_project_structure):
        """Test execute with file output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch.object(
                        tool.file_output_manager, "save_to_file"
                    ) as mock_save:
                        mock_save.return_value = "/output/results.json"

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_file": "results.json",
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        # In toon format, output_file info is in toon_content
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, sample_project_structure):
        """Test execute with suppress_output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch.object(
                        tool.file_output_manager, "save_to_file"
                    ) as mock_save:
                        mock_save.return_value = "/output/results.json"

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_file": "results.json",
                            "suppress_output": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        # In toon format, output_file info is in toon_content
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_with_optimize_paths(self, tool, sample_project_structure):
        """Test execute with optimize_paths."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "/path/to/file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "/path/to/file1.py", "line": 1}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.optimize_match_paths",
                        return_value=[{"path": "file1.py", "line": 1}],
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "optimize_paths": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        # In toon format, results are in toon_content
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_rg_failure(self, tool, sample_project_structure):
        """Test execute when ripgrep command fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (2, b"", b"ripgrep: error"),
                ]

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is False
                assert "error" in result
                assert result["returncode"] == 2

    @pytest.mark.asyncio
    async def test_execute_with_gitignore_detection(
        self, tool, sample_project_structure
    ):
        """Test that .gitignore detection works."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.side_effect = [
                        (0, b"", b""),
                        (0, b"", b""),
                    ]

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.get_default_detector"
                    ) as mock_detector:
                        mock_detector.return_value.should_use_no_ignore.return_value = (
                            True
                        )
                        mock_detector.return_value.get_detection_info.return_value = {
                            "reason": "test reason"
                        }

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                        }

                        await tool.execute(arguments)

                        # Verify that no_ignore was auto-enabled
                        call_kwargs = mock_build.call_args.kwargs
                        assert call_kwargs["no_ignore"] is True

    @pytest.mark.asyncio
    async def test_execute_with_sort_path(self, tool, sample_project_structure):
        """Test execute with sort by path."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/z.py\n/path/a.py\n", b""),
                    (0, b"", b""),
                ]

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "sort": "path",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_toon_format(self, tool, sample_project_structure):
        """Test execute with toon output format."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.apply_toon_format_to_response"
                    ) as mock_toon:
                        mock_toon.return_value = {"toon": "formatted"}

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_format": "toon",
                        }

                        result = await tool.execute(arguments)

                        assert mock_toon.called
                        assert result == {"toon": "formatted"}

    @pytest.mark.asyncio
    async def test_execute_file_limit_clamping(self, tool, sample_project_structure):
        """Test that file_limit is properly clamped."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.side_effect = [
                        (0, b"", b""),
                        (0, b"", b""),
                    ]

                    # Request limit higher than hard cap
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "file_limit": 50000,
                    }

                    await tool.execute(arguments)

                    # Verify limit was clamped
                    call_kwargs = mock_build.call_args.kwargs
                    from tree_sitter_analyzer.mcp.tools import fd_rg_utils

                    assert call_kwargs["limit"] == fd_rg_utils.MAX_RESULTS_HARD_CAP

    @pytest.mark.asyncio
    async def test_execute_with_max_count(self, tool, sample_project_structure):
        """Test execute with max_count parameter."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (
                        0,
                        b'{"path": "file1.py", "line": 1}\n{"path": "file1.py", "line": 2}\n',
                        b"",
                    ),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[
                        {"path": "file1.py", "line": 1},
                        {"path": "file1.py", "line": 2},
                    ],
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "max_count": 1,
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert result["count"] == 1  # Limited by max_count

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, tool, sample_project_structure):
        """Test execute with timeout parameter."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"", b""),
                    (0, b"", b""),
                ]

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "timeout_ms": 5000,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_file_save_error(self, tool, sample_project_structure):
        """Test execute when file save fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch.object(
                        tool.file_output_manager, "save_to_file"
                    ) as mock_save:
                        mock_save.side_effect = Exception("Save failed")

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_file": "results.json",
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "file_save_error" in result
                        assert result["file_saved"] is False
