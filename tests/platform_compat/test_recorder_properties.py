import tempfile
from pathlib import Path

from tree_sitter_analyzer.platform_compat.fixtures import ALL_FIXTURES
from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder


class TestRecorderProperties:
    def test_recording_completeness(self):
        """
        Property 6: Behavior recording completeness
        Validates: Requirements 2.1
        """
        recorder = BehaviorRecorder()
        profile = recorder.record_all()

        # Check that all fixtures are present in the profile
        for fixture in ALL_FIXTURES:
            assert (
                fixture.id in profile.behaviors
            ), f"Fixture {fixture.id} missing from profile"

        assert len(profile.behaviors) == len(ALL_FIXTURES)

    def test_profile_content_completeness(self):
        """
        Property 7: Profile content completeness
        Validates: Requirements 2.2
        """
        recorder = BehaviorRecorder()
        profile = recorder.record_all()

        for behavior in profile.behaviors.values():
            assert behavior.construct_id is not None
            assert behavior.node_type is not None
            assert isinstance(behavior.element_count, int)
            assert isinstance(behavior.attributes, list)
            assert isinstance(behavior.has_error, bool)

            # We expect at least the root node type to be 'program' or similar for SQL
            assert (
                behavior.node_type == "program" or behavior.node_type == "source_file"
            )  # tree-sitter-sql usually returns 'program' or 'source_file' depending on version

    def test_profile_persistence_integration(self):
        """
        Property 8: Profile persistence correctness (Integration)
        Validates: Requirements 2.3, 2.5
        """
        recorder = BehaviorRecorder()
        profile = recorder.record_all()

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            recorder.save_profile(profile, base_path)

            # Verify file exists
            parts = profile.platform_key.split("-")
            expected_path = base_path / parts[0] / parts[1] / "profile.json"
            assert expected_path.exists()
