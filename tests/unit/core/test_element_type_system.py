#!/usr/bin/env python3
"""
Test Element Type System

Tests for the unified element type system to ensure consistency
between CLI commands and MCP tools.
"""

import contextlib
import sys
from io import StringIO
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli_main import main
from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
    is_element_of_type,
)


def _advanced_args(sample_java_file: str) -> list[str]:
    sample_dir = str(Path(sample_java_file).parent)
    return [
        "cli",
        sample_java_file,
        "--advanced",
        "--output-format",
        "text",
        "--project-root",
        sample_dir,
    ]


def _table_args(sample_java_file: str) -> list[str]:
    sample_dir = str(Path(sample_java_file).parent)
    return [
        "cli",
        sample_java_file,
        "--table",
        "full",
        "--project-root",
        sample_dir,
    ]


def _run_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> str:
    monkeypatch.setattr(sys, "argv", argv)
    mock_stdout = StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    with contextlib.suppress(SystemExit):
        main()

    return mock_stdout.getvalue()


def _parse_advanced_counts(output: str) -> dict[str, int]:
    labels = {
        "Classes: ": "classes",
        "Methods: ": "methods",
        "Fields: ": "fields",
        "Imports: ": "imports",
    }
    element_counts = {}

    for line in output.splitlines():
        stripped = line.strip()
        for prefix, key in labels.items():
            if not stripped.startswith(prefix):
                continue
            with contextlib.suppress(ValueError, IndexError):
                element_counts[key] = int(stripped.split(": ")[1])
            break

    return element_counts


def _parse_table_class_info_counts(output: str) -> dict[str, int]:
    table_counts = {}
    in_class_info = False

    for line in output.splitlines():
        stripped = line.strip()
        if "## Class Info" in stripped:
            in_class_info = True
            continue
        if stripped.startswith("## ") and in_class_info:
            in_class_info = False
            continue
        if not in_class_info:
            continue

        _capture_table_count(table_counts, stripped, "Total Methods", "methods")
        _capture_table_count(table_counts, stripped, "Total Fields", "fields")

    return table_counts


def _capture_table_count(
    table_counts: dict[str, int],
    line: str,
    label: str,
    key: str,
) -> None:
    if label not in line:
        return
    parts = line.split("|")
    if len(parts) < 3:
        return
    with contextlib.suppress(ValueError):
        table_counts[key] = int(parts[2].strip())


class TestElementTypeSystem:
    """Test the unified element type system"""

    def test_element_type_constants(self):
        """Test that element type constants are correctly defined"""
        assert ELEMENT_TYPE_CLASS == "class"
        assert ELEMENT_TYPE_FUNCTION == "function"
        assert ELEMENT_TYPE_VARIABLE == "variable"
        assert ELEMENT_TYPE_IMPORT == "import"
        assert ELEMENT_TYPE_PACKAGE == "package"

    def test_get_element_type_with_element_type_attribute(self):
        """Test get_element_type with element_type attribute"""

        class MockElement:
            def __init__(self, element_type):
                self.element_type = element_type

        element = MockElement(ELEMENT_TYPE_CLASS)
        assert get_element_type(element) == ELEMENT_TYPE_CLASS

        element = MockElement(ELEMENT_TYPE_FUNCTION)
        assert get_element_type(element) == ELEMENT_TYPE_FUNCTION

    def test_get_element_type_with_class_name(self):
        """Test get_element_type with __class__.__name__ fallback"""

        class Class:
            pass

        class Function:
            pass

        class Variable:
            pass

        assert get_element_type(Class()) == ELEMENT_TYPE_CLASS
        assert get_element_type(Function()) == ELEMENT_TYPE_FUNCTION
        assert get_element_type(Variable()) == ELEMENT_TYPE_VARIABLE

    def test_is_element_of_type(self):
        """Test is_element_of_type function"""

        class MockElement:
            def __init__(self, element_type):
                self.element_type = element_type

        element = MockElement(ELEMENT_TYPE_CLASS)
        assert is_element_of_type(element, ELEMENT_TYPE_CLASS) is True
        assert is_element_of_type(element, ELEMENT_TYPE_FUNCTION) is False


class TestCLIElementTypeConsistency:
    """Test CLI commands use correct element type system"""

    @pytest.fixture
    def sample_java_file(self, tmp_path):
        """Create a sample Java file for testing"""
        java_content = """
package com.example;

import java.util.List;

public class SampleClass {
    private String field1;
    private int field2;

    public void method1() {
        // method body
    }

    private void method2() {
        // method body
    }

    public static void method3() {
        // method body
    }
}
"""
        file_path = tmp_path / "SampleClass.java"
        file_path.write_text(java_content, encoding="utf-8")
        return str(file_path)

    def test_advanced_command_element_counts(self, monkeypatch, sample_java_file):
        """Test that advanced command shows correct element counts"""
        output = _run_cli(monkeypatch, _advanced_args(sample_java_file))
        element_counts = _parse_advanced_counts(output)

        # Verify expected counts for the sample file
        assert element_counts.get("classes", 0) == 1, (
            f"Expected 1 class, got {element_counts.get('classes', 0)}"
        )
        assert element_counts.get("methods", 0) == 3, (
            f"Expected 3 methods, got {element_counts.get('methods', 0)}"
        )
        assert element_counts.get("fields", 0) == 2, (
            f"Expected 2 fields, got {element_counts.get('fields', 0)}"
        )
        assert element_counts.get("imports", 0) == 1, (
            f"Expected 1 import, got {element_counts.get('imports', 0)}"
        )

    def test_table_command_element_counts(self, monkeypatch, sample_java_file):
        """Test that table command shows correct element counts"""
        output = _run_cli(monkeypatch, _table_args(sample_java_file))
        table_counts = _parse_table_class_info_counts(output)

        # Verify expected counts
        assert table_counts["methods"] == 3, (
            f"Expected 3 methods in table, got {table_counts['methods']}"
        )
        assert table_counts["fields"] == 2, (
            f"Expected 2 fields in table, got {table_counts['fields']}"
        )

    def test_consistency_between_advanced_and_table(
        self, monkeypatch, sample_java_file
    ):
        """Test that advanced and table commands show consistent results"""
        advanced_counts = _parse_advanced_counts(
            _run_cli(monkeypatch, _advanced_args(sample_java_file))
        )
        table_counts = _parse_table_class_info_counts(
            _run_cli(monkeypatch, _table_args(sample_java_file))
        )

        # Verify consistency
        assert advanced_counts["methods"] == table_counts["methods"], (
            f"Method count mismatch: advanced={advanced_counts['methods']}, table={table_counts['methods']}"
        )
        assert advanced_counts["fields"] == table_counts["fields"], (
            f"Field count mismatch: advanced={advanced_counts['fields']}, table={table_counts['fields']}"
        )


class TestElementTypeRegression:
    """Test to prevent regression in element type system"""

    def test_zero_element_counts_detection(self, monkeypatch, tmp_path):
        """Test that zero element counts are detected and flagged"""
        # Create a minimal Java file
        java_content = """
public class EmptyClass {
}
"""
        file_path = tmp_path / "EmptyClass.java"
        file_path.write_text(java_content, encoding="utf-8")
        sample_java_file = str(file_path)
        output = _run_cli(monkeypatch, _advanced_args(sample_java_file))
        element_counts = _parse_advanced_counts(output)

        # For an empty class, we should have 1 class, 0 methods, 0 fields, 0 imports
        assert element_counts.get("classes", 0) == 1, "Empty class should have 1 class"
        assert element_counts.get("methods", 0) == 0, (
            "Empty class should have 0 methods"
        )
        assert element_counts.get("fields", 0) == 0, "Empty class should have 0 fields"
        assert element_counts.get("imports", 0) == 0, (
            "Empty class should have 0 imports"
        )
