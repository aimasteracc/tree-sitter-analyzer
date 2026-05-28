"""
Property-based tests for Java language helper functions.

Tests correctness invariants for:
- _split_respecting_generics: comma-splitting that respects angle-bracket depth
- determine_visibility: modifier-to-visibility mapping
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages._java_element_helpers import (
    _split_respecting_generics,
)
from tree_sitter_analyzer.languages.java_helpers import determine_visibility

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SIMPLE_IDENT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        min_codepoint=65,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=12,
).filter(lambda s: s[0].isupper() and s[0].isascii())

_TYPE_ARG = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    min_size=1,
    max_size=3,
)


@st.composite
def simple_type(draw):
    """Generate a simple Java type name without generics."""
    return draw(_SIMPLE_IDENT)


@st.composite
def generic_type(draw):
    """Generate a generic Java type like 'Map<K, V>' or 'List<String>'."""
    base = draw(_SIMPLE_IDENT)
    n_args = draw(st.integers(min_value=1, max_value=3))
    args = [draw(_TYPE_ARG) for _ in range(n_args)]
    return f"{base}<{', '.join(args)}>"


@st.composite
def java_type(draw):
    """Either a simple or a generic Java type."""
    return draw(st.one_of(simple_type(), generic_type()))


@st.composite
def interface_list(draw):
    """A comma-joined list of 1-5 Java types."""
    n = draw(st.integers(min_value=1, max_value=5))
    types = [draw(java_type()) for _ in range(n)]
    return types, ", ".join(types)


# ---------------------------------------------------------------------------
# Properties: _split_respecting_generics
# ---------------------------------------------------------------------------


class TestSplitRespectingGenericsProperties:
    """Property-based tests for _split_respecting_generics."""

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_roundtrip_element_count(self, data):
        """Split must return exactly as many elements as were joined."""
        types, joined = data
        result = _split_respecting_generics(joined)
        assert len(result) == len(types), (
            f"Expected {len(types)} elements from '{joined}', got {len(result)}: {result}"
        )

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_no_empty_elements(self, data):
        """No result element should be empty or whitespace-only."""
        _, joined = data
        result = _split_respecting_generics(joined)
        for elem in result:
            assert elem.strip(), f"Empty element in result {result} from '{joined}'"

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_each_element_starts_with_capital(self, data):
        """Every result element should start with a capital letter (Java type convention)."""
        _, joined = data
        result = _split_respecting_generics(joined)
        for elem in result:
            assert elem[0].isupper(), (
                f"Element '{elem}' does not start with capital in result from '{joined}'"
            )

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_no_depth0_comma_inside_element(self, data):
        """No result element should contain a depth-0 comma (unbalanced generic brackets)."""
        _, joined = data
        result = _split_respecting_generics(joined)
        for elem in result:
            depth = 0
            for ch in elem:
                if ch == "<":
                    depth += 1
                elif ch == ">":
                    depth -= 1
                elif ch == "," and depth == 0:
                    assert False, (
                        f"Element '{elem}' contains depth-0 comma; "
                        f"generics not respected in '{joined}'"
                    )

    @settings(max_examples=200)
    @given(n=st.integers(min_value=1, max_value=6))
    def test_simple_types_no_generics(self, n):
        """For n simple types joined by ', ', result should have exactly n elements."""
        types = [f"Type{i}" for i in range(n)]
        joined = ", ".join(types)
        result = _split_respecting_generics(joined)
        assert len(result) == n, (
            f"Expected {n} elements from '{joined}', got {len(result)}: {result}"
        )

    @settings(max_examples=100)
    @given(k=st.integers(min_value=1, max_value=4))
    def test_single_generic_with_k_args(self, k):
        """Map<A, B, C> with k type args must come back as one element."""
        args = [chr(ord("A") + i) for i in range(k)]
        single = f"Map<{', '.join(args)}>"
        result = _split_respecting_generics(single)
        assert len(result) == 1, (
            f"Expected 1 element for '{single}', got {len(result)}: {result}"
        )
        assert result[0].startswith("Map"), f"Expected 'Map...' but got '{result[0]}'"


# ---------------------------------------------------------------------------
# Properties: determine_visibility
# ---------------------------------------------------------------------------


class TestDetermineVisibilityProperties:
    """Property-based tests for Java determine_visibility."""

    _NOISE = ["static", "final", "abstract", "synchronized", "native", "transient"]

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_public_wins_over_noise(self, noise):
        """'public' in modifiers always returns 'public' regardless of other modifiers."""
        modifiers = noise + ["public"]
        assert determine_visibility(modifiers) == "public"

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_private_wins_over_noise(self, noise):
        """'private' in modifiers always returns 'private' regardless of other modifiers."""
        modifiers = noise + ["private"]
        assert determine_visibility(modifiers) == "private"

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_protected_wins_over_noise(self, noise):
        """'protected' in modifiers always returns 'protected' regardless of other modifiers."""
        modifiers = noise + ["protected"]
        assert determine_visibility(modifiers) == "protected"

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_no_visibility_modifier_returns_package(self, noise):
        """No visibility keyword → package-private."""
        assert determine_visibility(noise) == "package"

    @settings(max_examples=50)
    @given(st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_return_value_is_one_of_four_options(self, modifiers):
        """Return value is always one of the four Java visibility levels."""
        result = determine_visibility(modifiers)
        assert result in {"public", "private", "protected", "package"}, (
            f"Unexpected visibility '{result}' for modifiers {modifiers}"
        )
