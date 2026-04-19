"""Error Propagation Analyzer.

Traces error/exception propagation through code, detecting:
- unhandled_raise: raise/throw not enclosed in try
- unhandled_throw: throw not enclosed in try
- swallowed_no_propagation: catch block that handles but never re-raises
- finally_no_catch: try-finally without catch/except

Supports Python, JavaScript/TypeScript, Java.
"""
from __future__ import annotations

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


class PropagationGapType(Enum):
    UNHANDLED_RAISE = "unhandled_raise"
    UNHANDLED_THROW = "unhandled_throw"
    SWALLOWED_NO_PROPAGATION = "swallowed_no_propagation"
    FINALLY_NO_CATCH = "finally_no_catch"


class RiskLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_GAP_RISK: dict[str, str] = {
    PropagationGapType.UNHANDLED_RAISE.value: RiskLevel.HIGH.value,
    PropagationGapType.UNHANDLED_THROW.value: RiskLevel.HIGH.value,
    PropagationGapType.SWALLOWED_NO_PROPAGATION.value: RiskLevel.MEDIUM.value,
    PropagationGapType.FINALLY_NO_CATCH.value: RiskLevel.LOW.value,
}


@dataclass(frozen=True)
class ErrorPropagationIssue:
    gap_type: str
    severity: str
    message: str
    file_path: str
    line_number: int
    end_line: int
    code_snippet: str
    suggestion: str
    language: str
    exception_types: tuple[str, ...] = ()
    risk_level: str = "medium"
    function_name: str = ""


@dataclass
class ErrorPropagationResult:
    file_path: str
    total_gaps: int = 0
    gaps: list[ErrorPropagationIssue] = field(default_factory=list)
    by_risk_level: dict[str, int] = field(default_factory=dict)
    by_gap_type: dict[str, int] = field(default_factory=dict)

    def add_gap(self, gap: ErrorPropagationIssue) -> None:
        self.gaps.append(gap)
        self.total_gaps += 1
        self.by_risk_level[gap.risk_level] = self.by_risk_level.get(gap.risk_level, 0) + 1
        self.by_gap_type[gap.gap_type] = self.by_gap_type.get(gap.gap_type, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_gaps": self.total_gaps,
            "gaps": [
                {
                    "gap_type": g.gap_type,
                    "severity": g.severity,
                    "message": g.message,
                    "line_number": g.line_number,
                    "end_line": g.end_line,
                    "code_snippet": g.code_snippet,
                    "suggestion": g.suggestion,
                    "language": g.language,
                    "exception_types": list(g.exception_types),
                    "risk_level": g.risk_level,
                    "function_name": g.function_name,
                }
                for g in self.gaps
            ],
            "by_risk_level": dict(self.by_risk_level),
            "by_gap_type": dict(self.by_gap_type),
        }


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line(node: tree_sitter.Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: tree_sitter.Node) -> int:
    return node.end_point[0] + 1


def _enclosing_function(node: tree_sitter.Node) -> str:
    cur = node.parent
    while cur:
        if cur.type in ("function_definition", "method_definition", "method_declaration",
                        "arrow_function", "function_declaration", "generator_function_declaration"):
            for child in cur.children:
                if child.type in ("identifier", "property_identifier"):
                    return _node_text(child, b"")
            return "<anonymous>"
        cur = cur.parent
    return "<module>"


class ErrorPropagationAnalyzer(BaseAnalyzer):
    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}

    def analyze_file(self, file_path: str | Path) -> ErrorPropagationResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            return ErrorPropagationResult(file_path=str(path))

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ErrorPropagationResult(file_path=str(path))

        try:
            source = path.read_bytes()
        except OSError as e:
            logger.debug(f"Cannot read {path}: {e}")
            return ErrorPropagationResult(file_path=str(path))

        tree = parser.parse(source)
        result = ErrorPropagationResult(file_path=str(path))

        if ext == ".py":
            self._analyze_python(language, tree, source, str(path), result)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            self._analyze_javascript(language, tree, source, str(path), result)
        elif ext == ".java":
            self._analyze_java(language, tree, source, str(path), result)

        return result

    def _run_query(
        self, language: Any, query: str, root: Any,
    ) -> list[tuple[Any, str]]:
        return TreeSitterQueryCompat.execute_query(language, query, root)

    # --- Python ---

    def _analyze_python(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        try_nodes = self._collect_try_ranges(language, tree, source, "try_statement", "except_clause")
        self._detect_python_unhandled_raises(language, tree, source, file_path, result, try_nodes)
        self._detect_python_swallowed(language, tree, source, file_path, result)
        self._detect_python_finally_no_catch(language, tree, source, file_path, result)

    def _collect_try_ranges(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        try_type: str,
        catch_type: str,
    ) -> list[tuple[int, int, list[int]]]:
        captures = self._run_query(language, f"({try_type}) @try_node", tree.root_node)
        ranges: list[tuple[int, int, list[int]]] = []
        for node, tag in captures:
            if tag != "try_node":
                continue
            start = node.start_byte
            end = node.end_byte
            catch_starts: list[int] = []
            for child in node.children:
                if child.type == catch_type:
                    catch_starts.append(child.start_byte)
            ranges.append((start, end, catch_starts))
        return ranges

    def _is_inside_try_body(
        self,
        byte_pos: int,
        try_ranges: list[tuple[int, int, list[int]]],
    ) -> bool:
        for start, end, catch_starts in try_ranges:
            if start <= byte_pos < end:
                body_end = catch_starts[0] if catch_starts else end
                if byte_pos < body_end:
                    return True
        return False

    def _detect_python_unhandled_raises(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
        try_ranges: list[tuple[int, int, list[int]]],
    ) -> None:
        captures = self._run_query(language, "(raise_statement) @raise", tree.root_node)
        for node, tag in captures:
            if tag != "raise":
                continue
            if self._is_inside_try_body(node.start_byte, try_ranges):
                continue
            exc_types = self._extract_python_exception_types(node, source)
            snippet = _node_text(node, source).split("\n")[0]
            fn = _enclosing_function(node)
            result.add_gap(ErrorPropagationIssue(
                gap_type=PropagationGapType.UNHANDLED_RAISE.value,
                severity="high",
                message=f"Unhandled raise in {fn}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_line(node),
                code_snippet=snippet[:120],
                suggestion="Wrap in try/except or declare in function signature",
                language="python",
                exception_types=exc_types,
                risk_level=RiskLevel.HIGH.value,
                function_name=fn,
            ))

    def _extract_python_exception_types(
        self, node: tree_sitter.Node, source: bytes,
    ) -> tuple[str, ...]:
        for child in node.children:
            if child.type == "call":
                for cc in child.children:
                    if cc.type == "identifier":
                        return (_node_text(cc, source),)
            elif child.type == "identifier":
                return (_node_text(child, source),)
        return ()

    def _detect_python_swallowed(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        captures = self._run_query(
            language, "(except_clause (block) @body) @clause", tree.root_node,
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
            body_text = _node_text(body_node, source)
            if "raise" in body_text:
                continue
            snippet = _node_text(node, source).split("\n")[0]
            fn = _enclosing_function(node)
            result.add_gap(ErrorPropagationIssue(
                gap_type=PropagationGapType.SWALLOWED_NO_PROPAGATION.value,
                severity="medium",
                message=f"Exception caught but not re-raised in {fn}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_end_line(body_node),
                code_snippet=snippet[:120],
                suggestion="Re-raise the exception or propagate to caller",
                language="python",
                risk_level=RiskLevel.MEDIUM.value,
                function_name=fn,
            ))

    def _detect_python_finally_no_catch(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        captures = self._run_query(language, "(try_statement) @try_node", tree.root_node)
        for node, tag in captures:
            if tag != "try_node":
                continue
            has_except = any(c.type == "except_clause" for c in node.children)
            has_finally = any(c.type == "finally_clause" for c in node.children)
            if has_finally and not has_except:
                snippet = _node_text(node, source).split("\n")[0]
                fn = _enclosing_function(node)
                result.add_gap(ErrorPropagationIssue(
                    gap_type=PropagationGapType.FINALLY_NO_CATCH.value,
                    severity="low",
                    message=f"try-finally without except in {fn}",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_end_line(node),
                    code_snippet=snippet[:120],
                    suggestion="Add except clause to handle errors in finally block",
                    language="python",
                    risk_level=RiskLevel.LOW.value,
                    function_name=fn,
                ))

    # --- JavaScript / TypeScript ---

    def _analyze_javascript(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        try_ranges = self._collect_try_ranges(language, tree, source, "try_statement", "catch_clause")
        self._detect_js_unhandled_throws(language, tree, source, file_path, result, try_ranges)
        self._detect_js_swallowed(language, tree, source, file_path, result)
        self._detect_js_finally_no_catch(language, tree, source, file_path, result)

    def _detect_js_unhandled_throws(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
        try_ranges: list[tuple[int, int, list[int]]],
    ) -> None:
        captures = self._run_query(language, "(throw_statement) @throw", tree.root_node)
        for node, tag in captures:
            if tag != "throw":
                continue
            if self._is_inside_try_body(node.start_byte, try_ranges):
                continue
            exc_types = self._extract_js_exception_types(node, source)
            snippet = _node_text(node, source).split("\n")[0]
            fn = _enclosing_function(node)
            result.add_gap(ErrorPropagationIssue(
                gap_type=PropagationGapType.UNHANDLED_THROW.value,
                severity="high",
                message=f"Unhandled throw in {fn}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_line(node),
                code_snippet=snippet[:120],
                suggestion="Wrap in try/catch or propagate to caller",
                language="javascript",
                exception_types=exc_types,
                risk_level=RiskLevel.HIGH.value,
                function_name=fn,
            ))

    def _extract_js_exception_types(
        self, node: tree_sitter.Node, source: bytes,
    ) -> tuple[str, ...]:
        for child in node.children:
            if child.type == "new_expression":
                for cc in child.children:
                    if cc.type == "identifier":
                        return (_node_text(cc, source),)
            elif child.type == "identifier":
                return (_node_text(child, source),)
        return ()

    def _detect_js_swallowed(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        captures = self._run_query(
            language, "(catch_clause (statement_block) @body) @clause", tree.root_node,
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
            body_text = _node_text(body_node, source)
            if "throw" in body_text:
                continue
            snippet = _node_text(node, source).split("\n")[0]
            fn = _enclosing_function(node)
            result.add_gap(ErrorPropagationIssue(
                gap_type=PropagationGapType.SWALLOWED_NO_PROPAGATION.value,
                severity="medium",
                message=f"Error caught but not re-thrown in {fn}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_end_line(body_node),
                code_snippet=snippet[:120],
                suggestion="Re-throw the error or propagate to caller",
                language="javascript",
                risk_level=RiskLevel.MEDIUM.value,
                function_name=fn,
            ))

    def _detect_js_finally_no_catch(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        captures = self._run_query(language, "(try_statement) @try_node", tree.root_node)
        for node, tag in captures:
            if tag != "try_node":
                continue
            has_catch = any(c.type == "catch_clause" for c in node.children)
            has_finally = any(c.type == "finally_clause" for c in node.children)
            if has_finally and not has_catch:
                snippet = _node_text(node, source).split("\n")[0]
                fn = _enclosing_function(node)
                result.add_gap(ErrorPropagationIssue(
                    gap_type=PropagationGapType.FINALLY_NO_CATCH.value,
                    severity="low",
                    message=f"try-finally without catch in {fn}",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_end_line(node),
                    code_snippet=snippet[:120],
                    suggestion="Add catch clause to handle errors in finally block",
                    language="javascript",
                    risk_level=RiskLevel.LOW.value,
                    function_name=fn,
                ))

    # --- Java ---

    def _analyze_java(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        try_ranges = self._collect_try_ranges(language, tree, source, "try_statement", "catch_clause")
        self._detect_java_unhandled_throws(language, tree, source, file_path, result, try_ranges)
        self._detect_java_swallowed(language, tree, source, file_path, result)
        self._detect_java_finally_no_catch(language, tree, source, file_path, result)

    def _detect_java_unhandled_throws(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
        try_ranges: list[tuple[int, int, list[int]]],
    ) -> None:
        captures = self._run_query(language, "(throw_statement) @throw", tree.root_node)
        for node, tag in captures:
            if tag != "throw":
                continue
            if self._is_inside_try_body(node.start_byte, try_ranges):
                continue
            exc_types = self._extract_java_exception_types(node, source)
            snippet = _node_text(node, source).split("\n")[0]
            fn = _enclosing_function(node)
            result.add_gap(ErrorPropagationIssue(
                gap_type=PropagationGapType.UNHANDLED_THROW.value,
                severity="high",
                message=f"Unhandled throw in {fn}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_line(node),
                code_snippet=snippet[:120],
                suggestion="Wrap in try/catch or declare throws in method signature",
                language="java",
                exception_types=exc_types,
                risk_level=RiskLevel.HIGH.value,
                function_name=fn,
            ))

    def _extract_java_exception_types(
        self, node: tree_sitter.Node, source: bytes,
    ) -> tuple[str, ...]:
        for child in node.children:
            if child.type == "object_creation_expression":
                for cc in child.children:
                    if cc.type == "type_identifier":
                        return (_node_text(cc, source),)
            elif child.type == "identifier":
                return (_node_text(child, source),)
        return ()

    def _detect_java_swallowed(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        captures = self._run_query(
            language, "(catch_clause (block) @body) @clause", tree.root_node,
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
            body_text = _node_text(body_node, source)
            if "throw" in body_text:
                continue
            snippet = _node_text(node, source).split("\n")[0]
            fn = _enclosing_function(node)
            result.add_gap(ErrorPropagationIssue(
                gap_type=PropagationGapType.SWALLOWED_NO_PROPAGATION.value,
                severity="medium",
                message=f"Exception caught but not re-thrown in {fn}",
                file_path=file_path,
                line_number=_line(node),
                end_line=_end_line(body_node),
                code_snippet=snippet[:120],
                suggestion="Re-throw or wrap the exception",
                language="java",
                risk_level=RiskLevel.MEDIUM.value,
                function_name=fn,
            ))

    def _detect_java_finally_no_catch(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ErrorPropagationResult,
    ) -> None:
        captures = self._run_query(language, "(try_statement) @try_node", tree.root_node)
        for node, tag in captures:
            if tag != "try_node":
                continue
            has_catch = any(c.type == "catch_clause" for c in node.children)
            has_finally = any(c.type == "finally_clause" for c in node.children)
            if has_finally and not has_catch:
                snippet = _node_text(node, source).split("\n")[0]
                fn = _enclosing_function(node)
                result.add_gap(ErrorPropagationIssue(
                    gap_type=PropagationGapType.FINALLY_NO_CATCH.value,
                    severity="low",
                    message=f"try-finally without catch in {fn}",
                    file_path=file_path,
                    line_number=_line(node),
                    end_line=_end_line(node),
                    code_snippet=snippet[:120],
                    suggestion="Add catch clause to handle errors",
                    language="java",
                    risk_level=RiskLevel.LOW.value,
                    function_name=fn,
                ))
