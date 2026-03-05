#!/usr/bin/env python3
"""
Tests for Search Content MCP Tool.

This module tests SearchContentTool class which provides
content search capabilities using ripgrep.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import (
    SearchContentTool,
)


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return SearchContentTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    # Create files
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")

    return tmp_path


class TestSearchContentToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        """Test that initialization creates a tool instance."""
        assert tool is not None
        assert hasattr(tool, "cache")
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        """Test initialization with project root."""
        tool = SearchContentTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_init_with_cache_disabled(self):
        """Test initialization with cache disabled."""
        tool = SearchContentTool(enable_cache=False)
        assert tool.cache is None

    def test_init_multiple_instances(self):
        """Test that multiple instances are independent."""
        tool1 = SearchContentTool()
        tool2 = SearchContentTool()
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
        assert definition["name"] == "search_content"

    def test_required_fields(self, tool):
        """Test that required fields are correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "query" in required
        assert len(required) == 1

    def test_roots_property(self, tool):
        """Test that roots property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "roots" in properties
        assert properties["roots"]["type"] == "array"

    def test_files_property(self, tool):
        """Test that files property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "files" in properties
        assert properties["files"]["type"] == "array"

    def test_query_property(self, tool):
        """Test that query property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query" in properties
        assert properties["query"]["type"] == "string"

    def test_case_property(self, tool):
        """Test that case property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "case" in properties
        assert properties["case"]["enum"] == ["smart", "insensitive", "sensitive"]
        assert properties["case"]["default"] == "smart"

    def test_total_only_property(self, tool):
        """Test that total_only property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "total_only" in properties
        assert properties["total_only"]["type"] == "boolean"
        assert properties["total_only"]["default"] is False

    def test_count_only_matches_property(self, tool):
        """Test that count_only_matches property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "count_only_matches" in properties
        assert properties["count_only_matches"]["type"] == "boolean"
        assert properties["count_only_matches"]["default"] is False

    def test_summary_only_property(self, tool):
        """Test that summary_only property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "summary_only" in properties
        assert properties["summary_only"]["type"] == "boolean"
        assert properties["summary_only"]["default"] is False

    def test_group_by_file_property(self, tool):
        """Test that group_by_file property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "group_by_file" in properties
        assert properties["group_by_file"]["type"] == "boolean"
        assert properties["group_by_file"]["default"] is False

    def test_optimize_paths_property(self, tool):
        """Test that optimize_paths property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "optimize_paths" in properties
        assert properties["optimize_paths"]["type"] == "boolean"
        assert properties["optimize_paths"]["default"] is False


class TestValidateRoots:
    """Tests for _validate_roots method."""

    def test_validate_roots_success(self, tool, sample_project_structure):
        """Test successful roots validation."""
        roots = [str(sample_project_structure)]
        validated = tool._validate_roots(roots)
        assert len(validated) == 1
        assert Path(validated[0]).is_absolute()

    def test_validate_roots_invalid_directory(self, tool):
        """Test validation fails when directory doesn't exist."""
        roots = ["/nonexistent/directory"]
        with pytest.raises(ValueError, match="Invalid root"):
            tool._validate_roots(roots)


class TestValidateFiles:
    """Tests for _validate_files method."""

    def test_validate_files_success(self, tool, sample_project_structure):
        """Test successful files validation."""
        files = [str(sample_project_structure / "README.md")]
        validated = tool._validate_files(files)
        assert len(validated) == 1

    def test_validate_files_empty_string(self, tool):
        """Test validation fails when file is empty string."""
        files = [""]
        with pytest.raises(ValueError, match="files entries must be non-empty strings"):
            tool._validate_files(files)

    def test_validate_files_not_found(self, tool):
        """Test validation fails when file doesn't exist."""
        files = ["/nonexistent/file.txt"]
        with pytest.raises(ValueError, match="Invalid file path"):
            tool._validate_files(files)


class TestValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments_with_roots(self, tool, sample_project_structure):
        """Test validation with valid arguments using roots."""
        arguments = {
            "roots": [str(sample_project_structure)],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_valid_arguments_with_files(self, tool, sample_project_structure):
        """Test validation with valid arguments using files."""
        arguments = {
            "files": [str(sample_project_structure / "README.md")],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_query(self, tool):
        """Test validation fails when query is missing."""
        arguments = {"roots": ["."]}
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

    def test_validate_missing_both_roots_and_files(self, tool):
        """Test validation fails when both roots and files are missing."""
        arguments = {"query": "test"}
        with pytest.raises(ValueError, match="Either roots or files must be provided"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_case_type(self, tool):
        """Test validation fails when case is not a string."""
        arguments = {"roots": ["."], "query": "test", "case": 123}
        with pytest.raises(ValueError, match="case must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_encoding_type(self, tool):
        """Test validation fails when encoding is not a string."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "encoding": 123,
        }
        with pytest.raises(ValueError, match="encoding must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_max_filesize_type(self, tool):
        """Test validation fails when max_filesize is not a string."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "max_filesize": 123,
        }
        with pytest.raises(ValueError, match="max_filesize must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_fixed_strings_type(self, tool):
        """Test validation fails when fixed_strings is not a boolean."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "fixed_strings": "true",
        }
        with pytest.raises(ValueError, match="fixed_strings must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_word_type(self, tool):
        """Test validation fails when word is not a boolean."""
        arguments = {"roots": ["."], "query": "test", "word": "true"}
        with pytest.raises(ValueError, match="word must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_multiline_type(self, tool):
        """Test validation fails when multiline is not a boolean."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "multiline": "true",
        }
        with pytest.raises(ValueError, match="multiline must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_include_globs_type(self, tool):
        """Test validation fails when include_globs is not an array."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "include_globs": "*.py",
        }
        with pytest.raises(
            ValueError, match="include_globs must be an array of strings"
        ):
            tool.validate_arguments(arguments)


class TestDetermineRequestedFormat:
    """Tests for _determine_requested_format method."""

    def test_determine_total_only_format(self, tool):
        """Test format determination for total_only."""
        arguments = {"total_only": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "total_only"

    def test_determine_count_only_format(self, tool):
        """Test format determination for count_only_matches."""
        arguments = {"count_only_matches": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "count_only"

    def test_determine_summary_format(self, tool):
        """Test format determination for summary_only."""
        arguments = {"summary_only": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "summary"

    def test_determine_group_by_file_format(self, tool):
        """Test format determination for group_by_file."""
        arguments = {"group_by_file": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "group_by_file"

    def test_determine_normal_format(self, tool):
        """Test format determination for normal mode."""
        arguments = {}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "normal"


class TestExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_rg_not_found(self, tool):
        """Test execute fails when rg command is not found."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=False,
        ):
            arguments = {"roots": ["."], "query": "test"}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "rg (ripgrep) command not found" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_total_only_mode(self, tool, sample_project_structure):
        """Test execute in total_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"42", b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_count_output",
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
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"10\n5\n", b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_count_output",
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
    async def test_execute_summary_only_mode(self, tool, sample_project_structure):
        """Test execute in summary_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
                        return_value={"top_files": ["file1.py"]},
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "summary_only": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        # In toon format, summary_only may not be in response
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_group_by_file_mode(self, tool, sample_project_structure):
        """Test execute in group_by_file mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
                        return_value={
                            "success": True,
                            "count": 1,
                            "files": [{"path": "file1.py"}],
                        },
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "group_by_file": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        # Files field is removed for token optimization, but toon_content contains it
                        assert "toon_content" in result
                        assert "files" not in result  # Removed for token optimization

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, sample_project_structure):
        """Test execute with file output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
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
                        assert "output_file" in result

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, sample_project_structure):
        """Test execute with suppress_output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
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
                        assert "output_file" in result
                        # Results should not be in response when suppressed
                        assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_with_toon_format(self, tool, sample_project_structure):
        """Test execute with toon output format."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.apply_toon_format_to_response"
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
    async def test_execute_rg_failure(self, tool, sample_project_structure):
        """Test execute when ripgrep command fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (2, b"", b"ripgrep: error")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is False
                assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_cache_hit(self, tool, sample_project_structure):
        """Test execute with cache hit."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"success": True, "count": 5}
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            arguments = {
                "roots": [str(sample_project_structure)],
                "query": "test",
            }

            result = await tool.execute(arguments)

            assert result["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_execute_with_cache_disabled(self, tool, sample_project_structure):
        """Test execute with cache disabled."""
        tool_no_cache = SearchContentTool(enable_cache=False)

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                await tool_no_cache.execute(arguments)

                # Verify cache was not used
                assert tool_no_cache.cache is None

    @pytest.mark.asyncio
    async def test_execute_with_parallel_processing(
        self, tool, sample_project_structure
    ):
        """Test execute with parallel processing enabled."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.split_roots_for_parallel_processing",
                return_value=[["root1"], ["root2"]],
            ):
                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_parallel_rg_searches",
                    new_callable=AsyncMock,
                ) as mock_parallel:
                    mock_parallel.return_value = (
                        (0, b"", b""),
                        (0, b"", b""),
                    )

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.merge_rg_results",
                        return_value=(0, b"", b""),
                    ):
                        arguments = {
                            "roots": [
                                str(sample_project_structure),
                                str(sample_project_structure / "src"),
                            ],
                            "query": "test",
                            "enable_parallel": True,
                        }

                        await tool.execute(arguments)

                        assert mock_parallel.called

    @pytest.mark.asyncio
    async def test_execute_with_files_parameter(self, tool, sample_project_structure):
        """Test execute with files parameter instead of roots."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "files": [str(sample_project_structure / "README.md")],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_optimize_paths(self, tool, sample_project_structure):
        """Test execute with optimize_paths."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"path": "/very/long/path/to/file1.py"}\n',
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "/very/long/path/to/file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
                        return_value=[{"path": "file1.py"}],
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "optimize_paths": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_file_save_error(self, tool, sample_project_structure):
        """Test execute when file save fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
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

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, tool, sample_project_structure):
        """Test execute with timeout parameter."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "timeout_ms": 5000,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_max_count(self, tool, sample_project_structure):
        """Test execute with max_count parameter."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "max_count": 100,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered branches in search_content_tool.py
# ---------------------------------------------------------------------------


class TestCacheHitBranches:
    """Test cache hit branches (lines 378-420)."""

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_with_int(self, tool, sample_project_structure):
        """Test total_only cache hit when cached result is integer (line 382-383)."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = 42
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "total_only": True,
            })
            assert result == 42

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_with_total_matches_dict(self, tool, sample_project_structure):
        """Test total_only cache hit when cached result is dict with total_matches (lines 384-389)."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"total_matches": 15, "file_counts": {}}
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "total_only": True,
            })
            assert result == 15

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_with_count_dict(self, tool, sample_project_structure):
        """Test total_only cache hit when cached result is dict with count (lines 394-396)."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"count": 7}
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "total_only": True,
            })
            assert result == 7

    @pytest.mark.asyncio
    async def test_cache_hit_total_only_fallback_zero(self, tool, sample_project_structure):
        """Test total_only cache hit with unrecognized cached type returns 0 (line 399)."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"unrelated": "data"}
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "total_only": True,
            })
            assert result == 0

    @pytest.mark.asyncio
    async def test_cache_hit_non_total_int_cached(self, tool, sample_project_structure):
        """Test non-total_only cache hit with integer cached (lines 406-413)."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = 10
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
            })
            assert result["success"] is True
            assert result["count"] == 10
            assert result["total_matches"] == 10
            assert result["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_cache_hit_non_total_other_type(self, tool, sample_project_structure):
        """Test non-total_only cache hit with non-dict/non-int cached (lines 414-420)."""
        tool.cache = MagicMock()
        tool.cache.get.return_value = "string_result"
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
            })
            assert result["success"] is True
            assert result["cached_result"] == "string_result"
            assert result["cache_hit"] is True


class TestGitignoreAutoDetection:
    """Test gitignore auto-detection branches (lines 479-485)."""

    @pytest.mark.asyncio
    async def test_auto_detect_no_ignore(self, tool, sample_project_structure):
        """Test auto-detection of --no-ignore when gitignore interferes (lines 479-487)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_detector"
        ) as mock_detector_fn:
            mock_detector = MagicMock()
            mock_detector.should_use_no_ignore.return_value = True
            mock_detector.get_detection_info.return_value = {"reason": "test reason"}
            mock_detector_fn.return_value = mock_detector

            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
            })
            assert result["success"] is True
            mock_detector.should_use_no_ignore.assert_called_once()


class TestCountOnlyToonFormat:
    """Test count_only with toon format (line 627)."""

    @pytest.mark.asyncio
    async def test_count_only_toon_format(self, tool, sample_project_structure):
        """Test count_only_matches returns toon format (line 625-627)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"file1.py:3\nfile2.py:5\n", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_count_output",
            return_value={"__total__": 8, "file1.py": 3, "file2.py": 5},
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.attach_toon_content_to_response"
        ) as mock_toon:
            mock_toon.return_value = {"format": "toon", "toon_content": "..."}

            await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "count_only_matches": True,
                "output_format": "toon",
            })
            mock_toon.assert_called()


class TestMaxCountTruncation:
    """Test max_count truncation (lines 637-638)."""

    @pytest.mark.asyncio
    async def test_truncation_by_max_count(self, tool, sample_project_structure):
        """Test that results are truncated when exceeding max_count (lines 636-638)."""
        many_matches = [{"path": f"file{i}.py", "line": i} for i in range(20)]
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=many_matches,
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "max_count": 5,
            })
            assert result["success"] is True
            assert result["truncated"] is True
            assert result["count"] == 5


class TestOptimizePathsOutputBranches:
    """Test optimize_paths with output_file/suppress_output (lines 659-705)."""

    @pytest.mark.asyncio
    async def test_optimize_paths_with_output_file(self, tool, sample_project_structure):
        """Test optimize_paths with output_file (lines 663-688)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
            return_value=[{"path": "f1.py"}],
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/result.json"
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "optimize_paths": True,
                "output_file": "result.json",
                "output_format": "json",
            })
            assert result["success"] is True
            assert "file_saved" in result

    @pytest.mark.asyncio
    async def test_optimize_paths_with_output_file_and_suppress(self, tool, sample_project_structure):
        """Test optimize_paths with output_file and suppress_output (lines 672-684).

        Note: suppress_output is mutually exclusive with optimize_paths at the validator level.
        We bypass the validator to test the downstream code path.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
            return_value=[{"path": "f1.py"}],
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/result.json"
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "optimize_paths": True,
                "output_file": "result.json",
                "suppress_output": True,
                "output_format": "json",
            })
            assert result["success"] is True
            assert "output_file" in result
            # Minimal response should not have results
            assert "results" not in result

    @pytest.mark.asyncio
    async def test_optimize_paths_with_output_file_suppress_toon(self, tool, sample_project_structure):
        """Test optimize_paths with suppress_output and toon format (lines 682-684).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
            return_value=[{"path": "f1.py"}],
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/result.json"
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.attach_toon_content_to_response"
        ) as mock_toon, patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            mock_toon.return_value = {"toon": "minimal"}
            await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "optimize_paths": True,
                "output_file": "result.json",
                "suppress_output": True,
                "output_format": "toon",
            })
            mock_toon.assert_called()

    @pytest.mark.asyncio
    async def test_optimize_paths_file_save_error(self, tool, sample_project_structure):
        """Test optimize_paths when file save fails (lines 689-692)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
            return_value=[{"path": "f1.py"}],
        ), patch.object(
            tool.file_output_manager, "save_to_file", side_effect=Exception("disk full")
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "optimize_paths": True,
                "output_file": "result.json",
                "output_format": "json",
            })
            assert "file_save_error" in result
            assert result["file_saved"] is False

    @pytest.mark.asyncio
    async def test_optimize_paths_suppress_no_file(self, tool, sample_project_structure):
        """Test optimize_paths with suppress_output but no output_file (lines 693-705).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
            return_value=[{"path": "f1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "optimize_paths": True,
                "suppress_output": True,
                "output_format": "json",
            })
            assert result["success"] is True
            assert "results" not in result

    @pytest.mark.asyncio
    async def test_optimize_paths_suppress_no_file_toon(self, tool, sample_project_structure):
        """Test optimize_paths with suppress_output (no file) in toon format (lines 703-704).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
            return_value=[{"path": "f1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.attach_toon_content_to_response"
        ) as mock_toon, patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            mock_toon.return_value = {"toon": "minimal"}
            await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "optimize_paths": True,
                "suppress_output": True,
                "output_format": "toon",
            })
            mock_toon.assert_called()


class TestGroupByFileOutputBranches:
    """Test group_by_file with output_file/suppress_output (lines 720-776)."""

    @pytest.mark.asyncio
    async def test_group_by_file_with_output_file(self, tool, sample_project_structure):
        """Test group_by_file with output_file (lines 725-750)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
            return_value={"success": True, "count": 1, "files": [{"path": "file1.py"}]},
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/grouped.json"
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "group_by_file": True,
                "output_file": "grouped.json",
                "output_format": "json",
            })
            assert "file_saved" in result

    @pytest.mark.asyncio
    async def test_group_by_file_output_file_suppress(self, tool, sample_project_structure):
        """Test group_by_file with output_file and suppress_output (lines 734-746).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
            return_value={"success": True, "count": 1, "files": [{"path": "file1.py"}]},
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/grouped.json"
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "group_by_file": True,
                "output_file": "grouped.json",
                "suppress_output": True,
                "output_format": "json",
            })
            assert result["success"] is True
            assert "output_file" in result
            assert "files" not in result

    @pytest.mark.asyncio
    async def test_group_by_file_file_save_error(self, tool, sample_project_structure):
        """Test group_by_file when file save fails (lines 751-754)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
            return_value={"success": True, "count": 1, "files": [{"path": "file1.py"}]},
        ), patch.object(
            tool.file_output_manager, "save_to_file", side_effect=Exception("disk full")
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "group_by_file": True,
                "output_file": "grouped.json",
                "output_format": "json",
            })
            assert "file_save_error" in result
            assert result["file_saved"] is False

    @pytest.mark.asyncio
    async def test_group_by_file_suppress_no_file(self, tool, sample_project_structure):
        """Test group_by_file with suppress_output but no output_file (lines 755-768).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
            return_value={"success": True, "count": 1, "summary": {}, "meta": {}, "files": [{"path": "file1.py"}]},
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "group_by_file": True,
                "suppress_output": True,
                "output_format": "json",
            })
            assert result["success"] is True
            assert "files" not in result

    @pytest.mark.asyncio
    async def test_group_by_file_suppress_no_file_toon(self, tool, sample_project_structure):
        """Test group_by_file suppress_output (no file) in toon format (lines 766-767).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
            return_value={"success": True, "count": 1, "summary": {}, "meta": {}, "files": []},
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.attach_toon_content_to_response"
        ) as mock_toon, patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            mock_toon.return_value = {"toon": "minimal"}
            await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "group_by_file": True,
                "suppress_output": True,
                "output_format": "toon",
            })
            mock_toon.assert_called()


class TestSummaryOutputBranches:
    """Test summary_only with output_file/suppress_output (lines 789-844)."""

    @pytest.mark.asyncio
    async def test_summary_with_output_file(self, tool, sample_project_structure):
        """Test summary_only with output_file (lines 793-818)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
            return_value={"top_files": ["file1.py"]},
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/summary.json"
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "summary_only": True,
                "output_file": "summary.json",
                "output_format": "json",
            })
            assert "file_saved" in result

    @pytest.mark.asyncio
    async def test_summary_output_file_suppress(self, tool, sample_project_structure):
        """Test summary_only with output_file and suppress_output (lines 802-814).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
            return_value={"top_files": ["file1.py"]},
        ), patch.object(
            tool.file_output_manager, "save_to_file", return_value="/out/summary.json"
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "summary_only": True,
                "output_file": "summary.json",
                "suppress_output": True,
                "output_format": "json",
            })
            assert result["success"] is True
            assert "output_file" in result

    @pytest.mark.asyncio
    async def test_summary_file_save_error(self, tool, sample_project_structure):
        """Test summary_only when file save fails (lines 819-822)."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
            return_value={"top_files": ["file1.py"]},
        ), patch.object(
            tool.file_output_manager, "save_to_file", side_effect=Exception("disk full")
        ):
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "summary_only": True,
                "output_file": "summary.json",
                "output_format": "json",
            })
            assert "file_save_error" in result
            assert result["file_saved"] is False

    @pytest.mark.asyncio
    async def test_summary_suppress_no_file(self, tool, sample_project_structure):
        """Test summary_only with suppress_output but no output_file (lines 823-836).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
            return_value={"top_files": ["file1.py"]},
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            result = await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "summary_only": True,
                "suppress_output": True,
                "output_format": "json",
            })
            assert result["success"] is True
            assert "results" not in result

    @pytest.mark.asyncio
    async def test_summary_suppress_no_file_toon(self, tool, sample_project_structure):
        """Test summary suppress_output (no file) in toon format (lines 834-835).

        Bypasses validator since these are mutually exclusive at validation level.
        """
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
            return_value=(0, b"", b""),
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
            return_value=[{"path": "file1.py"}],
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
            return_value={"top_files": ["file1.py"]},
        ), patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.attach_toon_content_to_response"
        ) as mock_toon, patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.get_default_validator"
        ) as mock_validator_fn:
            mock_validator_fn.return_value = MagicMock()
            mock_toon.return_value = {"toon": "minimal"}
            await tool.execute({
                "roots": [str(sample_project_structure)],
                "query": "test",
                "summary_only": True,
                "suppress_output": True,
                "output_format": "toon",
            })
            mock_toon.assert_called()


class TestCreateCountOnlyCacheKey:
    """Test _create_count_only_cache_key method (lines 307-334)."""

    def test_create_count_only_cache_key_no_cache(self, tool):
        """Test returns None when cache is disabled (line 317)."""
        tool.cache = None
        result = tool._create_count_only_cache_key("key", {"query": "test"})
        assert result is None

    def test_create_count_only_cache_key_success(self, tool):
        """Test creating count_only cache key from total_only key."""
        tool.cache = MagicMock()
        tool.cache.create_cache_key.return_value = "count_only_key"
        result = tool._create_count_only_cache_key(
            "total_only_key",
            {"query": "test", "roots": ["."], "total_only": True}
        )
        assert result == "count_only_key"
        # Verify that count_only_matches was set in the call
        tool.cache.create_cache_key.assert_called_once()
