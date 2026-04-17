#!/usr/bin/env python3
"""
Tests for Semantic Impact Analysis.

Validates the risk scoring model, visibility extraction,
type hierarchy detection, and suggestion generation.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.analysis.semantic_impact import (
    SemanticRiskLevel,
    SymbolProfile,
    Visibility,
    analyze_semantic_impact,
    build_symbol_profile,
    extract_visibility_from_element,
    report_to_dict,
)


class TestVisibilityExtraction:
    """Test visibility extraction from elements."""

    def test_public_visibility(self) -> None:
        assert extract_visibility_from_element({"visibility": "public"}) == Visibility.PUBLIC

    def test_private_visibility(self) -> None:
        assert extract_visibility_from_element({"visibility": "private"}) == Visibility.PRIVATE

    def test_protected_visibility(self) -> None:
        assert extract_visibility_from_element({"visibility": "protected"}) == Visibility.PROTECTED

    def test_internal_visibility_maps_to_package(self) -> None:
        assert extract_visibility_from_element({"visibility": "internal"}) == Visibility.PACKAGE

    def test_empty_visibility_defaults_to_public(self) -> None:
        assert extract_visibility_from_element({}) == Visibility.PUBLIC

    def test_unknown_visibility_defaults_to_public(self) -> None:
        assert extract_visibility_from_element({"visibility": "unknown"}) == Visibility.PUBLIC

    def test_case_insensitive_visibility(self) -> None:
        assert extract_visibility_from_element({"visibility": "PUBLIC"}) == Visibility.PUBLIC
        assert extract_visibility_from_element({"visibility": "Private"}) == Visibility.PRIVATE

    def test_object_with_visibility_attribute(self) -> None:
        class FakeElement:
            visibility = "protected"

        assert extract_visibility_from_element(FakeElement()) == Visibility.PROTECTED


class TestRiskScoring:
    """Test the composite risk score computation."""

    def test_no_callers_private_is_safe(self) -> None:
        report = analyze_semantic_impact(
            symbol="helper",
            caller_count=0,
            profile=SymbolProfile(
                name="helper",
                file_path="test.py",
                language="python",
                visibility=Visibility.PRIVATE,
            ),
        )
        assert report.risk_level == SemanticRiskLevel.SAFE
        assert report.risk_score < 20

    def test_many_callers_public_is_high(self) -> None:
        report = analyze_semantic_impact(
            symbol="processPayment",
            caller_count=50,
            profile=SymbolProfile(
                name="processPayment",
                file_path="PaymentService.java",
                language="java",
                visibility=Visibility.PUBLIC,
            ),
        )
        assert report.risk_level in (SemanticRiskLevel.HIGH, SemanticRiskLevel.CRITICAL)
        assert report.risk_score >= 60

    def test_base_class_change_is_high(self) -> None:
        report = analyze_semantic_impact(
            symbol="BaseService",
            caller_count=10,
            profile=SymbolProfile(
                name="BaseService",
                file_path="BaseService.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_abstract=True,
            ),
        )
        assert report.is_type_hierarchy_root is True
        assert report.risk_level in (
            SemanticRiskLevel.HIGH,
            SemanticRiskLevel.CRITICAL,
            SemanticRiskLevel.MODERATE,
        )
        assert "Base class" in " ".join(report.factors)

    def test_interface_member_high_impact(self) -> None:
        report = analyze_semantic_impact(
            symbol="execute",
            caller_count=15,
            profile=SymbolProfile(
                name="execute",
                file_path="ICommand.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_interface_member=True,
            ),
        )
        assert report.risk_score >= 40
        # Interface members are detected as type hierarchy roots (no base classes)
        # so they trigger the "Base class" factor
        assert any(
            "interface" in f.lower() or "base class" in f.lower() or "implementation" in f.lower()
            for f in report.factors
        )

    def test_static_member_gets_bonus(self) -> None:
        report_static = analyze_semantic_impact(
            symbol="getInstance",
            caller_count=10,
            profile=SymbolProfile(
                name="getInstance",
                file_path="Config.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_static=True,
            ),
        )
        report_instance = analyze_semantic_impact(
            symbol="getValue",
            caller_count=10,
            profile=SymbolProfile(
                name="getValue",
                file_path="Config.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_static=False,
            ),
        )
        assert report_static.risk_score > report_instance.risk_score

    def test_constructor_higher_than_method(self) -> None:
        report_ctor = analyze_semantic_impact(
            symbol="__init__",
            caller_count=10,
            profile=SymbolProfile(
                name="__init__",
                file_path="app.py",
                language="python",
                visibility=Visibility.PUBLIC,
                is_constructor=True,
            ),
        )
        report_method = analyze_semantic_impact(
            symbol="process",
            caller_count=10,
            profile=SymbolProfile(
                name="process",
                file_path="app.py",
                language="python",
                visibility=Visibility.PUBLIC,
                is_constructor=False,
            ),
        )
        assert report_ctor.risk_score > report_method.risk_score

    def test_deep_call_chain_adds_risk(self) -> None:
        report = analyze_semantic_impact(
            symbol="handleRequest",
            caller_count=5,
            call_chain_depth=5,
            profile=SymbolProfile(
                name="handleRequest",
                file_path="handler.py",
                language="python",
                visibility=Visibility.PUBLIC,
            ),
        )
        assert any("Deep call chain" in f for f in report.factors)

    def test_framework_annotations_add_risk(self) -> None:
        report = analyze_semantic_impact(
            symbol="getUser",
            caller_count=3,
            profile=SymbolProfile(
                name="getUser",
                file_path="UserController.java",
                language="java",
                visibility=Visibility.PUBLIC,
                annotations=("GetMapping", "ApiOperation"),
            ),
        )
        assert any("Framework" in f for f in report.factors)


class TestRiskLevelClassification:
    """Test risk level boundary conditions."""

    def test_safe_threshold(self) -> None:
        report = analyze_semantic_impact(
            symbol="local_var",
            caller_count=0,
            profile=SymbolProfile(
                name="local_var",
                file_path="test.py",
                language="python",
                visibility=Visibility.PRIVATE,
            ),
        )
        assert report.risk_level == SemanticRiskLevel.SAFE

    def test_low_threshold(self) -> None:
        report = analyze_semantic_impact(
            symbol="helper",
            caller_count=2,
            profile=SymbolProfile(
                name="helper",
                file_path="test.py",
                language="python",
                visibility=Visibility.PACKAGE,
            ),
        )
        # Should be LOW or SAFE (low callers, package visibility)
        assert report.risk_level in (SemanticRiskLevel.SAFE, SemanticRiskLevel.LOW)

    def test_moderate_threshold(self) -> None:
        report = analyze_semantic_impact(
            symbol="processData",
            caller_count=10,
            profile=SymbolProfile(
                name="processData",
                file_path="service.py",
                language="python",
                visibility=Visibility.PUBLIC,
            ),
        )
        assert report.risk_level in (
            SemanticRiskLevel.LOW,
            SemanticRiskLevel.MODERATE,
            SemanticRiskLevel.HIGH,
        )

    def test_score_capped_at_100(self) -> None:
        report = analyze_semantic_impact(
            symbol="mega_api",
            caller_count=1000,
            call_chain_depth=10,
            profile=SymbolProfile(
                name="mega_api",
                file_path="core.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_abstract=True,
                is_static=True,
                is_constructor=True,
                annotations=("GetMapping", "PostMapping", "Autowired"),
            ),
        )
        assert report.risk_score <= 100
        assert report.risk_level == SemanticRiskLevel.CRITICAL


class TestSymbolProfileBuilding:
    """Test building profiles from analysis elements."""

    def test_build_from_dict(self) -> None:
        element = {
            "name": "calculateTotal",
            "visibility": "public",
            "element_type": "method",
            "is_abstract": False,
            "is_static": True,
            "annotations": ["Override"],
        }
        profile = build_symbol_profile(element, "Cart.java", "java")
        assert profile.name == "calculateTotal"
        assert profile.visibility == Visibility.PUBLIC
        assert profile.is_static is True
        assert profile.annotations == ("Override",)

    def test_constructor_detection_python(self) -> None:
        element = {"name": "__init__", "visibility": "public"}
        profile = build_symbol_profile(element, "app.py", "python")
        assert profile.is_constructor is True

    def test_constructor_detection_java(self) -> None:
        element = {"name": "<init>", "visibility": "public"}
        profile = build_symbol_profile(element, "App.java", "java")
        assert profile.is_constructor is True

    def test_interface_member_detection(self) -> None:
        element = {"name": "execute", "element_type": "interface_method"}
        profile = build_symbol_profile(element, "ICommand.java", "java")
        assert profile.is_interface_member is True

    def test_base_classes_extraction(self) -> None:
        element = {"name": "Dog", "base_classes": ["Animal", "Comparable"]}
        profile = build_symbol_profile(element, "Dog.java", "java")
        assert profile.base_classes == ("Animal", "Comparable")


class TestSuggestionGeneration:
    """Test that appropriate suggestions are generated."""

    def test_safe_change_suggestion(self) -> None:
        report = analyze_semantic_impact(
            symbol="local_helper",
            caller_count=0,
            profile=SymbolProfile(
                name="local_helper",
                file_path="test.py",
                language="python",
                visibility=Visibility.PRIVATE,
            ),
        )
        assert any("Safe" in s for s in report.suggestions)

    def test_base_class_suggestion(self) -> None:
        report = analyze_semantic_impact(
            symbol="AbstractService",
            caller_count=5,
            profile=SymbolProfile(
                name="AbstractService",
                file_path="AbstractService.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_abstract=True,
            ),
        )
        assert any("base class" in s.lower() or "subclasses" in s.lower() for s in report.suggestions)

    def test_high_impact_deprecation_suggestion(self) -> None:
        report = analyze_semantic_impact(
            symbol="oldApi",
            caller_count=100,
            call_chain_depth=3,
            profile=SymbolProfile(
                name="oldApi",
                file_path="api.py",
                language="python",
                visibility=Visibility.PUBLIC,
                is_abstract=True,
            ),
        )
        assert report.risk_level in (SemanticRiskLevel.HIGH, SemanticRiskLevel.CRITICAL), (
            f"Expected HIGH/CRITICAL, got {report.risk_level} (score={report.risk_score})"
        )
        assert any("deprecat" in s.lower() for s in report.suggestions)

    def test_deep_chain_suggestion(self) -> None:
        report = analyze_semantic_impact(
            symbol="deepMethod",
            caller_count=5,
            call_chain_depth=5,
            profile=SymbolProfile(
                name="deepMethod",
                file_path="service.py",
                language="python",
                visibility=Visibility.PUBLIC,
            ),
        )
        assert any("call chain" in s.lower() for s in report.suggestions)


class TestReportSerialization:
    """Test report to dict conversion."""

    def test_report_to_dict(self) -> None:
        report = analyze_semantic_impact(
            symbol="testMethod",
            caller_count=3,
            profile=SymbolProfile(
                name="testMethod",
                file_path="test.py",
                language="python",
                visibility=Visibility.PUBLIC,
            ),
        )
        d = report_to_dict(report)
        assert d["symbol"] == "testMethod"
        assert d["risk_level"] in ("safe", "low", "moderate", "high", "critical")
        assert isinstance(d["risk_score"], int)
        assert isinstance(d["factors"], list)
        assert isinstance(d["suggestions"], list)
        assert d["visibility"] == "public"

    def test_report_roundtrip(self) -> None:
        report = analyze_semantic_impact(
            symbol="processData",
            caller_count=10,
            call_chain_depth=3,
            profile=SymbolProfile(
                name="processData",
                file_path="service.py",
                language="python",
                visibility=Visibility.PUBLIC,
                is_abstract=True,
            ),
        )
        d = report_to_dict(report)

        # All fields should be present
        expected_keys = {
            "symbol", "risk_level", "risk_score", "factors",
            "caller_count", "visibility", "call_chain_depth",
            "is_type_hierarchy_root", "suggestions",
        }
        assert set(d.keys()) == expected_keys


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_none_profile(self) -> None:
        report = analyze_semantic_impact(
            symbol="unknown_method",
            caller_count=0,
        )
        assert report.symbol == "unknown_method"
        assert report.risk_level == SemanticRiskLevel.SAFE

    def test_zero_call_chain_depth(self) -> None:
        report = analyze_semantic_impact(
            symbol="standalone",
            caller_count=1,
            call_chain_depth=0,
        )
        assert report.call_chain_depth == 0

    def test_very_long_symbol_name(self) -> None:
        name = "a" * 500
        report = analyze_semantic_impact(symbol=name, caller_count=0)
        assert report.symbol == name

    def test_unicode_symbol_name(self) -> None:
        report = analyze_semantic_impact(symbol="処理する", caller_count=0)
        assert report.symbol == "処理する"

    def test_no_profile_with_file_path(self) -> None:
        report = analyze_semantic_impact(
            symbol="myFunc",
            file_path="test.py",
            caller_count=5,
        )
        assert report.symbol == "myFunc"
        # Should work without crashing even without full profile

    def test_multiple_factors_combined(self) -> None:
        """Multiple risk factors should all contribute."""
        report = analyze_semantic_impact(
            symbol="handleRequest",
            caller_count=30,
            call_chain_depth=6,
            profile=SymbolProfile(
                name="handleRequest",
                file_path="Controller.java",
                language="java",
                visibility=Visibility.PUBLIC,
                is_abstract=True,
                is_static=True,
                annotations=("PostMapping", "Autowired"),
            ),
        )
        assert report.risk_level in (SemanticRiskLevel.HIGH, SemanticRiskLevel.CRITICAL)
        assert len(report.factors) >= 3  # Multiple contributing factors
        assert report.risk_score >= 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
