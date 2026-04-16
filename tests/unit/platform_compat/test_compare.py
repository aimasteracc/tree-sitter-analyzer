"""Tests for platform_compat.compare — profile comparison logic."""
from __future__ import annotations

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


def _make_behavior(
    construct_id: str = "test",
    node_type: str = "select_statement",
    element_count: int = 3,
    attributes: list[str] | None = None,
    has_error: bool = False,
    known_issues: list[str] | None = None,
) -> ParsingBehavior:
    return ParsingBehavior(
        construct_id=construct_id,
        node_type=node_type,
        element_count=element_count,
        attributes=attributes or ["keyword", "expression"],
        has_error=has_error,
        known_issues=known_issues or [],
    )


def _make_profile(
    platform_key: str = "linux",
    behaviors: dict[str, ParsingBehavior] | None = None,
) -> BehaviorProfile:
    return BehaviorProfile(
        schema_version="1.0.0",
        platform_key=platform_key,
        behaviors=behaviors or {},
        adaptation_rules=[],
    )


class TestProfileComparison:
    def test_no_differences(self) -> None:
        beh = _make_behavior()
        a = _make_profile("macos", {"sel": beh})
        b = _make_profile("linux", {"sel": beh})
        result = compare_profiles(a, b)
        assert not result.has_differences

    def test_missing_in_b(self) -> None:
        beh = _make_behavior("join")
        a = _make_profile("macos", {"join": beh})
        b = _make_profile("linux", {})
        result = compare_profiles(a, b)
        assert result.has_differences
        assert any(d.diff_type == "missing" for d in result.differences)
        missing = [d for d in result.differences if d.diff_type == "missing"]
        assert missing[0].platform_a_value == "present"
        assert missing[0].platform_b_value == "missing"

    def test_missing_in_a(self) -> None:
        beh = _make_behavior("subquery")
        a = _make_profile("macos", {})
        b = _make_profile("linux", {"subquery": beh})
        result = compare_profiles(a, b)
        assert result.has_differences
        missing = [d for d in result.differences if d.diff_type == "missing"]
        assert missing[0].platform_a_value == "missing"
        assert missing[0].platform_b_value == "present"

    def test_error_mismatch(self) -> None:
        beh_a = _make_behavior("cte", has_error=False)
        beh_b = _make_behavior("cte", has_error=True)
        a = _make_profile("macos", {"cte": beh_a})
        b = _make_profile("linux", {"cte": beh_b})
        result = compare_profiles(a, b)
        assert any(d.diff_type == "error_mismatch" for d in result.differences)

    def test_count_mismatch(self) -> None:
        beh_a = _make_behavior("group_by", element_count=5)
        beh_b = _make_behavior("group_by", element_count=3)
        a = _make_profile("macos", {"group_by": beh_a})
        b = _make_profile("linux", {"group_by": beh_b})
        result = compare_profiles(a, b)
        assert any(d.diff_type == "count_mismatch" for d in result.differences)
        count_diff = [d for d in result.differences if d.diff_type == "count_mismatch"]
        assert count_diff[0].platform_a_value == 5
        assert count_diff[0].platform_b_value == 3

    def test_attribute_mismatch(self) -> None:
        beh_a = _make_behavior("union", attributes=["keyword", "left", "right"])
        beh_b = _make_behavior("union", attributes=["keyword", "left"])
        a = _make_profile("macos", {"union": beh_a})
        b = _make_profile("linux", {"union": beh_b})
        result = compare_profiles(a, b)
        assert any(d.diff_type == "attribute_mismatch" for d in result.differences)

    def test_multiple_differences(self) -> None:
        beh_a1 = _make_behavior("select", has_error=False, element_count=4)
        beh_b1 = _make_behavior("select", has_error=True, element_count=2)
        beh_a2 = _make_behavior("insert")
        a = _make_profile("macos", {"select": beh_a1, "insert": beh_a2})
        b = _make_profile("linux", {"select": beh_b1})
        result = compare_profiles(a, b)
        diff_types = {d.diff_type for d in result.differences}
        assert "missing" in diff_types
        assert "error_mismatch" in diff_types
        assert "count_mismatch" in diff_types

    def test_comparison_preserves_platform_keys(self) -> None:
        a = _make_profile("macos")
        b = _make_profile("linux")
        result = compare_profiles(a, b)
        assert result.platform_a == "macos"
        assert result.platform_b == "linux"


class TestGenerateDiffReport:
    def test_no_differences_report(self) -> None:
        comp = ProfileComparison(platform_a="macos", platform_b="linux", differences=[])
        report = generate_diff_report(comp)
        assert "No differences found" in report
        assert "macos" in report
        assert "linux" in report

    def test_report_with_differences(self) -> None:
        diffs = [
            BehaviorDifference(
                construct_id="select",
                diff_type="count_mismatch",
                details="Count mismatch for select",
                platform_a_value=5,
                platform_b_value=3,
            )
        ]
        comp = ProfileComparison(platform_a="macos", platform_b="linux", differences=diffs)
        report = generate_diff_report(comp)
        assert "Comparison Report" in report
        assert "Total differences: 1" in report
        assert "select" in report
        assert "count_mismatch" in report
        assert "5" in report
        assert "3" in report

    def test_report_with_multiple_differences(self) -> None:
        diffs = [
            BehaviorDifference(
                construct_id="cte",
                diff_type="error_mismatch",
                details="Error mismatch for cte",
                platform_a_value=False,
                platform_b_value=True,
            ),
            BehaviorDifference(
                construct_id="join",
                diff_type="missing",
                details="Join missing in linux",
                platform_a_value="present",
                platform_b_value="missing",
            ),
        ]
        comp = ProfileComparison(platform_a="macos", platform_b="linux", differences=diffs)
        report = generate_diff_report(comp)
        assert "Total differences: 2" in report
        assert "cte" in report
        assert "join" in report


class TestBehaviorDifference:
    def test_dataclass_fields(self) -> None:
        diff = BehaviorDifference(
            construct_id="subquery",
            diff_type="attribute_mismatch",
            details="Attributes differ",
            platform_a_value=["a", "b"],
            platform_b_value=["a"],
        )
        assert diff.construct_id == "subquery"
        assert diff.diff_type == "attribute_mismatch"
        assert diff.platform_a_value == ["a", "b"]
        assert diff.platform_b_value == ["a"]


class TestProfileComparisonDataclass:
    def test_has_differences_false_when_empty(self) -> None:
        comp = ProfileComparison(platform_a="a", platform_b="b", differences=[])
        assert not comp.has_differences

    def test_has_differences_true_when_present(self) -> None:
        diff = BehaviorDifference(
            construct_id="x", diff_type="missing",
            details="x", platform_a_value="a", platform_b_value="b",
        )
        comp = ProfileComparison(platform_a="a", platform_b="b", differences=[diff])
        assert comp.has_differences
