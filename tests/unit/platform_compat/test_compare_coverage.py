"""Coverage tests for compare.py — target 55.74% → ≥80%."""

import pytest

from tree_sitter_analyzer.platform_compat.compare import (
    BehaviorDifference,
    ProfileComparison,
    compare_profiles,
    generate_diff_report,
)
from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
    ParsingBehavior,
)


def _make_behavior(  # helper
    construct_id="f1",
    node_type="function",
    element_count=3,
    attributes=None,
    has_error=False,
    known_issues=None,
):
    return ParsingBehavior(
        construct_id=construct_id,
        node_type=node_type,
        element_count=element_count,
        attributes=attributes or [],
        has_error=has_error,
        known_issues=known_issues or [],
    )


def _make_profile(platform_key="linux-3.12", behaviors=None):
    return BehaviorProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        platform_key=platform_key,
        behaviors=behaviors or {},
        adaptation_rules=[],
    )


# ------------------------------------------------------------------
# compare_profiles coverage gaps
# ------------------------------------------------------------------


def test_missing_construct_in_b():
    """Cover key in keys_a - keys_b (line 60)."""
    a = _make_profile("linux-3.12", {"f1": _make_behavior("f1")})
    b = _make_profile("macos-3.12", {})
    result = compare_profiles(a, b)
    assert result.has_differences
    diff = result.differences[0]
    assert diff.construct_id == "f1"
    assert diff.diff_type == "missing"
    assert "linux-3.12" in diff.details or "missing" in diff.platform_b_value


def test_missing_construct_in_a():
    """Cover key in keys_b - keys_a."""
    a = _make_profile("linux-3.12", {})
    b = _make_profile("macos-3.12", {"f1": _make_behavior("f1")})
    result = compare_profiles(a, b)
    assert result.has_differences
    diff = result.differences[0]
    assert diff.construct_id == "f1"
    assert diff.diff_type == "missing"


def test_error_mismatch():
    """Cover error_mismatch branch."""
    a = _make_profile("linux-3.12", {"f1": _make_behavior("f1", has_error=False)})
    b = _make_profile("macos-3.12", {"f1": _make_behavior("f1", has_error=True)})
    result = compare_profiles(a, b)
    assert result.has_differences
    assert any(d.construct_id == "f1" and d.diff_type == "error_mismatch" for d in result.differences)


def test_count_mismatch():
    """Cover count_mismatch branch (line 91-99)."""
    a = _make_profile("linux-3.12", {"f1": _make_behavior("f1", element_count=3)})
    b = _make_profile("macos-3.12", {"f1": _make_behavior("f1", element_count=5)})
    result = compare_profiles(a, b)
    assert result.has_differences
    assert any(d.construct_id == "f1" and d.diff_type == "count_mismatch" for d in result.differences)


def test_attribute_mismatch():
    """Cover attribute_mismatch with DeepDiff (line 100-116)."""
    a = _make_profile("linux-3.12", {"f1": _make_behavior("f1", attributes=["a", "b"])})
    b = _make_profile("macos-3.12", {"f1": _make_behavior("f1", attributes=["a", "c"])})
    result = compare_profiles(a, b)
    assert any(d.diff_type == "attribute_mismatch" for d in result.differences)


def test_no_differences():
    """Cover the happy path with no differences."""
    b1 = _make_behavior("f1")
    b2 = _make_behavior("f1")
    a = _make_profile("linux-3.12", {"f1": b1})
    b = _make_profile("macos-3.12", {"f1": b2})
    result = compare_profiles(a, b)
    assert not result.has_differences


# ------------------------------------------------------------------
# generate_diff_report coverage gaps (lines 143-161)
# ------------------------------------------------------------------


def test_diff_report_with_differences():
    """Cover generate_diff_report when has_differences is True."""
    a = _make_profile("linux-3.12", {"f1": _make_behavior("f1")})
    b = _make_profile("macos-3.12", {})
    comparison = compare_profiles(a, b)
    report = generate_diff_report(comparison)
    assert "linux-3.12" in report
    assert "macos-3.12" in report
    assert "f1" in report
    assert "missing" in report.lower()


def test_diff_report_no_differences():
    """Cover generate_diff_report when has_differences is False."""
    b1 = _make_behavior("f1")
    a = _make_profile("linux-3.12", {"f1": b1})
    b = _make_profile("macos-3.12", {"f1": b1})
    comparison = compare_profiles(a, b)
    report = generate_diff_report(comparison)
    assert "No differences found" in report


# ------------------------------------------------------------------
# dataclass coverage
# ------------------------------------------------------------------


def test_behavior_difference_fields():
    """Cover BehaviorDifference dataclass instantiation."""
    bd = BehaviorDifference(
        construct_id="f1",
        diff_type="missing",
        details="test",
        platform_a_value="present",
        platform_b_value="missing",
    )
    assert bd.construct_id == "f1"
    assert bd.diff_type == "missing"


def test_profile_comparison_has_differences():
    """Cover ProfileComparison.has_differences property."""
    empty = ProfileComparison(
        platform_a="a", platform_b="b", differences=[]
    )
    assert not empty.has_differences
    full = ProfileComparison(
        platform_a="a", platform_b="b",
        differences=[BehaviorDifference("x", "missing", "", "", "")]
    )
    assert full.has_differences
