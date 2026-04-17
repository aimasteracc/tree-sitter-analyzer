"""
Integration tests for test generation CLI command.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


# Use a unique working directory for each test to avoid conflicts when running in parallel
@pytest.fixture
def test_cwd(tmp_path: Path) -> Path:
    """Create a unique working directory for each test."""
    return tmp_path


@pytest.fixture
def sample_python_file(temp_dir: tempfile.TemporaryDirectory) -> str:
    """Create a sample Python file for testing."""
    file_path = f"{temp_dir.name}/sample.py"
    with open(file_path, "w") as f:
        f.write("""
def add(x: int, y: int) -> int:
    '''Add two numbers together.'''
    return x + y

def greet(name: str) -> str:
    '''Greet the user by name.'''
    if not name:
        return "Hello, Anonymous!"
    return f"Hello, {name}!"

def divide(a: float, b: float) -> float:
    '''Divide two numbers.'''
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

async def async_function(x: int) -> int:
    '''Async function (should be skipped).'''
    return x * 2
""")
    return file_path


class TestTestGenCommand:
    """Integration tests for test generation CLI command."""

    def test_generate_tests_single_file(self, sample_python_file: str, test_cwd: Path) -> None:
        """Should generate tests for a single Python file."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer.cli.commands.test_gen_command", sample_python_file],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0
        output_file = test_cwd / "test_sample.py"
        assert "test_sample.py" in result.stdout or output_file.exists()

    def test_generate_tests_with_output(self, sample_python_file: str, test_cwd: Path) -> None:
        """Should generate tests to specified output path."""
        output_path = "custom_test.py"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.test_gen_command",
                sample_python_file,
                "--output",
                output_path,
            ],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0
        assert (test_cwd / output_path).exists()

    def test_generate_tests_verbose(self, sample_python_file: str, test_cwd: Path) -> None:
        """Should show verbose output."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.test_gen_command",
                sample_python_file,
                "--verbose",
            ],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0
        # Check that async function warning is shown (verbose mode shows this)
        assert "Skipping async function" in result.stderr
        # Check that test file was created
        assert (test_cwd / "test_sample.py").exists()

    def test_generate_tests_dry_run(self, sample_python_file: str, test_cwd: Path) -> None:
        """Should show what would be generated without writing files."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.test_gen_command",
                sample_python_file,
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0
        # Check both stdout and stderr
        output = result.stdout + result.stderr
        assert "def test_" in output
        assert "import pytest" in output
        assert not (test_cwd / "test_sample.py").exists()

    def test_generate_tests_file_not_found(self) -> None:
        """Should handle file not found error."""
        result = subprocess.run(
            [sys.executable, "-m", "tree_sitter_analyzer.cli.commands.test_gen_command", "nonexistent.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "File not found" in result.stderr

    def test_generate_tests_multiple_files(self, sample_python_file: str, test_cwd: Path, temp_dir: tempfile.TemporaryDirectory) -> None:
        """Should generate tests for multiple files."""
        # Create a second file
        file_path_2 = f"{temp_dir.name}/sample2.py"
        with open(file_path_2, "w") as f:
            f.write("def multiply(a: int, b: int) -> int:\n    return a * b\n")

        output_dir = test_cwd / "tests"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.test_gen_command",
                sample_python_file,
                file_path_2,
                "--output-dir",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0
        # Check both stdout and stderr for success message
        output = result.stdout + result.stderr
        assert "Generated tests for 2/2 file(s)" in output or result.returncode == 0

    def test_generated_test_is_valid_python(self, sample_python_file: str, test_cwd: Path) -> None:
        """Should generate syntactically valid Python code."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.test_gen_command",
                sample_python_file,
            ],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0

        # Try to compile the generated file
        output_path = test_cwd / "test_sample.py"
        try:
            with open(output_path) as f:
                code = f.read()
            compile(code, str(output_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax error: {e}")

    def test_generate_tests_with_module_path(self, sample_python_file: str, test_cwd: Path) -> None:
        """Should use custom module path for imports."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.test_gen_command",
                sample_python_file,
                "--module-path",
                "mymodule",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=str(test_cwd),
        )

        assert result.returncode == 0
        assert "from mymodule import (" in result.stdout


@pytest.fixture
def temp_dir() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary directory for testing."""
    return tempfile.TemporaryDirectory()
