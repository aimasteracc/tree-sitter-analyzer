"""
Return Path Analyzer.

Detects functions with inconsistent return paths: some branches return a
value while others fall through to implicit None. Catches a common bug
class in dynamically-typed languages where the caller expects a value but
sometimes gets None.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

ISSUE_INCONSISTENT_RETURN = "inconsistent_return"
ISSUE_IMPLICIT_NONE = "implicit_none"
ISSUE_COMPLEX_RETURN_PATH = "complex_return_path"
ISSUE_EMPTY_RETURN = "empty_return"

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

def _severity(issue_type: str) -> str:
    if issue_type == ISSUE_INCONSISTENT_RETURN:
        return SEVERITY_HIGH
    if issue_type == ISSUE_IMPLICIT_NONE:
        return SEVERITY_MEDIUM
    if issue_type == ISSUE_COMPLEX_RETURN_PATH:
        return SEVERITY_LOW
    return SEVERITY_LOW

@dataclass(frozen=True)
class ReturnPoint:
    """A single return/yield/throw statement in a function."""

    line_number: int
    has_value: bool
    node_type: str

@dataclass(frozen=True)
class ReturnPathIssue:
    """A detected return path problem."""

    issue_type: str
    severity: str
    line_number: int
    message: str

@dataclass(frozen=True)
class FunctionReturnPath:
    """Return path analysis of a single function/method."""

    name: str
    start_line: int
    end_line: int
    return_points: tuple[ReturnPoint, ...]
    has_implicit_none: bool
    issues: tuple[ReturnPathIssue, ...]
    element_type: str

    @property
    def return_count(self) -> int:
        return len(self.return_points)

    @property
    def value_returns(self) -> int:
        return sum(1 for r in self.return_points if r.has_value)

    @property
    def empty_returns(self) -> int:
        return sum(1 for r in self.return_points if not r.has_value)

@dataclass(frozen=True)
class ReturnPathResult:
    """Aggregated return path result for a file."""

    functions: tuple[FunctionReturnPath, ...]
    total_functions: int
    functions_with_issues: int
    total_issues: int
    file_path: str

    def get_functions_with_issues(self) -> list[FunctionReturnPath]:
        return [f for f in self.functions if f.issues]

class ReturnPathAnalyzer(BaseAnalyzer):
    """Analyzes return paths of functions in source code."""

    def analyze_file(self, file_path: Path | str) -> ReturnPathResult:
        path = Path(file_path)
        if not path.exists():
            return ReturnPathResult(
                functions=(),
                total_functions=0,
                functions_with_issues=0,
                total_issues=0,
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return ReturnPathResult(
                functions=(),
                total_functions=0,
                functions_with_issues=0,
                total_issues=0,
                file_path=str(path),
            )

        functions = self._extract_functions(path, ext)
        total = len(functions)
        with_issues = sum(1 for f in functions if f.issues)
        total_issues = sum(len(f.issues) for f in functions)

        return ReturnPathResult(
            functions=tuple(functions),
            total_functions=total,
            functions_with_issues=with_issues,
            total_issues=total_issues,
            file_path=str(path),
        )

    def _extract_functions(self, path: Path, ext: str) -> list[FunctionReturnPath]:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        content = path.read_bytes()
        tree = parser.parse(content)

        if ext == ".py":
            return self._extract_python(tree.root_node, content)
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._extract_js(tree.root_node, content)
        if ext == ".java":
            return self._extract_java(tree.root_node, content)
        if ext == ".go":
            return self._extract_go(tree.root_node, content)
        return []

    # ── Return path extraction helper ──────────────────────────────────

    def _collect_returns(
        self,
        body: tree_sitter.Node,
        content: bytes,
        return_types: frozenset[str],
        yield_types: frozenset[str] | None = None,
    ) -> tuple[list[ReturnPoint], bool]:
        """Collect all return/yield statements in a function body.

        Returns (return_points, has_implicit_none).
        has_implicit_none is True if the function can reach the end without
        an explicit return statement.
        """
        points: list[ReturnPoint] = []

        def walk(n: tree_sitter.Node, depth: int) -> bool:
            """Walk AST, collecting return points. Returns True if all paths
            return explicitly (no implicit None possible)."""
            if n.type in return_types:
                has_val = self._return_has_value(n, content)
                points.append(
                    ReturnPoint(
                        line_number=n.start_point[0] + 1,
                        has_value=has_val,
                        node_type=n.type,
                    )
                )
                return True

            if yield_types and n.type in yield_types:
                points.append(
                    ReturnPoint(
                        line_number=n.start_point[0] + 1,
                        has_value=True,
                        node_type=n.type,
                    )
                )
                # yield doesn't terminate the function
                return False

            # For compound statements, check if all branches return
            if n.type in {"if_statement", "elif_clause"}:
                return self._check_branch_returns(n, content, return_types, yield_types, points)

            if n.type in {"try_statement", "try_with_resources_statement"}:
                return self._check_try_returns(n, content, return_types, yield_types, points)

            if n.type in {"for_statement", "while_statement", "do_statement"}:
                # Loops don't guarantee execution
                for child in n.children:
                    walk(child, depth + 1)
                return False

            # Block / statement_list: if ANY child guarantees return,
            # the block guarantees return (sequential execution can't skip it)
            if n.type in {"block", "statement_block", "compound_statement"}:
                any_returns = False
                for child in n.children:
                    child_returns = walk(child, depth + 1)
                    if child_returns:
                        any_returns = True
                return any_returns

            # Default: recurse into children, but doesn't guarantee return itself
            for child in n.children:
                walk(child, depth + 1)
            return False

        all_paths_return = walk(body, 0)
        has_implicit_none = not all_paths_return and len(points) > 0

        return points, has_implicit_none

    def _return_has_value(self, node: tree_sitter.Node, content: bytes) -> bool:
        """Check if a return statement has a value argument."""
        for child in node.children:
            if child.is_named and child.type not in (";", "\n"):
                return True
        return False

    def _check_branch_returns(
        self,
        node: tree_sitter.Node,
        content: bytes,
        return_types: frozenset[str],
        yield_types: frozenset[str] | None,
        points: list[ReturnPoint],
    ) -> bool:
        """Check if if/elif branches all return. Returns True if all paths return."""
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")

        cons_returns = False
        alt_returns = False

        if consequence:
            cons_returns = self._walk_for_returns(consequence, content, return_types, yield_types, points)

        if alternative:
            if alternative.type == "elif_clause" or alternative.type == "if_statement":
                alt_returns = self._check_branch_returns(
                    alternative, content, return_types, yield_types, points
                )
            else:
                alt_returns = self._walk_for_returns(alternative, content, return_types, yield_types, points)

        # All paths return only if both branches exist and both return
        if consequence and alternative:
            return cons_returns and alt_returns
        return False

    def _check_try_returns(
        self,
        node: tree_sitter.Node,
        content: bytes,
        return_types: frozenset[str],
        yield_types: frozenset[str] | None,
        points: list[ReturnPoint],
    ) -> bool:
        """Check try/except/finally return coverage."""
        all_return = True
        for child in node.children:
            if child.type in {"block", "compound_statement", "statement_block"}:
                child_returns = self._walk_for_returns(child, content, return_types, yield_types, points)
                if not child_returns:
                    all_return = False
            elif child.type in {"except_clause", "finally_clause",
                                "catch_clause", "handler"}:
                # Extract the block inside except/finally
                block = child.child_by_field_name("body")
                if block is None:
                    for cc in child.children:
                        if cc.type in {"block", "compound_statement", "statement_block"}:
                            block = cc
                            break
                if block:
                    child_returns = self._walk_for_returns(block, content, return_types, yield_types, points)
                    if not child_returns:
                        all_return = False
                else:
                    all_return = False
        return all_return

    def _walk_for_returns(
        self,
        node: tree_sitter.Node,
        content: bytes,
        return_types: frozenset[str],
        yield_types: frozenset[str] | None,
        points: list[ReturnPoint],
    ) -> bool:
        """Walk a subtree collecting return points. Returns True if all paths return."""
        if node.type in return_types:
            has_val = self._return_has_value(node, content)
            points.append(
                ReturnPoint(
                    line_number=node.start_point[0] + 1,
                    has_value=has_val,
                    node_type=node.type,
                )
            )
            return True

        if yield_types and node.type in yield_types:
            points.append(
                ReturnPoint(
                    line_number=node.start_point[0] + 1,
                    has_value=True,
                    node_type=node.type,
                )
            )
            return False

        if node.type in {"if_statement", "elif_clause"}:
            return self._check_branch_returns(node, content, return_types, yield_types, points)

        if node.type in {"try_statement", "try_with_resources_statement"}:
            return self._check_try_returns(node, content, return_types, yield_types, points)

        if node.type in {"for_statement", "while_statement", "do_statement"}:
            for child in node.children:
                self._walk_for_returns(child, content, return_types, yield_types, points)
            return False

        if node.type in {"block", "statement_block", "compound_statement"}:
            all_return = True
            has_any_return = False
            for child in node.children:
                child_returns = self._walk_for_returns(child, content, return_types, yield_types, points)
                if child_returns:
                    has_any_return = True
                else:
                    all_return = False
            return all_return and has_any_return

        for child in node.children:
            self._walk_for_returns(child, content, return_types, yield_types, points)
        return False

    def _analyze_issues(
        self,
        return_points: list[ReturnPoint],
        has_implicit_none: bool,
        func_name: str,
    ) -> list[ReturnPathIssue]:
        """Detect return path issues."""
        issues: list[ReturnPathIssue] = []

        # Separate yields from actual returns
        actual_returns = [r for r in return_points if r.node_type != "yield"]
        yield_count = sum(1 for r in return_points if r.node_type == "yield")

        # Pure generator functions (only yields, no returns) are exempt
        is_pure_generator = yield_count > 0 and len(actual_returns) == 0
        if is_pure_generator:
            return issues

        value_count = sum(1 for r in actual_returns if r.has_value)
        empty_count = sum(1 for r in actual_returns if not r.has_value)

        # Inconsistent return: some paths return value, some don't
        if value_count > 0 and (empty_count > 0 or has_implicit_none):
            first_value = next(r for r in actual_returns if r.has_value)
            issues.append(
                ReturnPathIssue(
                    issue_type=ISSUE_INCONSISTENT_RETURN,
                    severity=SEVERITY_HIGH,
                    line_number=first_value.line_number,
                    message=(
                        f"'{func_name}' returns a value on some paths "
                        f"but {('returns nothing on others' if empty_count > 0 else 'falls through on others')}"
                    ),
                )
            )

        # Implicit None return
        if has_implicit_none and value_count > 0:
            issues.append(
                ReturnPathIssue(
                    issue_type=ISSUE_IMPLICIT_NONE,
                    severity=SEVERITY_MEDIUM,
                    line_number=return_points[-1].line_number + 1 if return_points else 0,
                    message=(
                        f"'{func_name}' can reach the end without returning a value"
                    ),
                )
            )

        # Empty return with value returns
        if empty_count > 0 and value_count > 0:
            first_empty = next(r for r in return_points if not r.has_value)
            issues.append(
                ReturnPathIssue(
                    issue_type=ISSUE_EMPTY_RETURN,
                    severity=SEVERITY_MEDIUM,
                    line_number=first_empty.line_number,
                    message=(
                        f"'{func_name}' has bare return on line {first_empty.line_number} "
                        f"while other paths return values"
                    ),
                )
            )

        # Complex return path
        if len(return_points) > 5:
            issues.append(
                ReturnPathIssue(
                    issue_type=ISSUE_COMPLEX_RETURN_PATH,
                    severity=SEVERITY_LOW,
                    line_number=return_points[0].line_number,
                    message=(
                        f"'{func_name}' has {len(return_points)} return points "
                        f"(consider simplifying)"
                    ),
                )
            )

        return issues

    # ── Python ──────────────────────────────────────────────────────────

    _PY_RETURN: frozenset[str] = frozenset({"return_statement"})
    _PY_YIELD: frozenset[str] = frozenset({"yield"})

    def _extract_python(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionReturnPath]:
        results: list[FunctionReturnPath] = []
        self._walk_python(root, content, results, in_class=False)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionReturnPath],
        in_class: bool,
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python(child, content, results, in_class)
            return

        if node.type == "class_definition":
            for child in node.children:
                self._walk_python(child, content, results, in_class=True)
            return

        if node.type == "function_definition":
            fn = self._analyze_python_function(node, content, in_class)
            if fn is not None:
                results.append(fn)

        for child in node.children:
            self._walk_python(child, content, results, in_class)

    def _analyze_python_function(
        self, node: tree_sitter.Node, content: bytes, in_class: bool
    ) -> FunctionReturnPath | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            return FunctionReturnPath(
                name=name,
                start_line=start_line,
                end_line=end_line,
                return_points=(),
                has_implicit_none=False,
                issues=(),
                element_type="method" if in_class else "function",
            )

        return_points, has_implicit = self._collect_returns(
            body, content, self._PY_RETURN, self._PY_YIELD
        )
        issues = self._analyze_issues(return_points, has_implicit, name)

        return FunctionReturnPath(
            name=name,
            start_line=start_line,
            end_line=end_line,
            return_points=tuple(return_points),
            has_implicit_none=has_implicit,
            issues=tuple(issues),
            element_type="method" if in_class else "function",
        )

    # ── JavaScript / TypeScript ─────────────────────────────────────────

    _JS_RETURN: frozenset[str] = frozenset({"return_statement"})
    _JS_THROW: frozenset[str] = frozenset({"throw_statement"})

    def _extract_js(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionReturnPath]:
        results: list[FunctionReturnPath] = []
        self._walk_js(root, content, results, in_class=False)
        return results

    def _walk_js(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionReturnPath],
        in_class: bool,
    ) -> None:
        if node.type in {"class_declaration", "class_expression"}:
            for child in node.children:
                self._walk_js(child, content, results, in_class=True)
            return

        if node.type in {"function_declaration", "generator_function_declaration"}:
            fn = self._analyze_js_function(node, content, in_class, "function")
            if fn is not None:
                results.append(fn)
            return

        if node.type == "method_definition":
            fn = self._analyze_js_function(node, content, True, "method")
            if fn is not None:
                results.append(fn)
            return

        if node.type == "arrow_function":
            fn = self._analyze_js_function(node, content, in_class, "arrow_function")
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_js(child, content, results, in_class)

    def _analyze_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        element_type: str,
    ) -> FunctionReturnPath | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node

        # Arrow functions with expression body have implicit return
        if element_type == "arrow_function" and body.type != "statement_block":
            return FunctionReturnPath(
                name=name or "<anonymous>",
                start_line=start_line,
                end_line=end_line,
                return_points=(
                    ReturnPoint(
                        line_number=start_line,
                        has_value=True,
                        node_type="arrow_expression",
                    ),
                ),
                has_implicit_none=False,
                issues=(),
                element_type="method" if in_class else element_type,
            )

        combined = self._JS_RETURN | self._JS_THROW
        return_points, has_implicit = self._collect_returns(body, content, combined)
        issues = self._analyze_issues(return_points, has_implicit, name or "<anonymous>")

        return FunctionReturnPath(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            return_points=tuple(return_points),
            has_implicit_none=has_implicit,
            issues=tuple(issues),
            element_type="method" if in_class else element_type,
        )

    # ── Java ────────────────────────────────────────────────────────────

    _JAVA_RETURN: frozenset[str] = frozenset({"return_statement"})
    _JAVA_THROW: frozenset[str] = frozenset({"throw_statement"})

    def _extract_java(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionReturnPath]:
        results: list[FunctionReturnPath] = []
        self._walk_java(root, content, results, in_class=False)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionReturnPath],
        in_class: bool,
    ) -> None:
        if node.type in {"class_declaration", "interface_declaration",
                          "enum_declaration", "record_declaration"}:
            for child in node.children:
                self._walk_java(child, content, results, in_class=True)
            return

        if node.type == "method_declaration":
            fn = self._analyze_java_method(node, content, in_class)
            if fn is not None:
                results.append(fn)
            return

        if node.type == "constructor_declaration":
            fn = self._analyze_java_method(node, content, True, "<init>")
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_java(child, content, results, in_class)

    def _analyze_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        override_name: str | None = None,
    ) -> FunctionReturnPath | None:
        if override_name:
            name = override_name
        else:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node

        combined = self._JAVA_RETURN | self._JAVA_THROW
        return_points, has_implicit = self._collect_returns(body, content, combined)
        issues = self._analyze_issues(return_points, has_implicit, name)

        return FunctionReturnPath(
            name=name,
            start_line=start_line,
            end_line=end_line,
            return_points=tuple(return_points),
            has_implicit_none=has_implicit,
            issues=tuple(issues),
            element_type="method" if in_class else "function",
        )

    # ── Go ──────────────────────────────────────────────────────────────

    _GO_RETURN: frozenset[str] = frozenset({"return_statement"})

    def _extract_go(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[FunctionReturnPath]:
        results: list[FunctionReturnPath] = []
        self._walk_go(root, content, results)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionReturnPath],
    ) -> None:
        if node.type == "function_declaration":
            fn = self._analyze_go_func(node, content, "function")
            if fn is not None:
                results.append(fn)
            return

        if node.type == "method_declaration":
            fn = self._analyze_go_func(node, content, "method")
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_go(child, content, results)

    def _analyze_go_func(
        self,
        node: tree_sitter.Node,
        content: bytes,
        element_type: str,
    ) -> FunctionReturnPath | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        body = node.child_by_field_name("body")
        if not body:
            body = node

        return_points, has_implicit = self._collect_returns(
            body, content, self._GO_RETURN
        )
        issues = self._analyze_issues(return_points, has_implicit, name or "<anonymous>")

        return FunctionReturnPath(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            return_points=tuple(return_points),
            has_implicit_none=has_implicit,
            issues=tuple(issues),
            element_type=element_type,
        )
