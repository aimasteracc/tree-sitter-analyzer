"""Tests for risk_scoring module."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.analyzer.git_analyzer import FileChurn, FileOwnership
from tree_sitter_analyzer.analyzer.risk_scoring import (
    FileRisk,
    RiskCalculator,
    RiskScore,
)


@pytest.fixture
def sample_churn() -> dict[str, FileChurn]:
    """Sample file churn data."""
    return {
        "high_churn.py": FileChurn(
            path="high_churn.py",
            commit_count=100,
            first_commit_date="2024-01-01",
            last_commit_date="2024-12-31",
            authors=[("dev@example.com", 100)],
        ),
        "low_churn.py": FileChurn(
            path="low_churn.py",
            commit_count=5,
            first_commit_date="2024-01-01",
            last_commit_date="2024-02-01",
            authors=[("dev@example.com", 5)],
        ),
        "medium_churn.py": FileChurn(
            path="medium_churn.py",
            commit_count=50,
            first_commit_date="2024-01-01",
            last_commit_date="2024-06-30",
            authors=[("dev@example.com", 50)],
        ),
    }


@pytest.fixture
def sample_ownership() -> dict[str, FileOwnership]:
    """Sample file ownership data."""
    return {
        "high_churn.py": FileOwnership(
            path="high_churn.py",
            top_contributor="dev@example.com",
            top_contributor_count=100,
            total_commits=100,
            ownership_percentage=100.0,
        ),
        "low_churn.py": FileOwnership(
            path="low_churn.py",
            top_contributor="dev2@example.com",
            top_contributor_count=5,
            total_commits=5,
            ownership_percentage=100.0,
        ),
    }


@pytest.fixture
def sample_complexity() -> dict[str, float]:
    """Sample complexity scores."""
    return {
        "complex.py": 100.0,
        "simple.py": 10.0,
        "medium.py": 50.0,
        "high_churn.py": 80.0,
        "low_churn.py": 20.0,
    }


@pytest.fixture
def sample_impact() -> dict[str, float]:
    """Sample impact scores."""
    return {
        "high_impact.py": 1000.0,
        "low_impact.py": 10.0,
        "medium_impact.py": 500.0,
        "high_churn.py": 800.0,
        "low_churn.py": 100.0,
    }


def test_risk_calculator_init_default() -> None:
    """Test RiskCalculator initialization with default weights."""
    calc = RiskCalculator()
    assert calc.weights["complexity"] == 0.3
    assert calc.weights["churn"] == 0.3
    assert calc.weights["impact"] == 0.4


def test_risk_calculator_init_custom_weights() -> None:
    """Test RiskCalculator initialization with custom weights."""
    calc = RiskCalculator(weights={"complexity": 0.5, "churn": 0.3, "impact": 0.2})
    assert calc.weights["complexity"] == 0.5
    assert calc.weights["churn"] == 0.3
    assert calc.weights["impact"] == 0.2


def test_risk_calculator_init_invalid_weights() -> None:
    """Test RiskCalculator initialization with invalid weights."""
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        RiskCalculator(weights={"complexity": 0.5, "churn": 0.3, "impact": 0.1})


def test_normalize_complexity(sample_complexity: dict[str, float]) -> None:
    """Test complexity score normalization."""
    calc = RiskCalculator()
    normalized = calc.normalize_complexity(sample_complexity)

    # Check all values are in 0-1 range
    assert all(0 <= v <= 1 for v in normalized.values())

    # Highest value should be 1.0
    assert normalized["complex.py"] == 1.0

    # Lowest value should be 0.0
    assert normalized["simple.py"] == 0.0

    # Middle value should be around 0.44 (50-10)/(100-10)
    assert abs(normalized["medium.py"] - 0.444) < 0.01


def test_normalize_complexity_empty() -> None:
    """Test complexity normalization with empty input."""
    calc = RiskCalculator()
    assert calc.normalize_complexity({}) == {}


def test_normalize_complexity_single_value() -> None:
    """Test complexity normalization with single value."""
    calc = RiskCalculator()
    result = calc.normalize_complexity({"only.py": 50.0})
    # Single value should be normalized to 0.5
    assert result["only.py"] == 0.5


def test_normalize_churn(sample_churn: dict[str, FileChurn]) -> None:
    """Test churn score normalization."""
    calc = RiskCalculator()
    normalized = calc.normalize_churn(sample_churn)

    # Check all values are in 0-1 range
    assert all(0 <= v <= 1 for v in normalized.values())

    # High churn (100 commits) should be 1.0
    assert normalized["high_churn.py"] == 1.0

    # Low churn (5 commits) should be 0.0
    assert normalized["low_churn.py"] == 0.0

    # Medium churn (50 commits) should be 0.4747
    assert abs(normalized["medium_churn.py"] - 0.474) < 0.01


def test_normalize_churn_empty() -> None:
    """Test churn normalization with empty input."""
    calc = RiskCalculator()
    assert calc.normalize_churn({}) == {}


def test_normalize_impact(sample_impact: dict[str, float]) -> None:
    """Test impact score normalization."""
    calc = RiskCalculator()
    normalized = calc.normalize_impact(sample_impact)

    # Check all values are in 0-1 range
    assert all(0 <= v <= 1 for v in normalized.values())

    # High impact should be 1.0
    assert normalized["high_impact.py"] == 1.0

    # Low impact should be 0.0
    assert normalized["low_impact.py"] == 0.0


def test_normalize_impact_empty() -> None:
    """Test impact normalization with empty input."""
    calc = RiskCalculator()
    assert calc.normalize_impact({}) == {}


def test_calculate_file_risk_basic() -> None:
    """Test single file risk calculation."""
    calc = RiskCalculator()
    risk = calc.calculate_file_risk(
        path="test.py",
        complexity_score=0.8,
        churn_score=0.6,
        impact_score=0.9,
    )

    assert risk.path == "test.py"
    assert risk.complexity_score == 0.8
    assert risk.churn_score == 0.6
    assert risk.impact_score == 0.9
    # Weighted: 0.8*0.3 + 0.6*0.3 + 0.9*0.4 = 0.24 + 0.18 + 0.36 = 0.78
    assert abs(risk.overall_risk - 0.78) < 0.01


def test_calculate_file_risk_with_context(
    sample_churn: dict[str, FileChurn], sample_ownership: dict[str, FileOwnership]
) -> None:
    """Test file risk calculation with ownership and churn context."""
    calc = RiskCalculator()
    risk = calc.calculate_file_risk(
        path="high_churn.py",
        complexity_score=0.5,
        churn_score=1.0,
        impact_score=0.8,
        ownership=sample_ownership["high_churn.py"],
        churn=sample_churn["high_churn.py"],
    )

    assert risk.path == "high_churn.py"
    assert risk.ownership is not None
    assert risk.ownership.top_contributor == "dev@example.com"
    assert risk.churn is not None
    assert risk.churn.commit_count == 100


def test_calculate_batch_risk(
    sample_complexity: dict[str, float],
    sample_churn: dict[str, FileChurn],
    sample_impact: dict[str, float],
    sample_ownership: dict[str, FileOwnership],
) -> None:
    """Test batch risk calculation."""
    calc = RiskCalculator()
    risks = calc.calculate_batch_risk(
        complexity_scores=sample_complexity,
        churn_data=sample_churn,
        impact_scores=sample_impact,
        ownership_data=sample_ownership,
    )

    # Should return list of FileRisk objects
    assert len(risks) > 0
    assert all(isinstance(r, FileRisk) for r in risks)

    # Should be sorted by overall risk (descending)
    for i in range(len(risks) - 1):
        assert risks[i].overall_risk >= risks[i + 1].overall_risk

    # Check that files with all three metrics are included
    paths = [r.path for r in risks]
    assert "high_churn.py" in paths
    assert "low_churn.py" in paths


def test_calculate_batch_risk_no_ownership(
    sample_complexity: dict[str, float],
    sample_churn: dict[str, FileChurn],
    sample_impact: dict[str, float],
) -> None:
    """Test batch risk calculation without ownership data."""
    calc = RiskCalculator()
    risks = calc.calculate_batch_risk(
        complexity_scores=sample_complexity,
        churn_data=sample_churn,
        impact_scores=sample_impact,
    )

    assert len(risks) > 0
    # ownership should be None for all files
    assert all(r.ownership is None for r in risks)


def test_calculate_batch_risk_custom_weights(
    sample_complexity: dict[str, float],
    sample_churn: dict[str, FileChurn],
    sample_impact: dict[str, float],
) -> None:
    """Test batch risk calculation with custom weights."""
    calc = RiskCalculator(weights={"complexity": 0.5, "churn": 0.4, "impact": 0.1})
    risks = calc.calculate_batch_risk(
        complexity_scores=sample_complexity,
        churn_data=sample_churn,
        impact_scores=sample_impact,
    )

    # High complexity file should rank higher with these weights
    paths = [r.path for r in risks]
    assert "complex.py" in paths


def test_get_top_risky_files(
    sample_complexity: dict[str, float],
    sample_churn: dict[str, FileChurn],
    sample_impact: dict[str, float],
) -> None:
    """Test getting top N risky files."""
    calc = RiskCalculator()
    risks = calc.calculate_batch_risk(
        complexity_scores=sample_complexity,
        churn_data=sample_churn,
        impact_scores=sample_impact,
    )

    top_2 = calc.get_top_risky_files(risks, n=2)
    assert len(top_2) == 2
    assert top_2[0].overall_risk >= top_2[1].overall_risk

    top_5 = calc.get_top_risky_files(risks, n=5)
    assert len(top_5) == min(5, len(risks))


def test_get_top_risky_files_n_larger_than_list(
    sample_complexity: dict[str, float],
    sample_churn: dict[str, FileChurn],
    sample_impact: dict[str, float],
) -> None:
    """Test getting top N when N is larger than the list."""
    calc = RiskCalculator()
    risks = calc.calculate_batch_risk(
        complexity_scores=sample_complexity,
        churn_data=sample_churn,
        impact_scores=sample_impact,
    )

    top_100 = calc.get_top_risky_files(risks, n=100)
    assert len(top_100) == len(risks)


def test_file_risk_immutability() -> None:
    """Test that FileRisk is frozen/immutable."""
    calc = RiskCalculator()
    risk = calc.calculate_file_risk(
        path="test.py",
        complexity_score=0.5,
        churn_score=0.5,
        impact_score=0.5,
    )

    with pytest.raises(Exception):  # FrozenInstanceError
        risk.overall_risk = 0.99


def test_file_risk_dataclass_fields() -> None:
    """Test FileRisk dataclass has all expected fields."""
    calc = RiskCalculator()
    risk = calc.calculate_file_risk(
        path="test.py",
        complexity_score=0.5,
        churn_score=0.5,
        impact_score=0.5,
    )

    assert risk.path == "test.py"
    assert risk.complexity_score == 0.5
    assert risk.churn_score == 0.5
    assert risk.impact_score == 0.5
    assert risk.ownership is None
    assert risk.churn is None


def test_risk_score_dataclass() -> None:
    """Test RiskScore dataclass."""
    score = RiskScore(
        complexity_score=0.5,
        churn_score=0.6,
        impact_score=0.7,
        weight=1.0,
    )

    assert score.complexity_score == 0.5
    assert score.churn_score == 0.6
    assert score.impact_score == 0.7
    assert score.weight == 1.0
