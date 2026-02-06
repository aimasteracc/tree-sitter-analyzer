"""
Layer 3 generator - 30-minute deep understanding.

Provides performance analysis, tech debt reports, refactoring suggestions,
and project health scoring.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from tree_sitter_analyzer_v2.features.instant_understanding.models import Layer3DeepInsights

logger = logging.getLogger(__name__)


class Layer3Generator:
    """Generates the 30-minute deep understanding layer."""

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def generate(self, results: Dict[str, Any]) -> Layer3DeepInsights:
        """Generate 30-minute deep understanding layer."""
        logger.info("Generating Layer 3 (30-minute insights)...")

        performance_analysis = self._build_performance_analysis(results)
        tech_debt_report = self._build_tech_debt_report(results)
        refactoring_suggestions = self._build_refactoring_suggestions(results)
        learning_path = self._generate_learning_path()
        health_score = self._calculate_health_score(results)

        return Layer3DeepInsights(
            performance_analysis=performance_analysis,
            tech_debt_report=tech_debt_report,
            refactoring_suggestions=refactoring_suggestions,
            learning_path=learning_path,
            health_score=health_score,
        )

    def _build_performance_analysis(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Build performance analysis section."""
        perf_hotspots = results.get("performance", [])
        return {
            "total_hotspots": len(perf_hotspots),
            "top_5": [
                {
                    "function": h.function,
                    "file": h.file,
                    "complexity": h.complexity,
                    "score": h.hotspot_score,
                    "recommendation": h.recommendation,
                }
                for h in perf_hotspots[:5]
            ],
        }

    def _build_tech_debt_report(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Build tech debt report section."""
        all_debts = results.get("tech_debt", [])
        report: Dict[str, Any] = {
            "total_count": len(all_debts),
            "by_severity": {
                "high": len([d for d in all_debts if d.severity == "high"]),
                "medium": len([d for d in all_debts if d.severity == "medium"]),
                "low": len([d for d in all_debts if d.severity == "low"]),
            },
            "by_type": {},
            "estimated_fix_hours": sum(d.estimated_fix_time for d in all_debts) / 60,
        }

        for debt in all_debts:
            debt_type = debt.debt_type.value
            report["by_type"][debt_type] = report["by_type"].get(debt_type, 0) + 1

        return report

    def _build_refactoring_suggestions(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build refactoring suggestions section."""
        knowledge = results.get("knowledge", {})
        hotspots = knowledge.get("hotspots", []) if knowledge else []

        return [
            {
                "function": h.get("function", ""),
                "file": h.get("file", ""),
                "reason": f"High impact ({h.get('called_by_count', 0)} callers)",
                "priority": h.get("impact_level", "low"),
            }
            for h in hotspots[:5]
            if h.get("impact_level") in ["high", "medium"]
        ]

    def _generate_learning_path(self) -> List[str]:
        """Generate recommended learning path."""
        learning_path = []

        if (self.project_path / "core" / "types.py").exists():
            learning_path.append("core/types.py - Data structures")
        if (self.project_path / "core" / "protocols.py").exists():
            learning_path.append("core/protocols.py - Interfaces")
        if (self.project_path / "core" / "parser.py").exists():
            learning_path.append("core/parser.py - Parser implementation")

        features_path = self.project_path / "features"
        if features_path.exists():
            for feature_file in sorted(features_path.glob("*.py")):
                if feature_file.name != "__init__.py":
                    learning_path.append(f"features/{feature_file.name} - Feature modules")
                    if len(learning_path) >= 5:
                        break

        if (self.project_path / "api" / "interface.py").exists():
            learning_path.append("api/interface.py - Public API")
        if (self.project_path / "cli" / "main.py").exists():
            learning_path.append("cli/main.py - CLI interface")

        return learning_path

    def _calculate_health_score(self, results: Dict[str, Any]) -> float:
        """Calculate project health score (0-100)."""
        score = 100.0

        all_debts = results.get("tech_debt", [])
        high_debts = len([d for d in all_debts if d.severity == "high"])
        medium_debts = len([d for d in all_debts if d.severity == "medium"])

        score -= high_debts * 5
        score -= medium_debts * 2

        perf_hotspots = results.get("performance", [])
        critical_hotspots = len([h for h in perf_hotspots if h.complexity > 15])
        score -= critical_hotspots * 3

        return max(0.0, min(100.0, score))
