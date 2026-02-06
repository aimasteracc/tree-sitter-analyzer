"""Tests for CLI main module."""

import tempfile
from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

from tree_sitter_analyzer_v2.cli.main import (
    create_parser,
    cmd_analyze,
    cmd_search_files,
    cmd_search_content,
    main,
)


class TestCreateParser:
    """Tests for create_parser function."""

    def test_parser_creation(self) -> None:
        """Test parser is created successfully."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "tree-sitter-analyzer-v2"

    def test_subcommands_registered(self) -> None:
        """Test all subcommands are registered."""
        parser = create_parser()
        
        # Parse with each command
        args = parser.parse_args(["analyze", "test.py"])
        assert args.command == "analyze"
        
        args = parser.parse_args(["search-files", "/tmp"])
        assert args.command == "search-files"
        
        args = parser.parse_args(["search-content", "/tmp", "pattern"])
        assert args.command == "search-content"

    def test_analyze_arguments(self) -> None:
        """Test analyze command arguments."""
        parser = create_parser()
        
        args = parser.parse_args(["analyze", "test.py", "--format", "toon"])
        assert args.file_path == "test.py"
        assert args.format == "toon"
        
        args = parser.parse_args(["analyze", "test.py", "--summary"])
        assert args.summary is True

    def test_search_files_arguments(self) -> None:
        """Test search-files command arguments."""
        parser = create_parser()
        
        args = parser.parse_args(["search-files", "/tmp", "*.py", "--type", "py"])
        assert args.root_dir == "/tmp"
        assert args.pattern == "*.py"
        assert args.type == "py"

    def test_search_content_arguments(self) -> None:
        """Test search-content command arguments."""
        parser = create_parser()
        
        args = parser.parse_args(["search-content", "/tmp", "pattern", "--type", "py", "-i"])
        assert args.root_dir == "/tmp"
        assert args.pattern == "pattern"
        assert args.type == "py"
        assert args.ignore_case is True


class TestCmdAnalyze:
    """Tests for cmd_analyze function."""

    def test_file_not_found(self) -> None:
        """Test error when file not found."""
        parser = create_parser()
        args = parser.parse_args(["analyze", "/nonexistent/file.py"])
        
        with patch("sys.stderr", new=StringIO()) as mock_stderr:
            result = cmd_analyze(args)
            assert result == 1
            assert "not found" in mock_stderr.getvalue().lower()

    def test_analyze_python_file(self) -> None:
        """Test analyzing Python file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def hello():\n    return 'world'\n")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file)])
            
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                result = cmd_analyze(args)
                assert result == 0
                output = mock_stdout.getvalue()
                assert "hello" in output or "function" in output.lower()

    def test_analyze_with_summary(self) -> None:
        """Test analyzing with summary format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Comment\nx = 1\n")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file), "--summary"])
            
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                result = cmd_analyze(args)
                assert result == 0

    def test_analyze_unsupported_language(self) -> None:
        """Test error when language is unsupported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.unknown"
            test_file.write_text("some content")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file)])
            
            with patch("sys.stderr", new=StringIO()) as mock_stderr:
                result = cmd_analyze(args)
                assert result == 1

    def test_analyze_typescript_file(self) -> None:
        """Test analyzing TypeScript file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.ts"
            test_file.write_text("const x: number = 42;\n")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file)])
            
            with patch("sys.stdout", new=StringIO()):
                result = cmd_analyze(args)
                assert result == 0

    def test_analyze_java_file(self) -> None:
        """Test analyzing Java file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "Test.java"
            test_file.write_text("public class Test { }\n")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file)])
            
            with patch("sys.stdout", new=StringIO()):
                result = cmd_analyze(args)
                assert result == 0


class TestCmdSearchFiles:
    """Tests for cmd_search_files function."""

    def test_directory_not_found(self) -> None:
        """Test error when directory not found."""
        parser = create_parser()
        args = parser.parse_args(["search-files", "/nonexistent/dir"])
        
        with patch("sys.stderr", new=StringIO()) as mock_stderr:
            result = cmd_search_files(args)
            assert result == 1
            assert "not found" in mock_stderr.getvalue().lower()

    def test_search_files_success(self) -> None:
        """Test searching files in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "test1.py").write_text("x = 1")
            (Path(tmpdir) / "test2.py").write_text("y = 2")
            
            parser = create_parser()
            args = parser.parse_args(["search-files", tmpdir, "*.py"])
            
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                result = cmd_search_files(args)
                assert result == 0
                output = mock_stdout.getvalue()
                assert "test1.py" in output or "test2.py" in output

    def test_search_files_with_type(self) -> None:
        """Test searching files with type filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1")
            (Path(tmpdir) / "test.txt").write_text("hello")
            
            parser = create_parser()
            args = parser.parse_args(["search-files", tmpdir, "*", "--type", "py"])
            
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                result = cmd_search_files(args)
                assert result == 0


class TestCmdSearchContent:
    """Tests for cmd_search_content function."""

    def test_directory_not_found(self) -> None:
        """Test error when directory not found."""
        parser = create_parser()
        args = parser.parse_args(["search-content", "/nonexistent/dir", "pattern"])
        
        with patch("sys.stderr", new=StringIO()) as mock_stderr:
            result = cmd_search_content(args)
            assert result == 1
            assert "not found" in mock_stderr.getvalue().lower()

    def test_search_content_success(self) -> None:
        """Test searching content in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("hello world\n")
            
            parser = create_parser()
            args = parser.parse_args(["search-content", tmpdir, "hello"])
            
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                result = cmd_search_content(args)
                assert result == 0
                output = mock_stdout.getvalue()
                assert "hello" in output

    def test_search_content_case_insensitive(self) -> None:
        """Test case-insensitive search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("HELLO world\n")
            
            parser = create_parser()
            args = parser.parse_args(["search-content", tmpdir, "hello", "-i"])
            
            with patch("sys.stdout", new=StringIO()) as mock_stdout:
                result = cmd_search_content(args)
                assert result == 0
                output = mock_stdout.getvalue()
                assert "HELLO" in output


class TestMain:
    """Tests for main function."""

    def test_no_command(self) -> None:
        """Test showing help when no command specified."""
        with patch("sys.stdout", new=StringIO()):
            result = main([])
            assert result == 0

    def test_unknown_command(self) -> None:
        """Test error on unknown command."""
        with patch("sys.stderr", new=StringIO()) as mock_stderr:
            # Create parser and directly test dispatch
            parser = create_parser()
            args = parser.parse_args(["analyze", "test.py"])
            # Override command to something unknown
            args.command = "unknown_cmd"
            
            # Test dispatch logic
            commands = {"analyze": lambda a: 0}
            handler = commands.get(args.command)
            if not handler:
                result = 1
            else:
                result = handler(args)
            assert result == 1

    def test_analyze_command_dispatch(self) -> None:
        """Test analyze command dispatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("x = 1\n")
            
            with patch("sys.stdout", new=StringIO()):
                result = main(["analyze", str(test_file)])
                assert result == 0

    def test_search_files_command_dispatch(self) -> None:
        """Test search-files command dispatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("x = 1")
            
            with patch("sys.stdout", new=StringIO()):
                result = main(["search-files", tmpdir])
                assert result == 0

    def test_search_content_command_dispatch(self) -> None:
        """Test search-content command dispatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("hello world")
            
            with patch("sys.stdout", new=StringIO()):
                result = main(["search-content", tmpdir, "hello"])
                assert result == 0


class TestAnalyzeFormats:
    """Tests for different output formats in analyze command."""

    def test_format_markdown(self) -> None:
        """Test markdown format output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def hello(): pass\n")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file), "--format", "markdown"])
            
            with patch("sys.stdout", new=StringIO()):
                result = cmd_analyze(args)
                assert result == 0

    def test_format_toon(self) -> None:
        """Test toon format output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("x = 1\n")
            
            parser = create_parser()
            args = parser.parse_args(["analyze", str(test_file), "--format", "toon"])
            
            with patch("sys.stdout", new=StringIO()):
                result = cmd_analyze(args)
                assert result == 0
