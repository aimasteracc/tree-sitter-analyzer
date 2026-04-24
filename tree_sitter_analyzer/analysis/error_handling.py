"""Error Handling Pattern Analyzer.

Detects error handling anti-patterns across codebases using AST analysis:

- Bare except / catch-all: except: or catch (e) without type filter
- Broad exception types: except Exception, catch (Exception e)
- Missing context: raise without preserving original exception chain
- Generic error messages: raise/throw with unhelpful hardcoded strings
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

class PatternSeverity(Enum):
    """Severity of error handling anti-pattern."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class PatternType(Enum):
    """Type of error handling anti-pattern."""

    BARE_EXCEPT = "bare_except"
    BROAD_EXCEPTION = "broad_exception"
    UNCHECKED_ERROR = "unchecked_error"
    MISSING_CONTEXT = "missing_context"
    GENERIC_ERROR_MESSAGE = "generic_error_message"

BROAD_EXCEPTION_NAMES: frozenset[str] = frozenset({
    "Exception", "BaseException", "RuntimeException",
    "Error", "Throwable",
})

GENERIC_MESSAGES: frozenset[str] = frozenset({
    "error", "Error", "ERROR",
    "failed", "Failed", "FAILED",
    "failure", "Failure",
    "exception", "Exception",
    "invalid", "Invalid",
    "bad", "Bad",
    "wrong", "Wrong",
    "oops", "Oops",
    "unknown error",
    "unexpected error",
    "something went wrong",
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
        if ext not in self.SUPPORTED_EXTENSIONS:
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
            if path.suffix in self.SUPPORTED_EXTENSIONS and path.is_file():
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
        self._detect_python_broad_exceptions(language, tree, source, file_path, result)
        self._detect_python_missing_context(tree, source, file_path, result)
        self._detect_python_generic_messages(tree, source, file_path, result)

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

    def _detect_python_missing_context(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect raise inside except without preserving original exception."""
        except_blocks: set[int] = set()

        def find_except_blocks(node: tree_sitter.Node) -> None:
            if node.type == "except_clause":
                except_blocks.add(id(node))
            for child in node.children:
                find_except_blocks(child)

        find_except_blocks(tree.root_node)

        def find_raises_in_except(
            node: tree_sitter.Node, in_except: bool
        ) -> None:
            if node.type == "except_clause":
                in_except = True
            if in_except and node.type == "raise_statement":
                text = _node_text(node, source)
                if "from " not in text and "from\t" not in text:
                    has_bare_raise = any(
                        c.type == "identifier" or c.type == "call"
                        for c in node.children
                    )
                    if has_bare_raise:
                        snippet = text.split("\n")[0]
                        result.add_issue(ErrorHandlingIssue(
                            pattern_type=PatternType.MISSING_CONTEXT.value,
                            severity=PatternSeverity.INFO.value,
                            message="Raise inside except without chaining original exception",
                            file_path=file_path,
                            line_number=_line(node),
                            end_line=_line(node),
                            code_snippet=snippet[:120],
                            suggestion="Chain original: raise NewError(...) from e",
                            language="python",
                        ))
            for child in node.children:
                find_raises_in_except(child, in_except)

        find_raises_in_except(tree.root_node, False)

    def _detect_python_generic_messages(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect raise with generic/unhelpful error messages."""

        def visit(node: tree_sitter.Node) -> None:
            if node.type == "raise_statement":
                for child in node.children:
                    if child.type == "call":
                        for arg in child.children:
                            if arg.type == "argument_list":
                                real_args = [
                                    a for a in arg.children
                                    if a.type not in ("(", ")", ",")
                                ]
                                if real_args:
                                    msg_node = real_args[0]
                                    if msg_node.type == "string":
                                        text = _node_text(
                                            msg_node, source
                                        ).strip("\"'")
                                        if self._is_generic_message(text):
                                            snippet = _node_text(
                                                node, source
                                            ).split("\n")[0]
                                            result.add_issue(
                                                ErrorHandlingIssue(
                                                    pattern_type=(
                                                        PatternType
                                                        .GENERIC_ERROR_MESSAGE
                                                        .value
                                                    ),
                                                    severity=(
                                                        PatternSeverity.INFO
                                                        .value
                                                    ),
                                                    message=(
                                                        f"Generic error message"
                                                        f': "{text}"'
                                                    ),
                                                    file_path=file_path,
                                                    line_number=_line(node),
                                                    end_line=_line(node),
                                                    code_snippet=snippet[:120],
                                                    suggestion=(
                                                        "Include diagnostic"
                                                        " context in error"
                                                        " message"
                                                    ),
                                                    language="python",
                                                )
                                            )
                            elif child.type == "string":
                                text = _node_text(child, source).strip("\"'")
                                if self._is_generic_message(text):
                                    snippet = _node_text(
                                        node, source
                                    ).split("\n")[0]
                                    result.add_issue(ErrorHandlingIssue(
                                        pattern_type=(
                                            PatternType.GENERIC_ERROR_MESSAGE
                                            .value
                                        ),
                                        severity=PatternSeverity.INFO.value,
                                        message=f'Generic error message: "{text}"',
                                        file_path=file_path,
                                        line_number=_line(node),
                                        end_line=_line(node),
                                        code_snippet=snippet[:120],
                                        suggestion=(
                                            "Include diagnostic context"
                                            " in error message"
                                        ),
                                        language="python",
                                    ))
            for child in node.children:
                visit(child)

        visit(tree.root_node)

    @staticmethod
    def _is_generic_message(text: str) -> bool:
        """Check if error message text is generic/unhelpful."""
        stripped = text.strip()
        if not stripped:
            return True
        if stripped.lower() in {m.lower() for m in GENERIC_MESSAGES}:
            return True
        if len(stripped) < 5:
            return True
        return False

    # --- JavaScript / TypeScript ---

    def _analyze_javascript(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        self._detect_js_catch_all(language, tree, source, file_path, result)
        self._detect_js_generic_messages(tree, source, file_path, result)

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

    def _detect_js_generic_messages(
        self,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        """Detect throw with generic/unhelpful error messages."""

        def visit(node: tree_sitter.Node) -> None:
            if node.type == "throw_statement":
                for child in node.children:
                    if child.type == "new_expression":
                        for arg in child.children:
                            if arg.type == "arguments":
                                real_args = [
                                    a for a in arg.children
                                    if a.type not in ("(", ")", ",")
                                ]
                                if real_args and real_args[0].type in (
                                    "string", "template_string"
                                ):
                                    text = _node_text(
                                        real_args[0], source
                                    ).strip("\"'`")
                                    if self._is_generic_message(text):
                                        snippet = _node_text(
                                            node, source
                                        ).split("\n")[0]
                                        result.add_issue(
                                            ErrorHandlingIssue(
                                                pattern_type=(
                                                    PatternType
                                                    .GENERIC_ERROR_MESSAGE
                                                    .value
                                                ),
                                                severity=(
                                                    PatternSeverity.INFO.value
                                                ),
                                                message=(
                                                    f'Generic error message:'
                                                    f' "{text}"'
                                                ),
                                                file_path=file_path,
                                                line_number=_line(node),
                                                end_line=_line(node),
                                                code_snippet=snippet[:120],
                                                suggestion=(
                                                    "Include diagnostic"
                                                    " context in error"
                                                    " message"
                                                ),
                                                language="javascript",
                                            )
                                        )
                    elif child.type in ("string", "template_string"):
                        text = _node_text(child, source).strip("\"'`")
                        if self._is_generic_message(text):
                            snippet = _node_text(
                                node, source
                            ).split("\n")[0]
                            result.add_issue(ErrorHandlingIssue(
                                pattern_type=(
                                    PatternType.GENERIC_ERROR_MESSAGE.value
                                ),
                                severity=PatternSeverity.INFO.value,
                                message=f'Generic error message: "{text}"',
                                file_path=file_path,
                                line_number=_line(node),
                                end_line=_line(node),
                                code_snippet=snippet[:120],
                                suggestion=(
                                    "Include diagnostic context in error"
                                    " message"
                                ),
                                language="javascript",
                            ))
            for c in node.children:
                visit(c)

        visit(tree.root_node)

    # --- Java ---

    def _analyze_java(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorHandlingResult,
    ) -> None:
        self._detect_java_broad_exceptions(language, tree, source, file_path, result)

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
