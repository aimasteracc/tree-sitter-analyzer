#!/usr/bin/env python3
"""Unit tests for platform_compat compare module."""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.platform_compat.compare import (
    BehaviorDifference,
    ProfileComparison,
    generate_diff_report,
    load_profile_from_file,
)
from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile


class TestBehaviorDifference:
    """Tests for BehaviorDifference dataclass."""

    def test_instantiation(self) -> None:
        """BehaviorDifference can be instantiated with required fields."""
        diff = BehaviorDifference(
            construct_id="test_construct",
            diff_type="missing",
            details="Construct missing",
            platform_a_value="present",
            platform_b_value="missing",
        )
        assert diff.construct_id == "test_construct"
        assert diff.diff_type == "missing"
        assert diff.details == "Construct missing"
        assert diff.platform_a_value == "present"
        assert diff.platform_b_value == "missing"


class TestProfileComparison:
    """Tests for ProfileComparison dataclass."""

    def test_instantiation(self) -> None:
        """ProfileComparison can be instantiated."""
        comp = ProfileComparison(
            platform_a="windows-3.12",
            platform_b="linux-3.11",
            differences=[],
        )
        assert comp.platform_a == "windows-3.12"
        assert comp.platform_b == "linux-3.11"
        assert comp.differences == []

    def test_has_differences_false_when_empty(self) -> None:
        """has_differences is False when differences list is empty."""
        comp = ProfileComparison(
            platform_a="a",
            platform_b="b",
            differences=[],
        )
        assert comp.has_differences is False

    def test_has_differences_true_when_non_empty(self) -> None:
        """has_differences is True when differences list has items."""
        comp = ProfileComparison(
            platform_a="a",
            platform_b="b",
            differences=[
                BehaviorDifference(
                    construct_id="x",
                    diff_type="missing",
                    details="x",
                    platform_a_value=None,
                    platform_b_value=None,
                )
            ],
        )
        assert comp.has_differences is True


class TestGenerateDiffReport:
    """Tests for generate_diff_report function."""

    def test_no_differences(self) -> None:
        """Report states no differences when comparison has none."""
        comp = ProfileComparison(
            platform_a="win",
            platform_b="linux",
            differences=[],
        )
        report = generate_diff_report(comp)
        assert "No differences" in report
        assert "win" in report
        assert "linux" in report

    def test_with_differences(self) -> None:
        """Report includes each difference."""
        comp = ProfileComparison(
            platform_a="win",
            platform_b="linux",
            differences=[
                BehaviorDifference(
                    construct_id="construct_a",
                    diff_type="missing",
                    details="Missing in linux",
                    platform_a_value="present",
                    platform_b_value="missing",
                )
            ],
        )
        report = generate_diff_report(comp)
        assert "construct_a" in report
        assert "missing" in report
        assert "Total differences: 1" in report


class TestLoadProfileFromFile:
    """Tests for load_profile_from_file function."""

    def test_load_valid_profile(self) -> None:
        """Loads valid profile JSON from file."""
        profile_data = {
            "schema_version": "1.0.0",
            "platform_key": "windows-3.12",
            "behaviors": {
                "simple_table": {
                    "construct_id": "simple_table",
                    "node_type": "program",
                    "element_count": 1,
                    "attributes": ["col:id"],
                    "has_error": False,
                    "known_issues": [],
                }
            },
            "adaptation_rules": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(profile_data, f)
            path = Path(f.name)

        try:
            profile = load_profile_from_file(path)
            assert isinstance(profile, BehaviorProfile)
            assert profile.platform_key == "windows-3.12"
            assert "simple_table" in profile.behaviors
            assert profile.behaviors["simple_table"].construct_id == "simple_table"
        finally:
            path.unlink()

    def test_load_nonexistent_raises(self) -> None:
        """Raises FileNotFoundError for nonexistent path."""
        with pytest.raises(FileNotFoundError):
            load_profile_from_file(Path("/nonexistent/profile.json"))
