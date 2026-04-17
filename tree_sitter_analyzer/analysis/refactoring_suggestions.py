"""
Refactoring Suggestions - Actionable guidance to fix code smells.

This module provides step-by-step refactoring suggestions based on code
smell detection results from code_smells.py. Instead of just reporting
problems, it generates specific fixes with before/after examples.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class SeverityLevel(Enum):
    """Severity levels for refactoring suggestions."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RefactoringType(Enum):
    """Types of refactoring suggestions."""
    EXTRACT_METHOD = "extract_method"
    EXTRACT_CLASS = "extract_class"
    GUARD_CLAUSE = "guard_clause"
    REPLACE_MAGIC_NUMBER = "replace_magic_number"
    REMOVE_UNUSED_IMPORTS = "remove_unused_imports"
    SPLIT_LARGE_CLASS = "split_large_class"
    REDUCE_NESTING = "reduce_nesting"


@dataclass
class CodeDiff:
    """Before/after code for a refactoring."""
    before: str
    after: str
    language: str
    line_start: int
    line_end: int


@dataclass
class RefactoringSuggestion:
    """A single refactoring suggestion."""
    type: RefactoringType
    title: str
    description: str
    severity: SeverityLevel
    file_path: str
    line_start: int
    line_end: int
    code_diff: CodeDiff | None = None
    estimated_effort: Literal["simple", "moderate", "complex"] = "moderate"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_diff": {
                "before": self.code_diff.before,
                "after": self.code_diff.after,
                "language": self.code_diff.language,
                "line_start": self.code_diff.line_start,
                "line_end": self.code_diff.line_end,
            } if self.code_diff else None,
            "estimated_effort": self.estimated_effort,
        }


@dataclass
class RefactoringReport:
    """Complete refactoring suggestions report."""
    file_path: str
    suggestions: list[RefactoringSuggestion] = field(default_factory=list)
    total_suggestions: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0

    def add_suggestion(self, suggestion: RefactoringSuggestion) -> None:
        """Add a suggestion to the report."""
        self.suggestions.append(suggestion)
        self.total_suggestions += 1

        if suggestion.severity == SeverityLevel.CRITICAL:
            self.critical_count += 1
        elif suggestion.severity == SeverityLevel.HIGH:
            self.high_count += 1
        elif suggestion.severity == SeverityLevel.MEDIUM:
            self.medium_count += 1

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "total_suggestions": self.total_suggestions,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "suggestions": [s.to_dict() for s in self.suggestions],
        }


class RefactoringAdvisor:
    """
    Generate refactoring suggestions based on code smell detection.

    This advisor analyzes code and provides actionable, specific guidance
    for fixing code quality issues. Suggestions include before/after code
    examples and estimated effort levels.
    """

    def __init__(self) -> None:
        """Initialize the refactoring advisor."""
        self._thresholds = {
            "method_length": 50,
            "nesting_depth": 4,
            "magic_number_min": 3,
            "magic_number_max": 1000,
        }

    def suggest_fixes(
        self,
        file_path: str,
        content: str,
        language: str,
        smell_results: dict | None = None,
    ) -> RefactoringReport:
        """
        Generate refactoring suggestions for a file.

        Args:
            file_path: Path to the source file
            content: File content
            language: Programming language
            smell_results: Optional pre-computed smell results

        Returns:
            RefactoringReport with all suggestions
        """
        report = RefactoringReport(file_path=file_path)

        # If smell_results provided, generate targeted suggestions
        if smell_results:
            report = self._suggest_from_smells(
                file_path, content, language, smell_results
            )
        else:
            # Analyze content directly for common issues
            report = self._analyze_content(
                file_path, content, language
            )

        return report

    def _suggest_from_smells(
        self,
        file_path: str,
        content: str,
        language: str,
        smell_results: dict,
    ) -> RefactoringReport:
        """Generate suggestions from pre-computed smell results."""
        report = RefactoringReport(file_path=file_path)

        lines = content.split("\n")

        for smell in smell_results.get("smells", []):
            smell_type = smell.get("type", "")
            line = smell.get("line", 0)

            if smell_type == "long_method":
                suggestion = self._generate_extract_method(
                    file_path, content, language, line, smell
                )
                report.add_suggestion(suggestion)

            elif smell_type == "deep_nesting":
                suggestion = self._generate_guard_clause(
                    file_path, content, language, line, smell
                )
                report.add_suggestion(suggestion)

            elif smell_type == "magic_number":
                suggestion = self._generate_constant_extraction(
                    file_path, content, language, line, smell
                )
                report.add_suggestion(suggestion)

            elif smell_type == "large_class":
                suggestion = self._generate_extract_class(
                    file_path, content, language, line, smell
                )
                report.add_suggestion(suggestion)

        return report

    def _analyze_content(
        self,
        file_path: str,
        content: str,
        language: str,
    ) -> RefactoringReport:
        """Analyze content directly for common refactoring opportunities."""
        report = RefactoringReport(file_path=file_path)
        lines = content.split("\n")

        # Check for deeply nested code (common pattern: 4+ spaces/tabs)
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(stripped)
            # Check for deep nesting (Python: 16+ spaces, JS: 8+ spaces)
            if (language == "python" and indent >= 16) or \
               (language in ["javascript", "typescript"] and indent >= 8):
                suggestion = self._generate_guard_clause(
                    file_path, content, language, i,
                    {"depth": indent // 4, "line": i}
                )
                report.add_suggestion(suggestion)

        return report

    def _generate_extract_method(
        self,
        file_path: str,
        content: str,
        language: str,
        line: int,
        smell: dict,
    ) -> RefactoringSuggestion:
        """Generate Extract Method refactoring suggestion."""
        method_length = smell.get("length", 0)

        description = (
            f"Method is {method_length} lines long (threshold: "
            f"{self._thresholds['method_length']}). "
            "Extract logical blocks into separate methods with descriptive names."
        )

        # Generate example before/after
        if language == "python":
            before = "def process_data(self, data):\n    # ... 50+ lines of logic ...\n    validate(data)\n    transform(data)\n    save(data)"
            after = "def process_data(self, data):\n    self._validate_data(data)\n    self._transform_data(data)\n    self._save_data(data)\n\ndef _validate_data(self, data):\n    # Validation logic\n    pass"
        else:
            before = f"// {method_length} line method with mixed concerns"
            after = "// Extracted into smaller, focused methods"

        return RefactoringSuggestion(
            type=RefactoringType.EXTRACT_METHOD,
            title="Extract Method",
            description=description,
            severity=SeverityLevel.MEDIUM if method_length < 75 else SeverityLevel.HIGH,
            file_path=file_path,
            line_start=line,
            line_end=line + method_length,
            code_diff=CodeDiff(
                before=before,
                after=after,
                language=language,
                line_start=line,
                line_end=line + method_length,
            ),
            estimated_effort="moderate" if method_length < 75 else "complex",
        )

    def _generate_guard_clause(
        self,
        file_path: str,
        content: str,
        language: str,
        line: int,
        smell: dict,
    ) -> RefactoringSuggestion:
        """Generate Guard Clause refactoring suggestion."""
        depth = smell.get("depth", 4)

        description = (
            f"Code is nested {depth} levels deep (threshold: "
            f"{self._thresholds['nesting_depth']}). "
            "Use guard clauses to return early and reduce nesting."
        )

        if language == "python":
            before = "def process(self, data):\n    if data:\n        if data.isValid():\n            if data.hasPermission():\n                # actual logic\n                return data.process()"
            after = "def process(self, data):\n    if not data:\n        return None\n    if not data.isValid():\n        return None\n    if not data.hasPermission():\n        return None\n    return data.process()"
        else:
            before = f"// {depth} levels of nesting"
            after = "// Use guard clauses: if (!condition) return;"

        return RefactoringSuggestion(
            type=RefactoringType.GUARD_CLAUSE,
            title="Introduce Guard Clause",
            description=description,
            severity=SeverityLevel.MEDIUM if depth < 6 else SeverityLevel.HIGH,
            file_path=file_path,
            line_start=line,
            line_end=line + depth * 2,
            code_diff=CodeDiff(
                before=before,
                after=after,
                language=language,
                line_start=line,
                line_end=line + depth * 2,
            ),
            estimated_effort="simple",
        )

    def _generate_constant_extraction(
        self,
        file_path: str,
        content: str,
        language: str,
        line: int,
        smell: dict,
    ) -> RefactoringSuggestion:
        """Generate Replace Magic Number with Constant suggestion."""
        value = smell.get("value", 42)

        description = (
            f"Magic number {value} found. "
            "Replace with a named constant for clarity and maintainability."
        )

        if language == "python":
            before = f"if size < {value}:\n    process()"
            after = f"MAX_THRESHOLD = {value}\n\nif size < MAX_THRESHOLD:\n    process()"
        else:
            before = f"// if (x < {value})"
            after = f"// private static final int MAX_THRESHOLD = {value};"

        return RefactoringSuggestion(
            type=RefactoringType.REPLACE_MAGIC_NUMBER,
            title="Extract Constant",
            description=description,
            severity=SeverityLevel.LOW,
            file_path=file_path,
            line_start=line,
            line_end=line,
            code_diff=CodeDiff(
                before=before,
                after=after,
                language=language,
                line_start=line,
                line_end=line,
            ),
            estimated_effort="simple",
        )

    def _generate_extract_class(
        self,
        file_path: str,
        content: str,
        language: str,
        line: int,
        smell: dict,
    ) -> RefactoringSuggestion:
        """Generate Extract Class refactoring suggestion."""
        class_size = smell.get("size", 0)

        description = (
            f"Class has {class_size} lines, indicating too many responsibilities. "
            "Identify cohesive groups of methods and extract them into separate classes."
        )

        return RefactoringSuggestion(
            type=RefactoringType.EXTRACT_CLASS,
            title="Extract Class",
            description=description,
            severity=SeverityLevel.HIGH if class_size > 500 else SeverityLevel.MEDIUM,
            file_path=file_path,
            line_start=line,
            line_end=line + class_size,
            code_diff=CodeDiff(
                before=f"class LargeClass:\n    # {class_size} lines",
                after="# Extract: ValidationHelper\nclass LargeClass:\n    validation: ValidationHelper",
                language=language,
                line_start=line,
                line_end=line + class_size,
            ),
            estimated_effort="complex",
        )
