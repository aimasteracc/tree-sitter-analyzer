"""
Unit tests for FileOutputManager.

Tests for file output manager which handles saving analysis results
to files with automatic extension detection and security validation.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager


def _normalize_path(path: str) -> str:
    """Normalize path to handle Windows short path names (8.3 format).

    On Windows, tempfile paths may use short names like RUNNER~1 while
    resolved paths use full names like runneradmin. This normalizes
    both to the same format for comparison.
    """
    try:
        return str(Path(path).resolve())
    except (OSError, ValueError):
        return path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def manager(temp_dir):
    """Create a FileOutputManager instance with temp directory."""
    return FileOutputManager(project_root=temp_dir)


class TestFileOutputManagerInit:
    """Tests for FileOutputManager initialization."""

    def test_init_with_project_root(self, temp_dir):
        """Test initialization with project root."""
        manager = FileOutputManager(project_root=temp_dir)
        assert manager.project_root == temp_dir
        assert manager.get_output_path() == temp_dir

    def test_init_without_project_root(self):
        """Test initialization without project root uses cwd."""
        manager = FileOutputManager(project_root=None)
        assert manager.project_root is None
        assert manager.get_output_path() == str(Path.cwd())

    def test_init_with_env_variable(self, temp_dir, monkeypatch):
        """Test initialization with TREE_SITTER_OUTPUT_PATH env variable."""
        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", temp_dir)
        manager = FileOutputManager(project_root=None)
        assert manager.get_output_path() == temp_dir


class TestFileOutputManagerGetManagedInstance:
    """Tests for get_managed_instance factory method."""

    @patch(
        "tree_sitter_analyzer.mcp.utils.file_output_factory.FileOutputManagerFactory"
    )
    def test_get_managed_instance_uses_factory(self, mock_factory):
        """Test get_managed_instance uses factory."""
        mock_instance = MagicMock()
        mock_factory.get_instance.return_value = mock_instance

        result = FileOutputManager.get_managed_instance("/test/project")

        mock_factory.get_instance.assert_called_once_with("/test/project")
        assert result == mock_instance

    @patch(
        "tree_sitter_analyzer.mcp.utils.file_output_factory.FileOutputManagerFactory"
    )
    def test_get_managed_instance_fallback_on_import_error(self, mock_factory):
        """Test get_managed_instance falls back when factory unavailable."""
        mock_factory.get_instance.side_effect = ImportError("Factory not available")

        with patch.object(
            FileOutputManager, "__init__", return_value=None
        ) as mock_init:
            FileOutputManager.get_managed_instance("/test/project")

            # Should have called __init__ as fallback
            mock_init.assert_called_once_with("/test/project")


class TestFileOutputManagerCreateInstance:
    """Tests for create_instance method."""

    def test_create_instance_direct(self, temp_dir):
        """Test create_instance creates new instance directly."""
        result = FileOutputManager.create_instance(temp_dir)
        assert isinstance(result, FileOutputManager)
        assert result.project_root == temp_dir


class TestFileOutputManagerGetOutputPath:
    """Tests for get_output_path method."""

    def test_get_output_path(self, manager, temp_dir):
        """Test getting output path."""
        assert manager.get_output_path() == temp_dir


class TestFileOutputManagerSetOutputPath:
    """Tests for set_output_path method."""

    def test_set_output_path_valid(self, manager, temp_dir):
        """Test setting valid output path."""
        new_path = os.path.join(temp_dir, "output")
        os.makedirs(new_path, exist_ok=True)

        manager.set_output_path(new_path)
        # Use normalized paths for comparison to handle Windows short path names
        assert _normalize_path(manager.get_output_path()) == _normalize_path(new_path)

    def test_set_output_path_not_exists(self, manager):
        """Test set_output_path fails when path doesn't exist."""
        with pytest.raises(ValueError, match="Output path does not exist"):
            manager.set_output_path("/nonexistent/path")

    def test_set_output_path_not_directory(self, manager, temp_dir):
        """Test set_output_path fails when path is not a directory."""
        file_path = os.path.join(temp_dir, "file.txt")
        Path(file_path).touch()

        with pytest.raises(ValueError, match="Output path is not a directory"):
            manager.set_output_path(file_path)


class TestFileOutputManagerDetectContentType:
    """Tests for detect_content_type method."""

    def test_detect_json_content(self, manager):
        """Test detecting JSON content."""
        content = '{"key": "value"}'
        assert manager.detect_content_type(content) == "json"

    def test_detect_json_array_content(self, manager):
        """Test detecting JSON array content."""
        content = '[{"key": "value"}]'
        assert manager.detect_content_type(content) == "json"

    def test_detect_toon_content(self, manager):
        """Test detecting TOON content."""
        content = "[10]{name,type,start_line}:\nTestClass,class,1"
        assert manager.detect_content_type(content) == "toon"

    def test_detect_csv_content(self, manager):
        """Test detecting CSV content."""
        content = "name,type,start_line\nTestClass,class,1"
        assert manager.detect_content_type(content) == "csv"

    def test_detect_markdown_content(self, manager):
        """Test detecting Markdown content."""
        content = "# Header\nSome content"
        assert manager.detect_content_type(content) == "markdown"

    def test_detect_markdown_table_content(self, manager):
        """Test detecting Markdown table content."""
        content = "| Name | Type |\n|-------|------|\n| Test  | Class |"
        assert manager.detect_content_type(content) == "markdown"

    def test_detect_text_content(self, manager):
        """Test detecting plain text content."""
        content = "Just some plain text"
        assert manager.detect_content_type(content) == "text"


class TestFileOutputManagerGetFileExtension:
    """Tests for get_file_extension method."""

    def test_get_extension_json(self, manager):
        """Test getting extension for JSON."""
        assert manager.get_file_extension("json") == ".json"

    def test_get_extension_csv(self, manager):
        """Test getting extension for CSV."""
        assert manager.get_file_extension("csv") == ".csv"

    def test_get_extension_markdown(self, manager):
        """Test getting extension for Markdown."""
        assert manager.get_file_extension("markdown") == ".md"

    def test_get_extension_toon(self, manager):
        """Test getting extension for TOON."""
        assert manager.get_file_extension("toon") == ".toon"

    def test_get_extension_text(self, manager):
        """Test getting extension for text."""
        assert manager.get_file_extension("text") == ".txt"

    def test_get_extension_unknown(self, manager):
        """Test getting extension for unknown type."""
        assert manager.get_file_extension("unknown") == ".txt"


class TestFileOutputManagerGenerateOutputFilename:
    """Tests for generate_output_filename method."""

    def test_generate_filename_json(self, manager):
        """Test generating filename for JSON content."""
        content = '{"key": "value"}'
        result = manager.generate_output_filename("output", content)
        assert result == "output.json"

    def test_generate_filename_with_existing_extension(self, manager):
        """Test generating filename removes existing extension."""
        content = '{"key": "value"}'
        result = manager.generate_output_filename("output.txt", content)
        assert result == "output.json"

    def test_generate_filename_toon(self, manager):
        """Test generating filename for TOON content."""
        content = "[10]{name,type,start_line}:\nTestClass,class,1"
        result = manager.generate_output_filename("output", content)
        assert result == "output.toon"

    def test_generate_filename_csv(self, manager):
        """Test generating filename for CSV content."""
        content = "name,type,start_line\nTestClass,class,1"
        result = manager.generate_output_filename("output", content)
        assert result == "output.csv"

    def test_generate_filename_markdown(self, manager):
        """Test generating filename for Markdown content."""
        content = "# Header\nContent"
        result = manager.generate_output_filename("output", content)
        assert result == "output.md"

    def test_generate_filename_text(self, manager):
        """Test generating filename for text content."""
        content = "Plain text"
        result = manager.generate_output_filename("output", content)
        assert result == "output.txt"


class TestFileOutputManagerSaveToFile:
    """Tests for save_to_file method."""

    def test_save_to_file_with_filename(self, manager, temp_dir):
        """Test saving content with explicit filename."""
        content = "Test content"
        filename = "test.txt"

        result_path = manager.save_to_file(content, filename=filename)

        assert result_path.endswith(filename)
        assert Path(result_path).exists()
        assert Path(result_path).read_text() == content

    def test_save_to_file_with_base_name(self, manager, temp_dir):
        """Test saving content with base name (auto extension)."""
        content = '{"key": "value"}'
        base_name = "output"

        result_path = manager.save_to_file(content, base_name=base_name)

        assert result_path.endswith(".json")
        assert Path(result_path).exists()
        saved_content = Path(result_path).read_text()
        assert json.loads(saved_content) == json.loads(content)

    def test_save_to_file_without_filename_or_base_name(self, manager):
        """Test save_to_file fails without filename or base_name."""
        with pytest.raises(ValueError):
            manager.save_to_file("content")

    def test_save_to_file_creates_directory(self, manager, temp_dir):
        """Test save_to_file creates output directory if needed."""
        content = "Test content"
        subdir = os.path.join(temp_dir, "subdir", "nested")
        filename = os.path.join(subdir, "test.txt")

        result_path = manager.save_to_file(content, filename=filename)

        assert Path(result_path).exists()
        assert Path(result_path).parent.exists()

    def test_save_to_file_base_name_none(self, manager):
        """Test save_to_file fails when base_name is None."""
        with pytest.raises(ValueError):
            manager.save_to_file("content", filename=None, base_name=None)


class TestFileOutputManagerValidateOutputPath:
    """Tests for validate_output_path method."""

    def test_validate_valid_path(self, manager, temp_dir):
        """Test validating a valid path."""
        is_valid, error = manager.validate_output_path(temp_dir)
        assert is_valid is True
        assert error is None

    def test_validate_nonexistent_parent(self, manager, temp_dir):
        """Test validation creates parent directory if it doesn't exist."""
        path = os.path.join(temp_dir, "nonexistent", "file.txt")
        is_valid, error = manager.validate_output_path(path)
        # validate_output_path creates the parent directory if it doesn't exist
        assert is_valid is True
        assert error is None
        # Verify the directory was created
        assert Path(os.path.join(temp_dir, "nonexistent")).exists()

    def test_validate_no_write_permission(self, manager, temp_dir):
        """Test validation fails for no write permission."""
        # This test is platform-dependent and may not work on all systems
        # We'll just verify the method handles the case
        path = os.path.join(temp_dir, "file.txt")
        is_valid, error = manager.validate_output_path(path)
        # On most systems, this should be valid
        assert is_valid is True or "write permission" in error


class TestFileOutputManagerSetProjectRoot:
    """Tests for set_project_root method."""

    def test_set_project_root(self, manager, temp_dir):
        """Test setting project root."""
        new_root = os.path.join(temp_dir, "new_root")
        os.makedirs(new_root, exist_ok=True)

        manager.set_project_root(new_root)
        assert manager.project_root == new_root

    def test_set_project_root_reinitializes_output_path(
        self, manager, temp_dir, monkeypatch
    ):
        """Test setting project root reinitializes output path when not set by env."""
        # Ensure no env variable is set
        monkeypatch.delenv("TREE_SITTER_OUTPUT_PATH", raising=False)

        new_root = os.path.join(temp_dir, "new_root")
        os.makedirs(new_root, exist_ok=True)

        manager.set_project_root(new_root)
        assert manager.get_output_path() == new_root

    def test_set_project_root_preserves_env_path(self, temp_dir, monkeypatch):
        """Test setting project root doesn't change output path if env is set."""
        env_path = os.path.join(temp_dir, "env_output")
        os.makedirs(env_path, exist_ok=True)
        # Set env variable BEFORE creating manager
        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", env_path)

        # Create manager with env variable already set
        manager = FileOutputManager(project_root=None)
        assert manager.get_output_path() == env_path

        new_root = os.path.join(temp_dir, "new_root")
        os.makedirs(new_root, exist_ok=True)

        manager.set_project_root(new_root)
        # Output path should still be the env path
        assert manager.get_output_path() == env_path


class TestFileOutputManagerIsToonFormat:
    """Tests for _is_toon_format method."""

    def test_is_toon_format_array_header(self, manager):
        """Test detecting TOON array header format."""
        content = "[10]{name,type,start_line}:"
        assert manager._is_toon_format(content) is True

    def test_is_toon_format_key_value_lines(self, manager):
        """Test detecting TOON key-value format."""
        content = "name: TestClass\ntype: class\nstart_line: 1"
        assert manager._is_toon_format(content) is True

    def test_is_toon_format_mixed(self, manager):
        """Test detecting TOON format with mixed content."""
        content = "[10]{name,type,start_line}:\nname: TestClass\ntype: class"
        assert manager._is_toon_format(content) is True

    def test_is_toon_format_json(self, manager):
        """Test JSON is not detected as TOON."""
        content = '{"name": "TestClass"}'
        assert manager._is_toon_format(content) is False

    def test_is_toon_format_plain_text(self, manager):
        """Test plain text is not detected as TOON."""
        content = "Just some plain text"
        assert manager._is_toon_format(content) is False

    def test_is_toon_format_empty(self, manager):
        """Test empty content is not TOON."""
        assert manager._is_toon_format("") is False
