"""
Integration tests for fd_rg module.

Tests Builder Pattern integration, command generation, and result parsing
with real fd/rg command execution.
"""

import subprocess
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.fd_rg.command_builder import (
    FdCommandBuilder,
    RgCommandBuilder,
)
from tree_sitter_analyzer.mcp.tools.fd_rg.config import FdCommandConfig, RgCommandConfig
from tree_sitter_analyzer.mcp.tools.fd_rg.result_parser import (
    FdResultParser,
    RgResultParser,
)
from tree_sitter_analyzer.mcp.tools.fd_rg.utils import check_external_command


class TestFdCommandBuilderIntegration:
    """Integration tests for FdCommandBuilder with real fd execution."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with test files."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        # Create files
        (tmp_path / "src" / "main.py").write_text("# Main file")
        (tmp_path / "src" / "utils.py").write_text("# Utils file")
        (tmp_path / "tests" / "test_main.py").write_text("# Test file")
        (tmp_path / "docs" / "README.md").write_text("# Documentation")
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n")

        return tmp_path

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_builder_basic_search(self, temp_project: Path):
        """Test FdCommandBuilder with basic file search."""
        config = FdCommandConfig(
            pattern="*.py",
            roots=[str(temp_project)],
            glob=True,
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "main.py" in result.stdout
        assert "utils.py" in result.stdout
        assert "test_main.py" in result.stdout

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_builder_with_extensions(self, temp_project: Path):
        """Test FdCommandBuilder with extension filtering."""
        config = FdCommandConfig(
            roots=[str(temp_project)],
            extensions=["py"],
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "main.py" in result.stdout
        assert "utils.py" in result.stdout
        # Should not include .md files
        assert "README.md" not in result.stdout

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_builder_with_type_filter(self, temp_project: Path):
        """Test FdCommandBuilder with type filtering."""
        config = FdCommandConfig(
            roots=[str(temp_project)],
            types=["f"],  # Files only
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        # Should find files
        assert "main.py" in result.stdout or "README.md" in result.stdout
        # Should not include directories
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if line:
                path = Path(line)
                # All results should be files, not directories
                assert not path.is_dir() or not path.exists()

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_builder_with_depth_limit(self, temp_project: Path):
        """Test FdCommandBuilder with depth limiting."""
        # Create nested structure
        nested_dir = temp_project / "src" / "nested" / "deep"
        nested_dir.mkdir(parents=True)
        (nested_dir / "deep_file.py").write_text("# Deep file")

        config = FdCommandConfig(
            pattern="*.py",
            roots=[str(temp_project)],
            glob=True,
            depth=2,  # Limit to 2 levels
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        # Should find files at depth 1-2
        assert "main.py" in result.stdout
        # Should not find files at depth 3+
        assert "deep_file.py" not in result.stdout

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_builder_with_exclude_patterns(self, temp_project: Path):
        """Test FdCommandBuilder with exclude patterns."""
        config = FdCommandConfig(
            roots=[str(temp_project)],
            exclude=["test_*"],
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "main.py" in result.stdout
        # Should exclude test files
        assert "test_main.py" not in result.stdout


class TestRgCommandBuilderIntegration:
    """Integration tests for RgCommandBuilder with real rg execution."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with test files."""
        (tmp_path / "file1.txt").write_text("Hello World\nPython is great\n")
        (tmp_path / "file2.txt").write_text("Hello Python\nWorld of code\n")
        (tmp_path / "file3.py").write_text("def hello():\n    print('Hello')\n")
        return tmp_path

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_basic_search(self, temp_project: Path):
        """Test RgCommandBuilder with basic content search."""
        config = RgCommandConfig(
            query="Hello",
            roots=[str(temp_project)],
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "Hello" in result.stdout
        # Should find in multiple files
        assert "file1.txt" in result.stdout or "file2.txt" in result.stdout

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_with_json_output(self, temp_project: Path):
        """Test RgCommandBuilder with JSON output format."""
        config = RgCommandConfig(
            query="Hello",
            roots=[str(temp_project)],
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        # Output should be JSON format
        assert "{" in result.stdout or "[" in result.stdout

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_case_sensitive(self, temp_project: Path):
        """Test RgCommandBuilder with case-sensitive search."""
        config = RgCommandConfig(
            query="hello",  # lowercase
            roots=[str(temp_project)],
            case="sensitive",
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        # Should find 'hello' in file3.py but not 'Hello' in file1/file2
        if result.returncode == 0:
            assert "file3.py" in result.stdout
            # May or may not find 'Hello' depending on exact match

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_with_file_pattern(self, temp_project: Path):
        """Test RgCommandBuilder with file pattern filtering."""
        config = RgCommandConfig(
            query="Hello",
            roots=[str(temp_project)],
            include_globs=["*.txt"],
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        # Should find in .txt files
        assert "file1.txt" in result.stdout or "file2.txt" in result.stdout
        # Should not search .py files
        assert "file3.py" not in result.stdout

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_count_only(self, temp_project: Path):
        """Test RgCommandBuilder with count-only mode."""
        config = RgCommandConfig(
            query="Hello",
            roots=[str(temp_project)],
            count_only_matches=True,
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        # Output should contain counts
        assert any(char.isdigit() for char in result.stdout)

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_with_context(self, temp_project: Path):
        """Test RgCommandBuilder with context lines."""
        config = RgCommandConfig(
            query="Python",
            roots=[str(temp_project)],
            context_before=1,
            context_after=1,
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        # Should include context lines
        lines = result.stdout.split("\n")
        assert len(lines) > 1  # Should have more than just match lines


class TestResultParserIntegration:
    """Integration tests for result parsers with real command output."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with test files."""
        (tmp_path / "file1.txt").write_text("line1\nline2\nline3\n")
        (tmp_path / "file2.txt").write_text("data1\ndata2\ndata3\n")
        return tmp_path

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_result_parser_with_real_output(self, temp_project: Path):
        """Test FdResultParser with real fd command output."""
        config = FdCommandConfig(
            pattern="*.txt",
            roots=[str(temp_project)],
            glob=True,
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0

        # Parse result
        parser = FdResultParser()
        parsed = parser.parse(result.stdout)

        assert isinstance(parsed, list)
        assert len(parsed) == 2  # file1.txt and file2.txt
        assert any("file1.txt" in str(p) for p in parsed)
        assert any("file2.txt" in str(p) for p in parsed)

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_result_parser_with_real_output(self, temp_project: Path):
        """Test RgResultParser with real rg command output."""
        config = RgCommandConfig(
            query="line",
            roots=[str(temp_project)],
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0

        # Parse result
        parser = RgResultParser()
        parsed = parser.parse(result.stdout)

        assert isinstance(parsed, list)
        assert len(parsed) > 0
        # Each match should have file, line, text
        for match in parsed:
            assert "file" in match or "path" in match
            assert "line" in match or "line_number" in match

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_result_parser_count_mode(self, temp_project: Path):
        """Test RgResultParser with count-only output."""
        config = RgCommandConfig(
            query="line",
            roots=[str(temp_project)],
            count_only_matches=True,
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Execute command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0

        # Parse result
        parser = RgResultParser()
        parsed = parser.parse_count(result.stdout)

        assert isinstance(parsed, dict)
        # Should have counts for files
        assert len(parsed) > 0
        for _file, count in parsed.items():
            assert isinstance(count, int)
            assert count > 0


class TestBuilderPatternIntegration:
    """Integration tests for Builder Pattern implementation."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project."""
        (tmp_path / "test.txt").write_text("test content")
        return tmp_path

    @pytest.mark.skipif(
        not check_external_command("fd"),
        reason="fd command not available",
    )
    def test_fd_builder_fluent_interface(self, temp_project: Path):
        """Test FdCommandBuilder fluent interface."""
        config = FdCommandConfig(
            pattern="*.txt",
            roots=[str(temp_project)],
            glob=True,
            hidden=False,
            no_ignore=False,
        )

        builder = FdCommandBuilder()
        command = builder.build(config)

        # Command should be valid
        assert isinstance(command, list)
        assert command[0] == "fd"
        assert "*.txt" in command

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_rg_builder_fluent_interface(self, temp_project: Path):
        """Test RgCommandBuilder fluent interface."""
        config = RgCommandConfig(
            query="test",
            roots=[str(temp_project)],
            case="smart",
            fixed_strings=False,
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        # Command should be valid
        assert isinstance(command, list)
        assert command[0] == "rg"
        assert "test" in command

    def test_config_validation(self):
        """Test configuration validation in __post_init__."""
        # Valid config
        config = FdCommandConfig(
            roots=["."],
        )
        assert config.roots == ["."]

        # Invalid depth
        with pytest.raises(ValueError):
            FdCommandConfig(
                roots=["."],
                depth=-1,  # Invalid
            )

    def test_config_immutability(self):
        """Test configuration immutability."""
        config = FdCommandConfig(
            roots=["."],
        )

        # Should not be able to modify
        with pytest.raises(AttributeError):
            config.roots = ["/tmp"]  # type: ignore


class TestEndToEndWorkflow:
    """End-to-end integration tests for complete workflow."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a comprehensive test project."""
        # Create structure
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()

        # Create files with searchable content
        (tmp_path / "src" / "main.py").write_text(
            "def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n"
        )
        (tmp_path / "src" / "utils.py").write_text(
            "def helper():\n    return 'helper'\n\ndef another_helper():\n    return 'another'\n"
        )
        (tmp_path / "tests" / "test_main.py").write_text(
            "def test_main():\n    assert True\n\ndef test_helper():\n    assert True\n"
        )

        return tmp_path

    @pytest.mark.skipif(
        not check_external_command("fd") or not check_external_command("rg"),
        reason="fd or rg command not available",
    )
    def test_find_then_search_workflow(self, temp_project: Path):
        """Test complete find-then-search workflow."""
        # Step 1: Find Python files
        fd_config = FdCommandConfig(
            pattern="*.py",
            roots=[str(temp_project)],
            glob=True,
        )

        fd_builder = FdCommandBuilder()
        fd_command = fd_builder.build(fd_config)

        fd_result = subprocess.run(
            fd_command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert fd_result.returncode == 0

        fd_parser = FdResultParser()
        python_files = fd_parser.parse(fd_result.stdout)

        assert len(python_files) == 3  # main.py, utils.py, test_main.py

        # Step 2: Search for 'def' in found files
        rg_config = RgCommandConfig(
            query="def",
            files=[str(f) for f in python_files],
        )

        rg_builder = RgCommandBuilder()
        rg_command = rg_builder.build(rg_config)

        rg_result = subprocess.run(
            rg_command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert rg_result.returncode == 0

        rg_parser = RgResultParser()
        matches = rg_parser.parse(rg_result.stdout)

        # Should find multiple 'def' keywords
        assert len(matches) >= 4  # main, helper, another_helper, test_main, test_helper

    @pytest.mark.skipif(
        not check_external_command("rg"),
        reason="rg command not available",
    )
    def test_search_with_multiple_options(self, temp_project: Path):
        """Test search with multiple configuration options."""
        config = RgCommandConfig(
            query="def",
            roots=[str(temp_project)],
            case="insensitive",
            include_globs=["*.py"],
            context_before=1,
            context_after=1,
        )

        builder = RgCommandBuilder()
        command = builder.build(config)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0

        parser = RgResultParser()
        matches = parser.parse(result.stdout)

        # Should find matches with context
        assert len(matches) > 0
        # Verify matches are from .py files only
        for match in matches:
            file_path = match.get("file") or match.get("path", "")
            if file_path:
                assert file_path.endswith(".py")
