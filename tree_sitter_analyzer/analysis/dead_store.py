"""Dead Store Detector.

Detects variables that are assigned but whose value is never read:
  - dead_store: variable assigned but value never read before reassignment or scope exit
  - immediate_reassignment: variable reassigned before the first value is read

Self-assignment (x = x) was handled by self_assignment.py (removed — covered by Ruff PLW0127).

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_DEAD_STORE = "dead_store"
ISSUE_IMMEDIATE_REASSIGNMENT = "immediate_reassignment"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_DEAD_STORE: SEVERITY_MEDIUM,
    ISSUE_IMMEDIATE_REASSIGNMENT: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_DEAD_STORE: "Variable is assigned but the value is never read before reassignment or scope exit",
    ISSUE_IMMEDIATE_REASSIGNMENT: "Variable is reassigned before the previous value was read",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_DEAD_STORE: "Remove the unused assignment or use the value.",
    ISSUE_IMMEDIATE_REASSIGNMENT: "Remove the first assignment if the value is not needed.",
}

# Node types that define a function/method scope per language
_FUNCTION_SCOPES: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "function_definition", "lambda",
    }),
    ".js": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".jsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".ts": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".tsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".java": frozenset({
        "method_declaration", "constructor_declaration",
        "lambda_expression",
    }),
    ".go": frozenset({
        "function_declaration", "method_declaration",
        "func_literal",
    }),
}

# Node types that represent an assignment per language
_ASSIGNMENT_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"assignment"}),
    ".js": frozenset({"assignment_expression", "variable_declarator"}),
    ".jsx": frozenset({"assignment_expression", "variable_declarator"}),
    ".ts": frozenset({"assignment_expression", "variable_declarator"}),
    ".tsx": frozenset({"assignment_expression", "variable_declarator"}),
    ".java": frozenset({"variable_declarator", "assignment_expression"}),
    ".go": frozenset({"short_var_declaration", "assignment_statement"}),
}

# Node types that we should skip into (sub-scopes) when scanning a function body
_SUB_SCOPE_CREATORS: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "function_definition", "lambda", "class_definition",
        "list_comprehension", "set_comprehension",
        "dictionary_comprehension", "generator_expression",
    }),
    ".js": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".jsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".ts": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".tsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".java": frozenset({
        "method_declaration", "constructor_declaration",
        "lambda_expression", "class_declaration",
        "interface_declaration",
    }),
    ".go": frozenset({
        "function_declaration", "method_declaration",
        "func_literal",
    }),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class DeadStoreIssue:
    line_number: int
    issue_type: str
    variable_name: str
    severity: str
    description: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "variable_name": self.variable_name,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class DeadStoreResult:
    total_functions: int
    issues: tuple[DeadStoreIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_functions": self.total_functions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _get_assignment_target(
    node: tree_sitter.Node, ext: str,
) -> str | None:
    """Extract the variable name being assigned to."""
    if ext == ".py":
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                return _safe_text(left) or None
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                return _safe_text(left) or None
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.type == "identifier":
                return _safe_text(name_node) or None
    elif ext == ".java":
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.type == "identifier":
                return _safe_text(name_node) or None
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                return _safe_text(left) or None
    elif ext == ".go":
        if node.type == "short_var_declaration":
            for child in node.children:
                if child.type == "expression_list":
                    for gc in child.children:
                        if gc.type == "identifier":
                            name = _safe_text(gc)
                            return name or None
                elif child.type == "identifier":
                    name = _safe_text(child)
                    return name or None
        if node.type == "assignment_statement":
            left = node.child_by_field_name("left")
            if left is not None:
                if left.type == "identifier":
                    return _safe_text(left) or None
                if left.type == "expression_list":
                    first = left.children[0] if left.children else None
                    if first is not None and first.type == "identifier":
                        return _safe_text(first) or None
    return None


def _collect_identifiers_in(
    node: tree_sitter.Node,
    names: set[str],
    exclude_target: str | None = None,
) -> None:
    """Collect all identifier references in a node tree."""
    if node.type == "identifier":
        name = _safe_text(node)
        if name and name != exclude_target:
            names.add(name)
        return
    for child in node.children:
        _collect_identifiers_in(child, names, exclude_target)


def _extract_reads(
    node: tree_sitter.Node,
    ext: str,
    sub_scopes: frozenset[str],
    reads: set[str],
) -> None:
    """Collect variable names that are read (used) in a node, skipping sub-scopes."""
    if node.type in sub_scopes:
        return
    if node.type == "identifier":
        name = _safe_text(node)
        if name:
            reads.add(name)
        return
    for child in node.children:
        _extract_reads(child, ext, sub_scopes, reads)


def _analyze_function_body(
    func_node: tree_sitter.Node,
    ext: str,
    issues: list[DeadStoreIssue],
) -> None:
    """Analyze a function body for dead stores."""
    assignment_types = _ASSIGNMENT_TYPES.get(ext, frozenset())
    sub_scopes = _SUB_SCOPE_CREATORS.get(ext, frozenset())

    body_node: tree_sitter.Node | None = None
    for child in func_node.children:
        if child.type in ("block", "body", "statement_block", "compound_statement"):
            body_node = child
            break
        if ext == ".py" and child.type == "block":
            body_node = child
            break
        if ext == ".go" and child.type == "block":
            body_node = child
            break

    if body_node is None:
        if ext == ".py":
            body_node = func_node
        else:
            return

    # Collect all statements in order
    assignments: list[tuple[str, int, tree_sitter.Node]] = []
    _collect_assignments(body_node, ext, assignment_types, sub_scopes, assignments)

    if not assignments:
        return

    # For each assignment, check if the previous value of that variable was read
    assigned_vars: dict[str, int] = {}
    for idx, (var_name, _line, _assign_node) in enumerate(assignments):
        prev_idx = assigned_vars.get(var_name)

        if prev_idx is not None:
            # Check if the variable was read between previous assignment and this one
            was_read = _check_read_between(
                assignments, prev_idx, idx, var_name, ext, sub_scopes,
            )
            if not was_read:
                prev_var, prev_line, _ = assignments[prev_idx]
                issues.append(DeadStoreIssue(
                    line_number=prev_line,
                    issue_type=ISSUE_IMMEDIATE_REASSIGNMENT,
                    variable_name=prev_var,
                    severity=_SEVERITY_MAP[ISSUE_IMMEDIATE_REASSIGNMENT],
                    description=_DESCRIPTIONS[ISSUE_IMMEDIATE_REASSIGNMENT],
                ))

        assigned_vars[var_name] = idx

    # Check for dead stores at scope exit (last assignment of each var was never read)
    _check_scope_exit(body_node, ext, assignments, assigned_vars, sub_scopes, issues)


def _collect_assignments(
    node: tree_sitter.Node,
    ext: str,
    assignment_types: frozenset[str],
    sub_scopes: frozenset[str],
    result: list[tuple[str, int, tree_sitter.Node]],
) -> None:
    """Collect all assignments in a node in order."""
    if node.type in sub_scopes:
        return
    if node.type in assignment_types:
        target = _get_assignment_target(node, ext)
        if target is not None:
            result.append((target, node.start_point[0] + 1, node))
        return
    for child in node.children:
        _collect_assignments(child, ext, assignment_types, sub_scopes, result)


def _check_read_between(
    assignments: list[tuple[str, int, tree_sitter.Node]],
    prev_idx: int,
    curr_idx: int,
    var_name: str,
    ext: str,
    sub_scopes: frozenset[str],
) -> bool:
    """Check if a variable was read between two assignment indices."""
    _, _, prev_node = assignments[prev_idx]
    _, _, curr_node = assignments[curr_idx]
    prev_end = prev_node.end_point[0]
    curr_start = curr_node.start_point[0]

    # Walk the AST between these line ranges to find reads
    # Use the parent node and check children in the line range
    reads: set[str] = set()
    if prev_node.parent is not None:
        _collect_reads_in_range(
            prev_node.parent, var_name, prev_end, curr_start,
            ext, sub_scopes, reads,
        )
    return var_name in reads


def _is_assignment_target(node: tree_sitter.Node, ext: str) -> bool:
    """Check if an identifier node is the target (left side) of an assignment."""
    parent = node.parent
    if parent is None:
        return False

    # Go: identifier may be nested inside expression_list under short_var_declaration
    if ext == ".go" and parent.type == "expression_list":
        grandparent = parent.parent
        if grandparent is not None and grandparent.type == "short_var_declaration":
            left_el = grandparent.child_by_field_name("left")
            if left_el is not None and left_el.id == parent.id:
                return True
        if grandparent is not None and grandparent.type == "assignment_statement":
            left_field = grandparent.child_by_field_name("left")
            if left_field is not None and left_field.id == parent.id:
                return True

    assignment_types = _ASSIGNMENT_TYPES.get(ext, frozenset())
    if parent.type not in assignment_types:
        return False
    if ext == ".py":
        left = parent.child_by_field_name("left")
        return left is not None and left.id == node.id
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        if parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            return left is not None and left.id == node.id
        if parent.type == "variable_declarator":
            name_node = parent.child_by_field_name("name")
            return name_node is not None and name_node.id == node.id
    if ext == ".java":
        if parent.type == "variable_declarator":
            name_node = parent.child_by_field_name("name")
            return name_node is not None and name_node.id == node.id
    if ext == ".go":
        if parent.type == "short_var_declaration":
            return True
        if parent.type == "assignment_statement":
            left = parent.child_by_field_name("left")
            if left is not None:
                if left.id == node.id:
                    return True
                if left.type == "expression_list":
                    for gc in left.children:
                        if gc.id == node.id:
                            return True
    return False


def _collect_reads_in_range(
    node: tree_sitter.Node,
    target_var: str,
    start_line: int,
    end_line: int,
    ext: str,
    sub_scopes: frozenset[str],
    reads: set[str],
) -> None:
    """Collect reads of target_var within a line range."""
    node_start = node.start_point[0]
    node_end = node.end_point[0]

    if node_end < start_line or node_start > end_line:
        return

    if node.type in sub_scopes:
        return

    if node.type == "identifier":
        name = _safe_text(node)
        if name == target_var:
            if _is_assignment_target(node, ext):
                return
            if node.start_point[0] >= start_line and node.start_point[0] <= end_line:
                reads.add(target_var)
        return

    for child in node.children:
        _collect_reads_in_range(
            child, target_var, start_line, end_line,
            ext, sub_scopes, reads,
        )


def _check_scope_exit(
    body_node: tree_sitter.Node,
    ext: str,
    assignments: list[tuple[str, int, tree_sitter.Node]],
    assigned_vars: dict[str, int],
    sub_scopes: frozenset[str],
    issues: list[DeadStoreIssue],
) -> None:
    """Check if last assignment of each var is dead (never read before scope exit)."""
    already_reported: set[int] = set()
    for issue in issues:
        already_reported.add(issue.line_number)

    for var_name, idx in assigned_vars.items():
        var_name_check, line, node = assignments[idx]
        if line in already_reported:
            continue

        # Check if this variable is read after the last assignment
        reads: set[str] = set()
        node_end_line = node.end_point[0]
        _collect_reads_after(
            body_node, var_name, node_end_line, ext, sub_scopes, reads,
        )
        if var_name not in reads:
            issues.append(DeadStoreIssue(
                line_number=line,
                issue_type=ISSUE_DEAD_STORE,
                variable_name=var_name,
                severity=_SEVERITY_MAP[ISSUE_DEAD_STORE],
                description=_DESCRIPTIONS[ISSUE_DEAD_STORE],
            ))


def _collect_reads_after(
    node: tree_sitter.Node,
    target_var: str,
    after_line: int,
    ext: str,
    sub_scopes: frozenset[str],
    reads: set[str],
) -> None:
    """Collect reads of target_var after a given line."""
    if node.type in sub_scopes:
        return

    if node.type == "identifier":
        name = _safe_text(node)
        if name == target_var:
            if _is_assignment_target(node, ext):
                return
            if node.start_point[0] >= after_line:
                reads.add(target_var)
        return

    for child in node.children:
        _collect_reads_after(
            child, target_var, after_line, ext, sub_scopes, reads,
        )


class DeadStoreAnalyzer(BaseAnalyzer):
    """Analyzes code for dead store issues."""

    def analyze_file(self, file_path: Path | str) -> DeadStoreResult:
        path = Path(file_path)
        if not path.exists():
            return DeadStoreResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return DeadStoreResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> DeadStoreResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DeadStoreResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        function_scopes = _FUNCTION_SCOPES.get(ext, frozenset())
        issues: list[DeadStoreIssue] = []
        total_functions = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_functions

            if node.type in function_scopes:
                total_functions += 1
                _analyze_function_body(node, ext, issues)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return DeadStoreResult(
            total_functions=total_functions,
            issues=tuple(issues),
            file_path=str(path),
        )
