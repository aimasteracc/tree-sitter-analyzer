#!/usr/bin/env python3
"""
Test Element Type System

Tests for the unified element type system to ensure consistency
between CLI commands and MCP tools.
"""

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
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--output-format",
                "text",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()

        # Parse element counts from output
        lines = output.split("\n")
        element_counts = {}

        for line in lines:
            line = line.strip()
            if line.startswith('"Classes: '):
                element_counts["classes"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Methods: '):
                element_counts["methods"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Fields: '):
                element_counts["fields"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Imports: '):
                element_counts["imports"] = int(line.split(": ")[1].rstrip('"'))

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
        sample_dir = str(Path(sample_java_file).parent)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--table",
                "full",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()

        # Parse method and field counts from table output - look for Total Methods and Total Fields in Class Info section
        lines = output.split("\n")
        method_count = 0
        field_count = 0
        in_class_info = False

        for line in lines:
            line = line.strip()

            # Check if we're in the Class Info section
            if "## Class Info" in line:
                in_class_info = True
                continue
            elif line.startswith("## ") and in_class_info:
                # We've moved to another section
                in_class_info = False
                continue

            if in_class_info and "Total Methods" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    try:
                        method_count = int(parts[2].strip())
                    except ValueError:
                        pass
            elif in_class_info and "Total Fields" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    try:
                        field_count = int(parts[2].strip())
                    except ValueError:
                        pass

        # Debug: Print the actual output to understand the format
        print("DEBUG: Table output lines:")
        for i, line in enumerate(output.split("\n")):
            if "Methods" in line or "Fields" in line or "Class Info" in line:
                print(f"  {i}: {repr(line)}")
        print(f"DEBUG: Parsed counts - methods: {method_count}, fields: {field_count}")

        # Verify expected counts
        assert method_count == 3, f"Expected 3 methods in table, got {method_count}"
        assert field_count == 2, f"Expected 2 fields in table, got {field_count}"

    def test_consistency_between_advanced_and_table(
        self, monkeypatch, sample_java_file
    ):
        """Test that advanced and table commands show consistent results"""
        sample_dir = str(Path(sample_java_file).parent)

        # Test advanced command
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--output-format",
                "text",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        advanced_output = mock_stdout.getvalue()

        # Parse advanced output
        advanced_counts = {}
        for line in advanced_output.split("\n"):
            line = line.strip()
            if line.startswith('"Classes: '):
                try:
                    advanced_counts["classes"] = int(line.split(": ")[1].rstrip('"'))
                except (ValueError, IndexError):
                    pass
            elif line.startswith('"Methods: '):
                try:
                    advanced_counts["methods"] = int(line.split(": ")[1].rstrip('"'))
                except (ValueError, IndexError):
                    pass
            elif line.startswith('"Fields: '):
                try:
                    advanced_counts["fields"] = int(line.split(": ")[1].rstrip('"'))
                except (ValueError, IndexError):
                    pass
            elif line.startswith('"Imports: '):
                try:
                    advanced_counts["imports"] = int(line.split(": ")[1].rstrip('"'))
                except (ValueError, IndexError):
                    pass

        # Test table command
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--table",
                "full",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        table_output = mock_stdout.getvalue()

        # Parse table output - look for Total Methods and Total Fields in Class Info section
        table_counts = {}
        in_class_info = False

        for line in table_output.split("\n"):
            line = line.strip()

            # Check if we're in the Class Info section
            if "## Class Info" in line:
                in_class_info = True
                continue
            elif line.startswith("## ") and in_class_info:
                # We've moved to another section
                in_class_info = False
                continue

            if in_class_info and "Total Methods" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    try:
                        table_counts["methods"] = int(parts[2].strip())
                    except ValueError:
                        pass
            elif in_class_info and "Total Fields" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    try:
                        table_counts["fields"] = int(parts[2].strip())
                    except ValueError:
                        pass

        # Debug: Print the actual output to understand the format
        print("DEBUG: Table output lines:")
        for i, line in enumerate(table_output.split("\n")):
            if "Methods" in line or "Fields" in line:
                print(f"  {i}: {repr(line)}")
        print(f"DEBUG: Parsed table counts: {table_counts}")

        # Verify consistency
        assert advanced_counts.get("methods", 0) == table_counts.get("methods", 0), (
            f"Method count mismatch: advanced={advanced_counts.get('methods', 0)}, table={table_counts.get('methods', 0)}"
        )
        assert advanced_counts.get("fields", 0) == table_counts.get("fields", 0), (
            f"Field count mismatch: advanced={advanced_counts.get('fields', 0)}, table={table_counts.get('fields', 0)}"
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
        sample_dir = str(Path(sample_java_file).parent)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli",
                sample_java_file,
                "--advanced",
                "--output-format",
                "text",
                "--project-root",
                sample_dir,
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)

        try:
            main()
        except SystemExit:
            pass

        output = mock_stdout.getvalue()

        # Parse element counts
        lines = output.split("\n")
        element_counts = {}

        for line in lines:
            line = line.strip()
            if line.startswith('"Classes: '):
                element_counts["classes"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Methods: '):
                element_counts["methods"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Fields: '):
                element_counts["fields"] = int(line.split(": ")[1].rstrip('"'))
            elif line.startswith('"Imports: '):
                element_counts["imports"] = int(line.split(": ")[1].rstrip('"'))

        # For an empty class, we should have 1 class, 0 methods, 0 fields, 0 imports
        assert element_counts.get("classes", 0) == 1, "Empty class should have 1 class"
        assert element_counts.get("methods", 0) == 0, (
            "Empty class should have 0 methods"
        )
        assert element_counts.get("fields", 0) == 0, "Empty class should have 0 fields"
        assert element_counts.get("imports", 0) == 0, (
            "Empty class should have 0 imports"
        )
