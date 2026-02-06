"""
Layer 1 generator - 5-minute quick overview.

Provides fast project overview with statistics, tech stack detection,
and entry point identification.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from tree_sitter_analyzer_v2.features.instant_understanding.models import Layer1Overview

logger = logging.getLogger(__name__)


class Layer1Generator:
    """Generates the 5-minute quick overview layer."""

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def generate(self, results: Dict[str, Any]) -> Layer1Overview:
        """Generate 5-minute quick overview layer."""
        logger.info("Generating Layer 1 (5-minute overview)...")

        stats = results.get("statistics", {})
        knowledge = results.get("knowledge", {})
        snapshot = knowledge.get("snapshot") if knowledge else None

        statistics = {
            "files": stats.get("total_files", 0),
            "lines": stats.get("total_lines", 0),
            "classes": snapshot.total_functions if snapshot else 0,
            "functions": snapshot.total_functions if snapshot else 0,
            "language": stats.get("language", "unknown"),
        }

        hotspots = knowledge.get("hotspots", []) if knowledge else []
        top_files = self._extract_top_files(hotspots)
        tech_stack = self._detect_tech_stack()
        entry_points = self._find_entry_points()

        return Layer1Overview(
            project_name=self.project_path.name,
            summary=f"Python project with {statistics['files']} files and {statistics['functions']} functions",
            statistics=statistics,
            top_files=top_files,
            tech_stack=tech_stack,
            entry_points=entry_points,
        )

    def _extract_top_files(self, hotspots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract top files from hotspots."""
        top_files = []
        seen_files: set = set()
        for hotspot in hotspots[:5]:
            file_name = hotspot.get("file", "")
            if file_name and file_name not in seen_files:
                top_files.append({
                    "file": file_name,
                    "function": hotspot.get("function", ""),
                    "impact": hotspot.get("impact_level", "low"),
                })
                seen_files.add(file_name)
        return top_files

    def _detect_tech_stack(self) -> Dict[str, Any]:
        """Detect technology stack from project files."""
        tech_stack: Dict[str, Any] = {
            "framework": "Unknown",
            "tools": [],
            "dependencies": [],
        }

        if (self.project_path / "pyproject.toml").exists():
            tech_stack["tools"].append("uv/poetry")
        if (self.project_path / "requirements.txt").exists():
            tech_stack["tools"].append("pip")
        if (self.project_path / "pytest.ini").exists() or (self.project_path / "pyproject.toml").exists():
            tech_stack["tools"].append("pytest")

        mcp_files = list(self.project_path.glob("**/mcp/**/*.py"))
        if mcp_files:
            tech_stack["framework"] = "MCP (Model Context Protocol)"

        if list(self.project_path.glob("**/tree_sitter*.py")):
            tech_stack["dependencies"].append("tree-sitter")

        return tech_stack

    def _find_entry_points(self) -> List[str]:
        """Find entry points (main functions, CLI, API)."""
        entry_points = []
        patterns = ["**/main.py", "**/__main__.py", "**/cli.py", "**/api.py", "**/server.py"]

        for pattern in patterns:
            for file_path in self.project_path.glob(pattern):
                if "__pycache__" not in str(file_path):
                    rel_path = file_path.relative_to(self.project_path)
                    entry_points.append(str(rel_path))

        return entry_points
