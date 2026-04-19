"""Error Handling Pattern Analyzer.

Detects error handling anti-patterns across codebases using AST analysis:

- Bare except / catch-all: except: or catch (e) without type filter
- Swallowed errors: empty except/catch blocks
- Broad exception types: except Exception, catch (Exception e)
- Go-specific: unchecked error returns

Supports Python, JavaScript/TypeScript, Java, and Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

class PatternSeverity(Enum):
    """Severity of error handling anti-pattern."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class PatternType(Enum):
    """Type of error handling anti-pattern."""

    BARE_EXCEPT = "bare_except"
    SWALLOWED_ERROR = "swallowed_error"
    BROAD_EXCEPTION = "broad_exception"
    UNCHECKED_ERROR = "unchecked_error"
    INCONSISTENT_STYLE = "inconsistent_style"
    FINALLY_WITHOUT_HANDLE = "finally_without_handle"

BROAD_EXCEPTION_NAMES: frozenset[str] = frozenset({
    "Exception", "BaseException", "RuntimeException",
    "Error", "Throwable",
})

@dataclass(frozen=True)
class ErrorHandlingIssue:
    """A single error handling anti-pattern detected in code."""

    pattern_type: str
    severity: str
    message: str
    file_path: str
    line_number: int
    end_line: int
    code_snippet: str
    suggestion: str
    language: str
    element_name: str = ""

@dataclass
class ErrorHandlingResult:
    """Aggregated result of error handling analysis."""

    file_path: str
    total_issues: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_pattern: dict[str, int] = field(default_factory=dict)
    issues: list[ErrorHandlingIssue] = field(default_factory=list)

    def add_issue(self, issue: ErrorHandlingIssue) -> None:
        self.issues.append(issue)
        self.total_issues += 1
        self.by_severity[issue.severity] = (
            self.by_severity.get(issue.severity, 0) + 1
        )
        self.by_pattern[issue.pattern_type] = (
            self.by_pattern.get(issue.pattern_type, 0) + 1
        )

def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

def _line(node: tree_sitter.Node) -> int:
    return node.start_point[0] + 1

def _end_line(node: tree_sitter.Node) -> int:
    return node.end_point[0] + 1

def _count_named_children(block_node: tree_sitter.Node, exclude: frozenset[str] = frozenset()) -> int:
    """Count named children excluding certain types."""
    return sum(
        1 for c in block_node.children
        if c.is_named and c.type not in exclude
    )

def _is_only_pass(block_node: tree_sitter.Node) -> bool:
    """Check if block only has pass_statement and comments."""
    for child in block_node.children:
        if child.is_named and child.type not in ("comment", "pass_statement"):
            return False
    return True

class ErrorHandlingAnalyzer(BaseAnalyzer):
    """Analyses error handling patterns in source code using AST."""

    def __init__(
        self,
        project_root: str | Path | None = None,
        severity_threshold: str = "info",
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self.severity_threshold = severity_threshold
        super().__init__()

    def _run_query(
        self,
        language: Any,
        query_string: str,
        root_node: Any,
    ) -> list[tuple[Any, str]]:
        """Execute a tree-sitter query using the compat layer."""
        return TreeSitterQueryCompat.execute_query(
            language, query_string, root_node
        )

    def analyze_file(self, file_path: str | Path) -> ErrorHandlingResult:
        """Analyze a single file for error handling anti-patterns."""
        path = Path(file_path)
        ext = path.suffix
        if ext not in SUPPORTED_EXTENSIONS:
            return ErrorHandlingResult(file_path=str(path))

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ErrorHandlingResult(file_path=str(path))

        try:
            source = path.read_bytes()
        except OSError as e:
            logger.debug(f"Cannot read {path}: {e}")
            return ErrorHandlingResult(file_path=str(path))

        tree = parser.parse(source)
        result = ErrorHandlingResult(file_path=str(path))

        if ext == ".py":
            self._analyze_python(language, tree, source, str(path), result)
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            self._analyze_javascript(language, tree, source, str(path), result)
        elif ext == ".java":
            self._analyze_java(language, tree, source, str(path), result)
        elif ext == ".go":
            self._analyze_go(language, tree, source, str(path), result)

        return result

    def analyze_project(
        self,
        root: str | Path | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> list[ErrorHandlingResult]:
        """Analyze all supported files in a project."""
        root = Path(root) if root else self.project_root
        exclude = set(exclude_patterns or []) | {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        }

        results: list[ErrorHandlingResult] = []
        for path in sorted(root.rglob("*")):
            if any(part in exclude for part in path.parts):
                continue
            if path.suffix in SUPPORTED_EXTENSIONS and path.is_file():
                result = self.analyze_file(path)
                if result.total_issues > 0:
                    results.append(result)

        return results

    # --- Python ---

    def _analyze_python(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        self._detect_python_bare_excepts(language, tree, source, file_path, result)
        self._detect_python_swallowed_errors(language, tree, source, file_path, result)
        self._detect_python_broad_exceptions(language, tree, source, file_path, result)

    def _detect_python_bare_excepts(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect bare except: clauses without exception type."""
        captures = self._run_query(
            language, "(except_clause) @except_clause", tree.root_node
        )
        for node, tag in captures:
            if tag != "except_clause":
                continue

            # bare except has no named children for exception type (only block)
            has_type = any(
                c.is_named and c.type != "block"
                for c in node.children
            )
            if not has_type:
                snippet = _node_text(node, source).split("\n")[0]
                result.add_issue(ErrorHandlingIssue(
                    pattern_type=PatternType.BARE_EXCEPT.value,
                    severity=PatternSeverity.ERROR.value,
                    message="Bare except clause without exception type",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_line(node),
                    code_snippet=snippet[:120],
                    suggestion="Specify exception type: except ValueError as e:",
                    language="python",
                ))

    def _detect_python_swallowed_errors(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect empty except blocks (only pass/comments)."""
        captures = self._run_query(
            language,
            "(except_clause (block) @body) @clause",
            tree.root_node,
        )
        # Group captures by parent clause
        clauses: dict[int, tree_sitter.Node] = {}
        bodies: dict[int, tree_sitter.Node] = {}
        for node, tag in captures:
            if tag == "clause":
                clauses[id(node)] = node
            elif tag == "body":
                bodies[id(node)] = node

        for _clause_id, clause_node in clauses.items():
            # Find the body that belongs to this clause
            body_node = None
            for child in clause_node.children:
                if child.type == "block":
                    body_node = child
                    break
            if body_node is None:
                continue

            if _is_only_pass(body_node):
                snippet = _node_text(clause_node, source).split("\n")[0]
                result.add_issue(ErrorHandlingIssue(
                    pattern_type=PatternType.SWALLOWED_ERROR.value,
                    severity=PatternSeverity.WARNING.value,
                    message="Empty except block (only pass/comment)",
                    file_path=file_path,
                    line_number=_line(clause_node),
                    end_line=_end_line(body_node),
                    code_snippet=snippet[:120],
                    suggestion="Log the error or re-raise: logger.error(...)",
                    language="python",
                ))

    def _detect_python_broad_exceptions(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect overly broad exception types like except Exception."""
        captures = self._run_query(
            language,
            "(except_clause) @clause",
            tree.root_node,
        )
        for node, tag in captures:
            if tag != "clause":
                continue

            # Find exception type: direct identifier, or inside as_pattern
            exc_type = ""
            for child in node.children:
                if not child.is_named or child.type == "block":
                    continue
                if child.type == "identifier":
                    exc_type = _node_text(child, source)
                    break
                elif child.type == "as_pattern":
                    for gc in child.children:
                        if gc.type == "identifier":
                            exc_type = _node_text(gc, source)
                            break
                    break
                elif child.type == "tuple":
                    break

            if not exc_type or exc_type not in BROAD_EXCEPTION_NAMES:
                continue

            snippet = _node_text(node, source).split("\n")[0]
            result.add_issue(ErrorHandlingIssue(
                pattern_type=PatternType.BROAD_EXCEPTION.value,
                severity=PatternSeverity.WARNING.value,
                message=f"Broad exception type: except {exc_type}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_line(node),
                code_snippet=snippet[:120],
                suggestion=f"Catch specific exceptions instead of {exc_type}",
                language="python",
            ))

    # --- JavaScript / TypeScript ---

    def _analyze_javascript(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        self._detect_js_swallowed_errors(language, tree, source, file_path, result)
        self._detect_js_catch_all(language, tree, source, file_path, result)

    def _detect_js_swallowed_errors(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect empty catch blocks in JS/TS."""
        captures = self._run_query(
            language,
            "(catch_clause (statement_block) @body) @clause",
            tree.root_node,
        )
        for node, tag in captures:
            if tag != "clause":
                continue
            body_node = None
            for child in node.children:
                if child.type == "statement_block":
                    body_node = child
                    break
            if body_node is None:
                continue

            if _count_named_children(body_node, frozenset({"comment"})) == 0:
                snippet = _node_text(node, source).split("\n")[0]
                result.add_issue(ErrorHandlingIssue(
                    pattern_type=PatternType.SWALLOWED_ERROR.value,
                    severity=PatternSeverity.WARNING.value,
                    message="Empty catch block",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_end_line(body_node),
                    code_snippet=snippet[:120],
                    suggestion="Handle the error or re-throw: console.error(e); throw e;",
                    language="javascript",
                ))

    def _detect_js_catch_all(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect catch(e) without type checking."""
        captures = self._run_query(
            language,
            "(catch_clause (identifier) @param (statement_block) @body) @clause",
            tree.root_node,
        )
        for node, tag in captures:
            if tag != "clause":
                continue

            param_node = None
            body_node = None
            for child in node.children:
                if child.type == "identifier" and param_node is None:
                    param_node = child
                elif child.type == "statement_block":
                    body_node = child

            if param_node is None or body_node is None:
                continue

            body_text = _node_text(body_node, source)
            param_name = _node_text(param_node, source)

            if "instanceof" in body_text:
                continue
            if f"{param_name}.constructor" in body_text:
                continue
            # Check if error is accessed (e.g. e.message, e.stack)
            # Use word boundary: look for param_name followed by dot
            if re.search(rf'(?<!\w){re.escape(param_name)}\.', body_text):
                continue

            stmt_count = _count_named_children(body_node, frozenset({"comment"}))
            if 0 < stmt_count <= 2:
                snippet = _node_text(node, source).split("\n")[0]
                result.add_issue(ErrorHandlingIssue(
                    pattern_type=PatternType.BROAD_EXCEPTION.value,
                    severity=PatternSeverity.INFO.value,
                    message=f"catch({param_name}) without type checking",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_line(node),
                    code_snippet=snippet[:120],
                    suggestion="Check error type: if (e instanceof TypeError) ...",
                    language="javascript",
                ))

    # --- Java ---

    def _analyze_java(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        self._detect_java_swallowed_errors(language, tree, source, file_path, result)
        self._detect_java_broad_exceptions(language, tree, source, file_path, result)

    def _detect_java_swallowed_errors(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect empty catch blocks in Java."""
        captures = self._run_query(
            language,
            "(catch_clause (block) @body) @clause",
            tree.root_node,
        )
        for node, tag in captures:
            if tag != "clause":
                continue
            body_node = None
            for child in node.children:
                if child.type == "block":
                    body_node = child
                    break
            if body_node is None:
                continue

            if _count_named_children(body_node, frozenset({"comment"})) == 0:
                snippet = _node_text(node, source).split("\n")[0]
                result.add_issue(ErrorHandlingIssue(
                    pattern_type=PatternType.SWALLOWED_ERROR.value,
                    severity=PatternSeverity.WARNING.value,
                    message="Empty catch block",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_end_line(body_node),
                    code_snippet=snippet[:120],
                    suggestion='Log or handle: log.error("message", e);',
                    language="java",
                ))

    def _detect_java_broad_exceptions(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect catch(Exception e) in Java."""
        captures = self._run_query(
            language,
            "(catch_clause) @clause",
            tree.root_node,
        )
        for node, tag in captures:
            if tag != "clause":
                continue

            exc_type = ""
            for child in node.children:
                if child.type == "catch_formal_parameter":
                    for param_child in child.children:
                        if param_child.type == "catch_type":
                            exc_type = _node_text(param_child, source)
                            break
                    break
            if not exc_type or exc_type not in BROAD_EXCEPTION_NAMES:
                continue

            snippet = _node_text(node, source).split("\n")[0]
            result.add_issue(ErrorHandlingIssue(
                pattern_type=PatternType.BROAD_EXCEPTION.value,
                severity=PatternSeverity.WARNING.value,
                message=f"catch({exc_type} e) catches too broadly",
                file_path=file_path,
                line_number=_line(node),
                end_line=_line(node),
                code_snippet=snippet[:120],
                suggestion=f"Catch specific exceptions instead of {exc_type}",
                language="java",
            ))

    # --- Go ---

    def _analyze_go(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        self._detect_go_unchecked_errors(language, tree, source, file_path, result)

    def _detect_go_unchecked_errors(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect err := doSomething() without subsequent if err != nil check."""
        # Collect lines with if err != nil checks
        err_check_lines: set[int] = set()

        # Simple form: if err != nil
        captures1 = self._run_query(
            language,
            '(if_statement condition: (binary_expression left: (identifier) @err_name operator: "!=")) @check',
            tree.root_node,
        )
        for node, tag in captures1:
            if tag == "check":
                err_check_lines.add(_line(node))

        # Find short_var_declarations: err := doSomething()
        captures2 = self._run_query(
            language,
            "(short_var_declaration left: (expression_list (identifier) @var_name) right: (expression_list (call_expression))) @decl",
            tree.root_node,
        )
        for node, tag in captures2:
            if tag != "decl":
                continue

            var_name = ""
            for child in node.children:
                if child.type == "expression_list":
                    for ec in child.children:
                        if ec.type == "identifier":
                            var_name = _node_text(ec, source)
                            break

            if var_name not in ("err", "error") and not var_name.endswith("Err"):
                continue

            decl_line = _line(node)
            has_check = any(
                abs(cl - decl_line) <= 5 for cl in err_check_lines
            )
            if not has_check:
                snippet = _node_text(node, source).split("\n")[0]
                result.add_issue(ErrorHandlingIssue(
                    pattern_type=PatternType.UNCHECKED_ERROR.value,
                    severity=PatternSeverity.WARNING.value,
                    message=f"Unchecked error return: {var_name}",
                    file_path=file_path,
                    line_number=decl_line,
                    end_line=decl_line,
                    code_snippet=snippet[:120],
                    suggestion=f"Check error: if {var_name} != nil {{ return {var_name} }}",
                    language="go",
                ))
