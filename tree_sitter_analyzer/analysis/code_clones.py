#!/usr/bin/env python3
"""
Code Clone Detection Engine.

Detects duplicate code patterns using AST fingerprinting and
similarity analysis. Identifies:
- Type 1: Exact copies (whitespace/comments ignored)
- Type 2: Structurally similar (renamed variables)
- Type 3: Functionally similar (different implementations)

Inspired by codeflow's pattern matching and clone detection research.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

# Clone types based on IEEE taxonomy
class CloneType(Enum):
    """Type of code clone."""
    TYPE_1_EXACT = "type_1_exact"  # Exact copies except whitespace
    TYPE_2_STRUCTURE = "type_2_structure"  # Renamed variables
    TYPE_3_FUNCTION = "type_3_function"  # Functionally similar


class CloneSeverity(Enum):
    """Severity based on clone size and impact."""
    INFO = "info"  # Small clones (< 5 lines)
    WARNING = "warning"  # Medium clones (5-15 lines)
    CRITICAL = "critical"  # Large clones (> 15 lines)


@dataclass(frozen=True)
class CodeClone:
    """A detected code clone."""

    clone_type: str
    severity: str
    file_a: str
    line_a: int
    file_b: str
    line_b: int
    length_lines: int
    description: str
    suggestion: str
    snippet: str = ""
    similarity: float = 0.0


@dataclass
class CloneDetectionResult:
    """Result of clone detection on a project."""

    total_clones: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    clones: list[CodeClone] = field(default_factory=list)

    def add_clone(self, clone: CodeClone) -> None:
        """Add a detected clone and update counts."""
        self.clones.append(clone)
        self.total_clones += 1
        self.by_type[clone.clone_type] = (
            self.by_type.get(clone.clone_type, 0) + 1
        )
        self.by_severity[clone.severity] = (
            self.by_severity.get(clone.severity, 0) + 1
        )


# Default configuration
DEFAULT_MIN_LINES: int = 5  # Minimum lines to consider as a clone
DEFAULT_MIN_SIMILARITY: float = 0.8  # 80% similarity threshold


class CodeCloneDetector:
    """Detect code clones using fingerprinting and similarity analysis."""

    # Patterns for normalization (Type 2 clone detection)
    NORMALIZATION_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r'\b[a-zA-Z_]\w*\b', 'VAR'),  # Variable names
        (r'\b\d+\b', 'NUM'),  # Numbers
        (r'["\'][^"\']*["\']', 'STR'),  # Strings
    ]

    def __init__(
        self,
        project_root: str,
        min_lines: int = DEFAULT_MIN_LINES,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> None:
        self.project_root = Path(project_root)
        self.min_lines = min_lines
        self.min_similarity = min_similarity

        # Normalized code cache
        self._normalized_cache: dict[str, list[str]] = {}

    def detect_project(self) -> CloneDetectionResult:
        """Detect clones across the entire project."""
        result = CloneDetectionResult()

        # Get all source files
        source_files = self._get_source_files()
        logger.info(f"Scanning {len(source_files)} files for clones...")

        # Extract code blocks from each file
        all_blocks: list[tuple[str, int, list[str]]] = []
        for file_path in source_files:
            blocks = self._extract_code_blocks(file_path)
            all_blocks.extend(blocks)

        # Compare all pairs of blocks
        for i, (file_a, line_a, lines_a) in enumerate(all_blocks):
            for file_b, line_b, lines_b in all_blocks[i + 1:]:
                clone = self._detect_clone_pair(
                    file_a, line_a, lines_a,
                    file_b, line_b, lines_b,
                )
                if clone:
                    result.add_clone(clone)

        logger.info(f"Found {result.total_clones} code clones")
        return result

    def _get_source_files(self) -> list[str]:
        """Get list of source files to analyze."""
        extensions = {
            ".py", ".java", ".js", ".ts", ".tsx", ".jsx",
            ".go", ".rs", ".cs", ".kt", ".c", ".cpp", ".h", ".rb",
        }
        files = []
        for ext in extensions:
            for path in self.project_root.rglob(f"*{ext}"):
                # Skip common non-source directories
                parts = path.parts
                skip_dirs = {
                    "node_modules", ".git", "vendor", "__pycache__",
                    "build", "dist", "target", ".venv",
                }
                if skip_dirs.intersection(parts):
                    continue
                rel = str(path.relative_to(self.project_root))
                files.append(rel)
        return sorted(files)

    def _extract_code_blocks(
        self,
        file_path: str,
    ) -> list[tuple[str, int, list[str]]]:
        """Extract code blocks (functions, methods) from a file."""
        full_path = self.project_root / file_path
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        lines = text.split("\n")
        blocks: list[tuple[str, int, list[str]]] = []

        # Determine if file is Python (indentation-based)
        is_python = file_path.endswith(".py")

        # Find function/method definitions
        in_function = False
        func_lines: list[str] = []
        func_start = 0
        brace_depth = 0
        base_indent = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check for function definition
            if self._is_function_def(stripped):
                if in_function and len(func_lines) >= self.min_lines:
                    blocks.append((file_path, func_start, func_lines.copy()))
                in_function = True
                func_start = i + 1
                func_lines = [line]
                brace_depth = line.count("{") - line.count("}")
                if is_python:
                    base_indent = len(line) - len(line.lstrip())
            elif in_function:
                func_lines.append(line)

                if is_python:
                    # For Python, function ends when we see dedent to base level
                    # or at end of file
                    current_indent = len(line) - len(line.lstrip())
                    is_last_line = i == len(lines) - 1
                    # Empty lines don't end the function, but dedented non-empty lines do
                    if (stripped and current_indent <= base_indent) or is_last_line:
                        # End of function
                        if len(func_lines) >= self.min_lines:
                            blocks.append((file_path, func_start, func_lines.copy()))
                        in_function = False
                        func_lines = []
                        base_indent = 0
                else:
                    # For brace-based languages
                    brace_depth += line.count("{") - line.count("}")

                    # Check if function ended
                    if brace_depth <= 0 and not stripped.startswith("#"):
                        if len(func_lines) >= self.min_lines:
                            blocks.append((file_path, func_start, func_lines.copy()))
                        in_function = False
                        func_lines = []
                        brace_depth = 0

        return blocks

    def _is_function_def(self, line: str) -> bool:
        """Check if a line is a function/method definition."""
        if not line or line.startswith("#") or line.startswith("//"):
            return False

        # Python def
        if line.startswith("def ") or line.startswith("async def "):
            return True

        # Java/C#/Go style
        if re.match(
            r'^(?:public|private|protected|static|async|override|'
            r'synchronized|final|abstract|\s)*\w+\s+\w+\s*\(',
            line,
        ):
            return True

        # Go func
        if line.startswith("func "):
            return True

        return False

    def _detect_clone_pair(
        self,
        file_a: str,
        line_a: int,
        lines_a: list[str],
        file_b: str,
        line_b: int,
        lines_b: list[str],
    ) -> CodeClone | None:
        """Detect if two code blocks are clones."""
        # Skip comparing same file/location
        if file_a == file_b and abs(line_a - line_b) < len(lines_a):
            return None

        # Normalize both blocks
        norm_a = self._normalize_code(lines_a)
        norm_b = self._normalize_code(lines_b)

        # Calculate similarity
        similarity = self._calculate_similarity(norm_a, norm_b)

        if similarity >= self.min_similarity:
            # Determine clone type and severity
            clone_type, severity = self._classify_clone(similarity, len(lines_a))

            snippet = "\n".join(lines_a[:3]) + "..." if len(lines_a) > 3 else "\n".join(lines_a)

            return CodeClone(
                clone_type=clone_type,
                severity=severity,
                file_a=file_a,
                line_a=line_a,
                file_b=file_b,
                line_b=line_b,
                length_lines=len(lines_a),
                description=(
                    f"Code clone ({similarity:.1%} similarity) "
                    f"between {file_a}:{line_a} and {file_b}:{line_b}"
                ),
                suggestion=(
                    "Extract the duplicate code into a shared function or method. "
                    "Consider using the Template Method pattern if differences are structural."
                ),
                snippet=snippet,
                similarity=similarity,
            )

        return None

    def _normalize_code(self, lines: list[str]) -> str:
        """Normalize code for comparison (Type 2 clone detection)."""
        text = " ".join(lines)

        # Remove comments
        text = re.sub(r'#.*', '', text)
        text = re.sub(r'//.*', '', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)

        # Normalize identifiers for Type 2 detection
        for pattern, replacement in self.NORMALIZATION_PATTERNS:
            text = re.sub(pattern, replacement, text)

        return text.strip()

    def _calculate_similarity(
        self,
        norm_a: str,
        norm_b: str,
    ) -> float:
        """Calculate similarity between two normalized code strings."""
        # Use simple token-level Jaccard similarity
        tokens_a = set(norm_a.split())
        tokens_b = set(norm_b.split())

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b

        return len(intersection) / len(union) if union else 0.0

    def _classify_clone(
        self,
        similarity: float,
        length: int,
    ) -> tuple[str, str]:
        """Classify clone type and severity."""
        # Type 1: Near-exact match (95%+ similarity)
        if similarity >= 0.95:
            clone_type = CloneType.TYPE_1_EXACT.value
        # Type 2: Structural similarity (80%+)
        elif similarity >= 0.85:
            clone_type = CloneType.TYPE_2_STRUCTURE.value
        # Type 3: Functional similarity
        else:
            clone_type = CloneType.TYPE_3_FUNCTION.value

        # Severity based on clone size
        if length >= 15:
            severity = CloneSeverity.CRITICAL.value
        elif length >= 5:
            severity = CloneSeverity.WARNING.value
        else:
            severity = CloneSeverity.INFO.value

        return clone_type, severity
