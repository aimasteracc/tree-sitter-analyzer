"""
Health score engine for source code files.

Grades each file A-F based on size, complexity, coupling, and annotation density.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".cs", ".kt", ".c", ".cpp", ".h",
}


@dataclass(frozen=True)
class FileHealthScore:
    """Health score for a single file."""

    file_path: str
    score: int
    grade: str
    lines: int
    methods: int
    imports: int
    breakdown: dict[str, int]


class HealthScorer:
    """Score files based on maintainability metrics."""

    GRADE_THRESHOLDS: list[tuple[int, str]] = [
        (90, "A"),
        (75, "B"),
        (60, "C"),
        (40, "D"),
    ]

    IMPORT_PATTERN = re.compile(
        r"^\s*(?:import|from|using|require)\s", re.MULTILINE
    )
    METHOD_PATTERN = re.compile(
        r"(?:void|int|long|double|float|boolean|String|char|byte|short|var|auto|func|def|fn|pub\s+fn|public|private|protected)"
        r"\s+\w+\s*\("
    )
    ANNOTATION_PATTERN = re.compile(r"@\w+")

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root)

    def score_all(self) -> list[FileHealthScore]:
        """Score all source files in the project."""
        scores: list[FileHealthScore] = []
        for ext in sorted(SUPPORTED_EXTENSIONS):
            for file_path in sorted(self.project_root.rglob(f"*{ext}")):
                rel = str(file_path.relative_to(self.project_root))
                scores.append(self.score_file(rel))
        return scores

    def score_file(self, file_path: str) -> FileHealthScore:
        """Score a single file."""
        full_path = self.project_root / file_path
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return FileHealthScore(
                file_path=file_path,
                score=0,
                grade="F",
                lines=0,
                methods=0,
                imports=0,
                breakdown={},
            )

        lines = text.count("\n") + 1
        imports = len(self.IMPORT_PATTERN.findall(text))
        methods = len(self.METHOD_PATTERN.findall(text))
        annotations = len(self.ANNOTATION_PATTERN.findall(text))

        breakdown = {
            "size_penalty": min(lines // 10, 30),
            "complexity_penalty": min(methods * 2, 20),
            "coupling_penalty": min(imports * 3, 20),
            "annotation_penalty": min(annotations, 15),
        }

        score = 100 - sum(breakdown.values())
        score = max(0, min(100, score))

        return FileHealthScore(
            file_path=file_path,
            score=score,
            grade=self._grade(score),
            lines=lines,
            methods=methods,
            imports=imports,
            breakdown=breakdown,
        )

    def _grade(self, score: int) -> str:
        """Convert numeric score to letter grade."""
        for threshold, grade in self.GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return "F"
