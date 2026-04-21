"""Project Brain — pre-warmed holistic model of the entire codebase.

On initialization, the Brain scans every source file, runs applicable neurons,
and builds a living perception map. Any query is answered instantly from
the pre-computed model — no per-request scanning needed.

Usage:
    brain = ProjectBrain("/path/to/project")
    brain.warm_up()  # scans all files, builds perception

    # Instant queries — no tool calls, no re-scanning
    brain.get_file_perception("src/foo.py")
    brain.get_hotspots()
    brain.get_health_score()
    brain.what_happens_if_i_change("src/foo.py", line=42)
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.neural_perception import (
    NeuralPerception,
    PerceptionMap,
)
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

_SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".c", ".cpp",
    ".hpp", ".h", ".cs", ".kt", ".rs", ".rb", ".php", ".swift", ".scala",
    ".sh", ".css", ".html", ".json", ".jsonc", ".json5", ".yaml", ".yml",
    ".md", ".sql",
}


@dataclass(frozen=True)
class FileKnowledge:
    """Pre-computed knowledge about a single file."""
    path: str
    language: str
    line_count: int
    health_score: float
    perception_score: float
    total_findings: int
    fired_neurons: int
    total_neurons: int
    severity_distribution: dict[str, int]
    category_coverage: dict[str, int]
    critical_hotspot_lines: tuple[int, ...]
    top_issues: tuple[str, ...]


@dataclass
class ProjectBrain:
    """Pre-warmed holistic model of the entire project.

    Warm-up scans all source files once. After that, every query is
    answered from the pre-computed model — zero re-scanning.
    """
    project_root: str
    _file_map: dict[str, FileKnowledge] = field(default_factory=dict)
    _hotspots: list[dict[str, Any]] = field(default_factory=list)
    _warm_time: float = 0.0
    _warm_duration: float = 0.0
    _file_hashes: dict[str, str] = field(default_factory=dict)
    _total_files: int = 0
    _total_lines: int = 0
    _overall_health: float = 100.0
    _category_totals: dict[str, int] = field(default_factory=dict)
    _severity_totals: dict[str, int] = field(default_factory=dict)
    _language_distribution: dict[str, int] = field(default_factory=dict)

    def warm_up(self) -> None:
        """Scan all project files and build the perception model."""
        start = time.monotonic()
        self._file_map = {}
        self._hotspots = []
        self._total_lines = 0
        self._language_distribution = defaultdict(int)
        self._category_totals = defaultdict(int)
        self._severity_totals = defaultdict(int)

        perception = NeuralPerception()
        files = self._collect_files()
        self._total_files = len(files)

        all_hotspots: list[dict[str, Any]] = []
        health_scores: list[float] = []

        for fpath in files:
            try:
                pmap = perception.perceive_file(fpath)
                knowledge = self._build_knowledge(fpath, pmap)
                self._file_map[fpath] = knowledge
                health_scores.append(knowledge.health_score)

                for h in pmap.hotspots:
                    all_hotspots.append({
                        "file": fpath,
                        "line": h.line,
                        "end_line": h.end_line,
                        "analyzer_count": h.analyzer_count,
                        "analyzer_names": h.analyzer_names,
                        "max_severity": h.max_severity.value,
                        "finding_types": h.finding_types,
                    })

                ext = Path(fpath).suffix.lower()
                self._language_distribution[ext] = self._language_distribution.get(ext, 0) + 1
            except Exception as e:
                logger.debug("Brain skip %s: %s", fpath, e)

        all_hotspots.sort(key=lambda h: h["analyzer_count"], reverse=True)
        self._hotspots = all_hotspots
        self._overall_health = (
            sum(health_scores) / len(health_scores) if health_scores else 100.0
        )
        self._warm_duration = time.monotonic() - start
        self._warm_time = time.time()

    def warm_up_incremental(self, changed_files: list[str]) -> None:
        """Re-scan only changed files. Skips unchanged."""
        perception = NeuralPerception()
        for fpath in changed_files:
            current_hash = self._file_hash(fpath)
            if (fpath in self._file_map
                    and self._file_hashes.get(fpath) == current_hash):
                continue
            try:
                pmap = perception.perceive_file(fpath)
                self._file_map[fpath] = self._build_knowledge(fpath, pmap)
                self._file_hashes[fpath] = current_hash
            except Exception as e:
                logger.debug("Brain incremental skip %s: %s", fpath, e)

    def get_file_perception(self, file_path: str) -> FileKnowledge | None:
        """Instant lookup — no re-scanning."""
        resolved = str(Path(file_path).resolve())
        return self._file_map.get(resolved) or self._file_map.get(file_path)

    def get_hotspots(self, min_analyzers: int = 2) -> list[dict[str, Any]]:
        return [h for h in self._hotspots
                if h["analyzer_count"] >= min_analyzers]

    def get_health_score(self) -> float:
        return round(self._overall_health, 1)

    def what_happens_if_i_change(
        self, file_path: str, line: int | None = None
    ) -> dict[str, Any]:
        """Predict impact of changing a file/line."""
        knowledge = self.get_file_perception(file_path)
        if knowledge is None:
            return {"error": f"Unknown file: {file_path}"}

        result: dict[str, Any] = {
            "file": file_path,
            "current_health": knowledge.health_score,
            "existing_findings": knowledge.total_findings,
            "active_neurons": knowledge.fired_neurons,
            "warnings": [],
        }

        if line is not None:
            affected = [
                h for h in self._hotspots
                if h["file"] == file_path
                and h["line"] <= line <= h["end_line"]
            ]
            if affected:
                result["line_hotspot"] = True
                result["overlapping_analyzers"] = affected[0]["analyzer_names"]
                result["severity"] = affected[0]["max_severity"]
                result["warnings"].append(
                    f"Line {line} is a compound hotspot "
                    f"({affected[0]['analyzer_count']} analyzers fire here)"
                )

        related = self._find_related_files(file_path)
        if related:
            result["related_files"] = related

        return result

    def get_summary(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "total_files": self._total_files,
            "total_lines": self._total_lines,
            "total_hotspots": len(self._hotspots),
            "critical_hotspots": len(self.get_hotspots(min_analyzers=3)),
            "overall_health": self.get_health_score(),
            "language_distribution": dict(self._language_distribution),
            "warm_time": round(self._warm_duration, 2),
            "warm_timestamp": self._warm_time,
        }

    def get_context_for_file(self, file_path: str) -> dict[str, Any]:
        """One-call complete context for an LLM — no further tool calls needed."""
        knowledge = self.get_file_perception(file_path)
        if knowledge is None:
            return {"error": f"Unknown file: {file_path}"}

        file_hotspots = [
            h for h in self._hotspots if h["file"] == file_path
        ]
        related = self._find_related_files(file_path)

        return {
            "file": file_path,
            "language": knowledge.language,
            "line_count": knowledge.line_count,
            "health": knowledge.health_score,
            "findings": knowledge.total_findings,
            "fired_neurons": f"{knowledge.fired_neurons}/{knowledge.total_neurons}",
            "severity": knowledge.severity_distribution,
            "categories": knowledge.category_coverage,
            "critical_lines": list(knowledge.critical_hotspot_lines),
            "top_issues": list(knowledge.top_issues),
            "hotspots": file_hotspots[:5],
            "related_files": related,
            "project_health": self.get_health_score(),
            "project_files": self._total_files,
        }

    def _collect_files(self) -> list[str]:
        root = Path(self.project_root)
        files: list[str] = []
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", ".tox",
            ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov",
            ".eggs", "*.egg-info", "dist", "build",
        }
        for p in root.rglob("*"):
            if any(skip in p.parts for skip in skip_dirs):
                continue
            if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTENSIONS:
                files.append(str(p))
        return sorted(files)

    def _build_knowledge(
        self, file_path: str, pmap: PerceptionMap
    ) -> FileKnowledge:
        try:
            line_count = sum(
                1 for _ in open(file_path, errors="replace")
            )
        except OSError:
            line_count = 0
        self._total_lines += line_count

        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "tsx", ".java": "java",
            ".go": "go", ".c": "c", ".cpp": "cpp", ".rs": "rust",
            ".rb": "ruby", ".php": "php", ".swift": "swift",
            ".kt": "kotlin", ".cs": "csharp", ".scala": "scala",
        }
        language = lang_map.get(ext, ext.lstrip("."))

        critical_lines = tuple(
            h.line for h in pmap.critical_hotspots
        )
        top_issues = tuple(
            f"[{h.max_severity.value}] L{h.line}: "
            f"{', '.join(h.analyzer_names)}"
            for h in pmap.hotspots[:5]
        )

        self._file_hashes[file_path] = self._file_hash(file_path)

        for cat, count in pmap.category_coverage.items():
            self._category_totals[cat] = self._category_totals.get(cat, 0) + count
        for sev, count in pmap.severity_distribution.items():
            self._severity_totals[sev] = self._severity_totals.get(sev, 0) + count

        return FileKnowledge(
            path=file_path,
            language=language,
            line_count=line_count,
            health_score=pmap.health_score,
            perception_score=pmap.perception_score,
            total_findings=pmap.total_findings,
            fired_neurons=pmap.fired_neurons,
            total_neurons=pmap.total_neurons,
            severity_distribution=pmap.severity_distribution,
            category_coverage=pmap.category_coverage,
            critical_hotspot_lines=critical_lines,
            top_issues=top_issues,
        )

    def _file_hash(self, file_path: str) -> str:
        try:
            content = Path(file_path).read_bytes()
            return hashlib.md5(content).hexdigest()
        except OSError:
            return ""

    def _relative(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self.project_root))
        except ValueError:
            return file_path

    def _find_related_files(self, file_path: str) -> list[str]:
        """Heuristic: files in same directory with hotspots."""
        directory = str(Path(file_path).parent)
        related: list[str] = []
        for path, knowledge in self._file_map.items():
            if path == file_path:
                continue
            if str(Path(path).parent) == directory and knowledge.total_findings > 0:
                related.append(path)
        return sorted(related)[:5]
