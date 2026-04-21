"""Health score engine for source code files.

Grades each file A-F based on size, complexity, coupling, and annotation density.
Uses tree-sitter AST for accurate metric computation (replaces regex-based approach).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

_FUNCTION_NODES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({
        "function_declaration", "arrow_function",
        "method_definition", "generator_function_declaration",
    }),
    ".jsx": frozenset({
        "function_declaration", "arrow_function",
        "method_definition", "generator_function_declaration",
    }),
    ".ts": frozenset({
        "function_declaration", "arrow_function",
        "method_definition", "generator_function_declaration",
    }),
    ".tsx": frozenset({
        "function_declaration", "arrow_function",
        "method_definition", "generator_function_declaration",
    }),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
    ".rs": frozenset({"function_item"}),
    ".cs": frozenset({"method_declaration", "constructor_declaration"}),
    ".kt": frozenset({"function_declaration"}),
    ".c": frozenset({"function_definition"}),
    ".cpp": frozenset({"function_definition", "declaration"}),
    ".h": frozenset({"function_definition", "declaration"}),
}

_IMPORT_NODES: dict[str, frozenset[str]] = {
    ".py": frozenset({"import_statement", "import_from_statement"}),
    ".js": frozenset({"import_statement"}),
    ".jsx": frozenset({"import_statement"}),
    ".ts": frozenset({"import_statement"}),
    ".tsx": frozenset({"import_statement"}),
    ".java": frozenset({"import_declaration"}),
    ".go": frozenset({"import_declaration"}),
    ".rs": frozenset({"use_declaration"}),
    ".cs": frozenset({"using_directive"}),
    ".kt": frozenset({"import_header"}),
    ".c": frozenset({"preproc_include"}),
    ".cpp": frozenset({"preproc_include"}),
    ".h": frozenset({"preproc_include"}),
}

_BRANCH_NODES: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "if_statement", "elif_clause", "for_statement", "while_statement",
        "except_clause", "conditional_expression",
    }),
    ".js": frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "catch_clause", "switch_case",
        "ternary_expression",
    }),
    ".jsx": frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "catch_clause", "switch_case",
        "ternary_expression",
    }),
    ".ts": frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "catch_clause", "switch_case",
        "ternary_expression",
    }),
    ".tsx": frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "catch_clause", "switch_case",
        "ternary_expression",
    }),
    ".java": frozenset({
        "if_statement", "for_statement", "while_statement",
        "catch_clause", "switch_expression", "ternary_expression",
    }),
    ".go": frozenset({
        "if_statement", "for_statement", "case_clause",
    }),
    ".rs": frozenset({
        "if_expression", "for_expression", "while_expression",
        "loop_expression", "match_expression", "match_arm",
    }),
    ".cs": frozenset({
        "if_statement", "for_statement", "while_statement",
        "catch_clause", "switch_statement", "switch_expression",
    }),
    ".kt": frozenset({
        "if_expression", "for_statement", "while_statement",
        "catch_block", "when_expression", "when_entry",
    }),
    ".c": frozenset({
        "if_statement", "for_statement", "while_statement",
        "switch_statement", "case_statement",
    }),
    ".cpp": frozenset({
        "if_statement", "for_statement", "while_statement",
        "catch_clause", "switch_statement", "case_statement",
    }),
    ".h": frozenset({
        "if_statement", "for_statement", "while_statement",
        "switch_statement", "case_statement",
    }),
}

_BOOLEAN_OPERATOR_NODES: dict[str, frozenset[str]] = {
    ".py": frozenset({"boolean_operator"}),
    ".js": frozenset({}),
    ".jsx": frozenset({}),
    ".ts": frozenset({}),
    ".tsx": frozenset({}),
    ".java": frozenset({}),
    ".go": frozenset({}),
    ".rs": frozenset({}),
    ".cs": frozenset({}),
    ".kt": frozenset({}),
    ".c": frozenset({}),
    ".cpp": frozenset({}),
    ".h": frozenset({}),
}

_ANNOTATION_NODES: dict[str, frozenset[str]] = {
    ".py": frozenset({"decorator"}),
    ".java": frozenset({"marker_annotation", "annotation"}),
    ".kt": frozenset({"annotation"}),
    ".cs": frozenset({"attribute"}),
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
    suggestions: tuple[str, ...] = ()


def _node_text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _collect_nodes(
    root: Any,
    target_types: frozenset[str],
) -> list[Any]:
    """Walk AST and collect all nodes matching target types."""
    results: list[Any] = []
    def _walk(node: Any) -> None:
        if node.type in target_types:
            results.append(node)
        for child in node.children:
            _walk(child)
    _walk(root)
    return results


def _count_boolean_operators(root: Any, ext: str, source: bytes) -> int:
    """Count && and || operators that contribute to cyclomatic complexity."""
    if ext not in _BOOLEAN_OPERATOR_NODES or not _BOOLEAN_OPERATOR_NODES[ext]:
        # For JS/TS/Java/C/C++: count binary_expression with && or ||
        ops: set[int] = set()
        def _walk_ops(node: Any) -> None:
            if node.type == "binary_expression":
                for child in node.children:
                    t = _node_text(child, source) if child.child_count == 0 else ""
                    if t in ("&&", "||", "and", "or"):
                        ops.add(id(node))
            for child in node.children:
                _walk_ops(child)
        _walk_ops(root)
        return len(ops)
    # Python: count boolean_operator nodes (each is one extra branch)
    return len(_collect_nodes(root, _BOOLEAN_OPERATOR_NODES[ext]))


class HealthScorer(BaseAnalyzer):
    """Score files based on maintainability metrics using AST analysis."""

    GRADE_THRESHOLDS: list[tuple[int, str]] = [
        (90, "A"),
        (75, "B"),
        (60, "C"),
        (40, "D"),
    ]

    SUPPORTED_EXTENSIONS: set[str] = {
        ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
        ".go", ".rs", ".cs", ".kt", ".c", ".cpp", ".h",
    }

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__()
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()

    def score_all(self) -> list[FileHealthScore]:
        """Score all source files in the project."""
        scores: list[FileHealthScore] = []
        for ext in sorted(self.SUPPORTED_EXTENSIONS):
            for file_path in sorted(self.project_root.rglob(f"*{ext}")):
                rel = str(file_path.relative_to(self.project_root))
                scores.append(self.score_file(rel))
        return scores

    def score_file(self, file_path: str) -> FileHealthScore:
        """Score a single file using AST-based metrics."""
        full_path = self.project_root / file_path
        ext = Path(file_path).suffix.lower()

        if ext not in self.SUPPORTED_EXTENSIONS:
            return FileHealthScore(
                file_path=file_path, score=0, grade="F",
                lines=0, methods=0, imports=0,
                cyclomatic_complexity=0, avg_function_length=0.0,
                breakdown={},
            )

        try:
            source = full_path.read_bytes()
        except OSError:
            return FileHealthScore(
                file_path=file_path, score=0, grade="F",
                lines=0, methods=0, imports=0,
                cyclomatic_complexity=0, avg_function_length=0.0,
                breakdown={},
            )

        text = source.decode("utf-8", errors="replace")
        lines = text.count("\n") + (0 if text.endswith("\n") else 1) if text else 0

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return self._regex_fallback(file_path, text, lines)

        tree = parser.parse(source)
        root = tree.root_node

        func_types = _FUNCTION_NODES.get(ext, frozenset())
        import_types = _IMPORT_NODES.get(ext, frozenset())
        branch_types = _BRANCH_NODES.get(ext, frozenset())
        annotation_types = _ANNOTATION_NODES.get(ext, frozenset())

        func_nodes = _collect_nodes(root, func_types)
        import_nodes = _collect_nodes(root, import_types)
        branch_nodes = _collect_nodes(root, branch_types)
        annotation_nodes = _collect_nodes(root, annotation_types)
        bool_op_count = _count_boolean_operators(root, ext, source)

        methods = len(func_nodes)
        imports = len(import_nodes)
        branches = len(branch_nodes) + bool_op_count
        cyclomatic = branches + 1
        annotations = len(annotation_nodes)

        avg_func_len = self._compute_avg_function_length(func_nodes, source, lines)

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

        suggestions = self._generate_suggestions(
            breakdown, lines, methods, cyclomatic, avg_func_len,
        )

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
            suggestions=tuple(suggestions),
        )

    def _compute_avg_function_length(
        self,
        func_nodes: list[Any],
        source: bytes,
        total_lines: int,
    ) -> float:
        """Compute average function length from AST node positions."""
        if not func_nodes:
            return 0.0

        lengths: list[int] = []
        for node in func_nodes:
            start_line = node.start_point[0]
            end_line = node.end_point[0]
            length = end_line - start_line + 1
            lengths.append(length)

        return sum(lengths) / len(lengths)

    def _regex_fallback(
        self, file_path: str, text: str, lines: int,
    ) -> FileHealthScore:
        """Fallback for unsupported languages or missing parsers."""
        return FileHealthScore(
            file_path=file_path,
            score=0,
            grade="F",
            lines=lines,
            methods=0,
            imports=0,
            cyclomatic_complexity=0,
            avg_function_length=0.0,
            breakdown={"size_penalty": min(lines // 10, 30)},
        )

    def _generate_suggestions(
        self,
        breakdown: dict[str, int],
        lines: int,
        methods: int,
        cyclomatic: int,
        avg_func_len: float,
    ) -> list[str]:
        """Generate actionable suggestions based on penalty breakdown."""
        suggestions: list[str] = []

        if breakdown.get("size_penalty", 0) >= 15:
            suggestions.append(
                f"File has {lines} lines (penalty={breakdown['size_penalty']}). "
                "Split into smaller modules with single responsibility."
            )

        if breakdown.get("complexity_penalty", 0) >= 10:
            suggestions.append(
                f"File has {methods} methods (penalty={breakdown['complexity_penalty']}). "
                "Extract related methods into separate service classes."
            )

        if breakdown.get("coupling_penalty", 0) >= 10:
            suggestions.append(
                f"High import count (penalty={breakdown['coupling_penalty']}). "
                "Reduce dependencies by using dependency injection or facade patterns."
            )

        if cyclomatic >= 10:
            suggestions.append(
                f"Cyclomatic complexity is {cyclomatic}. "
                "Simplify branching logic with early returns, guard clauses, or strategy pattern."
            )

        if avg_func_len >= 30:
            suggestions.append(
                f"Average function length is {avg_func_len:.0f} lines. "
                "Break long functions into smaller, named helper functions."
            )

        if breakdown.get("branch_penalty", 0) >= 10:
            suggestions.append(
                "High branch density detected. "
                "Consider using polymorphism or lookup tables instead of conditional chains."
            )

        if lines > 0 and methods > 0 and lines / methods > 80:
            suggestions.append(
                f"Methods average {lines / methods:.0f} lines each. "
                "Target 20-30 lines per method for better readability."
            )

        return suggestions

    def _grade(self, score: int) -> str:
        """Convert numeric score to letter grade."""
        for threshold, grade in self.GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return "F"
