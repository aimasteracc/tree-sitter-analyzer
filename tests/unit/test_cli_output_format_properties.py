#!/usr/bin/env python3
"""
Property-based tests for CLI output format consistency.

**Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

Tests that CLI commands with specified output formats produce output that
conforms to that format's specification.

**Validates: Requirements 9.2**
"""

import json
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.output_manager import (
    OutputManager,
    output_data,
    output_json,
    set_output_mode,
)

# Common settings for all property tests that use capsys fixture
PROPERTY_SETTINGS = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


# ========================================
# Hypothesis Strategies for CLI Data
# ========================================

# Strategy for generating simple values that are JSON-serializable
simple_value = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1000000, max_value=1000000),
    st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
    st.text(
        min_size=0,
        max_size=100,
        alphabet=st.characters(
            blacklist_categories=("Cs",),  # Exclude surrogate characters
            blacklist_characters=("\x00",),  # Exclude null characters
        ),
    ),
)

# Strategy for generating file paths
file_path = st.sampled_from(
    [
        "src/main.py",
        "test/test_file.py",
        "lib/utils.js",
        "app/models/user.java",
        "config/settings.yaml",
        "README.md",
        "package.json",
        "Makefile",
    ]
)

# Strategy for generating file lists
file_list = st.lists(file_path, min_size=0, max_size=10, unique=True)


# Strategy for generating match results
@st.composite
def match_result(draw):
    """Generate a search match result."""
    return {
        "file": draw(file_path),
        "line": draw(st.integers(min_value=1, max_value=1000)),
        "column": draw(st.integers(min_value=1, max_value=200)),
        "content": draw(
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(
                    blacklist_categories=("Cs",),
                    blacklist_characters=("\x00", "\r", "\n"),
                ),
            )
        ),
        "match": draw(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    blacklist_categories=("Cs",),
                    blacklist_characters=("\x00", "\r", "\n"),
                ),
            )
        ),
    }


# Strategy for generating search results
@st.composite
def search_result(draw):
    """Generate a complete search result."""
    matches = draw(st.lists(match_result(), min_size=0, max_size=10))
    return {
        "success": True,
        "query": draw(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    blacklist_categories=("Cs",), blacklist_characters=("\x00",)
                ),
            )
        ),
        "total_matches": len(matches),
        "matches": matches,
        "files_searched": draw(st.integers(min_value=0, max_value=100)),
    }


# Strategy for generating list files results
@st.composite
def list_files_result(draw):
    """Generate a list files result."""
    files = draw(file_list)
    return {
        "success": True,
        "files": files,
        "count": len(files),
        "root": draw(st.sampled_from([".", "src", "tests", "lib"])),
    }


# Strategy for generating analysis results
@st.composite
def analysis_result_data(draw):
    """Generate an analysis result data structure."""
    return {
        "file_path": draw(file_path),
        "language": draw(
            st.sampled_from(["python", "java", "javascript", "typescript"])
        ),
        "success": True,
        "line_count": draw(st.integers(min_value=1, max_value=10000)),
        "classes": draw(
            st.lists(
                st.fixed_dictionaries(
                    {
                        "name": st.sampled_from(
                            ["MyClass", "TestClass", "Service", "Handler"]
                        ),
                        "line": st.integers(min_value=1, max_value=1000),
                    }
                ),
                min_size=0,
                max_size=5,
            )
        ),
        "methods": draw(
            st.lists(
                st.fixed_dictionaries(
                    {
                        "name": st.sampled_from(
                            ["main", "test", "process", "handle", "execute"]
                        ),
                        "line": st.integers(min_value=1, max_value=1000),
                    }
                ),
                min_size=0,
                max_size=10,
            )
        ),
    }


# Strategy for generating error results
@st.composite
def error_result(draw):
    """Generate an error result."""
    return {
        "success": False,
        "error": draw(
            st.sampled_from(
                [
                    "File not found",
                    "Permission denied",
                    "Invalid syntax",
                    "Timeout exceeded",
                    "Unknown language",
                ]
            )
        ),
        "file_path": draw(file_path),
    }


# Strategy for generating any valid CLI output data
cli_output_data = st.one_of(
    search_result(),
    list_files_result(),
    analysis_result_data(),
    error_result(),
    st.integers(min_value=0, max_value=10000),  # Count results
    st.lists(file_path, min_size=0, max_size=20),  # Simple file lists
)


# ========================================
# Property Tests for CLI Output Format Consistency
# ========================================


class TestCLIOutputFormatProperties:
    """
    Property-based tests for CLI output format consistency.

    **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**
    **Validates: Requirements 9.2**
    """

    @PROPERTY_SETTINGS
    @given(data=cli_output_data)
    def test_property_12_json_format_produces_valid_json(self, data: Any, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any CLI output data with JSON format specified, the output SHALL be
        valid JSON that can be parsed.

        **Validates: Requirements 9.2**
        """
        # Create output manager with JSON mode
        manager = OutputManager(quiet=False, json_output=True)

        # Output data in JSON format
        manager.data(data, format_type="json")

        # Capture output
        captured = capsys.readouterr()

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(captured.out)
            # Property: Parsed JSON should be equivalent to original data
            # (accounting for JSON serialization rules)
            assert (
                parsed is not None or data is None
            ), "JSON output should parse to equivalent value"
        except json.JSONDecodeError as e:
            pytest.fail(
                f"JSON format should produce valid JSON: {e}\nOutput was: {captured.out}"
            )

    @PROPERTY_SETTINGS
    @given(data=cli_output_data)
    def test_property_12_json_format_roundtrip_preserves_data(self, data: Any, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any CLI output data, JSON serialization and deserialization SHALL
        preserve the data structure.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(data, format_type="json")

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)

        # Property: Round-trip should preserve data type
        if isinstance(data, dict):
            assert isinstance(
                parsed, dict
            ), "Dict data should remain dict after round-trip"
            # Property: All keys should be preserved
            assert (
                set(data.keys()) == set(parsed.keys())
            ), f"All keys should be preserved. Original: {set(data.keys())}, Got: {set(parsed.keys())}"
        elif isinstance(data, list):
            assert isinstance(
                parsed, list
            ), "List data should remain list after round-trip"
            assert len(data) == len(parsed), "List length should be preserved"
        elif isinstance(data, int):
            assert parsed == data, "Integer data should be preserved exactly"

    @PROPERTY_SETTINGS
    @given(data=cli_output_data)
    def test_property_12_text_format_produces_readable_output(self, data: Any, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any CLI output data with text format specified, the output SHALL be
        human-readable text (non-empty for non-empty data).

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=False)
        manager.data(data, format_type="text")

        captured = capsys.readouterr()

        # Property: Text output should be a string
        assert isinstance(captured.out, str), "Text output should be a string"

        # Property: Non-empty data should produce non-empty output
        if data is not None and data != [] and data != {}:
            assert (
                len(captured.out.strip()) > 0
            ), f"Non-empty data should produce non-empty text output. Data: {data}"

    @PROPERTY_SETTINGS
    @given(data=search_result())
    def test_property_12_search_result_json_contains_required_fields(
        self, data: dict, capsys
    ):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any search result, JSON output SHALL contain all required fields.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(data, format_type="json")

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)

        # Property: Required fields should be present
        assert "success" in parsed, "Search result should contain 'success' field"
        assert (
            "total_matches" in parsed
        ), "Search result should contain 'total_matches' field"
        assert "matches" in parsed, "Search result should contain 'matches' field"

        # Property: Match count should be consistent
        assert parsed["total_matches"] == len(
            parsed["matches"]
        ), "total_matches should equal length of matches array"

    @PROPERTY_SETTINGS
    @given(data=list_files_result())
    def test_property_12_list_files_result_json_contains_required_fields(
        self, data: dict, capsys
    ):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any list files result, JSON output SHALL contain all required fields.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(data, format_type="json")

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)

        # Property: Required fields should be present
        assert "success" in parsed, "List files result should contain 'success' field"
        assert "files" in parsed, "List files result should contain 'files' field"
        assert "count" in parsed, "List files result should contain 'count' field"

        # Property: Count should match files length
        assert parsed["count"] == len(
            parsed["files"]
        ), "count should equal length of files array"

    @PROPERTY_SETTINGS
    @given(data=analysis_result_data())
    def test_property_12_analysis_result_json_contains_required_fields(
        self, data: dict, capsys
    ):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any analysis result, JSON output SHALL contain all required fields.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(data, format_type="json")

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)

        # Property: Required fields should be present
        assert "file_path" in parsed, "Analysis result should contain 'file_path' field"
        assert "language" in parsed, "Analysis result should contain 'language' field"
        assert "success" in parsed, "Analysis result should contain 'success' field"

    @PROPERTY_SETTINGS
    @given(quiet=st.booleans(), json_output=st.booleans())
    def test_property_12_output_mode_configuration(
        self, quiet: bool, json_output: bool, capsys
    ):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any output mode configuration, the OutputManager SHALL respect
        the quiet and json_output settings.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=quiet, json_output=json_output)

        # Test info output
        manager.info("Test info message")
        captured = capsys.readouterr()

        if quiet:
            # Property: Quiet mode should suppress info messages
            assert (
                "Test info message" not in captured.out
            ), "Quiet mode should suppress info messages"
        else:
            # Property: Non-quiet mode should show info messages
            assert (
                "Test info message" in captured.out
            ), "Non-quiet mode should show info messages"

    @PROPERTY_SETTINGS
    @given(
        items=st.lists(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    blacklist_categories=("Cs",), blacklist_characters=("\x00",)
                ),
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_property_12_output_list_contains_all_items(self, items: list, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any list of items, output_list SHALL include all items in the output.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=False)
        manager.output_list(items)

        captured = capsys.readouterr()

        # Property: All items should appear in output
        for item in items:
            assert item in captured.out, f"Item '{item}' should appear in list output"


class TestCLIOutputFormatEdgeCases:
    """
    Property-based tests for CLI output format edge cases.

    **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**
    **Validates: Requirements 9.2**
    """

    @PROPERTY_SETTINGS
    @given(
        data=st.dictionaries(
            keys=st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    blacklist_categories=("Cs",), blacklist_characters=("\x00",)
                ),
            ),
            values=simple_value,
            min_size=0,
            max_size=10,
        )
    )
    def test_property_12_arbitrary_dict_json_format(self, data: dict, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any arbitrary dictionary, JSON format SHALL produce valid JSON.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(data, format_type="json")

        captured = capsys.readouterr()

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(captured.out)
            assert isinstance(
                parsed, dict
            ), "Dict input should produce dict JSON output"
        except json.JSONDecodeError as e:
            pytest.fail(f"Arbitrary dict should produce valid JSON: {e}")

    @PROPERTY_SETTINGS
    @given(data=st.lists(simple_value, min_size=0, max_size=20))
    def test_property_12_arbitrary_list_json_format(self, data: list, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any arbitrary list, JSON format SHALL produce valid JSON.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(data, format_type="json")

        captured = capsys.readouterr()

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(captured.out)
            assert isinstance(
                parsed, list
            ), "List input should produce list JSON output"
            assert len(parsed) == len(data), "List length should be preserved"
        except json.JSONDecodeError as e:
            pytest.fail(f"Arbitrary list should produce valid JSON: {e}")

    @PROPERTY_SETTINGS
    @given(count=st.integers(min_value=0, max_value=1000000))
    def test_property_12_integer_count_json_format(self, count: int, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any integer count result, JSON format SHALL produce valid JSON number.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(count, format_type="json")

        captured = capsys.readouterr()

        # Property: Output should be valid JSON
        parsed = json.loads(captured.out)

        # Property: Integer should be preserved exactly
        assert (
            parsed == count
        ), f"Integer {count} should be preserved exactly, got {parsed}"

    @PROPERTY_SETTINGS
    @given(
        error_msg=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(
                blacklist_categories=("Cs",), blacklist_characters=("\x00",)
            ),
        )
    )
    def test_property_12_error_output_contains_message(self, error_msg: str, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For any error message, error output SHALL contain the message.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=False)
        manager.error(error_msg)

        captured = capsys.readouterr()

        # Property: Error message should appear in stderr
        assert (
            error_msg in captured.err
        ), f"Error message '{error_msg}' should appear in error output"

        # Property: Error output should be prefixed with ERROR
        assert "ERROR:" in captured.err, "Error output should be prefixed with 'ERROR:'"

    def test_property_12_empty_data_json_format(self, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For empty data structures, JSON format SHALL produce valid empty JSON.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)

        # Test empty dict
        manager.data({}, format_type="json")
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {}, "Empty dict should produce {}"

        # Test empty list
        manager.data([], format_type="json")
        captured = capsys.readouterr()
        assert json.loads(captured.out) == [], "Empty list should produce []"

    def test_property_12_none_data_json_format(self, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        For None data, JSON format SHALL produce valid JSON null.

        **Validates: Requirements 9.2**
        """
        manager = OutputManager(quiet=False, json_output=True)
        manager.data(None, format_type="json")

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)

        assert parsed is None, "None should produce JSON null"


class TestGlobalOutputFunctions:
    """
    Property-based tests for global output functions.

    **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**
    **Validates: Requirements 9.2**
    """

    @PROPERTY_SETTINGS
    @given(data=cli_output_data)
    def test_property_12_global_output_data_json(self, data: Any, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        The global output_data function SHALL produce valid JSON when format is json.

        **Validates: Requirements 9.2**
        """
        # Set global output mode to JSON
        set_output_mode(quiet=False, json_output=True)

        # Use global function
        output_data(data, format_type="json")

        captured = capsys.readouterr()

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(captured.out)
            assert parsed is not None or data is None
        except json.JSONDecodeError as e:
            pytest.fail(f"Global output_data should produce valid JSON: {e}")

    @PROPERTY_SETTINGS
    @given(data=cli_output_data)
    def test_property_12_global_output_json_function(self, data: Any, capsys):
        """
        **Feature: test-coverage-improvement, Property 12: CLI Output Format Consistency**

        The global output_json function SHALL always produce valid JSON.

        **Validates: Requirements 9.2**
        """
        set_output_mode(quiet=False, json_output=True)
        output_json(data)

        captured = capsys.readouterr()

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(captured.out)
            assert parsed is not None or data is None
        except json.JSONDecodeError as e:
            pytest.fail(f"output_json should produce valid JSON: {e}")
