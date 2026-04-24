"""Exception Signature Analyzer.

Extracts the "exception signature" of each function — the set of exception
types that can escape (are not caught internally) — and checks whether
they are documented in docstrings / JSDoc / Javadoc.

Finding types:
- undocumented_exception (medium): function raises X but doc doesn't mention it
- exception_signature (info): complete exception signature for a function

Supports Python, JavaScript/TypeScript, Java, Go (partial).
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


class FindingType(Enum):
    UNDOCUMENTED_EXCEPTION = "undocumented_exception"
    EXCEPTION_SIGNATURE = "exception_signature"


class Severity(Enum):
    MEDIUM = "medium"
    INFO = "info"


@dataclass(frozen=True)
class ExceptionSignatureIssue:
    finding_type: str
    severity: str
    message: str
    file_path: str
    line_number: int
    end_line: int
    code_snippet: str
    suggestion: str
    language: str
    function_name: str
    exception_types: tuple[str, ...] = ()


@dataclass
class ExceptionSignatureResult:
    file_path: str
    total_findings: int = 0
    issues: list[ExceptionSignatureIssue] = field(default_factory=list)
    by_type: dict[str, int] = field(default_factory=dict)
    functions_scanned: int = 0

    def add_finding(self, issue: ExceptionSignatureIssue) -> None:
        self.issues.append(issue)
        self.total_findings += 1
        self.by_type[issue.finding_type] = (
            self.by_type.get(issue.finding_type, 0) + 1
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_findings": self.total_findings,
            "functions_scanned": self.functions_scanned,
            "by_type": dict(self.by_type),
            "issues": [
                {
                    "finding_type": i.finding_type,
                    "severity": i.severity,
                    "message": i.message,
                    "line_number": i.line_number,
                    "end_line": i.end_line,
                    "code_snippet": i.code_snippet,
                    "suggestion": i.suggestion,
                    "language": i.language,
                    "function_name": i.function_name,
                    "exception_types": list(i.exception_types),
                }
                for i in self.issues
            ],
        }


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line(node: tree_sitter.Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: tree_sitter.Node) -> int:
    return node.end_point[0] + 1


def _extract_python_exception_type(
    raise_node: tree_sitter.Node, source: bytes
) -> str:
    """Extract the exception type name from a Python raise statement."""
    for child in raise_node.children:
        if child.type == "call":
            for c in child.children:
                if c.type == "identifier" or c.type == "attribute":
                    return _node_text(c, source)
        elif child.type == "identifier":
            return _node_text(child, source)
        elif child.type == "string":
            return "Exception"
    return "Exception"


def _extract_js_exception_type(
    throw_node: tree_sitter.Node, source: bytes
) -> str:
    """Extract the exception type name from a JS/TS throw statement."""
    for child in throw_node.children:
        if child.type == "new_expression":
            for c in child.children:
                if c.is_named and c.type in ("identifier", "member_expression"):
                    return _node_text(c, source)
        elif child.type == "identifier":
            return _node_text(child, source)
        elif child.type in ("string", "template_string"):
            return "Error"
    return "Error"


def _extract_java_exception_type(
    throw_node: tree_sitter.Node, source: bytes
) -> str:
    """Extract the exception type name from a Java throw statement."""
    for child in throw_node.children:
        if child.type == "object_creation_expression":
            for c in child.children:
                if c.type == "type_identifier":
                    return _node_text(c, source)
        elif child.type == "identifier":
            return _node_text(child, source)
    return "Exception"


def _normalize_exception_name(name: str) -> str:
    """Normalize exception names for matching (strip module path, etc.)."""
    if "." in name:
        return name.rsplit(".", 1)[-1]
    return name


def _is_exception_caught(
    exc_name: str,
    caught_types: list[str],
    is_catch_all: bool,
) -> bool:
    """Check if an exception type is caught by a catch/except clause."""
    if is_catch_all:
        return True
    normalized = _normalize_exception_name(exc_name)
    for ct in caught_types:
        if _normalize_exception_name(ct) == normalized:
            return True
    return False


# --- Docstring / JSDoc exception extraction ---

_PYTHON_RAISES_RE = re.compile(
    r":raises?\s+(\w+)", re.IGNORECASE
)
_PYTHON_RAISES_BRACKET_RE = re.compile(
    r":raises?\s+\{?(\w+)\}?", re.IGNORECASE
)
_PYTHON_EXC_TAG_RE = re.compile(
    r":exc:\x60(\w+)\x60", re.IGNORECASE
)

_JSDOC_THROWS_RE = re.compile(
    r"@throws?\s*\{(\w+)\}", re.IGNORECASE
)

_JAVADOC_THROWS_RE = re.compile(
    r"@throws?\s+(\w+)", re.IGNORECASE
)


def _extract_python_documented_exceptions(
    func_node: tree_sitter.Node, source: bytes
) -> set[str]:
    """Extract exception types documented in Python docstring."""
    expr_stmt = None
    first_child = func_node.children[0] if func_node.children else None
    if first_child and first_child.type == "decorator":
        for c in func_node.children:
            if c.type != "decorator":
                first_child = c
                break

    body = None
    for child in func_node.children:
        if child.type == "block":
            body = child
            break
    if body is None:
        return set()

    first_stmt = body.children[0] if body.children else None
    if first_stmt is None:
        return set()

    if first_stmt.type == "expression_statement":
        expr_stmt = first_stmt
    if expr_stmt is None:
        return set()

    for child in expr_stmt.children:
        if child.type == "string":
            doc = _node_text(child, source).strip("\"' \n")
            result: set[str] = set()
            for m in _PYTHON_RAISES_RE.finditer(doc):
                result.add(m.group(1))
            for m in _PYTHON_RAISES_BRACKET_RE.finditer(doc):
                result.add(m.group(1))
            for m in _PYTHON_EXC_TAG_RE.finditer(doc):
                result.add(m.group(1))
            return result
    return set()


def _extract_js_documented_exceptions(
    func_node: tree_sitter.Node, source: bytes
) -> set[str]:
    """Extract exception types documented in JSDoc @throws."""
    prev = func_node.prev_named_sibling
    if prev is None:
        prev = func_node.prev_sibling
    if prev is None or prev.type != "comment":
        return set()

    doc = _node_text(prev, source)
    result: set[str] = set()
    for m in _JSDOC_THROWS_RE.finditer(doc):
        result.add(m.group(1))
    return result


def _extract_java_documented_exceptions(
    func_node: tree_sitter.Node, source: bytes
) -> set[str]:
    """Extract exception types documented in Javadoc @throws."""
    prev = func_node.prev_named_sibling
    if prev is None:
        prev = func_node.prev_sibling
    if prev is None or prev.type != "block_comment":
        return set()

    doc = _node_text(prev, source)
    result: set[str] = set()
    for m in _JAVADOC_THROWS_RE.finditer(doc):
        result.add(m.group(1))
    return result


class ExceptionSignatureAnalyzer(BaseAnalyzer):
    """Analyzes functions to extract exception signatures and check documentation."""

    def __init__(
        self,
        project_root: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()
        super().__init__()

    def _run_query(
        self,
        language: Any,
        query_string: str,
        root_node: Any,
    ) -> list[tuple[Any, str]]:
        return TreeSitterQueryCompat.execute_query(
            language, query_string, root_node
        )

    def analyze_file(self, file_path: str | Path) -> ExceptionSignatureResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            return ExceptionSignatureResult(file_path=str(path))

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ExceptionSignatureResult(file_path=str(path))

        try:
            source = path.read_bytes()
        except OSError as e:
            logger.debug(f"Cannot read {path}: {e}")
            return ExceptionSignatureResult(file_path=str(path))

        tree = parser.parse(source)
        result = ExceptionSignatureResult(file_path=str(path))

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
    ) -> list[ExceptionSignatureResult]:
        root = Path(root) if root else self.project_root
        exclude = set(exclude_patterns or []) | {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        }
        results: list[ExceptionSignatureResult] = []
        for path in sorted(root.rglob("*")):
            if any(part in exclude for part in path.parts):
                continue
            if path.suffix in self.SUPPORTED_EXTENSIONS and path.is_file():
                result = self.analyze_file(path)
                if result.total_findings > 0:
                    results.append(result)
        return results

    # --- Python ---

    def _analyze_python(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ExceptionSignatureResult,
    ) -> None:
        func_nodes: list[tree_sitter.Node] = []
        self._collect_python_functions(tree.root_node, func_nodes)
        result.functions_scanned = len(func_nodes)

        for func in func_nodes:
            func_name = self._python_func_name(func, source)
            body = self._get_body(func)
            if body is None:
                continue

            catch_contexts = self._collect_python_catch_contexts(body, source)
            escaping = self._collect_python_escaping_exceptions(
                body, catch_contexts, source
            )

            if not escaping:
                continue

            exc_types = tuple(sorted(escaping))
            snippet = _node_text(func, source).split("\n")[0][:120]
            result.add_finding(ExceptionSignatureIssue(
                finding_type=FindingType.EXCEPTION_SIGNATURE.value,
                severity=Severity.INFO.value,
                message=f"{func_name} can throw: {', '.join(exc_types)}",
                file_path=file_path,
                line_number=_line(func),
                end_line=_end_line(func),
                code_snippet=snippet,
                suggestion="Document these exceptions in the docstring with :raises",
                language="python",
                function_name=func_name,
                exception_types=exc_types,
            ))

            documented = _extract_python_documented_exceptions(func, source)
            undocumented = sorted(escaping - documented)
            if undocumented:
                result.add_finding(ExceptionSignatureIssue(
                    finding_type=FindingType.UNDOCUMENTED_EXCEPTION.value,
                    severity=Severity.MEDIUM.value,
                    message=(
                        f"{func_name} raises {', '.join(undocumented)}"
                        f" but they are not documented in docstring"
                    ),
                    file_path=file_path,
                    line_number=_line(func),
                    end_line=_end_line(func),
                    code_snippet=snippet,
                    suggestion=(
                        "Add to docstring: "
                        + ", ".join(f":raises {e}:" for e in undocumented)
                    ),
                    language="python",
                    function_name=func_name,
                    exception_types=tuple(undocumented),
                ))

    def _collect_python_functions(
        self, node: tree_sitter.Node, out: list[tree_sitter.Node]
    ) -> None:
        if node.type in ("function_definition", "method"):
            out.append(node)
        for child in node.children:
            if child.type in ("lambda",):
                continue
            self._collect_python_functions(child, out)

    def _python_func_name(
        self, func: tree_sitter.Node, source: bytes
    ) -> str:
        for child in func.children:
            if child.type == "identifier":
                return _node_text(child, source)
        return "<anonymous>"

    def _get_body(self, func: tree_sitter.Node) -> tree_sitter.Node | None:
        for child in func.children:
            if child.type in ("block", "statement_block", "constructor_body"):
                return child
        return None

    def _collect_python_catch_contexts(
        self, body: tree_sitter.Node, source: bytes
    ) -> list[tuple[int, int, list[str], bool]]:
        """Collect (start_byte, end_byte, caught_types, is_catch_all) for each try."""
        contexts: list[tuple[int, int, list[str], bool]] = []
        self._walk_python_try(body, source, contexts)
        return contexts

    def _walk_python_try(
        self,
        node: tree_sitter.Node,
        source: bytes,
        out: list[tuple[int, int, list[str], bool]],
    ) -> None:
        if node.type == "try_statement":
            all_caught_types: list[str] = []
            any_catch_all = False
            for child in node.children:
                if child.type != "except_clause":
                    continue
                caught_types: list[str] = []
                is_catch_all = True
                for ec in child.children:
                    if not ec.is_named or ec.type == "block":
                        continue
                    is_catch_all = False
                    if ec.type == "identifier":
                        caught_types.append(_node_text(ec, source))
                    elif ec.type == "as_pattern":
                        for gc in ec.children:
                            if gc.type == "identifier":
                                caught_types.append(_node_text(gc, source))
                            elif gc.type == "tuple":
                                for tc in gc.children:
                                    if tc.type == "identifier":
                                        caught_types.append(_node_text(tc, source))
                    elif ec.type == "tuple":
                        for tc in ec.children:
                            if tc.type == "identifier":
                                caught_types.append(_node_text(tc, source))
                if is_catch_all:
                    any_catch_all = True
                all_caught_types.extend(caught_types)

            out.append((
                node.start_byte,
                node.end_byte,
                all_caught_types,
                any_catch_all,
            ))

        for child in node.children:
            self._walk_python_try(child, source, out)

    def _collect_python_escaping_exceptions(
        self,
        body: tree_sitter.Node,
        catch_contexts: list[tuple[int, int, list[str], bool]],
        source: bytes,
    ) -> set[str]:
        """Walk body, find raise statements, check if they escape."""
        escaping: set[str] = set()
        self._walk_python_raises(
            body, catch_contexts, source, escaping
        )
        return escaping

    def _walk_python_raises(
        self,
        node: tree_sitter.Node,
        catch_contexts: list[tuple[int, int, list[str], bool]],
        source: bytes,
        escaping: set[str],
    ) -> None:
        if node.type == "raise_statement":
            exc_type = _extract_python_exception_type(node, source)
            normalized = _normalize_exception_name(exc_type)
            is_caught = False
            for start, end, caught, is_all in catch_contexts:
                if start <= node.start_byte < end:
                    if _is_exception_caught(normalized, caught, is_all):
                        is_caught = True
                        break
            if not is_caught:
                escaping.add(normalized)

        for child in node.children:
            if child.type in ("function_definition", "class_definition", "lambda"):
                continue
            self._walk_python_raises(child, catch_contexts, source, escaping)

    # --- JavaScript / TypeScript ---

    def _analyze_javascript(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ExceptionSignatureResult,
    ) -> None:
        func_nodes: list[tree_sitter.Node] = []
        self._collect_js_functions(tree.root_node, func_nodes)
        result.functions_scanned = len(func_nodes)

        for func in func_nodes:
            func_name = self._js_func_name(func, source)
            body = self._get_body(func)
            if body is None:
                continue

            catch_contexts = self._collect_js_catch_contexts(body)
            escaping = self._collect_js_escaping_exceptions(
                body, catch_contexts, source
            )

            if not escaping:
                continue

            exc_types = tuple(sorted(escaping))
            snippet = _node_text(func, source).split("\n")[0][:120]
            result.add_finding(ExceptionSignatureIssue(
                finding_type=FindingType.EXCEPTION_SIGNATURE.value,
                severity=Severity.INFO.value,
                message=f"{func_name} can throw: {', '.join(exc_types)}",
                file_path=file_path,
                line_number=_line(func),
                end_line=_end_line(func),
                code_snippet=snippet,
                suggestion="Document these exceptions with @throws in JSDoc",
                language="javascript",
                function_name=func_name,
                exception_types=exc_types,
            ))

            documented = _extract_js_documented_exceptions(func, source)
            undocumented = sorted(escaping - documented)
            if undocumented:
                result.add_finding(ExceptionSignatureIssue(
                    finding_type=FindingType.UNDOCUMENTED_EXCEPTION.value,
                    severity=Severity.MEDIUM.value,
                    message=(
                        f"{func_name} throws {', '.join(undocumented)}"
                        f" but they are not documented in JSDoc"
                    ),
                    file_path=file_path,
                    line_number=_line(func),
                    end_line=_end_line(func),
                    code_snippet=snippet,
                    suggestion=(
                        "Add to JSDoc: "
                        + ", ".join(
                            f"@throws {{{e}}}" for e in undocumented
                        )
                    ),
                    language="javascript",
                    function_name=func_name,
                    exception_types=tuple(undocumented),
                ))

    def _collect_js_functions(
        self, node: tree_sitter.Node, out: list[tree_sitter.Node]
    ) -> None:
        if node.type in (
            "function_declaration", "function", "arrow_function",
            "method_definition", "generator_function_declaration",
        ):
            out.append(node)
        for child in node.children:
            self._collect_js_functions(child, out)

    def _js_func_name(
        self, func: tree_sitter.Node, source: bytes
    ) -> str:
        for child in func.children:
            if child.type == "identifier" or child.type == "property_identifier":
                return _node_text(child, source)
        return "<anonymous>"

    def _collect_js_catch_contexts(
        self, body: tree_sitter.Node
    ) -> list[tuple[int, int, list[str], bool]]:
        contexts: list[tuple[int, int, list[str], bool]] = []
        self._walk_js_catch(body, contexts)
        return contexts

    def _walk_js_catch(
        self,
        node: tree_sitter.Node,
        out: list[tuple[int, int, list[str], bool]],
    ) -> None:
        if node.type == "try_statement":
            is_catch_all = False
            for child in node.children:
                if child.type == "catch_clause":
                    is_catch_all = True
            out.append((
                node.start_byte, node.end_byte,
                [], is_catch_all,
            ))

        for child in node.children:
            self._walk_js_catch(child, out)

    def _collect_js_escaping_exceptions(
        self,
        body: tree_sitter.Node,
        catch_contexts: list[tuple[int, int, list[str], bool]],
        source: bytes,
    ) -> set[str]:
        escaping: set[str] = set()
        self._walk_js_throws(body, catch_contexts, source, escaping)
        return escaping

    def _walk_js_throws(
        self,
        node: tree_sitter.Node,
        catch_contexts: list[tuple[int, int, list[str], bool]],
        source: bytes,
        escaping: set[str],
    ) -> None:
        if node.type == "throw_statement":
            exc_type = _extract_js_exception_type(node, source)
            normalized = _normalize_exception_name(exc_type)
            is_caught = False
            for start, end, caught, is_all in catch_contexts:
                if start <= node.start_byte < end:
                    if _is_exception_caught(normalized, caught, is_all):
                        is_caught = True
                        break
            if not is_caught:
                escaping.add(normalized)

        for child in node.children:
            if child.type in (
                "function_declaration", "function", "arrow_function",
                "method_definition",
            ):
                continue
            self._walk_js_throws(child, catch_contexts, source, escaping)

    # --- Java ---

    def _analyze_java(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ExceptionSignatureResult,
    ) -> None:
        func_nodes: list[tree_sitter.Node] = []
        self._collect_java_functions(tree.root_node, func_nodes)
        result.functions_scanned = len(func_nodes)

        for func in func_nodes:
            func_name = self._java_func_name(func, source)
            body = self._get_body(func)
            if body is None:
                continue

            catch_contexts = self._collect_java_catch_contexts(body, source)
            escaping = self._collect_java_escaping_exceptions(
                body, catch_contexts, source
            )

            # Remove exceptions already declared in throws clause
            declared = self._java_throws_clause(func, source)
            escaping -= declared

            if not escaping:
                continue

            exc_types = tuple(sorted(escaping))
            snippet = _node_text(func, source).split("\n")[0][:120]
            result.add_finding(ExceptionSignatureIssue(
                finding_type=FindingType.EXCEPTION_SIGNATURE.value,
                severity=Severity.INFO.value,
                message=f"{func_name} can throw: {', '.join(exc_types)}",
                file_path=file_path,
                line_number=_line(func),
                end_line=_end_line(func),
                code_snippet=snippet,
                suggestion="Document these exceptions with @throws in Javadoc",
                language="java",
                function_name=func_name,
                exception_types=exc_types,
            ))

            documented = _extract_java_documented_exceptions(func, source)
            undocumented = sorted(escaping - documented)
            if undocumented:
                result.add_finding(ExceptionSignatureIssue(
                    finding_type=FindingType.UNDOCUMENTED_EXCEPTION.value,
                    severity=Severity.MEDIUM.value,
                    message=(
                        f"{func_name} throws {', '.join(undocumented)}"
                        f" but they are not documented in Javadoc"
                    ),
                    file_path=file_path,
                    line_number=_line(func),
                    end_line=_end_line(func),
                    code_snippet=snippet,
                    suggestion=(
                        "Add to Javadoc: "
                        + ", ".join(
                            f"@throws {e}" for e in undocumented
                        )
                    ),
                    language="java",
                    function_name=func_name,
                    exception_types=tuple(undocumented),
                ))

    def _collect_java_functions(
        self, node: tree_sitter.Node, out: list[tree_sitter.Node]
    ) -> None:
        if node.type in ("method_declaration", "constructor_declaration"):
            out.append(node)
        for child in node.children:
            self._collect_java_functions(child, out)

    def _java_func_name(
        self, func: tree_sitter.Node, source: bytes
    ) -> str:
        for child in func.children:
            if child.type == "identifier":
                return _node_text(child, source)
            if child.type == "constructor_declarator":
                for gc in child.children:
                    if gc.type == "identifier":
                        return _node_text(gc, source)
        return "<constructor>"

    def _java_throws_clause(
        self, func: tree_sitter.Node, source: bytes
    ) -> set[str]:
        for child in func.children:
            if child.type == "throws":
                result: set[str] = set()
                for tc in child.children:
                    if tc.type == "type_identifier":
                        result.add(_normalize_exception_name(
                            _node_text(tc, source)
                        ))
                return result
        return set()

    def _collect_java_catch_contexts(
        self, body: tree_sitter.Node, source: bytes
    ) -> list[tuple[int, int, list[str], bool]]:
        contexts: list[tuple[int, int, list[str], bool]] = []
        self._walk_java_catch(body, source, contexts)
        return contexts

    def _walk_java_catch(
        self,
        node: tree_sitter.Node,
        source: bytes,
        out: list[tuple[int, int, list[str], bool]],
    ) -> None:
        if node.type == "try_statement":
            all_caught_types: list[str] = []
            any_catch_all = False
            for child in node.children:
                if child.type != "catch_clause":
                    continue
                is_catch_all = True
                for cc in child.children:
                    if cc.type == "catch_formal_parameter":
                        is_catch_all = False
                        for pc in cc.children:
                            if pc.type == "catch_type":
                                all_caught_types.append(
                                    _normalize_exception_name(
                                        _node_text(pc, source)
                                    )
                                )
                if is_catch_all:
                    any_catch_all = True

            out.append((
                node.start_byte, node.end_byte,
                all_caught_types, any_catch_all,
            ))

        for child in node.children:
            self._walk_java_catch(child, source, out)

    def _collect_java_escaping_exceptions(
        self,
        body: tree_sitter.Node,
        catch_contexts: list[tuple[int, int, list[str], bool]],
        source: bytes,
    ) -> set[str]:
        escaping: set[str] = set()
        self._walk_java_throws(body, catch_contexts, source, escaping)
        return escaping

    def _walk_java_throws(
        self,
        node: tree_sitter.Node,
        catch_contexts: list[tuple[int, int, list[str], bool]],
        source: bytes,
        escaping: set[str],
    ) -> None:
        if node.type == "throw_statement":
            exc_type = _extract_java_exception_type(node, source)
            normalized = _normalize_exception_name(exc_type)
            is_caught = False
            for start, end, caught, is_all in catch_contexts:
                if start <= node.start_byte < end:
                    if _is_exception_caught(normalized, caught, is_all):
                        is_caught = True
                        break
            if not is_caught:
                escaping.add(normalized)

        for child in node.children:
            if child.type in ("method_declaration", "class_declaration"):
                continue
            self._walk_java_throws(child, catch_contexts, source, escaping)

    # --- Go (partial) ---

    def _analyze_go(
        self,
        language: tree_sitter.Language,
        tree: Tree,
        source: bytes,
        file_path: str,
        result: ExceptionSignatureResult,
    ) -> None:
        func_nodes: list[tree_sitter.Node] = []
        self._collect_go_functions(tree.root_node, func_nodes)
        result.functions_scanned = len(func_nodes)

        for func in func_nodes:
            func_name = self._go_func_name(func, source)
            body = self._get_body(func)
            if body is None:
                continue

            # Go: find panic calls that aren't in a defer/recover
            panics = self._collect_go_panics(body, source)
            if not panics:
                continue

            exc_types = tuple(sorted(panics))
            snippet = _node_text(func, source).split("\n")[0][:120]
            result.add_finding(ExceptionSignatureIssue(
                finding_type=FindingType.EXCEPTION_SIGNATURE.value,
                severity=Severity.INFO.value,
                message=f"{func_name} can panic with: {', '.join(exc_types)}",
                file_path=file_path,
                line_number=_line(func),
                end_line=_end_line(func),
                code_snippet=snippet,
                suggestion="Go does not use exception documentation",
                language="go",
                function_name=func_name,
                exception_types=exc_types,
            ))

    def _collect_go_functions(
        self, node: tree_sitter.Node, out: list[tree_sitter.Node]
    ) -> None:
        if node.type in ("function_declaration", "method_declaration"):
            out.append(node)
        for child in node.children:
            self._collect_go_functions(child, out)

    def _go_func_name(
        self, func: tree_sitter.Node, source: bytes
    ) -> str:
        for child in func.children:
            if child.type == "identifier":
                return _node_text(child, source)
        return "<anonymous>"

    def _collect_go_panics(
        self, body: tree_sitter.Node, source: bytes
    ) -> set[str]:
        panics: set[str] = set()
        self._walk_go_panic(body, source, panics)
        return panics

    def _walk_go_panic(
        self,
        node: tree_sitter.Node,
        source: bytes,
        panics: set[str],
    ) -> None:
        if node.type == "call_expression":
            func_name = None
            for child in node.children:
                if child.type == "identifier":
                    func_name = _node_text(child, source)
                    break
            if func_name == "panic":
                panics.add("panic")
        for child in node.children:
            if child.type in ("function_declaration", "method_declaration"):
                continue
            self._walk_go_panic(child, source, panics)
