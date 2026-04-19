"""
Assertion Quality Analyzer.

Analyzes test assertion quality beyond coverage and smell detection.
Detects the gap between "has tests" and "has good tests" by examining
what assertions actually verify.

Quality issues detected:
  - weak_assertion: assertion checks existence only (toBeDefined, assertTrue(x))
  - vague_comparison: assertion uses vague matchers (toBeTruthy, assert x)
  - clustered_assertions: all assertions clustered at end of test
  - missing_branch_assertion: conditional branch without assertion after it
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

QUALITY_WEAK = "weak_assertion"
QUALITY_VAGUE = "vague_comparison"
QUALITY_CLUSTERED = "clustered_assertions"
QUALITY_MISSING_BRANCH = "missing_branch_assertion"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_QUALITY_SEVERITY: dict[str, str] = {
    QUALITY_WEAK: SEVERITY_MEDIUM,
    QUALITY_VAGUE: SEVERITY_MEDIUM,
    QUALITY_CLUSTERED: SEVERITY_LOW,
    QUALITY_MISSING_BRANCH: SEVERITY_HIGH,
}

_QUALITY_DESCRIPTIONS: dict[str, str] = {
    QUALITY_WEAK: "Assertion checks existence/truthiness only, not behavior",
    QUALITY_VAGUE: "Assertion uses vague matcher instead of specific value",
    QUALITY_CLUSTERED: "All assertions clustered at end, not interleaved with logic",
    QUALITY_MISSING_BRANCH: "Conditional branch has no assertion to verify its path",
}

# Weak assertion patterns (existence-only checks)
_WEAK_PYTHON_ASSERTS = frozenset({
    "asserttrue", "assert_is_not_none", "assertisnotnone",
    "assert_is_none", "assertisnone", "assert_", "fail",
})
_WEAK_PYTHON_PLAIN_ASSERT_OPS = frozenset({"is not None", "is None", "is not", "is"})

_VAGUE_PYTHON_ASSERTS = frozenset({
    "assert_", "asserttrue", "assertfalse",
})

# JS/TS weak matchers
_WEAK_JS_MATCHERS = frozenset({
    "tobedefined", "tobeundefined", "tobetruthy", "tobefalsy",
    "tobenull", "tobenaN", "tobefinite",
})
_VAGUE_JS_MATCHERS = frozenset({
    "tobetruthy", "tobefalsy", "tobenaN", "tobefinite",
    "tostrictequal", "toequal",
})

# Java weak methods
_WEAK_JAVA_METHODS = frozenset({
    "asserttrue", "assertfalse", "assertnotnull", "assertnull",
    "fail",
})

# Go weak patterns
_WEAK_GO_METHODS = frozenset({
    "nil", "notnil", "true", "false",
})

@dataclass(frozen=True)
class AssertionIssue:
    issue_type: str
    line: int
    column: int
    assertion_text: str
    severity: str
    description: str
    suggestion: str

@dataclass(frozen=True)
class TestFunctionQuality:
    name: str
    start_line: int
    end_line: int
    assertion_count: int
    issues: tuple[AssertionIssue, ...]
    quality_score: float

@dataclass(frozen=True)
class AssertionQualityResult:
    file_path: str
    test_functions: tuple[TestFunctionQuality, ...]
    total_tests: int
    total_issues: int
    quality_score: float
    issue_counts: dict[str, int] = field(default_factory=dict)

def _decode(node: tree_sitter.Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")

def _severity_for(issue_type: str) -> str:
    return _QUALITY_SEVERITY.get(issue_type, SEVERITY_LOW)

def _empty_result(file_path: str) -> AssertionQualityResult:
    return AssertionQualityResult(
        file_path=file_path,
        test_functions=(),
        total_tests=0,
        total_issues=0,
        quality_score=100.0,
        issue_counts={},
    )

def _compute_quality_score(
    assertion_count: int,
    issues: list[AssertionIssue],
) -> float:
    if assertion_count == 0:
        return 0.0
    penalty = 0.0
    for issue in issues:
        if issue.severity == SEVERITY_HIGH:
            penalty += 20.0
        elif issue.severity == SEVERITY_MEDIUM:
            penalty += 10.0
        else:
            penalty += 5.0
    return max(0.0, 100.0 - penalty)

class AssertionQualityAnalyzer(BaseAnalyzer):
    """Analyzes test assertion quality across Python, JS/TS, Java, Go."""

    def analyze_file(
        self,
        file_path: Path | str,
        cluster_threshold: float = 0.8,
    ) -> AssertionQualityResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))
        if not self._is_test_file(path, ext):
            return _empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return _empty_result(str(path))

        tree = parser.parse(content)

        if ext == ".py":
            functions = self._extract_python(
                tree.root_node, content, cluster_threshold
            )
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            functions = self._extract_javascript(
                tree.root_node, content, cluster_threshold
            )
        elif ext == ".java":
            functions = self._extract_java(
                tree.root_node, content, cluster_threshold
            )
        elif ext == ".go":
            functions = self._extract_go(
                tree.root_node, content, cluster_threshold
            )
        else:
            functions = []

        total_issues = sum(len(f.issues) for f in functions)
        issue_counts: dict[str, int] = {}
        for f in functions:
            for iss in f.issues:
                issue_counts[iss.issue_type] = (
                    issue_counts.get(iss.issue_type, 0) + 1
                )

        scores = [f.quality_score for f in functions]
        avg_score = sum(scores) / len(scores) if scores else 100.0

        return AssertionQualityResult(
            file_path=str(path),
            test_functions=tuple(functions),
            total_tests=len(functions),
            total_issues=total_issues,
            quality_score=round(avg_score, 1),
            issue_counts=issue_counts,
        )

    @staticmethod
    def _is_test_file(path: Path, ext: str) -> bool:
        name = path.name.lower()
        if ext == ".py":
            return (
                name.startswith("test_")
                or name.endswith("_test.py")
                or name == "tests.py"
            )
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return (
                name.startswith("test_")
                or name.endswith("_test.js")
                or name.endswith("_test.ts")
                or name.endswith(".test.js")
                or name.endswith(".test.ts")
                or name.endswith(".spec.js")
                or name.endswith(".spec.ts")
            )
        if ext == ".java":
            return (
                name.endswith("test.java")
                or name.endswith("tests.java")
                or name.endswith("it.java")
            )
        if ext == ".go":
            return name.endswith("_test.go")
        return False

    # --- Python ---

    def _extract_python(
        self,
        root: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> list[TestFunctionQuality]:
        results: list[TestFunctionQuality] = []
        self._walk_python(root, content, results, cluster_threshold, in_class=False)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunctionQuality],
        cluster_threshold: float,
        in_class: bool,
    ) -> None:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node and (
                in_class
                or _decode(name_node).startswith("test_")
            ):
                quality = self._analyze_python_function(
                    node, content, cluster_threshold
                )
                results.append(quality)
                return

        if node.type == "class_definition":
            for child in node.children:
                self._walk_python(
                    child, content, results, cluster_threshold, in_class=True
                )
            return

        for child in node.children:
            self._walk_python(
                child, content, results, cluster_threshold, in_class=in_class
            )

    def _analyze_python_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> TestFunctionQuality:
        body = node.child_by_field_name("body")
        if body is None:
            name_node = node.child_by_field_name("name")
            name = _decode(name_node) if name_node else "<unknown>"
            return TestFunctionQuality(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                assertion_count=0,
                issues=(),
                quality_score=100.0,
            )

        name_node = node.child_by_field_name("name")
        name = _decode(name_node) if name_node else "<unknown>"

        assertions = self._find_python_assertions(body, content)
        issues: list[AssertionIssue] = []

        for assertion in assertions:
            assertion_issues = self._classify_python_assertion(
                assertion, content
            )
            issues.extend(assertion_issues)

        issues.extend(
            self._check_python_clustered(body, content, cluster_threshold, assertions)
        )
        issues.extend(self._check_python_branch_assertions(body, content))

        score = _compute_quality_score(len(assertions), issues)

        return TestFunctionQuality(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=len(assertions),
            issues=tuple(issues),
            quality_score=score,
        )

    def _find_python_assertions(
        self, body: tree_sitter.Node, content: bytes
    ) -> list[tree_sitter.Node]:
        assertions: list[tree_sitter.Node] = []
        self._collect_python_assertions(body, assertions)
        return assertions

    def _collect_python_assertions(
        self, node: tree_sitter.Node, assertions: list[tree_sitter.Node]
    ) -> None:
        if node.type == "assert_statement":
            assertions.append(node)
            return
        if node.type == "expression_statement":
            expr = node.child_by_field_name("value") or (
                node.children[0] if node.children else None
            )
            if expr and expr.type == "call":
                func = expr.child_by_field_name("function")
                if func:
                    func_text = _decode(func).lower()
                    if func_text.startswith("self.assert") or func_text == "assert_":
                        assertions.append(node)
                        return
                    if func_text == "assert_that" or func_text.startswith("assert_"):
                        assertions.append(node)
                        return
        for child in node.children:
            self._collect_python_assertions(child, assertions)

    def _classify_python_assertion(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[AssertionIssue]:
        issues: list[AssertionIssue] = []
        text = content[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        text.lower().strip()

        if node.type == "assert_statement":
            inner = text[len("assert") :].strip()
            if not inner:
                return issues
            is_vague = True
            for op in ("==", "!=", ">=", "<=", ">", "<", "in ", "not in "):
                if op in inner:
                    is_vague = False
                    break
            if "is not None" in inner or " is None" in inner:
                issues.append(
                    AssertionIssue(
                        issue_type=QUALITY_WEAK,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        assertion_text=text[:80],
                        severity=_severity_for(QUALITY_WEAK),
                        description=_QUALITY_DESCRIPTIONS[QUALITY_WEAK],
                        suggestion="Assert a specific property or return value instead of just existence",
                    )
                )
                return issues
            if is_vague and not any(c in inner for c in ".("):
                issues.append(
                    AssertionIssue(
                        issue_type=QUALITY_VAGUE,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        assertion_text=text[:80],
                        severity=_severity_for(QUALITY_VAGUE),
                        description=_QUALITY_DESCRIPTIONS[QUALITY_VAGUE],
                        suggestion="Use assert x == expected_value instead of assert x",
                    )
                )
            return issues

        call_node = node.children[0] if node.children else None
        if call_node is None or call_node.type != "call":
            return issues

        func = call_node.child_by_field_name("function")
        if func is None:
            return issues
        func_text = _decode(func).lower()

        base_name = func_text.split(".")[-1] if "." in func_text else func_text

        if base_name in _WEAK_PYTHON_ASSERTS:
            issues.append(
                AssertionIssue(
                    issue_type=QUALITY_WEAK,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    assertion_text=text[:80],
                    severity=_severity_for(QUALITY_WEAK),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_WEAK],
                    suggestion="Assert a specific value, not just truthiness or existence",
                )
            )
        elif base_name in _VAGUE_PYTHON_ASSERTS:
            issues.append(
                AssertionIssue(
                    issue_type=QUALITY_VAGUE,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    assertion_text=text[:80],
                    severity=_severity_for(QUALITY_VAGUE),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_VAGUE],
                    suggestion="Use assertEqual/assertAlmostEqual with expected value",
                )
            )

        return issues

    def _check_python_clustered(
        self,
        body: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
        assertions: list[tree_sitter.Node],
    ) -> list[AssertionIssue]:
        if len(assertions) < 3:
            return []

        body_lines = body.end_point[0] - body.start_point[0]
        if body_lines < 5:
            return []

        last_assert_line = max(a.start_point[0] for a in assertions)
        first_assert_line = min(a.start_point[0] for a in assertions)
        span = last_assert_line - first_assert_line

        if span == 0:
            span = 1
        ratio = len(assertions) / span

        if ratio > cluster_threshold:
            return [
                AssertionIssue(
                    issue_type=QUALITY_CLUSTERED,
                    line=first_assert_line + 1,
                    column=0,
                    assertion_text=f"{len(assertions)} assertions in {span} lines",
                    severity=_severity_for(QUALITY_CLUSTERED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_CLUSTERED],
                    suggestion="Interleave assertions with test logic for better failure diagnostics",
                )
            ]
        return []

    def _check_python_branch_assertions(
        self, body: tree_sitter.Node, content: bytes
    ) -> list[AssertionIssue]:
        issues: list[AssertionIssue] = []
        self._check_branch_assertions_recursive(body, content, issues)
        return issues

    def _check_branch_assertions_recursive(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[AssertionIssue],
    ) -> None:
        if node.type == "if_statement":
            consequence = node.child_by_field_name("consequence")
            alternative = node.child_by_field_name("alternative")

            if consequence and not self._has_assertion_in_tree(consequence, content):
                issues.append(
                    AssertionIssue(
                        issue_type=QUALITY_MISSING_BRANCH,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        assertion_text=content[
                            node.start_byte : min(
                                node.end_byte, node.start_byte + 60
                            )
                        ]
                        .decode("utf-8", errors="replace")
                        .split("\n")[0],
                        severity=_severity_for(QUALITY_MISSING_BRANCH),
                        description="if-branch has no assertion",
                        suggestion="Add an assertion to verify the if-branch behavior",
                    )
                )

            if alternative and not self._has_assertion_in_tree(alternative, content):
                issues.append(
                    AssertionIssue(
                        issue_type=QUALITY_MISSING_BRANCH,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        assertion_text="else/elif branch",
                        severity=_severity_for(QUALITY_MISSING_BRANCH),
                        description="else/elif-branch has no assertion",
                        suggestion="Add an assertion to verify the else-branch behavior",
                    )
                )

        if node.type == "try_statement":
            for child in node.children:
                if child.type == "except_clause":
                    body = child.child_by_field_name("body")
                    target = body or child
                    if not self._has_assertion_in_tree(target, content):
                        issues.append(
                            AssertionIssue(
                                issue_type=QUALITY_MISSING_BRANCH,
                                line=child.start_point[0] + 1,
                                column=child.start_point[1],
                                assertion_text="except handler",
                                severity=_severity_for(QUALITY_MISSING_BRANCH),
                                description="except handler has no assertion",
                                suggestion="Assert the expected exception or its properties",
                            )
                        )

        for child in node.children:
            self._check_branch_assertions_recursive(child, content, issues)

    def _has_assertion_in_tree(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        assertions: list[tree_sitter.Node] = []
        self._collect_python_assertions(node, assertions)
        return len(assertions) > 0

    # --- JavaScript/TypeScript ---

    def _extract_javascript(
        self,
        root: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> list[TestFunctionQuality]:
        results: list[TestFunctionQuality] = []
        for node in self._find_js_test_functions(root):
            quality = self._analyze_js_function(
                node, content, cluster_threshold
            )
            results.append(quality)
        return results

    def _find_js_test_functions(
        self, root: tree_sitter.Node
    ) -> list[tree_sitter.Node]:
        functions: list[tree_sitter.Node] = []
        self._walk_js_tests(root, functions)
        return functions

    def _walk_js_tests(
        self, node: tree_sitter.Node, functions: list[tree_sitter.Node]
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func and func.type == "identifier":
                name = _decode(func)
                if name in ("it", "test"):
                    args = node.child_by_field_name("arguments")
                    if args:
                        for child in args.children:
                            if child.type in (
                                "function",
                                "arrow_function",
                                "function_expression",
                            ):
                                functions.append(child)
                                return
            if func and func.type == "member_expression":
                obj = func.child_by_field_name("object")
                prop = func.child_by_field_name("property")
                if obj and prop:
                    obj_text = _decode(obj)
                    prop_text = _decode(prop)
                    if obj_text == "describe" and prop_text in ("it", "test"):
                        args = node.child_by_field_name("arguments")
                        if args:
                            for child in args.children:
                                if child.type in (
                                    "function",
                                    "arrow_function",
                                    "function_expression",
                                ):
                                    functions.append(child)
                                    return

        for child in node.children:
            self._walk_js_tests(child, functions)

    def _analyze_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> TestFunctionQuality:
        body = node.child_by_field_name("body")
        if body is None:
            return TestFunctionQuality(
                name="<js-test>",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                assertion_count=0,
                issues=(),
                quality_score=100.0,
            )

        assertions = self._find_js_assertions(body, content)
        issues: list[AssertionIssue] = []

        for assertion in assertions:
            assertion_issues = self._classify_js_assertion(assertion, content)
            issues.extend(assertion_issues)

        issues.extend(
            self._check_js_clustered(body, content, cluster_threshold, assertions)
        )

        score = _compute_quality_score(len(assertions), issues)

        return TestFunctionQuality(
            name="<js-test>",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=len(assertions),
            issues=tuple(issues),
            quality_score=score,
        )

    def _find_js_assertions(
        self, body: tree_sitter.Node, content: bytes
    ) -> list[tree_sitter.Node]:
        assertions: list[tree_sitter.Node] = []
        self._collect_js_assertions(body, assertions)
        return assertions

    def _collect_js_assertions(
        self, node: tree_sitter.Node, assertions: list[tree_sitter.Node]
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                func_text = _decode(func).lower()
                if (
                    func_text == "expect"
                    or func_text.startswith("assert.")
                    or func_text.startswith("assert(")
                    or func_text == "assertthat"
                ):
                    assertions.append(node)
                    return
                if func.type == "member_expression":
                    obj = func.child_by_field_name("object")
                    if obj and _decode(obj).lower() == "expect":
                        assertions.append(node)
                        return
        for child in node.children:
            self._collect_js_assertions(child, assertions)

    def _classify_js_assertion(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[AssertionIssue]:
        issues: list[AssertionIssue] = []
        content[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

        self._check_js_expect_chain(node, content, issues)

        return issues

    def _check_js_expect_chain(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[AssertionIssue],
    ) -> None:
        if node.type != "call_expression":
            return

        func = node.child_by_field_name("function")
        if func is None:
            return

        self._trace_expect_chain(func, content, node, issues)

    def _trace_expect_chain(
        self,
        node: tree_sitter.Node,
        content: bytes,
        original_node: tree_sitter.Node,
        issues: list[AssertionIssue],
    ) -> None:
        if node.type == "member_expression":
            prop = node.child_by_field_name("property")
            obj = node.child_by_field_name("object")
            if prop:
                matcher = _decode(prop).lower()
                text = content[
                    original_node.start_byte : original_node.end_byte
                ].decode("utf-8", errors="replace")

                if matcher in _WEAK_JS_MATCHERS:
                    issues.append(
                        AssertionIssue(
                            issue_type=QUALITY_WEAK,
                            line=original_node.start_point[0] + 1,
                            column=original_node.start_point[1],
                            assertion_text=text[:80],
                            severity=_severity_for(QUALITY_WEAK),
                            description=_QUALITY_DESCRIPTIONS[QUALITY_WEAK],
                            suggestion=f"Use toBe() with a specific value instead of {matcher}()",
                        )
                    )
                elif matcher in _VAGUE_JS_MATCHERS:
                    issues.append(
                        AssertionIssue(
                            issue_type=QUALITY_VAGUE,
                            line=original_node.start_point[0] + 1,
                            column=original_node.start_point[1],
                            assertion_text=text[:80],
                            severity=_severity_for(QUALITY_VAGUE),
                            description=_QUALITY_DESCRIPTIONS[QUALITY_VAGUE],
                            suggestion=f"Use a more specific matcher instead of {matcher}()",
                        )
                    )

            if obj:
                self._trace_expect_chain(
                    obj, content, original_node, issues
                )

    def _check_js_clustered(
        self,
        body: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
        assertions: list[tree_sitter.Node],
    ) -> list[AssertionIssue]:
        if len(assertions) < 3:
            return []

        last_assert_line = max(a.start_point[0] for a in assertions)
        first_assert_line = min(a.start_point[0] for a in assertions)
        span = last_assert_line - first_assert_line
        if span == 0:
            span = 1
        ratio = len(assertions) / span

        if ratio > cluster_threshold:
            return [
                AssertionIssue(
                    issue_type=QUALITY_CLUSTERED,
                    line=first_assert_line + 1,
                    column=0,
                    assertion_text=f"{len(assertions)} assertions in {span} lines",
                    severity=_severity_for(QUALITY_CLUSTERED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_CLUSTERED],
                    suggestion="Interleave assertions with test logic",
                )
            ]
        return []

    # --- Java ---

    def _extract_java(
        self,
        root: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> list[TestFunctionQuality]:
        results: list[TestFunctionQuality] = []
        self._walk_java(root, content, results, cluster_threshold)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunctionQuality],
        cluster_threshold: float,
    ) -> None:
        if node.type == "method_declaration":
            name_node = None
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
            if name_node:
                name = _decode(name_node)
                if (
                    name.startswith("test")
                    or name.startswith("should")
                    or name.startswith("it")
                    or name.startswith("when")
                ):
                    quality = self._analyze_java_method(
                        node, content, cluster_threshold
                    )
                    results.append(quality)
                    return

        for child in node.children:
            self._walk_java(child, content, results, cluster_threshold)

    def _analyze_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> TestFunctionQuality:
        body = node.child_by_field_name("body")
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
        name = _decode(name_node) if name_node else "<java-test>"

        if body is None:
            return TestFunctionQuality(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                assertion_count=0,
                issues=(),
                quality_score=100.0,
            )

        assertions = self._find_java_assertions(body, content)
        issues: list[AssertionIssue] = []

        for assertion in assertions:
            assertion_issues = self._classify_java_assertion(assertion, content)
            issues.extend(assertion_issues)

        issues.extend(
            self._check_java_clustered(body, content, cluster_threshold, assertions)
        )

        score = _compute_quality_score(len(assertions), issues)

        return TestFunctionQuality(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=len(assertions),
            issues=tuple(issues),
            quality_score=score,
        )

    def _find_java_assertions(
        self, body: tree_sitter.Node, content: bytes
    ) -> list[tree_sitter.Node]:
        assertions: list[tree_sitter.Node] = []
        self._collect_java_assertions(body, assertions)
        return assertions

    def _collect_java_assertions(
        self, node: tree_sitter.Node, assertions: list[tree_sitter.Node]
    ) -> None:
        if node.type == "expression_statement":
            expr = node.children[0] if node.children else None
            if expr and expr.type == "method_invocation":
                method_name = None
                for child in expr.children:
                    if child.type == "identifier":
                        method_name = _decode(child)
                        break
                if method_name:
                    ml = method_name.lower()
                    if ml.startswith("assert") or ml in ("fail", "verify"):
                        assertions.append(node)
                        return
        for child in node.children:
            self._collect_java_assertions(child, assertions)

    def _classify_java_assertion(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[AssertionIssue]:
        issues: list[AssertionIssue] = []
        text = content[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        text_lower = text.lower().strip()

        for weak in _WEAK_JAVA_METHODS:
            if weak in text_lower and "(" in text_lower:
                issues.append(
                    AssertionIssue(
                        issue_type=QUALITY_WEAK,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        assertion_text=text[:80],
                        severity=_severity_for(QUALITY_WEAK),
                        description=_QUALITY_DESCRIPTIONS[QUALITY_WEAK],
                        suggestion="Use assertEquals with expected value instead",
                    )
                )
                break

        return issues

    def _check_java_clustered(
        self,
        body: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
        assertions: list[tree_sitter.Node],
    ) -> list[AssertionIssue]:
        if len(assertions) < 3:
            return []
        last_assert_line = max(a.start_point[0] for a in assertions)
        first_assert_line = min(a.start_point[0] for a in assertions)
        span = last_assert_line - first_assert_line
        if span == 0:
            span = 1
        ratio = len(assertions) / span
        if ratio > cluster_threshold:
            return [
                AssertionIssue(
                    issue_type=QUALITY_CLUSTERED,
                    line=first_assert_line + 1,
                    column=0,
                    assertion_text=f"{len(assertions)} assertions in {span} lines",
                    severity=_severity_for(QUALITY_CLUSTERED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_CLUSTERED],
                    suggestion="Interleave assertions with test logic",
                )
            ]
        return []

    # --- Go ---

    def _extract_go(
        self,
        root: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> list[TestFunctionQuality]:
        results: list[TestFunctionQuality] = []
        self._walk_go(root, content, results, cluster_threshold)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[TestFunctionQuality],
        cluster_threshold: float,
    ) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node and _decode(name_node).startswith("Test"):
                quality = self._analyze_go_function(
                    node, content, cluster_threshold
                )
                results.append(quality)
                return

        for child in node.children:
            self._walk_go(child, content, results, cluster_threshold)

    def _analyze_go_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
    ) -> TestFunctionQuality:
        name_node = node.child_by_field_name("name")
        name = _decode(name_node) if name_node else "<go-test>"

        body = node.child_by_field_name("body")
        if body is None:
            return TestFunctionQuality(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                assertion_count=0,
                issues=(),
                quality_score=100.0,
            )

        assertions = self._find_go_assertions(body, content)
        issues: list[AssertionIssue] = []

        for assertion in assertions:
            assertion_issues = self._classify_go_assertion(assertion, content)
            issues.extend(assertion_issues)

        issues.extend(
            self._check_go_clustered(body, content, cluster_threshold, assertions)
        )

        score = _compute_quality_score(len(assertions), issues)

        return TestFunctionQuality(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            assertion_count=len(assertions),
            issues=tuple(issues),
            quality_score=score,
        )

    def _find_go_assertions(
        self, body: tree_sitter.Node, content: bytes
    ) -> list[tree_sitter.Node]:
        assertions: list[tree_sitter.Node] = []
        self._collect_go_assertions(body, assertions)
        return assertions

    def _collect_go_assertions(
        self, node: tree_sitter.Node, assertions: list[tree_sitter.Node]
    ) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                func_text = _decode(func)
                if "." in func_text:
                    method = func_text.split(".")[-1]
                    if method in (
                        "Equal",
                        "NotEqual",
                        "True",
                        "False",
                        "Nil",
                        "NotNil",
                        "Error",
                        "NoError",
                        "Contains",
                        "Len",
                    ):
                        assertions.append(node)
                        return
                if func_text in (
                    "assert",
                    "require",
                    "check",
                ):
                    assertions.append(node)
                    return
        for child in node.children:
            self._collect_go_assertions(child, assertions)

    def _classify_go_assertion(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[AssertionIssue]:
        issues: list[AssertionIssue] = []
        text = content[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        text.lower()

        func = node.child_by_field_name("function")
        if func:
            method = _decode(func).split(".")[-1]
            if method in _WEAK_GO_METHODS:
                issues.append(
                    AssertionIssue(
                        issue_type=QUALITY_WEAK,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        assertion_text=text[:80],
                        severity=_severity_for(QUALITY_WEAK),
                        description=_QUALITY_DESCRIPTIONS[QUALITY_WEAK],
                        suggestion=f"Use Equal with expected value instead of {method}",
                    )
                )

        return issues

    def _check_go_clustered(
        self,
        body: tree_sitter.Node,
        content: bytes,
        cluster_threshold: float,
        assertions: list[tree_sitter.Node],
    ) -> list[AssertionIssue]:
        if len(assertions) < 3:
            return []
        last_assert_line = max(a.start_point[0] for a in assertions)
        first_assert_line = min(a.start_point[0] for a in assertions)
        span = last_assert_line - first_assert_line
        if span == 0:
            span = 1
        ratio = len(assertions) / span
        if ratio > cluster_threshold:
            return [
                AssertionIssue(
                    issue_type=QUALITY_CLUSTERED,
                    line=first_assert_line + 1,
                    column=0,
                    assertion_text=f"{len(assertions)} assertions in {span} lines",
                    severity=_severity_for(QUALITY_CLUSTERED),
                    description=_QUALITY_DESCRIPTIONS[QUALITY_CLUSTERED],
                    suggestion="Interleave assertions with test logic",
                )
            ]
        return []
