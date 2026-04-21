"""Risk scoring engine for project radar.

This module provides functionality to calculate unified risk scores by combining:
- Complexity scores (from cognitive_complexity)
- Churn metrics (from git_analyzer)
- Impact scores (from semantic_impact)
"""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter_analyzer.analyzer.git_analyzer import FileChurn, FileOwnership

__all__ = ["FileRisk", "RiskScore"]


@dataclass(frozen=True)
class RiskScore:
    """Individual risk metric for a file."""

    complexity_score: float  # 0-1, normalized complexity
    churn_score: float  # 0-1, normalized commit frequency
    impact_score: float  # 0-1, normalized blast radius
    weight: float  # Weight for this metric in overall calculation


@dataclass(frozen=True)
class FileRisk:
    """Unified risk assessment for a single file."""

    path: str
    complexity_score: float  # 0-1
    churn_score: float  # 0-1
    impact_score: float  # 0-1
    overall_risk: float  # 0-1, weighted average

    # Optional context
    ownership: FileOwnership | None = None
    churn: FileChurn | None = None


class RiskCalculator:
    """Calculate unified risk scores for files."""

    # Default weights for risk calculation (sum to 1.0)
    DEFAULT_WEIGHTS: dict[str, float] = {
        "complexity": 0.3,
        "churn": 0.3,
        "impact": 0.4,
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """Initialize the calculator with optional custom weights.

        Args:
            weights: Custom weights for complexity/churn/impact.
                     Must sum to 1.0. Defaults to equal weights.
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        if abs(sum(self.weights.values()) - 1.0) > 0.01:
            msg = f"Weights must sum to 1.0, got {sum(self.weights.values())}"
            raise ValueError(msg)

    def normalize_complexity(
        self, complexity_values: dict[str, float]
    ) -> dict[str, float]:
        """Normalize complexity scores to 0-1 range using min-max scaling.

        Args:
            complexity_values: Dictionary mapping file paths to raw complexity scores.

        Returns:
            Dictionary mapping file paths to normalized complexity scores (0-1).
        """
        if not complexity_values:
            return {}

        values = list(complexity_values.values())
        min_val = min(values)
        max_val = max(values)

        # Avoid division by zero
        if max_val == min_val:
            return dict.fromkeys(complexity_values, 0.5)

        return {
            path: (value - min_val) / (max_val - min_val)
            for path, value in complexity_values.items()
        }

    def normalize_churn(self, churn_data: dict[str, FileChurn]) -> dict[str, float]:
        """Normalize churn metrics to 0-1 range using min-max scaling.

        Args:
            churn_data: Dictionary mapping file paths to FileChurn objects.

        Returns:
            Dictionary mapping file paths to normalized churn scores (0-1).
        """
        if not churn_data:
            return {}

        # Use commit count for normalization
        commit_counts: dict[str, float] = {
            path: float(data.commit_count) for path, data in churn_data.items()
        }
        return self._normalize_values(commit_counts)

    def normalize_impact(
        self, impact_values: dict[str, float]
    ) -> dict[str, float]:
        """Normalize impact scores to 0-1 range using min-max scaling.

        Args:
            impact_values: Dictionary mapping file paths to raw impact scores.

        Returns:
            Dictionary mapping file paths to normalized impact scores (0-1).
        """
        if not impact_values:
            return {}

        return self._normalize_values(impact_values)

    def _normalize_values(self, values: dict[str, float]) -> dict[str, float]:
        """Internal helper for min-max normalization.

        Args:
            values: Dictionary mapping file paths to raw values.

        Returns:
            Dictionary mapping file paths to normalized values (0-1).
        """
        nums = list(values.values())
        min_val = min(nums)
        max_val = max(nums)

        if max_val == min_val:
            return dict.fromkeys(values, 0.5)

        return {
            path: (value - min_val) / (max_val - min_val) for path, value in values.items()
        }

    def calculate_file_risk(
        self,
        path: str,
        complexity_score: float,
        churn_score: float,
        impact_score: float,
        ownership: FileOwnership | None = None,
        churn: FileChurn | None = None,
    ) -> FileRisk:
        """Calculate unified risk score for a single file.

        Args:
            path: File path.
            complexity_score: Normalized complexity score (0-1).
            churn_score: Normalized churn score (0-1).
            impact_score: Normalized impact score (0-1).
            ownership: Optional file ownership data.
            churn: Optional file churn data.

        Returns:
            FileRisk object with unified risk score.
        """
        # Calculate weighted average
        overall = (
            complexity_score * self.weights["complexity"]
            + churn_score * self.weights["churn"]
            + impact_score * self.weights["impact"]
        )

        return FileRisk(
            path=path,
            complexity_score=complexity_score,
            churn_score=churn_score,
            impact_score=impact_score,
            overall_risk=overall,
            ownership=ownership,
            churn=churn,
        )

    def calculate_batch_risk(
        self,
        complexity_scores: dict[str, float],
        churn_data: dict[str, FileChurn],
        impact_scores: dict[str, float],
        ownership_data: dict[str, FileOwnership] | None = None,
    ) -> list[FileRisk]:
        """Calculate unified risk scores for multiple files.

        Args:
            complexity_scores: Raw complexity scores per file.
            churn_data: FileChurn objects per file.
            impact_scores: Raw impact scores per file.
            ownership_data: Optional FileOwnership objects per file.

        Returns:
            List of FileRisk objects sorted by overall risk (descending).
        """
        # Normalize all metrics
        norm_complexity = self.normalize_complexity(complexity_scores)
        norm_churn = self.normalize_churn(churn_data)
        norm_impact = self.normalize_impact(impact_scores)

        # Get all unique file paths
        all_paths = set(norm_complexity) | set(norm_churn) | set(norm_impact)

        risks: list[FileRisk] = []
        for path in all_paths:
            comp = norm_complexity.get(path, 0.0)
            chn = norm_churn.get(path, 0.0)
            imp = norm_impact.get(path, 0.0)
            owner = ownership_data.get(path) if ownership_data else None
            churn_obj = churn_data.get(path)

            risk = self.calculate_file_risk(path, comp, chn, imp, owner, churn_obj)
            risks.append(risk)

        # Sort by overall risk (descending)
        return sorted(risks, key=lambda r: r.overall_risk, reverse=True)

    def get_top_risky_files(
        self,
        risks: list[FileRisk],
        n: int = 20,
    ) -> list[FileRisk]:
        """Get the top N riskiest files.

        Args:
            risks: List of FileRisk objects (should be pre-sorted).
            n: Number of files to return.

        Returns:
            List of top N riskiest files.
        """
        return risks[:n]
