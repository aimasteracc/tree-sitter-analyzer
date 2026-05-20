"""Tests for platform_compat.compare module."""

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


def _behavior(
    construct_id: str = "sel_all",
    node_type: str = "select_statement",
    element_count: int = 1,
    attributes: list[str] | None = None,
    has_error: bool = False,
) -> ParsingBehavior:
    return ParsingBehavior(
        construct_id=construct_id,
        node_type=node_type,
        element_count=element_count,
        attributes=attributes or ["keyword:SELECT", "wildcard:*"],
        has_error=has_error,
    )


def _profile(
    platform_key: str = "linux-3.12",
    behaviors: dict[str, ParsingBehavior] | None = None,
) -> BehaviorProfile:
    return BehaviorProfile(
        schema_version="1.0.0",
        platform_key=platform_key,
        behaviors=behaviors or {},
        adaptation_rules=[],
    )


class TestBehaviorDifference:
    def test_fields(self) -> None:
        diff = BehaviorDifference(
            construct_id="sel_all",
            diff_type="missing",
            details="Construct missing",
            platform_a_value="present",
            platform_b_value="missing",
        )
        assert diff.construct_id == "sel_all"
        assert diff.diff_type == "missing"

    def test_diff_types(self) -> None:
        for dt in ("missing", "attribute_mismatch", "error_mismatch", "count_mismatch"):
            diff = BehaviorDifference(
                construct_id="x",
                diff_type=dt,
                details="",
                platform_a_value=None,
                platform_b_value=None,
            )
            assert diff.diff_type == dt


class TestProfileComparison:
    def test_has_differences_false_when_empty(self) -> None:
        comp = ProfileComparison(
            platform_a="linux-3.12",
            platform_b="windows-3.12",
            differences=[],
        )
        assert comp.has_differences is False

    def test_has_differences_true(self) -> None:
        diff = BehaviorDifference(
            construct_id="x",
            diff_type="missing",
            details="",
            platform_a_value=None,
            platform_b_value=None,
        )
        comp = ProfileComparison(
            platform_a="a",
            platform_b="b",
            differences=[diff],
        )
        assert comp.has_differences is True


class TestCompareProfilesIdentical:
    def test_identical_profiles_no_differences(self) -> None:
        behaviors = {"sel": _behavior("sel")}
        a = _profile("linux-3.12", behaviors)
        b = _profile("windows-3.12", behaviors)
        result = compare_profiles(a, b)
        assert not result.has_differences

    def test_identical_platform_keys_in_result(self) -> None:
        a = _profile("linux-3.12")
        b = _profile("windows-3.12")
        result = compare_profiles(a, b)
        assert result.platform_a == "linux-3.12"
        assert result.platform_b == "windows-3.12"


class TestCompareProfilesMissing:
    def test_construct_in_a_missing_in_b(self) -> None:
        behaviors_a = {"sel": _behavior("sel")}
        a = _profile("linux", behaviors_a)
        b = _profile("windows", {})
        result = compare_profiles(a, b)
        assert result.has_differences
        assert any(
            d.diff_type == "missing" and d.platform_b_value == "missing"
            for d in result.differences
        )

    def test_construct_in_b_missing_in_a(self) -> None:
        behaviors_b = {"sel": _behavior("sel")}
        a = _profile("linux", {})
        b = _profile("windows", behaviors_b)
        result = compare_profiles(a, b)
        assert result.has_differences
        assert any(
            d.diff_type == "missing" and d.platform_a_value == "missing"
            for d in result.differences
        )


class TestCompareProfilesMismatch:
    def test_error_mismatch(self) -> None:
        beh_a = {"sel": _behavior("sel", has_error=False)}
        beh_b = {"sel": _behavior("sel", has_error=True)}
        result = compare_profiles(_profile("a", beh_a), _profile("b", beh_b))
        assert any(d.diff_type == "error_mismatch" for d in result.differences)

    def test_count_mismatch(self) -> None:
        beh_a = {"sel": _behavior("sel", element_count=1)}
        beh_b = {"sel": _behavior("sel", element_count=3)}
        result = compare_profiles(_profile("a", beh_a), _profile("b", beh_b))
        assert any(d.diff_type == "count_mismatch" for d in result.differences)

    def test_attribute_mismatch(self) -> None:
        beh_a = {"sel": _behavior("sel", attributes=["x"])}
        beh_b = {"sel": _behavior("sel", attributes=["y"])}
        result = compare_profiles(_profile("a", beh_a), _profile("b", beh_b))
        assert any(d.diff_type == "attribute_mismatch" for d in result.differences)

    def test_no_diff_when_same_attributes(self) -> None:
        beh = {"sel": _behavior("sel", attributes=["a", "b"])}
        result = compare_profiles(_profile("a", beh), _profile("b", beh))
        assert not result.has_differences


class TestGenerateDiffReport:
    def test_no_differences(self) -> None:
        comp = ProfileComparison("linux", "windows", [])
        report = generate_diff_report(comp)
        assert "No differences" in report
        assert "linux" in report
        assert "windows" in report

    def test_with_differences(self) -> None:
        diff = BehaviorDifference(
            construct_id="sel_all",
            diff_type="missing",
            details="Construct sel_all missing in windows",
            platform_a_value="present",
            platform_b_value="missing",
        )
        comp = ProfileComparison("linux", "windows", [diff])
        report = generate_diff_report(comp)
        assert "sel_all" in report
        assert "missing" in report
        assert "Total differences: 1" in report

    def test_multiple_differences(self) -> None:
        diffs = [
            BehaviorDifference("a", "missing", "x", "present", "missing"),
            BehaviorDifference("b", "count_mismatch", "y", 1, 3),
        ]
        comp = ProfileComparison("a", "b", diffs)
        report = generate_diff_report(comp)
        assert "Total differences: 2" in report
        assert "Construct: a" in report
        assert "Construct: b" in report
