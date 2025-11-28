#!/usr/bin/env python3
"""
Property-based tests for YAML scalar type identification.

Feature: yaml-language-support
Tests correctness properties for YAML scalar type identification to ensure:
- String scalars are correctly identified
- Number scalars are correctly identified
- Boolean scalars are correctly identified
- Null scalars are correctly identified
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElementExtractor,
)

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


class TestYAMLScalarTypeProperties:
    """Property-based tests for YAML scalar type identification."""

    @settings(max_examples=100)
    @given(
        key_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        ),
        string_value=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=30,
        ).filter(
            lambda x: x.lower()
            not in ["true", "false", "yes", "no", "on", "off", "null"]
        ),
    )
    def test_property_5_string_scalar_identification(
        self, key_name: str, string_value: str
    ):
        """
        Feature: yaml-language-support, Property 5: Scalar Type Identification

        For any YAML string scalar value, the extractor SHALL correctly identify
        its type as "string".

        Validates: Requirements 2.1
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content = f"{key_name}: {string_value}"

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Find mapping elements with values
        mappings = [
            e for e in elements if e.element_type == "mapping" and e.value is not None
        ]

        # Property: At least one string scalar should be found
        assert (
            len(mappings) > 0
        ), "Should extract at least one mapping with string value"

        # Property: String scalars must be identified as "string"
        for mapping in mappings:
            assert mapping.value_type == "string", (
                f"String scalar should have value_type='string', "
                f"got '{mapping.value_type}' for value '{mapping.value}'"
            )

        # Property: String values should not be empty
        for mapping in mappings:
            assert mapping.value is not None, "String value should not be None"
            assert len(mapping.value.strip()) > 0, "String value should not be empty"

    @settings(max_examples=100)
    @given(
        key_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        ),
        number_value=st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.floats(
                min_value=-1000000.0,
                max_value=1000000.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
    )
    def test_property_5_number_scalar_identification(
        self, key_name: str, number_value: float | int
    ):
        """
        Feature: yaml-language-support, Property 5: Scalar Type Identification

        For any YAML number scalar value, the extractor SHALL correctly identify
        its type as "number".

        Validates: Requirements 2.1
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content = f"{key_name}: {number_value}"

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Find mapping elements with values
        mappings = [
            e for e in elements if e.element_type == "mapping" and e.value is not None
        ]

        # Property: At least one number scalar should be found
        assert (
            len(mappings) > 0
        ), "Should extract at least one mapping with number value"

        # Property: Number scalars must be identified as "number"
        for mapping in mappings:
            assert mapping.value_type == "number", (
                f"Number scalar should have value_type='number', "
                f"got '{mapping.value_type}' for value '{mapping.value}'"
            )

        # Property: Number values should be parseable as numbers
        for mapping in mappings:
            assert mapping.value is not None, "Number value should not be None"
            try:
                float(mapping.value)
            except ValueError:
                pytest.fail(
                    f"Number value '{mapping.value}' should be parseable as float"
                )

    @settings(max_examples=100)
    @given(
        key_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        ),
        bool_value=st.sampled_from(["true", "false", "yes", "no", "on", "off"]),
    )
    def test_property_5_boolean_scalar_identification(
        self, key_name: str, bool_value: str
    ):
        """
        Feature: yaml-language-support, Property 5: Scalar Type Identification

        For any YAML boolean scalar value, the extractor SHALL correctly identify
        its type as "boolean".

        Validates: Requirements 2.1
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content = f"{key_name}: {bool_value}"

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Find mapping elements with values
        mappings = [
            e for e in elements if e.element_type == "mapping" and e.value is not None
        ]

        # Property: At least one boolean scalar should be found
        assert (
            len(mappings) > 0
        ), "Should extract at least one mapping with boolean value"

        # Property: Boolean scalars must be identified as "boolean"
        for mapping in mappings:
            assert mapping.value_type == "boolean", (
                f"Boolean scalar should have value_type='boolean', "
                f"got '{mapping.value_type}' for value '{mapping.value}'"
            )

        # Property: Boolean values should be valid YAML boolean representations
        valid_booleans = ["true", "false", "yes", "no", "on", "off"]
        for mapping in mappings:
            assert mapping.value is not None, "Boolean value should not be None"
            assert (
                mapping.value in valid_booleans
            ), f"Boolean value '{mapping.value}' should be a valid YAML boolean"

    @settings(max_examples=100)
    @given(
        key_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        ),
        null_value=st.sampled_from(["null", "~"]),
    )
    def test_property_5_null_scalar_identification(
        self, key_name: str, null_value: str
    ):
        """
        Feature: yaml-language-support, Property 5: Scalar Type Identification

        For any YAML null scalar value, the extractor SHALL correctly identify
        its type as "null".

        Validates: Requirements 2.1
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content = f"{key_name}: {null_value}"

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Find mapping elements with null values
        mappings = [e for e in elements if e.element_type == "mapping"]

        # Property: At least one null scalar should be found
        assert len(mappings) > 0, "Should extract at least one mapping with null value"

        # Property: Null scalars must be identified as "null"
        for mapping in mappings:
            assert mapping.value_type == "null", (
                f"Null scalar should have value_type='null', "
                f"got '{mapping.value_type}' for value '{mapping.value}'"
            )

        # Property: Null values should be None or valid YAML null representations
        valid_nulls = ["null", "~", None]
        for mapping in mappings:
            assert (
                mapping.value in valid_nulls
            ), f"Null value '{mapping.value}' should be None or a valid YAML null representation"
