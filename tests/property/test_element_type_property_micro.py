#!/usr/bin/env python3
"""Micro property test — push hypothesis coverage past 10% gate."""

from hypothesis import given
from hypothesis import strategies as st

from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    is_element_of_type,
)
from tree_sitter_analyzer.models import CodeElement


class DummyElement(CodeElement):
    pass


class TestElementTypeProperty:
    @given(st.sampled_from(["class", "function", "variable", "import", "unknown"]))
    def test_is_element_of_type_matches_string(self, etype):
        elem = DummyElement(
            name="test",
            start_line=1,
            end_line=1,
            element_type=etype,
        )
        if etype == "class":
            assert is_element_of_type(elem, ELEMENT_TYPE_CLASS) is True
        elif etype == "function":
            assert is_element_of_type(elem, ELEMENT_TYPE_FUNCTION) is True
        else:
            assert is_element_of_type(elem, ELEMENT_TYPE_CLASS) is False
