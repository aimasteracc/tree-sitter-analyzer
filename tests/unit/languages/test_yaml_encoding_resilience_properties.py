#!/usr/bin/env python3
"""
Property-based tests for YAML encoding resilience.

Feature: yaml-language-support
Tests correctness properties for YAML encoding handling to ensure:
- Non-UTF-8 files are handled with fallback encodings
- Various character encodings are supported
- Encoding detection works correctly
"""

import asyncio
import os
import tempfile

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLPlugin,
)

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


class MockRequest:
    """Mock request for testing."""

    def __init__(self):
        self.output_format = "json"
        self.detail_level = "full"


class TestYAMLEncodingResilienceProperties:
    """Property-based tests for YAML encoding resilience."""

    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
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
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=48,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=30,
        ),
    )
    def test_property_13_utf8_encoding_handling(self, key_name: str, value: str):
        """
        Feature: yaml-language-support, Property 13: Encoding Resilience

        For any YAML file with UTF-8 encoding, the plugin SHALL successfully
        parse and extract elements.

        Validates: Requirements 6.2
        """
        yaml_content = f"{key_name}: {value}"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            plugin = YAMLPlugin()
            result = asyncio.run(plugin.analyze_file(temp_path, MockRequest()))

            # Property: Analysis should succeed
            assert (
                result.success
            ), f"UTF-8 file analysis should succeed: {result.error_message}"

            # Property: Elements should be extracted
            assert len(result.elements) > 0, "Should extract at least one element"

        finally:
            os.unlink(temp_path)

    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    @given(
        key_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=15,
        ),
        value=st.integers(min_value=0, max_value=1000),
    )
    def test_property_13_latin1_encoding_handling(self, key_name: str, value: int):
        """
        Feature: yaml-language-support, Property 13: Encoding Resilience

        For any YAML file with Latin-1 encoding, the plugin SHALL attempt
        fallback encodings and handle the file gracefully.

        Validates: Requirements 6.2
        """
        yaml_content = f"{key_name}: {value}"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="latin-1"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            plugin = YAMLPlugin()
            result = asyncio.run(plugin.analyze_file(temp_path, MockRequest()))

            # Property: Analysis should succeed (fallback encoding)
            assert (
                result.success
            ), f"Latin-1 file analysis should succeed: {result.error_message}"

            # Property: Elements should be extracted
            assert len(result.elements) > 0, "Should extract at least one element"

        finally:
            os.unlink(temp_path)

    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    @given(
        num_keys=st.integers(min_value=1, max_value=10),
    )
    def test_property_13_encoding_consistency(self, num_keys: int):
        """
        Feature: yaml-language-support, Property 13: Encoding Resilience

        For any YAML content, parsing with different encodings that can
        represent the same content SHALL produce consistent results.

        Validates: Requirements 6.2
        """
        lines = [f"key{i}: value{i}" for i in range(num_keys)]
        yaml_content = "\n".join(lines)

        plugin = YAMLPlugin()
        results = []
        encodings = ["utf-8", "latin-1"]

        for encoding in encodings:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding=encoding
            ) as f:
                f.write(yaml_content)
                temp_path = f.name

            try:
                result = asyncio.run(plugin.analyze_file(temp_path, MockRequest()))
                results.append((encoding, result))
            finally:
                os.unlink(temp_path)

        # Property: All encodings should succeed
        for encoding, result in results:
            assert result.success, f"Analysis with {encoding} should succeed"

        # Property: All encodings should extract the same number of elements
        element_counts = [len(r.elements) for _, r in results]
        assert len(set(element_counts)) == 1, (
            f"All encodings should extract same number of elements. "
            f"Got: {dict(zip(encodings, element_counts, strict=False))}"
        )
