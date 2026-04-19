"""Tautological Condition Detector.

Detects conditions that always evaluate to the same value:
  - contradictory_condition: x == 5 and x == 10 (always false)
  - subsumed_condition: x > 3 and x > 5 (first clause redundant)
  - tautological_comparison: x == x, x != x, if True/False

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

def _txt(node: tree_sitter.Node) -> str:
    """Safely extract text from a tree-sitter node."""
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_CONTRADICTORY = "contradictory_condition"
ISSUE_SUBSUMED = "subsumed_condition"
ISSUE_TAUTOLOGICAL = "tautological_comparison"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_CONTRADICTORY: SEVERITY_HIGH,
    ISSUE_SUBSUMED: SEVERITY_MEDIUM,
    ISSUE_TAUTOLOGICAL: SEVERITY_HIGH,
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_CONTRADICTORY: (
        "Fix contradictory comparisons - one operand or operator is likely wrong"
    ),
    ISSUE_SUBSUMED: (
        "Remove the redundant subsumed comparison"
    ),
    ISSUE_TAUTOLOGICAL: (
        "Remove the always-true/false comparison or fix the operands"
    ),
}

_FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".jsx": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".ts": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".tsx": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}

_AND_TYPES: frozenset[str] = frozenset({"and", "&&", "and_expr", "boolean_operator"})
_OR_TYPES: frozenset[str] = frozenset({"or", "||", "or_expr"})

_COMPARISON_OPS: frozenset[str] = frozenset({
    "==", "!=", ">", "<", ">=", "<=",
    "===", "!==", "is", "is not",
})

_LITERAL_TRUE: frozenset[str] = frozenset({"True", "true"})
_LITERAL_FALSE: frozenset[str] = frozenset({"False", "false"})

@dataclass(frozen=True)
class TautologicalIssue:
    """A single tautological condition issue."""

    issue_type: str
    line: int
    message: str
    severity: str
    details: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
            "suggestion": self.suggestion,
        }

@dataclass(frozen=True)
class TautologicalResult:
    """Aggregated result of tautological condition analysis."""

    issues: tuple[TautologicalIssue, ...]
    functions_analyzed: int
    total_issues: int
    high_severity_count: int
    file_path: str

    def get_issues_by_severity(
        self, severity: str,
    ) -> list[TautologicalIssue]:
        return [i for i in self.issues if i.severity == severity]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "functions_analyzed": self.functions_analyzed,
            "total_issues": self.total_issues,
            "high_severity_count": self.high_severity_count,
            "issues": [i.to_dict() for i in self.issues],
        }

class TautologicalConditionAnalyzer(BaseAnalyzer):
    """Detects tautological, contradictory, and subsumed conditions."""

    def __init__(self) -> None:
        super().__init__()

    def analyze_file(self, file_path: str) -> TautologicalResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            return TautologicalResult(
                issues=(),
                functions_analyzed=0,
                total_issues=0,
                high_severity_count=0,
                file_path=file_path,
            )

        source = path.read_bytes()
        _, parser = self._get_parser(ext)
        if parser is None:
            return TautologicalResult(
                issues=(),
                functions_analyzed=0,
                total_issues=0,
                high_severity_count=0,
                file_path=file_path,
            )
        tree = parser.parse(source)
        root = tree.root_node

        issues: list[TautologicalIssue] = []
        functions_analyzed = 0
        func_types = _FUNCTION_NODE_TYPES.get(ext, frozenset())

        def _walk(n: tree_sitter.Node) -> None:
            nonlocal functions_analyzed

            if n.type in func_types:
                functions_analyzed += 1
                issues.extend(self._check_conditions(n, ext))

            for child in n.children:
                _walk(child)

        _walk(root)

        high_count = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
        return TautologicalResult(
            issues=tuple(issues),
            functions_analyzed=functions_analyzed,
            total_issues=len(issues),
            high_severity_count=high_count,
            file_path=file_path,
        )

    def _check_conditions(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> list[TautologicalIssue]:
        """Walk function body to find tautological conditions."""
        issues: list[TautologicalIssue] = []
        visited: set[int] = set()

        def _walk(node: tree_sitter.Node) -> None:
            if node.id in visited:
                return
            visited.add(node.id)

            issues.extend(self._check_boolean_literal(node, ext))
            issues.extend(self._check_self_comparison(node, ext))
            issues.extend(self._check_contradictory(node, ext))
            issues.extend(self._check_subsumed(node, ext))

            for child in node.children:
                _walk(child)

        _walk(func_node)
        return issues

    def _check_boolean_literal(
        self, node: tree_sitter.Node, ext: str,
    ) -> list[TautologicalIssue]:
        """Detect if True/False used as condition."""
        if ext == ".py" and node.type == "if_statement":
            cond = node.child_by_field_name("condition")
            if cond:
                text = _txt(cond).strip()
                if text in _LITERAL_TRUE or text in _LITERAL_FALSE:
                    return [TautologicalIssue(
                        issue_type=ISSUE_TAUTOLOGICAL,
                        line=node.start_point[0] + 1,
                        message=f"Condition is always {text.lower()}",
                        severity=_SEVERITY_MAP[ISSUE_TAUTOLOGICAL],
                        details=f"Literal boolean: {text}",
                        suggestion=_SUGGESTIONS[ISSUE_TAUTOLOGICAL],
                    )]
        return []

    def _check_self_comparison(
        self, node: tree_sitter.Node, ext: str,
    ) -> list[TautologicalIssue]:
        """Detect x == x, x != x, x > x, etc."""
        if node.type != "comparison_operator":
            if ext in {".js", ".jsx", ".ts", ".tsx", ".go"}:
                if node.type != "binary_expression":
                    return []
            elif ext == ".java":
                if node.type != "method_invocation":
                    return []
            else:
                return []

        if ext in {".js", ".jsx", ".ts", ".tsx", ".go"} and node.type == "binary_expression":
            op = node.child_by_field_name("operator")
            if not op:
                return []
            op_text = _txt(op)
            if op_text not in _COMPARISON_OPS:
                return []
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right:
                left_text = _txt(left).strip()
                right_text = _txt(right).strip()
                if left_text and right_text and left_text == right_text:
                    return [TautologicalIssue(
                        issue_type=ISSUE_TAUTOLOGICAL,
                        line=node.start_point[0] + 1,
                        message=(
                            f"Self-comparison: '{left_text} {op_text} {right_text}' "
                            f"is always {'true' if op_text in {'==', '===', '<=', '>='} else 'false'}"
                        ),
                        severity=_SEVERITY_MAP[ISSUE_TAUTOLOGICAL],
                        details=f"{left_text} {op_text} {right_text}",
                        suggestion=_SUGGESTIONS[ISSUE_TAUTOLOGICAL],
                    )]
            return []

        if node.type == "comparison_operator":
            children = node.children
            if len(children) >= 3:
                left_text = _txt(children[0]).strip()
                op_text = _txt(children[1]).strip()
                right_text = _txt(children[2]).strip()
                if left_text and right_text and left_text == right_text:
                    return [TautologicalIssue(
                        issue_type=ISSUE_TAUTOLOGICAL,
                        line=node.start_point[0] + 1,
                        message=(
                            f"Self-comparison: '{left_text} {op_text} {right_text}' "
                            f"is always {'true' if op_text in {'==', '===', '<=', '>='} else 'false'}"
                        ),
                        severity=_SEVERITY_MAP[ISSUE_TAUTOLOGICAL],
                        details=f"{left_text} {op_text} {right_text}",
                        suggestion=_SUGGESTIONS[ISSUE_TAUTOLOGICAL],
                    )]
        return []

    def _extract_comparison(
        self, node: tree_sitter.Node, ext: str,
    ) -> tuple[str, str, str] | None:
        """Extract (left, op, right) from a comparison node. Returns None if not a comparison."""
        if ext == ".py" and node.type == "comparison_operator":
            children = node.children
            if len(children) >= 3:
                left = _txt(children[0]).strip()
                op = _txt(children[1]).strip()
                right = _txt(children[2]).strip()
                if op in _COMPARISON_OPS and left and right:
                    return left, op, right

        if ext in {".js", ".jsx", ".ts", ".tsx"} and node.type == "binary_expression":
            op_node = node.child_by_field_name("operator")
            left_node = node.child_by_field_name("left")
            right_node = node.child_by_field_name("right")
            if op_node and left_node and right_node:
                op = _txt(op_node).strip()
                left = _txt(left_node).strip()
                right = _txt(right_node).strip()
                if op in _COMPARISON_OPS and left and right:
                    return left, op, right

        if ext == ".java" and node.type == "binary_expression":
            op_node = node.child_by_field_name("operator")
            if op_node:
                op = _txt(op_node).strip()
                if op in _COMPARISON_OPS:
                    left_node = node.child_by_field_name("left")
                    right_node = node.child_by_field_name("right")
                    if left_node and right_node:
                        return _txt(left_node).strip(), op, _txt(right_node).strip()

        if ext == ".java" and node.type == "method_invocation":
            method = node.child_by_field_name("name")
            obj = node.child_by_field_name("object")
            args = node.child_by_field_name("arguments")
            if method and obj and args:
                method_text = _txt(method).strip()
                if method_text == "equals":
                    obj_text = _txt(obj).strip()
                    arg_texts = [
                        _txt(c).strip() for c in args.children
                        if c.type not in {"(", ")", ","}
                    ]
                    if arg_texts:
                        return obj_text, "==", arg_texts[0]

        if ext == ".go":
            if node.type == "binary_expression":
                op_node = node.child_by_field_name("operator")
                left_node = node.child_by_field_name("left")
                right_node = node.child_by_field_name("right")
                if op_node and left_node and right_node:
                    op = _txt(op_node).strip()
                    left = _txt(left_node).strip()
                    right = _txt(right_node).strip()
                    if op in _COMPARISON_OPS and left and right:
                        return left, op, right

        return None

    def _collect_and_children(
        self, node: tree_sitter.Node, ext: str,
    ) -> list[tree_sitter.Node]:
        """Collect all children of a chain of AND operators."""
        result: list[tree_sitter.Node] = []

        if ext == ".py":
            if node.type == "boolean_operator":
                for child in node.children:
                    child_text = _txt(child).strip()
                    if child_text == "and":
                        continue
                    inner = self._collect_and_children(child, ext)
                    result.extend(inner)
            else:
                result.append(node)
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".go"}:
            if node.type == "binary_expression":
                op = node.child_by_field_name("operator")
                if op and _txt(op).strip() == "&&":
                    left = node.child_by_field_name("left")
                    right = node.child_by_field_name("right")
                    if left:
                        result.extend(self._collect_and_children(left, ext))
                    if right:
                        result.extend(self._collect_and_children(right, ext))
                else:
                    result.append(node)
            else:
                result.append(node)
        elif ext == ".java":
            if node.type == "binary_expression":
                has_and = False
                for child in node.children:
                    if _txt(child).strip() == "&&":
                        has_and = True
                        break
                if has_and:
                    left = node.child_by_field_name("left")
                    right = node.child_by_field_name("right")
                    if left:
                        result.extend(self._collect_and_children(left, ext))
                    if right:
                        result.extend(self._collect_and_children(right, ext))
                else:
                    result.append(node)
            else:
                result.append(node)
        else:
            result.append(node)

        return result

    def _check_contradictory(
        self, node: tree_sitter.Node, ext: str,
    ) -> list[TautologicalIssue]:
        """Detect contradictory comparisons in AND chains."""
        issues: list[TautologicalIssue] = []

        is_and = False
        if ext == ".py" and node.type == "boolean_operator":
            children_text = [_txt(c).strip() for c in node.children]
            if "and" in children_text:
                is_and = True
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".go"} and node.type == "binary_expression":
            op = node.child_by_field_name("operator")
            if op and _txt(op).strip() == "&&":
                is_and = True
        elif ext == ".java" and node.type == "binary_expression":
            for child in node.children:
                if _txt(child).strip() == "&&":
                    is_and = True
                    break

        if not is_and:
            return []

        parts = self._collect_and_children(node, ext)
        comparisons: list[tuple[str, str, str, tree_sitter.Node]] = []

        for part in parts:
            comp = self._extract_comparison(part, ext)
            if comp:
                comparisons.append((*comp, part))

        for i in range(len(comparisons)):
            for j in range(i + 1, len(comparisons)):
                left_i, op_i, right_i, node_i = comparisons[i]
                left_j, op_j, right_j, _ = comparisons[j]

                if left_i == left_j:
                    is_contra = self._are_contradictory(
                        left_i, op_i, right_i, op_j, right_j,
                    )
                    if is_contra:
                        issues.append(TautologicalIssue(
                            issue_type=ISSUE_CONTRADICTORY,
                            line=node_i.start_point[0] + 1,
                            message=(
                                f"Contradictory conditions on '{left_i}': "
                                f"'{left_i} {op_i} {right_i}' vs "
                                f"'{left_j} {op_j} {right_j}'"
                            ),
                            severity=_SEVERITY_MAP[ISSUE_CONTRADICTORY],
                            details=(
                                f"{left_i} {op_i} {right_i} AND "
                                f"{left_j} {op_j} {right_j}"
                            ),
                            suggestion=_SUGGESTIONS[ISSUE_CONTRADICTORY],
                        ))
        return issues

    def _are_contradictory(
        self,
        _var: str, op1: str, val1: str, op2: str, val2: str,
    ) -> bool:
        """Check if two comparisons on the same variable contradict."""
        try:
            n1 = float(val1)
            n2 = float(val2)
        except ValueError:
            if val1 != val2:
                return False
            same_val = val1 == val2
            if same_val:
                if {op1, op2} == {"==", "!="} or {op1, op2} == {"===", "!=="}:
                    return True
                if {op1, op2} == {"==", "!="}:
                    return True
            return False

        if op1 == "==" and op2 == "==":
            return n1 != n2
        if op1 in {"==", "==="} and op2 in {"==", "==="}:
            return n1 != n2
        if {op1, op2} == {"==", "!="} or {op1, op2} == {"===", "!=="}:
            return n1 == n2
        gt_ops = {">", ">="}
        lt_ops = {"<", "<="}
        if op1 in gt_ops and op2 in lt_ops:
            return n1 >= n2
        if op1 in lt_ops and op2 in gt_ops:
            return n2 >= n1
        return False

    def _check_subsumed(
        self, node: tree_sitter.Node, ext: str,
    ) -> list[TautologicalIssue]:
        """Detect subsumed comparisons where one is redundant."""
        issues: list[TautologicalIssue] = []

        is_and = False
        if ext == ".py" and node.type == "boolean_operator":
            children_text = [_txt(c).strip() for c in node.children]
            if "and" in children_text:
                is_and = True
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".go"} and node.type == "binary_expression":
            op = node.child_by_field_name("operator")
            if op and _txt(op).strip() == "&&":
                is_and = True
        elif ext == ".java" and node.type == "binary_expression":
            for child in node.children:
                if _txt(child).strip() == "&&":
                    is_and = True
                    break

        if not is_and:
            return []

        parts = self._collect_and_children(node, ext)
        comparisons: list[tuple[str, str, str, tree_sitter.Node]] = []

        for part in parts:
            comp = self._extract_comparison(part, ext)
            if comp:
                comparisons.append((*comp, part))

        for i in range(len(comparisons)):
            for j in range(len(comparisons)):
                if i == j:
                    continue
                left_i, op_i, right_i, node_i = comparisons[i]
                left_j, op_j, right_j, _ = comparisons[j]

                if left_i == left_j:
                    subsumed = self._is_subsumed(op_i, right_i, op_j, right_j)
                    if subsumed:
                        issues.append(TautologicalIssue(
                            issue_type=ISSUE_SUBSUMED,
                            line=node_i.start_point[0] + 1,
                            message=(
                                f"Subsumed condition: '{left_i} {op_i} {right_i}' "
                                f"is redundant given '{left_j} {op_j} {right_j}'"
                            ),
                            severity=_SEVERITY_MAP[ISSUE_SUBSUMED],
                            details=(
                                f"{left_i} {op_i} {right_i} subsumed by "
                                f"{left_j} {op_j} {right_j}"
                            ),
                            suggestion=_SUGGESTIONS[ISSUE_SUBSUMED],
                        ))
        return issues

    def _is_subsumed(self, op1: str, val1: str, op2: str, val2: str) -> bool:
        """Check if op1+val1 is subsumed by op2+val2 (first is redundant)."""
        try:
            n1 = float(val1)
            n2 = float(val2)
        except ValueError:
            return False

        if op1 == ">" and op2 == ">":
            return n1 <= n2
        if op1 == ">=" and op2 == ">=":
            return n1 <= n2
        if op1 == ">" and op2 == ">=":
            return n1 < n2
        if op1 == ">=" and op2 == ">":
            return n1 <= n2
        if op1 == "<" and op2 == "<":
            return n1 >= n2
        if op1 == "<=" and op2 == "<=":
            return n1 >= n2
        if op1 == "<" and op2 == "<=":
            return n1 > n2
        if op1 == "<=" and op2 == "<":
            return n1 >= n2
        return False
