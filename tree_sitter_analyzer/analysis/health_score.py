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
    cyclomatic_complexity: int
    avg_function_length: float
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
    BRANCH_PATTERN = re.compile(
        r"\b(?:if|elif|else\s+if|else|for|while|catch|except|case|&&|\|\||\?\s)"
        r"|&&|\|\|"
    )
    FUNCTION_START_PATTERN = re.compile(
        r"^\s*(?:public|private|protected|static|synchronized|async|\s)*"
        r"(?:void|int|long|double|float|boolean|String|char|byte|short|var|auto|def|fn|func)\s+\w+\s*\("
        r"|^\s*def\s+\w+"
        r"|^\s*func\s+\w+"
        r"|^\s*fn\s+\w+"
        r"|^\s*(?:pub\s+)?fn\s+\w+",
        re.MULTILINE,
    )

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
                cyclomatic_complexity=0,
                avg_function_length=0.0,
                breakdown={},
            )

        lines = text.count("\n") + 1
        imports = len(self.IMPORT_PATTERN.findall(text))
        methods = len(self.METHOD_PATTERN.findall(text))
        annotations = len(self.ANNOTATION_PATTERN.findall(text))
        branches = len(self.BRANCH_PATTERN.findall(text))
        cyclomatic = branches + 1

        func_starts = [m.start() for m in self.FUNCTION_START_PATTERN.finditer(text)]
        file_lines = text.split("\n")
        total_lines = len(file_lines)
        if func_starts and methods > 0:
            func_lengths: list[int] = []
            for i, start_pos in enumerate(func_starts):
                start_line = text[:start_pos].count("\n")
                if i + 1 < len(func_starts):
                    end_line = text[:func_starts[i + 1]].count("\n")
                else:
                    end_line = total_lines
                func_lengths.append(end_line - start_line)
            avg_func_len = sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        else:
            avg_func_len = float(lines) / max(methods, 1)

        breakdown = {
            "size_penalty": min(lines // 10, 30),
            "complexity_penalty": min(methods * 2, 20),
            "coupling_penalty": min(imports * 3, 20),
            "annotation_penalty": min(annotations, 15),
            "branch_penalty": min(cyclomatic, 15),
            "function_length_penalty": min(int(avg_func_len) // 5, 10),
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
            cyclomatic_complexity=cyclomatic,
            avg_function_length=round(avg_func_len, 1),
            breakdown=breakdown,
        )

    def _grade(self, score: int) -> str:
        """Convert numeric score to letter grade."""
        for threshold, grade in self.GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return "F"
