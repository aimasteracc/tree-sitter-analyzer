"""
Layer 2 generator - 15-minute architecture understanding.

Provides module structure, design pattern detection, and call graph analysis.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from tree_sitter_analyzer_v2.features.instant_understanding.models import Layer2Architecture

logger = logging.getLogger(__name__)


class Layer2Generator:
    """Generates the 15-minute architecture understanding layer."""

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def generate(self, results: Dict[str, Any]) -> Layer2Architecture:
        """Generate 15-minute architecture understanding layer."""
        logger.info("Generating Layer 2 (15-minute architecture)...")

        knowledge = results.get("knowledge", {})
        hotspots = knowledge.get("hotspots", []) if knowledge else []

        module_structure = self._build_module_structure()
        call_graph = {
            "total_functions": len(hotspots),
            "high_impact": len([h for h in hotspots if h.get("impact_level") == "high"]),
            "medium_impact": len([h for h in hotspots if h.get("impact_level") == "medium"]),
            "low_impact": len([h for h in hotspots if h.get("impact_level") == "low"]),
        }
        design_patterns = self._detect_design_patterns()
        hotspot_chart = self._generate_hotspot_chart(hotspots[:10])
        dependency_graph = self._describe_dependencies()

        return Layer2Architecture(
            module_structure=module_structure,
            call_graph=call_graph,
            design_patterns=design_patterns,
            hotspot_chart=hotspot_chart,
            dependency_graph=dependency_graph,
        )

    def _build_module_structure(self) -> Dict[str, Any]:
        """Build module structure overview."""
        modules: Dict[str, int] = {}

        for py_file in self.project_path.glob("**/*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                rel_path = py_file.relative_to(self.project_path)
                parts = rel_path.parts[:-1]
                if parts:
                    module_name = ".".join(parts)
                    modules[module_name] = modules.get(module_name, 0) + 1
            except Exception:
                continue

        return {"total_modules": len(modules), "modules": modules}

    def _detect_design_patterns(self) -> List[str]:
        """Detect design patterns using heuristics."""
        patterns = []

        # Check for Singleton
        for py_file in self.project_path.glob("**/*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "_instance" in content and "def __new__" in content:
                    patterns.append("Singleton")
                    break
            except Exception:
                continue

        # Check for Factory
        for py_file in self.project_path.glob("**/*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "Factory" in content and "def create_" in content:
                    patterns.append("Factory")
                    break
            except Exception:
                continue

        # Check for Observer
        if list(self.project_path.glob("**/watcher.py")) or list(self.project_path.glob("**/observer.py")):
            patterns.append("Observer")

        # Check for Strategy/Protocol
        for py_file in self.project_path.glob("**/*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "Protocol" in content or "ABC" in content:
                    patterns.append("Strategy/Protocol")
                    break
            except Exception:
                continue

        return list(set(patterns))

    def _generate_hotspot_chart(self, hotspots: List[Dict[str, Any]]) -> str:
        """Generate ASCII bar chart for hotspots."""
        if not hotspots:
            return "No hotspots detected"

        lines = []
        max_score = max(h.get("impact_score", 1) for h in hotspots)

        for hotspot in hotspots:
            func = hotspot.get("function", "unknown")
            score = hotspot.get("impact_score", 0)
            bar_length = int((score / max_score) * 30) if max_score > 0 else 0
            bar = "#" * bar_length
            lines.append(f"{func[:30]:30s} {bar} {score}")

        return "\n".join(lines)

    def _describe_dependencies(self) -> str:
        """Describe project dependencies in text format."""
        dep_files = []

        if (self.project_path / "requirements.txt").exists():
            dep_files.append("requirements.txt")
        if (self.project_path / "pyproject.toml").exists():
            dep_files.append("pyproject.toml")
        if (self.project_path / "setup.py").exists():
            dep_files.append("setup.py")

        if dep_files:
            return f"Dependency files found: {', '.join(dep_files)}"
        return "No standard dependency files found"
