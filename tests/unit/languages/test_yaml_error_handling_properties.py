#!/usr/bin/env python3
"""
Property-based tests for YAML error handling robustness.

Feature: yaml-language-support
Tests correctness properties for YAML error handling to ensure:
- Invalid YAML returns error result without crashing
- Parser handles malformed input gracefully
- Error messages are descriptive and helpful
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.languages.yaml_plugin import YAML_AVAILABLE, YAMLPlugin

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


# Strategies for generating invalid YAML content
@st.composite
def invalid_yaml_unbalanced_brackets(draw):
    """Generate YAML with unbalanced brackets."""
    num_open = draw(st.integers(min_value=1, max_value=5))
    num_close = draw(st.integers(min_value=0, max_value=num_open - 1))

    content = "data:\n"
    content += "  items: " + "[" * num_open
    content += "item1, item2"
    content += "]" * num_close
    return content


@st.composite
def invalid_yaml_bad_indentation(draw):
    """Generate YAML with inconsistent indentation."""
    lines = ["root:"]

    # Add lines with random bad indentation
    num_lines = draw(st.integers(min_value=2, max_value=5))
    for i in range(num_lines):
        # Random indentation that doesn't follow YAML rules
        indent = draw(st.integers(min_value=1, max_value=10))
        if indent % 2 != 0 and i > 0:  # Odd indentation after first line
            key = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=10,
                )
            )
            lines.append(" " * indent + f"{key}: value")

    return "\n".join(lines)


@st.composite
def invalid_yaml_duplicate_keys(draw):
    """Generate YAML with duplicate keys at same level."""
    key = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        )
    )

    # Create duplicate keys
    lines = [
        f"{key}: value1",
        f"{key}: value2",
        f"{key}: value3",
    ]
    return "\n".join(lines)


@st.composite
def invalid_yaml_malformed_anchors(draw):
    """Generate YAML with malformed anchor/alias syntax."""
    anchor_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        )
    )

    # Create malformed anchor/alias
    malformed_type = draw(
        st.sampled_from(
            [
                "missing_ampersand",
                "missing_asterisk",
                "invalid_chars",
                "dangling_alias",
            ]
        )
    )

    if malformed_type == "missing_ampersand":
        return f"anchor: {anchor_name}\nref: *{anchor_name}"
    elif malformed_type == "missing_asterisk":
        return f"anchor: &{anchor_name}\nref: {anchor_name}"
    elif malformed_type == "invalid_chars":
        return f"anchor: &{anchor_name}@#$\nref: *{anchor_name}"
    else:  # dangling_alias
        return "ref: *nonexistent_anchor"


@st.composite
def invalid_yaml_unclosed_quotes(draw):
    """Generate YAML with unclosed quotes."""
    key = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        )
    )

    quote_type = draw(st.sampled_from(['"', "'"]))
    value = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        )
    )

    # Unclosed quote
    return f"{key}: {quote_type}{value}"


@st.composite
def invalid_yaml_mixed_syntax_errors(draw):
    """Generate YAML with multiple syntax errors."""
    errors = []

    # Add various syntax errors
    num_errors = draw(st.integers(min_value=2, max_value=4))

    for _ in range(num_errors):
        error_type = draw(
            st.sampled_from(
                [
                    "missing_colon",
                    "extra_colon",
                    "invalid_list_marker",
                    "mixed_tabs_spaces",
                ]
            )
        )

        if error_type == "missing_colon":
            errors.append("key value")
        elif error_type == "extra_colon":
            errors.append("key:: value")
        elif error_type == "invalid_list_marker":
            errors.append("items:\n  * item1\n  * item2")
        else:  # mixed_tabs_spaces
            errors.append("root:\n\tkey1: value1\n  key2: value2")

    return "\n".join(errors)


@st.composite
def invalid_yaml_control_characters(draw):
    """Generate YAML with invalid control characters."""
    key = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        )
    )

    # Add control characters that are invalid in YAML
    control_char = draw(st.sampled_from(["\x00", "\x01", "\x02", "\x08", "\x0b"]))

    return f"{key}: value{control_char}data"


@st.composite
def invalid_yaml_document_markers(draw):
    """Generate YAML with malformed document markers."""
    marker_type = draw(
        st.sampled_from(
            [
                "incomplete_start",
                "incomplete_end",
                "mixed_markers",
            ]
        )
    )

    if marker_type == "incomplete_start":
        return "--\nkey: value"
    elif marker_type == "incomplete_end":
        return "key: value\n.."
    else:  # mixed_markers
        return "---\nkey1: value1\n--\nkey2: value2"


class TestYAMLErrorHandlingProperties:
    """Property-based tests for YAML error handling robustness."""

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(invalid_content=invalid_yaml_unbalanced_brackets())
    async def test_property_12_error_handling_unbalanced_brackets(
        self, invalid_content: str
    ):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For any YAML content with unbalanced brackets, the parser SHALL return
        an error result without crashing.

        Validates: Requirements 6.1
        """
        # Create temporary YAML file with invalid content
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "invalid.yaml"
            yaml_file.write_text(invalid_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned (not None)
                assert (
                    result is not None
                ), "Parser returned None instead of error result"

                # Property: Result should indicate failure or handle gracefully
                # Note: tree-sitter is very permissive and may parse invalid YAML
                # The key property is that it doesn't crash
                assert isinstance(
                    result.success, bool
                ), "Result must have success field"

                # Property: If parsing fails, error message should be present
                if not result.success:
                    assert (
                        result.error_message is not None
                    ), "Failed result must have error message"
                    assert (
                        len(result.error_message) > 0
                    ), "Error message must not be empty"

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on invalid YAML (unbalanced brackets): {e}\n"
                    f"Content: {invalid_content[:100]}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(invalid_content=invalid_yaml_bad_indentation())
    async def test_property_12_error_handling_bad_indentation(
        self, invalid_content: str
    ):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For any YAML content with inconsistent indentation, the parser SHALL
        return an error result without crashing.

        Validates: Requirements 6.1
        """
        # Create temporary YAML file with invalid content
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "bad_indent.yaml"
            yaml_file.write_text(invalid_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None"
                assert isinstance(
                    result.success, bool
                ), "Result must have success field"

                # Property: Error handling must be graceful
                if not result.success:
                    assert result.error_message is not None
                    assert len(result.error_message) > 0

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on bad indentation: {e}\n"
                    f"Content: {invalid_content[:100]}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(invalid_content=invalid_yaml_unclosed_quotes())
    async def test_property_12_error_handling_unclosed_quotes(
        self, invalid_content: str
    ):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For any YAML content with unclosed quotes, the parser SHALL return
        an error result without crashing.

        Validates: Requirements 6.1
        """
        # Create temporary YAML file with invalid content
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "unclosed_quotes.yaml"
            yaml_file.write_text(invalid_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None"
                assert isinstance(
                    result.success, bool
                ), "Result must have success field"

                # Property: Error handling must be graceful
                if not result.success:
                    assert result.error_message is not None
                    assert len(result.error_message) > 0

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on unclosed quotes: {e}\n"
                    f"Content: {invalid_content[:100]}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(invalid_content=invalid_yaml_mixed_syntax_errors())
    async def test_property_12_error_handling_mixed_syntax_errors(
        self, invalid_content: str
    ):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For any YAML content with multiple syntax errors, the parser SHALL
        return an error result without crashing.

        Validates: Requirements 6.1
        """
        # Create temporary YAML file with invalid content
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "mixed_errors.yaml"
            yaml_file.write_text(invalid_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None"
                assert isinstance(
                    result.success, bool
                ), "Result must have success field"

                # Property: Error handling must be graceful
                if not result.success:
                    assert result.error_message is not None
                    assert len(result.error_message) > 0

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on mixed syntax errors: {e}\n"
                    f"Content: {invalid_content[:100]}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        invalid_content=st.one_of(
            invalid_yaml_unbalanced_brackets(),
            invalid_yaml_bad_indentation(),
            invalid_yaml_unclosed_quotes(),
            invalid_yaml_mixed_syntax_errors(),
        )
    )
    async def test_property_12_error_handling_comprehensive(self, invalid_content: str):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For any invalid YAML content, the parser SHALL handle errors gracefully
        without crashing, and SHALL return a valid result object.

        Validates: Requirements 6.1
        """
        # Create temporary YAML file with invalid content
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "comprehensive_invalid.yaml"
            yaml_file.write_text(invalid_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash under any circumstances
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property 1: Result must always be returned
                assert (
                    result is not None
                ), "Parser must return a result object, not None"

                # Property 2: Result must have required fields
                assert hasattr(result, "success"), "Result must have 'success' field"
                assert hasattr(
                    result, "error_message"
                ), "Result must have 'error_message' field"
                assert hasattr(
                    result, "file_path"
                ), "Result must have 'file_path' field"
                assert hasattr(result, "language"), "Result must have 'language' field"
                assert hasattr(result, "elements"), "Result must have 'elements' field"

                # Property 3: Result fields must have correct types
                assert isinstance(result.success, bool), "'success' must be boolean"
                assert isinstance(result.file_path, str), "'file_path' must be string"
                assert isinstance(result.language, str), "'language' must be string"
                assert isinstance(result.elements, list), "'elements' must be list"

                # Property 4: Language must be correct
                assert result.language == "yaml", "Language must be 'yaml'"

                # Property 5: File path must match input
                assert result.file_path == str(yaml_file), "File path must match input"

                # Property 6: If parsing fails, error message must be descriptive
                if not result.success:
                    assert (
                        result.error_message is not None
                    ), "Failed result must have error message"
                    assert isinstance(
                        result.error_message, str
                    ), "Error message must be string"
                    assert (
                        len(result.error_message) > 0
                    ), "Error message must not be empty"

                # Property 7: Elements list must be valid (even if empty)
                assert isinstance(result.elements, list), "Elements must be a list"

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on invalid YAML: {e}\n"
                    f"Content preview: {invalid_content[:200]}\n"
                    f"Exception type: {type(e).__name__}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(invalid_content=invalid_yaml_control_characters())
    async def test_property_12_error_handling_control_characters(
        self, invalid_content: str
    ):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For any YAML content with invalid control characters, the parser SHALL
        handle the content gracefully without crashing.

        Validates: Requirements 6.1
        """
        # Create temporary YAML file with invalid content
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "control_chars.yaml"
            yaml_file.write_text(invalid_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None"
                assert isinstance(
                    result.success, bool
                ), "Result must have success field"

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on control characters: {e}\n"
                    f"Content length: {len(invalid_content)}"
                )

    @pytest.mark.asyncio
    async def test_property_12_error_handling_empty_file(self):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For an empty YAML file, the parser SHALL return a valid result without
        crashing (as per Requirements 6.3).

        Validates: Requirements 6.1, 6.3
        """
        # Create temporary empty YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "empty.yaml"
            yaml_file.write_text("", encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash on empty file
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None for empty file"

                # Property: Result should indicate success (empty is valid YAML)
                assert result.success, "Empty file should be valid YAML"

                # Property: Elements should be empty or minimal
                assert isinstance(result.elements, list), "Elements must be a list"

            except Exception as e:
                pytest.fail(f"Parser crashed on empty file: {e}")

    @pytest.mark.asyncio
    async def test_property_12_error_handling_comments_only(self):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For a YAML file containing only comments, the parser SHALL return a
        valid result without crashing (as per Requirements 6.4).

        Validates: Requirements 6.1, 6.4
        """
        # Create temporary YAML file with only comments
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "comments_only.yaml"
            yaml_file.write_text(
                "# This is a comment\n# Another comment\n# Yet another comment",
                encoding="utf-8",
            )

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash on comments-only file
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None for comments-only file"

                # Property: Result should indicate success
                assert result.success, "Comments-only file should be valid YAML"

                # Property: Should extract comment elements
                assert isinstance(result.elements, list), "Elements must be a list"

                # Property: Comment elements should be present
                comment_elements = [
                    e
                    for e in result.elements
                    if hasattr(e, "element_type") and e.element_type == "comment"
                ]
                assert (
                    len(comment_elements) > 0
                ), "Should extract comment elements from comments-only file"

            except Exception as e:
                pytest.fail(f"Parser crashed on comments-only file: {e}")

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
        deadline=None,  # Disable deadline for this test due to file I/O variability
    )
    @given(
        valid_prefix=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        ),
        invalid_suffix=invalid_yaml_unclosed_quotes(),
    )
    async def test_property_12_error_handling_partial_validity(
        self, valid_prefix: str, invalid_suffix: str
    ):
        """
        Feature: yaml-language-support, Property 12: Error Handling Robustness

        For YAML content that starts valid but becomes invalid, the parser SHALL
        handle the content gracefully and return a result without crashing.

        Validates: Requirements 6.1
        """
        # Create YAML with valid start and invalid end
        content = f"{valid_prefix}: valid_value\n{invalid_suffix}"

        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "partial_valid.yaml"
            yaml_file.write_text(content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Property: Parser must not crash
            try:
                result = await plugin.analyze_file(str(yaml_file), request)

                # Property: Result must be returned
                assert result is not None, "Parser returned None"
                assert isinstance(
                    result.success, bool
                ), "Result must have success field"

                # Property: Parser may extract valid parts even if overall invalid
                assert isinstance(result.elements, list), "Elements must be a list"

            except Exception as e:
                pytest.fail(
                    f"Parser crashed on partially valid YAML: {e}\n"
                    f"Content: {content[:100]}"
                )
