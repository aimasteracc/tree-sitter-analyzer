"""
Main engine for Instant Project Understanding.

Orchestrates data collection from all analyzers and coordinates
layer generation.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tree_sitter_analyzer_v2.features.project_knowledge import ProjectKnowledgeEngine
from tree_sitter_analyzer_v2.features.refactoring_analyzer import RefactoringAnalyzer
from tree_sitter_analyzer_v2.features.performance_analyzer import PerformanceAnalyzer
from tree_sitter_analyzer_v2.features.tech_debt_tracker import TechDebtAnalyzer

from tree_sitter_analyzer_v2.features.instant_understanding.models import (
    UnderstandingReport,
)
from tree_sitter_analyzer_v2.features.instant_understanding.layer1 import Layer1Generator
from tree_sitter_analyzer_v2.features.instant_understanding.layer2 import Layer2Generator
from tree_sitter_analyzer_v2.features.instant_understanding.layer3 import Layer3Generator
from tree_sitter_analyzer_v2.features.instant_understanding.mermaid import MermaidGenerator
from tree_sitter_analyzer_v2.features.instant_understanding.output import (
    ReportFormatter,
    save_report,
)

logger = logging.getLogger(__name__)


class InstantUnderstandingEngine:
    """
    Instant Project Understanding Engine.

    Combines multiple analyzers to generate layered understanding reports.
    Pure data processing - no AI/LLM required.

    Usage:
        engine = InstantUnderstandingEngine(Path("./project"))
        report = engine.analyze()
        engine.save_report(report, Path("understanding.md"))
    """

    def __init__(self, project_path: Path, language: str = "python"):
        """
        Initialize the understanding engine.

        Args:
            project_path: Path to the project to analyze
            language: Primary language (default: python)
        """
        self.project_path = Path(project_path).resolve()
        self.language = language

        logger.info(f"Initializing InstantUnderstandingEngine for {self.project_path}")

        # Initialize analyzers
        self.knowledge_engine = ProjectKnowledgeEngine(self.project_path)
        self.refactoring_analyzer = RefactoringAnalyzer(max_depth=10)
        self.performance_analyzer = PerformanceAnalyzer()
        self.tech_debt_analyzer = TechDebtAnalyzer()

        # Initialize layer generators
        self._layer1_gen = Layer1Generator(self.project_path)
        self._layer2_gen = Layer2Generator(self.project_path)
        self._layer3_gen = Layer3Generator(self.project_path)
        self._mermaid_gen = MermaidGenerator(self.project_path)
        self._formatter = ReportFormatter()

    def analyze(self, force_rebuild: bool = False) -> UnderstandingReport:
        """
        Perform complete analysis and generate understanding report.

        Args:
            force_rebuild: Force rebuild all caches

        Returns:
            UnderstandingReport with 3 layers
        """
        logger.info("Starting instant understanding analysis...")

        # Step 1: Collect data from all analyzers
        analysis_results = self._collect_analysis_data(force_rebuild)

        # Step 2: Generate 3 layers
        layer1 = self._layer1_gen.generate(analysis_results)
        layer2 = self._layer2_gen.generate(analysis_results)
        layer3 = self._layer3_gen.generate(analysis_results)

        # Step 3: Generate Mermaid diagrams
        mermaid_diagrams = self._mermaid_gen.generate_all(analysis_results)

        report = UnderstandingReport(
            layer1=layer1,
            layer2=layer2,
            layer3=layer3,
            mermaid_diagrams=mermaid_diagrams,
        )

        logger.info("Analysis complete!")
        return report

    def _collect_analysis_data(self, force_rebuild: bool) -> Dict[str, Any]:
        """Collect data from all analyzers."""
        logger.info("Collecting data from analyzers...")

        results: Dict[str, Any] = {}

        # 1. Project Knowledge
        results["knowledge"] = self._collect_knowledge_data(force_rebuild)

        # 2. Performance Analysis
        results["performance"] = self._collect_performance_data()

        # 3. Tech Debt Analysis
        results["tech_debt"] = self._collect_tech_debt_data()

        # 4. File statistics
        results["statistics"] = self._collect_statistics()

        return results

    def _collect_knowledge_data(self, force_rebuild: bool) -> Optional[Dict[str, Any]]:
        """Collect data from knowledge engine."""
        try:
            snapshot = self.knowledge_engine.build_snapshot(force=force_rebuild)
            hotspots = self.knowledge_engine.get_hotspots(top_n=20)
            logger.info("Knowledge engine: OK")
            return {"snapshot": snapshot, "hotspots": hotspots}
        except Exception as e:
            logger.error(f"Knowledge engine failed: {e}")
            return None

    def _collect_performance_data(self) -> list:
        """Collect data from performance analyzer."""
        try:
            perf_results = []
            for py_file in self.project_path.glob("**/*.py"):
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue
                try:
                    hotspots = self.performance_analyzer.analyze_file(py_file)
                    perf_results.extend(hotspots)
                except Exception:
                    continue

            perf_results.sort(key=lambda x: x.hotspot_score, reverse=True)
            logger.info(f"Performance analyzer: found {len(perf_results)} hotspots")
            return perf_results[:20]
        except Exception as e:
            logger.error(f"Performance analyzer failed: {e}")
            return []

    def _collect_tech_debt_data(self) -> list:
        """Collect data from tech debt analyzer."""
        try:
            all_debts = []
            for py_file in self.project_path.glob("**/*.py"):
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue
                try:
                    debts = self.tech_debt_analyzer.analyze_file(py_file)
                    all_debts.extend(debts)
                except Exception:
                    continue

            logger.info(f"Tech debt analyzer: found {len(all_debts)} debts")
            return all_debts
        except Exception as e:
            logger.error(f"Tech debt analyzer failed: {e}")
            return []

    def _collect_statistics(self) -> Dict[str, Any]:
        """Collect file statistics."""
        try:
            all_files = list(self.project_path.glob("**/*.py"))
            py_files = [f for f in all_files if "__pycache__" not in str(f)]

            total_lines = 0
            for py_file in py_files:
                try:
                    lines = py_file.read_text(encoding="utf-8", errors="ignore").count("\n")
                    total_lines += lines
                except Exception:
                    continue

            logger.info(f"Statistics: {len(py_files)} files, {total_lines} lines")
            return {
                "total_files": len(py_files),
                "total_lines": total_lines,
                "language": self.language,
            }
        except Exception as e:
            logger.error(f"Statistics collection failed: {e}")
            return {}

    def to_markdown(self, report: UnderstandingReport) -> str:
        """Convert report to Markdown format."""
        return self._formatter.to_markdown(report)

    def save_report(self, report: UnderstandingReport, output_path: Path) -> None:
        """Save understanding report to file."""
        save_report(report, output_path)

    # Delegate methods for backward compatibility with tests
    def _generate_layer1_overview(self, results: Dict[str, Any]) -> Any:
        """Delegate to Layer1Generator."""
        return self._layer1_gen.generate(results)

    def _generate_layer2_architecture(self, results: Dict[str, Any]) -> Any:
        """Delegate to Layer2Generator."""
        return self._layer2_gen.generate(results)

    def _generate_layer3_insights(self, results: Dict[str, Any]) -> Any:
        """Delegate to Layer3Generator."""
        return self._layer3_gen.generate(results)

    def _detect_tech_stack(self) -> Dict[str, Any]:
        """Delegate to Layer1Generator."""
        return self._layer1_gen._detect_tech_stack()

    def _find_entry_points(self) -> list:
        """Delegate to Layer1Generator."""
        return self._layer1_gen._find_entry_points()

    def _build_module_structure(self) -> Dict[str, Any]:
        """Delegate to Layer2Generator."""
        return self._layer2_gen._build_module_structure()

    def _detect_design_patterns(self) -> list:
        """Delegate to Layer2Generator."""
        return self._layer2_gen._detect_design_patterns()

    def _generate_hotspot_chart(self, hotspots: list) -> str:
        """Delegate to Layer2Generator."""
        return self._layer2_gen._generate_hotspot_chart(hotspots)

    def _describe_dependencies(self) -> str:
        """Delegate to Layer2Generator."""
        return self._layer2_gen._describe_dependencies()

    def _generate_learning_path(self) -> list:
        """Delegate to Layer3Generator."""
        return self._layer3_gen._generate_learning_path()

    def _calculate_health_score(self, results: Dict[str, Any]) -> float:
        """Delegate to Layer3Generator."""
        return self._layer3_gen._calculate_health_score(results)

    def _generate_architecture_mermaid(self) -> str:
        """Delegate to MermaidGenerator."""
        return self._mermaid_gen.generate_architecture()

    def _generate_call_graph_mermaid(self, hotspots: list) -> str:
        """Delegate to MermaidGenerator."""
        return self._mermaid_gen.generate_call_graph(hotspots)

    def _generate_performance_heatmap_mermaid(self, hotspots: list) -> str:
        """Delegate to MermaidGenerator."""
        return self._mermaid_gen.generate_performance_heatmap(hotspots)
