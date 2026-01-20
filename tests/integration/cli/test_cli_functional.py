#!/usr/bin/env python3
"""
Functional integration tests for the CLI commands.
Tests real execution paths without mocking the core engine.
"""

import subprocess
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def sample_py():
    project_root = Path(__file__).parent.parent.parent.parent.resolve()
    temp_dir = project_root / "tests" / "temp_samples"
    temp_dir.mkdir(parents=True, exist_ok=True)
    unique_id = uuid.uuid4().hex
    path = temp_dir / f"sample_{unique_id}.py"
    path.write_text(
        "class MyClass:\n    def my_method(self):\n        return 42\n",
        encoding="utf-8",
    )
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def sample_java():
    project_root = Path(__file__).parent.parent.parent.parent.resolve()
    temp_dir = project_root / "tests" / "temp_samples"
    temp_dir.mkdir(parents=True, exist_ok=True)
    unique_id = uuid.uuid4().hex
    path = temp_dir / f"Sample_{unique_id}.java"
    path.write_text(
        "public class Sample {\n    public void test() {}\n}\n", encoding="utf-8"
    )
    yield path
    if path.exists():
        path.unlink()


def run_cli(*args):
    return subprocess.run(
        ["uv", "run", "tree-sitter-analyzer"] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestCLIFunctional:
    """Verify CLI commands work end-to-end with real files."""

    def test_summary_command_real(self, sample_py):
        res = run_cli(str(sample_py.resolve()), "--summary")
        assert res.returncode == 0
        assert "Summary Results" in res.stdout
        assert "MyClass" in res.stdout

    def test_table_full_command_real(self, sample_java):
        res = run_cli(str(sample_java.resolve()), "--table", "full")
        assert res.returncode == 0
        assert "Sample" in res.stdout
        assert "class" in res.stdout.lower()

    def test_query_command_real(self, sample_py):
        res = run_cli(str(sample_py.resolve()), "--query-key", "functions")
        assert res.returncode == 0
        assert "my_method" in res.stdout

    def test_toon_format_real(self, sample_py):
        res = run_cli(str(sample_py.resolve()), "--table", "toon")
        assert res.returncode == 0
        assert "MyClass" in res.stdout
        assert "my_method" in res.stdout

    def test_invalid_file_error(self):
        res = run_cli("nonexistent_file_that_really_does_not_exist.py")
        assert res.returncode != 0
        assert "exist" in res.stderr
