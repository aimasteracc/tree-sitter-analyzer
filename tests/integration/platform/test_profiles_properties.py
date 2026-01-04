import json
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
    ParsingBehavior,
)


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


class TestProfileProperties:
    @settings(deadline=None)  # Disable deadline due to I/O variability
    @given(behavior_profile_strategy())
    def test_profile_persistence_correctness(self, profile):
        """
        Property 8: Profile persistence correctness
        Validates: Requirements 2.3, 2.5
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Save profile
            profile.save(base_path)

            # Load profile
            loaded_profile = BehaviorProfile.load(profile.platform_key, base_path)

            assert loaded_profile is not None
            assert loaded_profile.platform_key == profile.platform_key
            assert loaded_profile.schema_version == profile.schema_version
            assert loaded_profile.adaptation_rules == profile.adaptation_rules

            # Check behaviors
            assert len(loaded_profile.behaviors) == len(profile.behaviors)
            for key, behavior in profile.behaviors.items():
                assert key in loaded_profile.behaviors
                loaded_behavior = loaded_profile.behaviors[key]
                assert loaded_behavior == behavior

    def test_profile_loading_correctness(self):
        """
        Property 3: Profile loading correctness
        Validates: Requirements 1.4, 4.2
        """
        # Test loading non-existent profile
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            loaded = BehaviorProfile.load("non-existent-3.12", base_path)
            assert loaded is None

        # Test loading invalid profile (schema validation)
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            os_name = "linux"
            py_ver = "3.12"
            profile_dir = base_path / os_name / py_ver
            profile_dir.mkdir(parents=True)

            with open(profile_dir / "profile.json", "w") as f:
                json.dump({"invalid": "data"}, f)

            # Should return None or raise exception?
            # The implementation catches exceptions and returns None
            loaded = BehaviorProfile.load(f"{os_name}-{py_ver}", base_path)
            assert loaded is None
