"""
Unit tests for change risk prediction.

Sprint 8: assess_change_risk() on CodeMapResult.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import ChangeRiskReport, ProjectCodeMap


@pytest.fixture
def cross_file_project():
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def result(cross_file_project):
    mapper = ProjectCodeMap()
    return mapper.scan(str(cross_file_project), extensions=[".py"])


class TestChangeRiskExists:
    """Test that assess_change_risk exists."""

    def test_method_exists(self, result):
        assert hasattr(result, "assess_change_risk")
        assert callable(result.assess_change_risk)

    def test_returns_report(self, result):
        report = result.assess_change_risk(changed_files=["models/user.py"])
        assert isinstance(report, ChangeRiskReport)

    def test_report_has_fields(self, result):
        report = result.assess_change_risk(changed_files=["models/user.py"])
        assert hasattr(report, "risk_level")
        assert hasattr(report, "affected_files")
        assert hasattr(report, "affected_symbols")
        assert hasattr(report, "reasons")


class TestChangeRiskLevels:
    """Test risk level calculation."""

    def test_risk_level_values(self, result):
        """Risk level should be one of: low, medium, high, critical."""
        report = result.assess_change_risk(changed_files=["models/user.py"])
        assert report.risk_level in {"low", "medium", "high", "critical"}

    def test_nonexistent_file_low_risk(self, result):
        """Files not in project should result in low risk."""
        report = result.assess_change_risk(changed_files=["does_not_exist.py"])
        assert report.risk_level == "low"


class TestChangeRiskToon:
    """Test TOON output."""

    def test_report_to_toon(self, result):
        report = result.assess_change_risk(changed_files=["models/user.py"])
        toon = report.to_toon()
        assert isinstance(toon, str)
        assert "RISK" in toon.upper() or "risk" in toon.lower()


class TestMcpChangeRiskAction:
    """Test MCP tool exposure."""

    def test_change_risk_action(self):
        from tree_sitter_analyzer_v2.mcp.tools.intelligence import _VALID_ACTIONS
        assert "change_risk" in _VALID_ACTIONS
