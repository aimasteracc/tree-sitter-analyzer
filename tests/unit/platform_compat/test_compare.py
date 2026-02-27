"""Tests for platform_compat.compare module."""

import pytest

from tree_sitter_analyzer.platform_compat.compare import (
    BehaviorDifference,
    ProfileComparison,
    compare_profiles,
    generate_diff_report,
)
from tree_sitter_analyzer.platform_compat.profiles import (
    BehaviorProfile,
    ParsingBehavior,
)


class TestBehaviorDifference:
    """Tests for the BehaviorDifference dataclass."""

    @pytest.mark.unit
    def test_create_difference(self):
        """Test creating a BehaviorDifference."""
        diff = BehaviorDifference(
            construct_id="simple_table",
            diff_type="missing",
            details="Construct missing in platform B",
            platform_a_value="present",
            platform_b_value="missing",
        )
        assert diff.construct_id == "simple_table"
        assert diff.diff_type == "missing"


class TestProfileComparison:
    """Tests for the ProfileComparison dataclass."""

    @pytest.mark.unit
    def test_has_differences_false(self):
        """Test has_differences is False when no differences."""
        comparison = ProfileComparison(
            platform_a="linux-3.12",
            platform_b="macos-3.12",
            differences=[],
        )
        assert comparison.has_differences is False

    @pytest.mark.unit
    def test_has_differences_true(self):
        """Test has_differences is True when differences exist."""
        diff = BehaviorDifference(
            construct_id="test",
            diff_type="missing",
            details="missing",
            platform_a_value="a",
            platform_b_value="b",
        )
        comparison = ProfileComparison(
            platform_a="linux-3.12",
            platform_b="macos-3.12",
            differences=[diff],
        )
        assert comparison.has_differences is True


class TestCompareProfiles:
    """Tests for the compare_profiles function."""

    @pytest.mark.unit
    def test_identical_profiles_no_differences(self):
        """Test that comparing identical profiles yields no differences."""
        behavior = ParsingBehavior(
            construct_id="simple_table",
            node_type="program",
            element_count=1,
            attributes=["col:id"],
            has_error=False,
        )
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={"simple_table": behavior},
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "simple_table": ParsingBehavior(
                    construct_id="simple_table",
                    node_type="program",
                    element_count=1,
                    attributes=["col:id"],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert not result.has_differences

    @pytest.mark.unit
    def test_missing_construct_in_profile_b(self):
        """Test detection of construct missing in profile B."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={
                "simple_table": ParsingBehavior(
                    construct_id="simple_table",
                    node_type="program",
                    element_count=1,
                    attributes=[],
                    has_error=False,
                ),
                "extra_construct": ParsingBehavior(
                    construct_id="extra_construct",
                    node_type="program",
                    element_count=0,
                    attributes=[],
                    has_error=False,
                ),
            },
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "simple_table": ParsingBehavior(
                    construct_id="simple_table",
                    node_type="program",
                    element_count=1,
                    attributes=[],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert result.has_differences
        missing_diffs = [d for d in result.differences if d.diff_type == "missing"]
        assert len(missing_diffs) == 1
        assert missing_diffs[0].construct_id == "extra_construct"
        assert missing_diffs[0].platform_a_value == "present"

    @pytest.mark.unit
    def test_missing_construct_in_profile_a(self):
        """Test detection of construct missing in profile A."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "only_in_b": ParsingBehavior(
                    construct_id="only_in_b",
                    node_type="program",
                    element_count=1,
                    attributes=[],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert result.has_differences
        missing_diffs = [d for d in result.differences if d.diff_type == "missing"]
        assert len(missing_diffs) == 1
        assert missing_diffs[0].construct_id == "only_in_b"
        assert missing_diffs[0].platform_a_value == "missing"

    @pytest.mark.unit
    def test_error_mismatch(self):
        """Test detection of error status mismatch."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={
                "test": ParsingBehavior(
                    construct_id="test",
                    node_type="program",
                    element_count=1,
                    attributes=[],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "test": ParsingBehavior(
                    construct_id="test",
                    node_type="program",
                    element_count=1,
                    attributes=[],
                    has_error=True,
                )
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert result.has_differences
        error_diffs = [d for d in result.differences if d.diff_type == "error_mismatch"]
        assert len(error_diffs) == 1
        assert error_diffs[0].platform_a_value is False
        assert error_diffs[0].platform_b_value is True

    @pytest.mark.unit
    def test_count_mismatch(self):
        """Test detection of element count mismatch."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={
                "test": ParsingBehavior(
                    construct_id="test",
                    node_type="program",
                    element_count=3,
                    attributes=[],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "test": ParsingBehavior(
                    construct_id="test",
                    node_type="program",
                    element_count=5,
                    attributes=[],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert result.has_differences
        count_diffs = [d for d in result.differences if d.diff_type == "count_mismatch"]
        assert len(count_diffs) == 1
        assert count_diffs[0].platform_a_value == 3
        assert count_diffs[0].platform_b_value == 5

    @pytest.mark.unit
    def test_attribute_mismatch(self):
        """Test detection of attribute mismatch."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={
                "test": ParsingBehavior(
                    construct_id="test",
                    node_type="program",
                    element_count=1,
                    attributes=["col:id", "col:name"],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "test": ParsingBehavior(
                    construct_id="test",
                    node_type="program",
                    element_count=1,
                    attributes=["col:id", "col:email"],
                    has_error=False,
                )
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert result.has_differences
        attr_diffs = [
            d for d in result.differences if d.diff_type == "attribute_mismatch"
        ]
        assert len(attr_diffs) == 1

    @pytest.mark.unit
    def test_empty_profiles_no_differences(self):
        """Test that two empty profiles produce no differences."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={},
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert not result.has_differences

    @pytest.mark.unit
    def test_multiple_difference_types(self):
        """Test detection of multiple difference types simultaneously."""
        profile_a = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={
                "common": ParsingBehavior(
                    construct_id="common",
                    node_type="program",
                    element_count=1,
                    attributes=["col:a"],
                    has_error=False,
                ),
                "only_a": ParsingBehavior(
                    construct_id="only_a",
                    node_type="program",
                    element_count=0,
                    attributes=[],
                    has_error=False,
                ),
            },
            adaptation_rules=[],
        )
        profile_b = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="macos-3.12",
            behaviors={
                "common": ParsingBehavior(
                    construct_id="common",
                    node_type="program",
                    element_count=2,
                    attributes=["col:b"],
                    has_error=True,
                ),
                "only_b": ParsingBehavior(
                    construct_id="only_b",
                    node_type="program",
                    element_count=0,
                    attributes=[],
                    has_error=False,
                ),
            },
            adaptation_rules=[],
        )
        result = compare_profiles(profile_a, profile_b)
        assert result.has_differences
        # Should have: missing only_a, missing only_b, error_mismatch, count_mismatch, attribute_mismatch
        diff_types = {d.diff_type for d in result.differences}
        assert "missing" in diff_types
        assert "error_mismatch" in diff_types
        assert "count_mismatch" in diff_types
        assert "attribute_mismatch" in diff_types


class TestGenerateDiffReport:
    """Tests for the generate_diff_report function."""

    @pytest.mark.unit
    def test_no_differences_report(self):
        """Test report when there are no differences."""
        comparison = ProfileComparison(
            platform_a="linux-3.12",
            platform_b="macos-3.12",
            differences=[],
        )
        report = generate_diff_report(comparison)
        assert "No differences found" in report
        assert "linux-3.12" in report
        assert "macos-3.12" in report

    @pytest.mark.unit
    def test_report_with_differences(self):
        """Test report generation with differences."""
        diff = BehaviorDifference(
            construct_id="simple_table",
            diff_type="error_mismatch",
            details="Error status mismatch for simple_table",
            platform_a_value=False,
            platform_b_value=True,
        )
        comparison = ProfileComparison(
            platform_a="linux-3.12",
            platform_b="macos-3.12",
            differences=[diff],
        )
        report = generate_diff_report(comparison)
        assert "Comparison Report" in report
        assert "linux-3.12" in report
        assert "macos-3.12" in report
        assert "simple_table" in report
        assert "error_mismatch" in report
        assert "Total differences: 1" in report

    @pytest.mark.unit
    def test_report_format_contains_separator(self):
        """Test that the report includes proper formatting separators."""
        diff = BehaviorDifference(
            construct_id="test",
            diff_type="missing",
            details="Missing construct",
            platform_a_value="present",
            platform_b_value="missing",
        )
        comparison = ProfileComparison(
            platform_a="linux-3.12",
            platform_b="macos-3.12",
            differences=[diff],
        )
        report = generate_diff_report(comparison)
        assert "=" * 60 in report
        assert "-" * 40 in report
