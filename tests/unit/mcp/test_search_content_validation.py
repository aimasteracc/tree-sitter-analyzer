#!/usr/bin/env python3
"""SearchContentTool validation tests — roots, files, arguments."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import (
    SearchContentTool,
)


@pytest.fixture
def tool():
    return SearchContentTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")
    return tmp_path


class TestValidateRoots:
    """Tests for _validate_roots method."""

    def test_validate_roots_success(self, tool, sample_project_structure):
        roots = [str(sample_project_structure)]
        validated = tool._validate_roots(roots)
        assert len(validated) == 1
        assert Path(validated[0]).is_absolute()

    def test_validate_roots_invalid_directory(self, tool):
        roots = ["/nonexistent/directory"]
        with pytest.raises(ValueError, match="Invalid root"):
            tool._validate_roots(roots)


class TestValidateFiles:
    """Tests for _validate_files method."""

    def test_validate_files_success(self, tool, sample_project_structure):
        files = [str(sample_project_structure / "README.md")]
        validated = tool._validate_files(files)
        assert len(validated) == 1

    def test_validate_files_empty_string(self, tool):
        files = [""]
        with pytest.raises(ValueError, match="files entries must be non-empty strings"):
            tool._validate_files(files)

    def test_validate_files_not_found(self, tool):
        files = ["/nonexistent/file.txt"]
        with pytest.raises(ValueError, match="Invalid file path"):
            tool._validate_files(files)


class TestValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments_with_roots(self, tool, sample_project_structure):
        arguments = {
            "roots": [str(sample_project_structure)],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_valid_arguments_with_files(self, tool, sample_project_structure):
        arguments = {
            "files": [str(sample_project_structure / "README.md")],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_query(self, tool):
        arguments = {"roots": ["."]}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_empty_query(self, tool):
        arguments = {"roots": ["."], "query": ""}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_whitespace_query(self, tool):
        arguments = {"roots": ["."], "query": "   "}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_missing_both_roots_and_files(self, tool):
        arguments = {"query": "test"}
        with pytest.raises(ValueError, match="Either roots or files must be provided"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_case_type(self, tool):
        arguments = {"roots": ["."], "query": "test", "case": 123}
        with pytest.raises(ValueError, match="case must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_encoding_type(self, tool):
        arguments = {
            "roots": ["."],
            "query": "test",
            "encoding": 123,
        }
        with pytest.raises(ValueError, match="encoding must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_max_filesize_type(self, tool):
        arguments = {
            "roots": ["."],
            "query": "test",
            "max_filesize": 123,
        }
        with pytest.raises(ValueError, match="max_filesize must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_fixed_strings_type(self, tool):
        arguments = {
            "roots": ["."],
            "query": "test",
            "fixed_strings": "true",
        }
        with pytest.raises(ValueError, match="fixed_strings must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_word_type(self, tool):
        arguments = {"roots": ["."], "query": "test", "word": "true"}
        with pytest.raises(ValueError, match="word must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_multiline_type(self, tool):
        arguments = {
            "roots": ["."],
            "query": "test",
            "multiline": "true",
        }
        with pytest.raises(ValueError, match="multiline must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_include_globs_type(self, tool):
        arguments = {
            "roots": ["."],
            "query": "test",
            "include_globs": "*.py",
        }
        with pytest.raises(
            ValueError, match="include_globs must be an array of strings"
        ):
            tool.validate_arguments(arguments)
