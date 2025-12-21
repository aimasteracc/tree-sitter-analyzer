from hypothesis import given
from hypothesis import strategies as st

from tree_sitter_analyzer.platform_compat.compare import compare_profiles
from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
    ParsingBehavior,
)


# Reuse strategies from test_profiles_properties.py if possible, or redefine
@st.composite
def parsing_behavior_strategy(draw):
    return ParsingBehavior(
        construct_id=draw(st.text(min_size=1)),
        node_type=draw(st.text(min_size=1)),
        element_count=draw(st.integers(min_value=0)),
        attributes=draw(st.lists(st.text())),
        has_error=draw(st.booleans()),
        known_issues=draw(st.lists(st.text())),
    )


@st.composite
def behavior_profile_strategy(draw):
    platform_key = f"{draw(st.sampled_from(['windows', 'linux', 'macos']))}-{draw(st.integers(3, 4))}.{draw(st.integers(8, 13))}"
    behaviors = draw(st.dictionaries(st.text(min_size=1), parsing_behavior_strategy()))
    return BehaviorProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        platform_key=platform_key,
        behaviors=behaviors,
        adaptation_rules=draw(st.lists(st.text())),
    )


class TestCompareProperties:
    @given(behavior_profile_strategy())
    def test_profile_comparison_identity(self, profile):
        """
        Property 9: Profile comparison accuracy (Identity)
        Validates: Requirements 2.4
        """
        # Comparing a profile with itself should yield no differences
        comparison = compare_profiles(profile, profile)
        assert not comparison.has_differences
        assert len(comparison.differences) == 0

    @given(behavior_profile_strategy())
    def test_profile_comparison_accuracy(self, profile):
        """
        Property 9: Profile comparison accuracy (Differences)
        Validates: Requirements 2.4
        """
        # Create a modified profile
        import copy

        profile_b = copy.deepcopy(profile)

        # Modify something if behaviors exist
        if profile_b.behaviors:
            key = list(profile_b.behaviors.keys())[0]
            # Flip error status
            profile_b.behaviors[key].has_error = not profile_b.behaviors[key].has_error

            comparison = compare_profiles(profile, profile_b)
            assert comparison.has_differences

            # Find the specific difference
            found = False
            for diff in comparison.differences:
                if diff.construct_id == key and diff.diff_type == "error_mismatch":
                    found = True
                    break
            assert found, "Expected error_mismatch difference not found"
