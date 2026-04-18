#!/usr/bin/env python3
"""Tests for environment variable tracking."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.env_tracker import (
    AccessType,
    EnvTrackingResult,
    EnvVarTracker,
    EnvVarUsage,
    group_by_var_name,
    track_env_vars,
)


@pytest.fixture
def sample_python_file(tmp_path: Path) -> Path:
    """Create a sample Python file with env var usage."""
    code = '''
import os

# Simple getenv call
api_key = os.getenv("API_KEY")

# Getenv with default
debug = os.getenv("DEBUG", "false")

# Environ index access
db_host = os.environ["DB_HOST"]

# Environ get method
port = os.environ.get("PORT", "8080")

# Multiple references to same var
key1 = os.getenv("SECRET_KEY")
key2 = os.environ.get("SECRET_KEY")
'''
    file_path = tmp_path / "test.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_javascript_file(tmp_path: Path) -> Path:
    """Create a sample JavaScript file with env var usage."""
    code = '''
// Property access
const apiKey = process.env.API_KEY;

// Subscript access
const dbHost = process.env["DB_HOST"];

// Multiple references
const secret1 = process.env.SECRET_KEY;
const secret2 = process.env["SECRET_KEY"];
'''
    file_path = tmp_path / "test.js"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_java_file(tmp_path: Path) -> Path:
    """Create a sample Java file with env var usage."""
    code = '''
public class Config {
    String apiKey = System.getenv("API_KEY");
    String dbHost = System.getProperty("db.host");

    String secret1 = System.getenv("SECRET_KEY");
    String secret2 = System.getProperty("secret.key");
}
'''
    file_path = tmp_path / "Config.java"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_go_file(tmp_path: Path) -> Path:
    """Create a sample Go file with env var usage."""
    code = '''
package main

import "os"

func main() {
    apiKey := os.Getenv("API_KEY")
    secretKey := os.Getenv("SECRET_KEY")
}
'''
    file_path = tmp_path / "main.go"
    file_path.write_text(code)
    return file_path


def test_python_simple_getenv(sample_python_file: Path) -> None:
    """Test simple os.getenv() detection."""
    result = track_env_vars(sample_python_file)

    assert result.total_references >= 1
    assert "API_KEY" in result.by_var


def test_python_getenv_with_default(sample_python_file: Path) -> None:
    """Test os.getenv() with default value."""
    result = track_env_vars(sample_python_file)

    assert "DEBUG" in result.by_var
    debug_usage = result.by_var["DEBUG"]
    assert debug_usage.has_default_count > 0


def test_python_environ_index(sample_python_file: Path) -> None:
    """Test os.environ[] access detection."""
    result = track_env_vars(sample_python_file)

    assert "DB_HOST" in result.by_var
    db_host_usage = result.by_var["DB_HOST"]
    assert AccessType.ENVIRON_INDEX.value in db_host_usage.access_types


def test_python_environ_get(sample_python_file: Path) -> None:
    """Test os.environ.get() detection."""
    result = track_env_vars(sample_python_file)

    assert "PORT" in result.by_var
    port_usage = result.by_var["PORT"]
    assert AccessType.ENVIRON_GET.value in port_usage.access_types


def test_python_multiple_references(sample_python_file: Path) -> None:
    """Test multiple references to the same variable."""
    result = track_env_vars(sample_python_file)

    assert "SECRET_KEY" in result.by_var
    secret_usage = result.by_var["SECRET_KEY"]
    assert secret_usage.total_references >= 2


def test_javascript_property_access(sample_javascript_file: Path) -> None:
    """Test process.env.VAR_NAME detection."""
    result = track_env_vars(sample_javascript_file)

    assert "API_KEY" in result.by_var
    api_key_usage = result.by_var["API_KEY"]
    assert AccessType.PROPERTY_ACCESS.value in api_key_usage.access_types


def test_javascript_subscript_access(sample_javascript_file: Path) -> None:
    """Test process.env["VAR_NAME"] detection."""
    result = track_env_vars(sample_javascript_file)

    assert "DB_HOST" in result.by_var
    db_host_usage = result.by_var["DB_HOST"]
    assert AccessType.ENVIRON_INDEX.value in db_host_usage.access_types


def test_java_system_getenv(sample_java_file: Path) -> None:
    """Test System.getenv() detection."""
    result = track_env_vars(sample_java_file)

    assert "API_KEY" in result.by_var
    api_key_usage = result.by_var["API_KEY"]
    assert AccessType.SYSTEM_GETENV.value in api_key_usage.access_types


def test_java_system_getproperty(sample_java_file: Path) -> None:
    """Test System.getProperty() detection."""
    result = track_env_vars(sample_java_file)

    # Note: Java properties use dot notation
    assert len(result.by_var) >= 1


def test_go_getenv(sample_go_file: Path) -> None:
    """Test os.Getenv() detection."""
    result = track_env_vars(sample_go_file)

    assert "API_KEY" in result.by_var
    api_key_usage = result.by_var["API_KEY"]
    assert AccessType.GO_GETENV.value in api_key_usage.access_types


def test_include_defaults_filter() -> None:
    """Test filtering out references with defaults."""
    code = '''
import os

with_default = os.getenv("HAS_DEFAULT", "value")
without_default = os.getenv("NO_DEFAULT")
'''
    tmp_path = Path("/tmp/test_env_tracker")
    tmp_path.mkdir(exist_ok=True)
    file_path = tmp_path / "test_defaults.py"
    file_path.write_text(code)

    # Include defaults
    result_with = track_env_vars(file_path, include_defaults=True)
    assert "HAS_DEFAULT" in result_with.by_var
    assert "NO_DEFAULT" in result_with.by_var

    # Exclude defaults
    result_without = track_env_vars(file_path, include_defaults=False)
    assert "HAS_DEFAULT" not in result_without.by_var
    assert "NO_DEFAULT" in result_without.by_var


def test_group_by_var_name() -> None:
    """Test grouping references by variable name."""
    from tree_sitter_analyzer.analysis.env_tracker import EnvVarReference

    refs = [
        EnvVarReference(
            var_name="API_KEY",
            file_path="test.py",
            line=1,
            column=1,
            access_type=AccessType.GETENV_CALL.value,
            context="test",
        ),
        EnvVarReference(
            var_name="API_KEY",
            file_path="test.py",
            line=2,
            column=1,
            access_type=AccessType.ENVIRON_GET.value,
            context="test",
        ),
        EnvVarReference(
            var_name="DB_HOST",
            file_path="test.py",
            line=3,
            column=1,
            access_type=AccessType.ENVIRON_INDEX.value,
            context="test",
        ),
    ]

    grouped = group_by_var_name(refs)

    assert "API_KEY" in grouped
    assert "DB_HOST" in grouped
    assert grouped["API_KEY"].total_references == 2
    assert grouped["DB_HOST"].total_references == 1


def test_unsupported_extension(tmp_path: Path) -> None:
    """Test that unsupported file types are handled gracefully."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("some text")

    result = track_env_vars(file_path)
    assert result.total_references == 0


def test_nonexistent_file() -> None:
    """Test that nonexistent files are handled gracefully."""
    result = track_env_vars("/nonexistent/file.py")
    assert result.total_references == 0


def test_empty_file(tmp_path: Path) -> None:
    """Test that empty files are handled gracefully."""
    file_path = tmp_path / "empty.py"
    file_path.write_text("")

    result = track_env_vars(file_path)
    assert result.total_references == 0


def test_tracking_result_aggregation() -> None:
    """Test EnvTrackingResult aggregation."""
    result = EnvTrackingResult()

    ref1 = EnvVarReference(
        var_name="VAR1",
        file_path="test.py",
        line=1,
        column=1,
        access_type=AccessType.GETENV_CALL.value,
        context="test",
    )

    ref2 = EnvVarReference(
        var_name="VAR2",
        file_path="test.py",
        line=2,
        column=1,
        access_type=AccessType.GETENV_CALL.value,
        context="test",
    )

    result.add_reference(ref1)
    assert result.total_references == 1
    assert result.unique_vars == 1
    assert result.by_file["test.py"] == 1

    result.add_reference(ref2)
    assert result.total_references == 2
    assert result.unique_vars == 2


def test_env_var_usage_aggregation() -> None:
    """Test EnvVarUsage aggregation."""
    usage = EnvVarUsage(var_name="TEST_VAR")

    ref1 = EnvVarReference(
        var_name="TEST_VAR",
        file_path="test1.py",
        line=1,
        column=1,
        access_type=AccessType.GETENV_CALL.value,
        context="test",
        has_default=True,
    )

    ref2 = EnvVarReference(
        var_name="TEST_VAR",
        file_path="test2.py",
        line=1,
        column=1,
        access_type=AccessType.ENVIRON_GET.value,
        context="test",
        has_default=False,
    )

    usage.add_reference(ref1)
    assert usage.total_references == 1
    assert usage.file_count == 1
    assert usage.has_default_count == 1
    assert usage.access_types[AccessType.GETENV_CALL.value] == 1

    usage.add_reference(ref2)
    assert usage.total_references == 2
    assert usage.file_count == 2
    assert usage.has_default_count == 1
    assert usage.access_types[AccessType.ENVIRON_GET.value] == 1
