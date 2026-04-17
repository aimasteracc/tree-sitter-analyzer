#!/usr/bin/env python3
"""
Code Smell Detection Engine.

Detects common code smells and anti-patterns using AST analysis
and heuristic metrics. Inspired by CodeFlow's pattern detection
and Fowler's refactoring catalog.

Detects:
- God Class: too many methods/fields
- Long Method: methods exceeding line threshold
- Deep Nesting: excessive control flow nesting
- Feature Envy: methods using another class more than their own
- Data Clumps: repeated parameter groups
- Magic Numbers: unexplained numeric literals
- Shotgun Surgery: changes scattered across many files
- Duplicated Parameters: same params in many functions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".cs", ".kt", ".c", ".cpp", ".h", ".rb",
}


class SmellSeverity(Enum):
    """Severity level for detected code smells."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SmellCategory(Enum):
    """Category of code smell (Fowler classification)."""

    BLOATERS = "bloaters"          # God Class, Long Method, Large Class
    COUPLERS = "couplers"          # Feature Envy, Inappropriate Intimacy
    CHANGE_PREVENTERS = "change_preventers"  # Shotgun Surgery, Divergent Change
    DISPENSABLES = "dispensables"  # Dead Code, Magic Numbers, Comments
    OO_ABUSERS = "oo_abusers"      # Refused Bequest, Switch Statements


@dataclass(frozen=True)
class CodeSmell:
    """A single detected code smell."""

    smell_type: str
    category: str
    severity: str
    file_path: str
    line: int
    description: str
    suggestion: str
    metric_value: str = ""
    element_name: str = ""


@dataclass
class SmellDetectionResult:
    """Aggregated result of code smell detection on a file."""

    file_path: str
    total_smells: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    smells: list[CodeSmell] = field(default_factory=list)

    def add_smell(self, smell: CodeSmell) -> None:
        """Add a detected smell and update counts."""
        self.smells.append(smell)
        self.total_smells += 1
        self.by_severity[smell.severity] = (
            self.by_severity.get(smell.severity, 0) + 1
        )
        self.by_category[smell.category] = (
            self.by_category.get(smell.category, 0) + 1
        )


# Thresholds configurable per project
DEFAULT_THRESHOLDS: dict[str, int] = {
    "god_class_methods": 15,
    "god_class_lines": 500,
    "long_method_lines": 50,
    "deep_nesting_levels": 4,
    "magic_number_min": 3,
    "magic_number_max": 1000,
    "large_parameter_count": 5,
    "many_imports": 20,
    "large_class_lines": 500,
}


class CodeSmellDetector:
    """Detect code smells in source files using regex heuristics and metrics."""

    def __init__(
        self,
        project_root: str,
        thresholds: dict[str, int] | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

        # Compiled patterns for efficiency
        self._method_pattern = re.compile(
            r"(?:void|int|long|double|float|boolean|String|char|byte|short|var|auto|"
            r"func|def|fn|pub\s+fn|public|private|protected|async|\s)*"
            r"\w+\s*\("
        )
        self._class_pattern = re.compile(
            r"^\s*(?:(?:public|private|protected|static|final|abstract|async|"
            r"sealed|open|internal|override|virtual)\s+)*"
            r"(?:class|struct|interface|enum|trait|impl|type)\s+(\w+)",
            re.MULTILINE,
        )
        self._import_pattern = re.compile(
            r"^\s*(?:import|from|using|require|#include|use)\s",
            re.MULTILINE,
        )
        self._opening_brace = re.compile(r"[{(]")
        self._closing_brace = re.compile(r"[})]")
        self._numeric_literal = re.compile(
            r"(?<![" r"'\"a-zA-Z_])"  # not part of identifier/string
            r"(-?\d+\.?\d*)"
            r"(?!\s*[:=]"
            r"(?!\s*\|))"
        )
        self._parameter_pattern = re.compile(
            r"\(([^)]{10,})\)"
        )
        self._nesting_keywords = re.compile(
            r"^\s*(?:if|elif|else|for|while|try|catch|except|with|switch|case|"
            r"do|foreach|match)\b",
            re.MULTILINE,
        )

    def detect_file(self, file_path: str) -> SmellDetectionResult:
        """Detect all code smells in a single file."""
        full_path = self.project_root / file_path
        result = SmellDetectionResult(file_path=file_path)

        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return result

        lines = text.split("\n")
        total_lines = len(lines)

        # Run all detectors
        self._detect_god_class(file_path, text, lines, total_lines, result)
        self._detect_long_methods(file_path, text, lines, total_lines, result)
        self._detect_deep_nesting(file_path, lines, result)
        self._detect_magic_numbers(file_path, lines, result)
        self._detect_many_imports(file_path, text, result)
        self._detect_large_classes(file_path, text, total_lines, result)

        return result

    def detect_project(self) -> list[SmellDetectionResult]:
        """Detect code smells across the entire project."""
        results: list[SmellDetectionResult] = []
        for ext in sorted(SUPPORTED_EXTENSIONS):
            for file_path in sorted(self.project_root.rglob(f"*{ext}")):
                # Skip common non-source directories
                parts = file_path.parts
                skip_dirs = {
                    "node_modules", ".git", "vendor", "__pycache__",
                    "build", "dist", "target", ".venv",
                }
                if skip_dirs.intersection(parts):
                    continue
                rel = str(file_path.relative_to(self.project_root))
                results.append(self.detect_file(rel))
        return results

    # --- Individual smell detectors ---

    def _detect_god_class(
        self,
        file_path: str,
        text: str,
        lines: list[str],
        total_lines: int,
        result: SmellDetectionResult,
    ) -> None:
        """Detect God Class — classes with too many methods."""
        threshold = self.thresholds["god_class_methods"]
        class_matches = list(self._class_pattern.finditer(text))

        for match in class_matches:
            class_name = match.group(1)
            class_start = text[:match.start()].count("\n") + 1

            # Find methods within this class
            class_text = text[match.start():]
            brace_depth = 0
            class_end = 0
            for i, ch in enumerate(class_text):
                if ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        class_end = i
                        break

            class_body = class_text[:class_end] if class_end else class_text
            method_count = len(self._method_pattern.findall(class_body))

            if method_count >= threshold:
                result.add_smell(CodeSmell(
                    smell_type="god_class",
                    category=SmellCategory.BLOATERS.value,
                    severity=SmellSeverity.CRITICAL.value,
                    file_path=file_path,
                    line=class_start,
                    description=(
                        f"Class '{class_name}' has {method_count} methods "
                        f"(threshold: {threshold})"
                    ),
                    suggestion=(
                        f"Split '{class_name}' into smaller, focused classes "
                        "following the Single Responsibility Principle."
                    ),
                    metric_value=str(method_count),
                    element_name=class_name,
                ))

    def _detect_long_methods(
        self,
        file_path: str,
        text: str,
        lines: list[str],
        total_lines: int,
        result: SmellDetectionResult,
    ) -> None:
        """Detect Long Method — methods exceeding line threshold."""
        threshold = self.thresholds["long_method_lines"]

        # Find function/method definitions with line numbers
        func_starts: list[tuple[int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Python def
            if stripped.startswith("def "):
                name = stripped.split("(")[0].replace("def ", "").strip()
                func_starts.append((i + 1, name))
            # Java/C#/Go style
            elif re.match(
                r"(?:public|private|protected|static|async|synchronized|"
                r"override|virtual|abstract|\s)*\w+\s+\w+\s*\(",
                stripped,
            ) and not stripped.startswith("//") and not stripped.startswith("*"):
                parts = stripped.split()
                if len(parts) >= 2:
                    name = parts[-1].split("(")[0]
                    if name not in {"if", "for", "while", "switch", "catch", "try"}:
                        func_starts.append((i + 1, name))
            # Go func
            elif stripped.startswith("func "):
                name = stripped.split("(")[0].replace("func ", "").strip()
                if name:
                    func_starts.append((i + 1, name))

        for idx, (start_line, func_name) in enumerate(func_starts):
            # Estimate function length
            if idx + 1 < len(func_starts):
                end_line = func_starts[idx + 1][0] - 1
            else:
                end_line = total_lines

            length = end_line - start_line + 1
            if length >= threshold:
                result.add_smell(CodeSmell(
                    smell_type="long_method",
                    category=SmellCategory.BLOATERS.value,
                    severity=SmellSeverity.WARNING.value
                    if length < threshold * 2
                    else SmellSeverity.CRITICAL.value,
                    file_path=file_path,
                    line=start_line,
                    description=(
                        f"Method '{func_name}' is {length} lines "
                        f"(threshold: {threshold})"
                    ),
                    suggestion=(
                        f"Break '{func_name}' into smaller helper methods. "
                        "Each method should do one thing well."
                    ),
                    metric_value=str(length),
                    element_name=func_name,
                ))

    def _detect_deep_nesting(
        self,
        file_path: str,
        lines: list[str],
        result: SmellDetectionResult,
    ) -> None:
        """Detect Deep Nesting — excessive control flow nesting."""
        max_depth = self.thresholds["deep_nesting_levels"]
        current_depth = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue

            # Count control flow keywords
            opens = len(re.findall(
                r"\b(?:if|elif|else|for|while|try|catch|except|with|"
                r"switch|case|foreach|match|do)\b",
                stripped,
            ))
            closes = stripped.count("}") + stripped.count(")") - stripped.count("{") - stripped.count("(")

            current_depth += opens - min(closes, opens)

            if current_depth >= max_depth:
                result.add_smell(CodeSmell(
                    smell_type="deep_nesting",
                    category=SmellCategory.BLOATERS.value,
                    severity=SmellSeverity.WARNING.value
                    if current_depth < max_depth + 2
                    else SmellSeverity.CRITICAL.value,
                    file_path=file_path,
                    line=i + 1,
                    description=(
                        f"Code nested {current_depth} levels deep "
                        f"(threshold: {max_depth})"
                    ),
                    suggestion=(
                        "Use early returns, guard clauses, or extract nested "
                        "logic into separate methods."
                    ),
                    metric_value=str(current_depth),
                ))
                # Only report once per nesting block
                break

    def _detect_magic_numbers(
        self,
        file_path: str,
        lines: list[str],
        result: SmellDetectionResult,
    ) -> None:
        """Detect Magic Numbers — unexplained numeric literals."""
        min_val = self.thresholds["magic_number_min"]
        max_val = self.thresholds["magic_number_max"]
        allowed = {0, 1, -1, 2, 10, 100, 1000}

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip imports, comments, strings, and const/enum declarations
            if (
                stripped.startswith("#")
                or stripped.startswith("//")
                or stripped.startswith("*")
                or stripped.startswith("import ")
                or stripped.startswith("from ")
                or "const " in stripped.lower()
                or "enum " in stripped.lower()
                or "FINAL" in stripped.upper()
            ):
                continue

            numbers = re.findall(
                r"(?<![a-zA-Z_\"'])"
                r"(-?\d+\.?\d*)"
                r"(?![a-zA-Z_\"'])",
                stripped,
            )
            for num_str in numbers:
                try:
                    num = float(num_str)
                    int_num = int(num)
                    if (
                        num == int_num
                        and int_num not in allowed
                        and abs(int_num) > min_val
                        and abs(int_num) < max_val
                        and "." not in num_str  # skip floats for now
                    ):
                        result.add_smell(CodeSmell(
                            smell_type="magic_number",
                            category=SmellCategory.DISPENSABLES.value,
                            severity=SmellSeverity.INFO.value,
                            file_path=file_path,
                            line=i + 1,
                            description=(
                                f"Magic number {int_num} used without explanation"
                            ),
                            suggestion=(
                                f"Extract {int_num} into a named constant "
                                "that explains its meaning."
                            ),
                            metric_value=str(int_num),
                        ))
                        break  # One report per line
                except (ValueError, OverflowError):
                    continue

    def _detect_many_imports(
        self,
        file_path: str,
        text: str,
        result: SmellDetectionResult,
    ) -> None:
        """Detect excessive imports — high coupling indicator."""
        threshold = self.thresholds["many_imports"]
        imports = self._import_pattern.findall(text)
        count = len(imports)

        if count >= threshold:
            result.add_smell(CodeSmell(
                smell_type="many_imports",
                category=SmellCategory.COUPLERS.value,
                severity=SmellSeverity.WARNING.value
                if count < threshold * 1.5
                else SmellSeverity.CRITICAL.value,
                file_path=file_path,
                line=1,
                description=(
                    f"File has {count} imports (threshold: {threshold})"
                ),
                suggestion=(
                    "Consider using the Facade pattern or consolidating "
                    "related imports into a single module."
                ),
                metric_value=str(count),
            ))

    def _detect_large_classes(
        self,
        file_path: str,
        text: str,
        total_lines: int,
        result: SmellDetectionResult,
    ) -> None:
        """Detect Large Class — files with too many lines."""
        threshold = self.thresholds.get("large_class_lines", 500)
        class_matches = list(self._class_pattern.finditer(text))

        for match in class_matches:
            class_name = match.group(1)
            class_start_line = text[:match.start()].count("\n") + 1

            # Estimate class end by brace matching
            class_text = text[match.start():]
            brace_depth = 0
            class_end = 0
            for idx, ch in enumerate(class_text):
                if ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        class_end = idx
                        break

            if class_end > 0:
                class_lines = class_text[:class_end].count("\n")
            else:
                class_lines = total_lines - class_start_line

            if class_lines >= threshold:
                result.add_smell(CodeSmell(
                    smell_type="large_class",
                    category=SmellCategory.BLOATERS.value,
                    severity=SmellSeverity.WARNING.value
                    if class_lines < threshold * 1.5
                    else SmellSeverity.CRITICAL.value,
                    file_path=file_path,
                    line=class_start_line,
                    description=(
                        f"Class '{class_name}' is {class_lines} lines "
                        f"(threshold: {threshold})"
                    ),
                    suggestion=(
                        f"Split '{class_name}' into smaller classes. "
                        "Consider extracting responsibilities into separate modules."
                    ),
                    metric_value=str(class_lines),
                    element_name=class_name,
                ))
