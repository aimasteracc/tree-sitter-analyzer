import json
import tempfile
from pathlib import Path

from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
    ParsingBehavior,
)
from tree_sitter_analyzer.platform_compat.report import generate_compatibility_matrix


class TestReportProperties:
    def test_compatibility_matrix_generation(self):
        """
        Property 10: Compatibility matrix generation
        Validates: Requirements 3.5
        """
        # Create temporary directory with mock profiles
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create 2 profiles
            p1 = BehaviorProfile(
                schema_version=PROFILE_SCHEMA_VERSION,
                platform_key="os1-3.10",
                behaviors={
                    "test_table": ParsingBehavior(
                        "test_table", "table", 1, [], False, []
                    )
                },
                adaptation_rules=[],
            )

            p2 = BehaviorProfile(
                schema_version=PROFILE_SCHEMA_VERSION,
                platform_key="os2-3.11",
                behaviors={
                    "test_table": ParsingBehavior(
                        "test_table", "table", 1, [], True, []
                    )  # Error
                },
                adaptation_rules=[],
            )

            # Save them
            # We manually save to avoid directory structure complexity for this test
            (base_path / "p1").mkdir()
            with open(base_path / "p1" / "profile.json", "w") as f:
                json.dump(p1.__dict__, f, default=lambda o: o.__dict__)

            (base_path / "p2").mkdir()
            with open(base_path / "p2" / "profile.json", "w") as f:
                json.dump(p2.__dict__, f, default=lambda o: o.__dict__)

            # Generate report
            report = generate_compatibility_matrix(base_path)

            # Verify content
            assert "# SQL Compatibility Matrix" in report
            assert "os1-3.10" in report
            assert "os2-3.11" in report
            assert "test_table" in report
            assert "✅ OK" in report
            assert "⚠️ Error" in report
