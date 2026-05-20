#!/usr/bin/env python3
"""Property test: element type mapping invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.constants import ELEMENT_TYPE_MAPPING


class TestElementTypeMappingProperty:
    """Verify ELEMENT_TYPE_MAPPING invariants under random key access."""

    @given(key=st.sampled_from(list(ELEMENT_TYPE_MAPPING.keys())))
    @settings(max_examples=50)
    def test_mapping_values_are_strings(self, key):
        value = ELEMENT_TYPE_MAPPING[key]
        assert isinstance(value, str)
