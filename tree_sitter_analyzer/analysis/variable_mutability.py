"""
Variable Mutability Analyzer.

Detects variable mutability issues that cause bugs and reduce code clarity.
Complements naming_convention (naming style) and coupling_metrics (module-level)
by analyzing variable-level behavior within functions.

Issues detected:
  - shadow_variable: inner scope redeclares an outer variable name
  - unused_assignment: variable assigned but never referenced afterward
  - reassigned_constant: UPPER_SNAKE_CASE variable gets reassigned
  - mutation_in_iteration: loop body modifies an outer-scope variable
"""
from __future__ import annotations

import re
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

MUTABILITY_SHADOW = "shadow_variable"
MUTABILITY_UNUSED = "unused_assignment"
MUTABILITY_REASSIGNED_CONST = "reassigned_constant"
MUTABILITY_LOOP_MUTATION = "mutation_in_iteration"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_SEVERITY_MAP: dict[str, str] = {
    MUTABILITY_SHADOW: SEVERITY_MEDIUM,
    MUTABILITY_UNUSED: SEVERITY_LOW,
    MUTABILITY_REASSIGNED_CONST: SEVERITY_HIGH,
    MUTABILITY_LOOP_MUTATION: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    MUTABILITY_SHADOW: "Inner scope redeclares variable from outer scope",
    MUTABILITY_UNUSED: "Variable is assigned but never used afterward",
    MUTABILITY_REASSIGNED_CONST: "UPPER_SNAKE_CASE variable is reassigned (constant violation)",
    MUTABILITY_LOOP_MUTATION: "Loop body modifies variable declared in outer scope",
}

_SUGGESTIONS: dict[str, str] = {
    MUTABILITY_SHADOW: "Rename the inner variable to avoid shadowing",
    MUTABILITY_UNUSED: "Remove the unused assignment or use the variable",
    MUTABILITY_REASSIGNED_CONST: "Use a lowercase name or avoid reassignment",
    MUTABILITY_LOOP_MUTATION: "Use a return value instead of mutating outer state",
}

_UPPER_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Scope boundary node types per language
_PYTHON_SCOPE_NODES = frozenset({
    "function_definition", "class_definition", "lambda",
    "list_comprehension", "set_comprehension", "dictionary_comprehension",
    "generator_expression", "for_statement", "while_statement",
    "if_statement", "with_statement", "try_statement",
})
_JS_SCOPE_NODES = frozenset({
    "function_declaration", "function_expression", "arrow_function",
    "method_definition", "for_statement", "for_in_statement",
    "for_of_statement", "while_statement", "if_statement",
    "block_statement", "catch_clause",
})
_JAVA_SCOPE_NODES = frozenset({
    "method_declaration", "constructor_declaration", "lambda_expression",
    "for_statement", "enhanced_for_statement", "while_statement",
    "if_statement", "try_statement", "catch_clause",
    "switch_statement", "synchronized_statement",
})
_GO_SCOPE_NODES = frozenset({
    "function_declaration", "method_declaration", "func_literal",
    "for_statement", "if_statement",
})

@dataclass(frozen=True)
class MutabilityIssue:
    issue_type: str
    line: int
    column: int
    variable_name: str
    severity: str
    description: str
    suggestion: str

@dataclass(frozen=True)
class MutabilityResult:
    file_path: str
    issues: tuple[MutabilityIssue, ...]
    total_issues: int
    quality_score: float
    issue_counts: dict[str, int] = field(default_factory=dict)

def _decode(node: tree_sitter.Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")

def _empty_result(file_path: str) -> MutabilityResult:
    return MutabilityResult(
        file_path=file_path,
        issues=(),
        total_issues=0,
        quality_score=100.0,
        issue_counts={},
    )

def _compute_score(issue_count: int, issues: list[MutabilityIssue]) -> float:
    if issue_count == 0:
        return 100.0
    penalty = 0.0
    for iss in issues:
        if iss.severity == SEVERITY_HIGH:
            penalty += 20.0
        elif iss.severity == SEVERITY_MEDIUM:
            penalty += 10.0
        else:
            penalty += 3.0
    return max(0.0, 100.0 - penalty)

class VariableMutabilityAnalyzer(BaseAnalyzer):
    """Analyzes variable mutability issues across Python, JS/TS, Java, Go."""

    def analyze_file(self, file_path: Path | str) -> MutabilityResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path))
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return _empty_result(str(path))

        tree = parser.parse(content)

        if ext == ".py":
            issues = self._analyze_python(tree.root_node, content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(tree.root_node, content)
        elif ext == ".java":
            issues = self._analyze_java(tree.root_node, content)
        elif ext == ".go":
            issues = self._analyze_go(tree.root_node, content)
        else:
            issues = []

        issue_counts: dict[str, int] = {}
        for iss in issues:
            issue_counts[iss.issue_type] = issue_counts.get(iss.issue_type, 0) + 1

        score = _compute_score(len(issues), issues)

        return MutabilityResult(
            file_path=str(path),
            issues=tuple(issues),
            total_issues=len(issues),
            quality_score=round(score, 1),
            issue_counts=issue_counts,
        )

    # ------------------------------------------------------------------ #
    #  Python                                                              #
    # ------------------------------------------------------------------ #

    def _analyze_python(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[MutabilityIssue]:
        issues: list[MutabilityIssue] = []
        self._walk_python_scope(root, content, issues, scope_stack=None)
        return issues

    def _walk_python_scope(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]] | None,
    ) -> None:
        if scope_stack is None:
            scope_stack = [set()]

        is_new_scope = node.type in _PYTHON_SCOPE_NODES

        if is_new_scope:
            scope_stack.append(set())

        # Collect assignments in this node
        if node.type in ("function_definition", "class_definition"):
            self._collect_python_assignments(node, content, issues, scope_stack)
            self._check_python_unused(node, content, issues)
            self._check_python_const_reassign(node, content, issues)
            self._check_python_loop_mutation(node, content, issues)

        for child in node.children:
            self._walk_python_scope(child, content, issues, scope_stack)

        if is_new_scope:
            scope_stack.pop()

    def _collect_python_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]],
    ) -> None:
        if len(scope_stack) < 2:
            return

        outer_vars = set()
        for scope in scope_stack[:-1]:
            outer_vars.update(scope)

        inner_vars = scope_stack[-1]

        self._find_python_assignments(node, content, outer_vars, inner_vars, issues)
        scope_stack[-1].update(inner_vars)

    def _find_python_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        inner_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    name = _decode(name_node)
                    if name in outer_vars:
                        issues.append(
                            MutabilityIssue(
                                issue_type=MUTABILITY_SHADOW,
                                line=name_node.start_point[0] + 1,
                                column=name_node.start_point[1],
                                variable_name=name,
                                severity=_SEVERITY_MAP[MUTABILITY_SHADOW],
                                description=_DESCRIPTIONS[MUTABILITY_SHADOW],
                                suggestion=_SUGGESTIONS[MUTABILITY_SHADOW],
                            )
                        )
                    inner_vars.add(name)

        if node.type == "for_statement":
            for child in node.children:
                if child.type == "identifier":
                    name = _decode(child)
                    if name in outer_vars:
                        issues.append(
                            MutabilityIssue(
                                issue_type=MUTABILITY_SHADOW,
                                line=child.start_point[0] + 1,
                                column=child.start_point[1],
                                variable_name=name,
                                severity=_SEVERITY_MAP[MUTABILITY_SHADOW],
                                description=_DESCRIPTIONS[MUTABILITY_SHADOW],
                                suggestion=_SUGGESTIONS[MUTABILITY_SHADOW],
                            )
                        )
                    inner_vars.add(name)

        for child in node.children:
            if child.type not in ("function_definition", "class_definition", "lambda"):
                self._find_python_assignments(child, content, outer_vars, inner_vars, issues)

    def _check_python_unused(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        assignments: dict[str, tree_sitter.Node] = {}
        references: set[str] = set()

        self._collect_python_assigns_and_refs(node, assignments, references)

        for name, assign_node in assignments.items():
            if name not in references and not name.startswith("_"):
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_UNUSED,
                        line=assign_node.start_point[0] + 1,
                        column=assign_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_UNUSED],
                        description=_DESCRIPTIONS[MUTABILITY_UNUSED],
                        suggestion=_SUGGESTIONS[MUTABILITY_UNUSED],
                    )
                )

    def _collect_python_assigns_and_refs(
        self,
        node: tree_sitter.Node,
        assignments: dict[str, tree_sitter.Node],
        references: set[str],
    ) -> None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    name = _decode(name_node)
                    if name not in assignments:
                        assignments[name] = name_node
            right = node.child_by_field_name("right")
            if right:
                self._collect_refs(right, references)
            return

        if node.type == "for_statement":
            for child in node.children:
                if child.type == "identifier":
                    name = _decode(child)
                    if name not in assignments:
                        assignments[name] = child
                elif child.type not in ("in", "for"):
                    self._collect_refs(child, references)
            return

        if node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    name = _decode(name_node)
                    references.add(name)
            right = node.child_by_field_name("right")
            if right:
                self._collect_refs(right, references)
            return

        # For all other node types, collect refs from identifiers
        # that are NOT assignment targets
        if node.type == "identifier":
            references.add(_decode(node))
            return

        for child in node.children:
            if child.type not in ("function_definition", "class_definition", "lambda"):
                self._collect_python_assigns_and_refs(child, assignments, references)

    def _collect_refs(
        self,
        node: tree_sitter.Node,
        references: set[str],
    ) -> None:
        if node.type == "identifier":
            references.add(_decode(node))
        for child in node.children:
            self._collect_refs(child, references)

    def _check_python_const_reassign(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        const_assigns: dict[str, tree_sitter.Node] = {}
        all_assigns: list[tuple[str, tree_sitter.Node]] = []

        self._collect_all_python_assigns(node, const_assigns, all_assigns)

        for name, first_node in const_assigns.items():
            count = sum(1 for n, nd in all_assigns if n == name)
            if count > 1:
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_REASSIGNED_CONST,
                        line=first_node.start_point[0] + 1,
                        column=first_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_REASSIGNED_CONST],
                        description=_DESCRIPTIONS[MUTABILITY_REASSIGNED_CONST],
                        suggestion=_SUGGESTIONS[MUTABILITY_REASSIGNED_CONST],
                    )
                )

    def _collect_all_python_assigns(
        self,
        node: tree_sitter.Node,
        const_assigns: dict[str, tree_sitter.Node],
        all_assigns: list[tuple[str, tree_sitter.Node]],
    ) -> None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    name = _decode(name_node)
                    all_assigns.append((name, name_node))
                    if _UPPER_SNAKE_RE.match(name) and name not in const_assigns:
                        const_assigns[name] = name_node

        for child in node.children:
            if child.type not in ("function_definition", "class_definition", "lambda"):
                self._collect_all_python_assigns(child, const_assigns, all_assigns)

    def _check_python_loop_mutation(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        self._walk_python_loops(node, content, issues)

    def _walk_python_loops(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type in ("for_statement", "while_statement"):
            self._check_loop_body_mutation(node, content, issues)

        for child in node.children:
            self._walk_python_loops(child, content, issues)

    def _check_loop_body_mutation(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        # Collect variables declared BEFORE the loop
        outer_vars = self._get_pre_loop_assignments(loop_node, content)

        # Check loop body for augmented assignments to outer vars
        body = None
        for child in loop_node.children:
            if child.type == "block":
                body = child
                break

        if body is None:
            return

        self._find_augmented_assigns(body, content, outer_vars, issues)

    def _get_pre_loop_assignments(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
    ) -> set[str]:
        parent = loop_node.parent
        if parent is None:
            return set()

        pre_vars: set[str] = set()
        for child in parent.children:
            if child.id == loop_node.id:
                break
            self._collect_assigns_from_node(child, pre_vars)
        return pre_vars

    def _collect_assigns_from_node(
        self,
        node: tree_sitter.Node,
        targets: set[str],
    ) -> None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    targets.add(_decode(name_node))
        elif node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    targets.add(_decode(name_node))
        elif node.type == "expression_statement":
            for child in node.children:
                self._collect_assigns_from_node(child, targets)

    def _find_augmented_assigns(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            if left:
                for name_node in self._extract_identifiers(left):
                    name = _decode(name_node)
                    if name in outer_vars:
                        issues.append(
                            MutabilityIssue(
                                issue_type=MUTABILITY_LOOP_MUTATION,
                                line=name_node.start_point[0] + 1,
                                column=name_node.start_point[1],
                                variable_name=name,
                                severity=_SEVERITY_MAP[MUTABILITY_LOOP_MUTATION],
                                description=_DESCRIPTIONS[MUTABILITY_LOOP_MUTATION],
                                suggestion=_SUGGESTIONS[MUTABILITY_LOOP_MUTATION],
                            )
                        )

        for child in node.children:
            self._find_augmented_assigns(child, content, outer_vars, issues)

    # ------------------------------------------------------------------ #
    #  JavaScript / TypeScript                                             #
    # ------------------------------------------------------------------ #

    def _analyze_javascript(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[MutabilityIssue]:
        issues: list[MutabilityIssue] = []
        self._walk_js_scope(root, content, issues, scope_stack=None)
        return issues

    def _walk_js_scope(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]] | None,
    ) -> None:
        if scope_stack is None:
            scope_stack = [set()]

        is_new_scope = node.type in _JS_SCOPE_NODES
        if is_new_scope:
            scope_stack.append(set())

        if node.type in ("function_declaration", "function_expression", "arrow_function", "method_definition"):
            self._collect_js_assignments(node, content, issues, scope_stack)
            self._check_js_unused(node, content, issues)
            self._check_js_const_reassign(node, content, issues)
            self._check_js_loop_mutation(node, content, issues)

        for child in node.children:
            self._walk_js_scope(child, content, issues, scope_stack)

        if is_new_scope:
            scope_stack.pop()

    def _collect_js_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]],
    ) -> None:
        if len(scope_stack) < 2:
            return

        outer_vars = set()
        for scope in scope_stack[:-1]:
            outer_vars.update(scope)
        inner_vars = scope_stack[-1]

        self._find_js_declarations(node, content, outer_vars, inner_vars, issues)
        scope_stack[-1].update(inner_vars)

    def _find_js_declarations(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        inner_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                name = _decode(name_node)
                if name in outer_vars:
                    issues.append(
                        MutabilityIssue(
                            issue_type=MUTABILITY_SHADOW,
                            line=name_node.start_point[0] + 1,
                            column=name_node.start_point[1],
                            variable_name=name,
                            severity=_SEVERITY_MAP[MUTABILITY_SHADOW],
                            description=_DESCRIPTIONS[MUTABILITY_SHADOW],
                            suggestion=_SUGGESTIONS[MUTABILITY_SHADOW],
                        )
                    )
                inner_vars.add(name)

        for child in node.children:
            if child.type not in ("function_declaration", "function_expression", "arrow_function", "method_definition"):
                self._find_js_declarations(child, content, outer_vars, inner_vars, issues)

    def _check_js_unused(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        assignments: dict[str, tree_sitter.Node] = {}
        references: set[str] = set()
        self._collect_js_assigns_and_refs(node, assignments, references)

        for name, assign_node in assignments.items():
            if name not in references and not name.startswith("_"):
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_UNUSED,
                        line=assign_node.start_point[0] + 1,
                        column=assign_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_UNUSED],
                        description=_DESCRIPTIONS[MUTABILITY_UNUSED],
                        suggestion=_SUGGESTIONS[MUTABILITY_UNUSED],
                    )
                )

    def _collect_js_assigns_and_refs(
        self,
        node: tree_sitter.Node,
        assignments: dict[str, tree_sitter.Node],
        references: set[str],
    ) -> None:
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                name = _decode(name_node)
                if name not in assignments:
                    assignments[name] = name_node
            value = node.child_by_field_name("value")
            if value:
                self._collect_refs(value, references)
            return

        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = _decode(left)
                if name not in assignments:
                    assignments[name] = left
            right = node.child_by_field_name("right")
            if right:
                self._collect_refs(right, references)
            return

        # Collect identifiers as references in all other contexts
        if node.type == "identifier":
            references.add(_decode(node))
            return

        for child in node.children:
            if child.type not in ("function_declaration", "function_expression", "arrow_function"):
                self._collect_js_assigns_and_refs(child, assignments, references)

    def _check_js_const_reassign(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        const_vars: dict[str, tree_sitter.Node] = {}
        self._find_js_const_declarations(node, const_vars)

        reassign_targets: set[str] = set()
        self._find_js_reassigns(node, reassign_targets)

        for name, name_node in const_vars.items():
            if name in reassign_targets:
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_REASSIGNED_CONST,
                        line=name_node.start_point[0] + 1,
                        column=name_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_REASSIGNED_CONST],
                        description=_DESCRIPTIONS[MUTABILITY_REASSIGNED_CONST],
                        suggestion=_SUGGESTIONS[MUTABILITY_REASSIGNED_CONST],
                    )
                )

    def _find_js_const_declarations(
        self,
        node: tree_sitter.Node,
        const_vars: dict[str, tree_sitter.Node],
    ) -> None:
        if node.type in ("variable_declaration", "lexical_declaration"):
            kind = node.child_by_field_name("kind")
            is_const = kind and _decode(kind) == "const"
            if is_const:
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            const_vars[_decode(name_node)] = name_node

        for child in node.children:
            self._find_js_const_declarations(child, const_vars)

    def _find_js_reassigns(
        self,
        node: tree_sitter.Node,
        targets: set[str],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                targets.add(_decode(left))

        for child in node.children:
            self._find_js_reassigns(child, targets)

    def _check_js_loop_mutation(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        self._walk_js_loops(node, content, issues)

    def _walk_js_loops(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type in ("for_statement", "for_in_statement", "for_of_statement", "while_statement"):
            outer_vars = self._get_js_pre_loop_assignments(node, content)
            if outer_vars:
                body = node.child_by_field_name("body")
                if body:
                    self._find_js_augmented_assigns(body, content, outer_vars, issues)

        for child in node.children:
            self._walk_js_loops(child, content, issues)

    def _get_js_pre_loop_assignments(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
    ) -> set[str]:
        parent = loop_node.parent
        if parent is None:
            return set()

        pre_vars: set[str] = set()
        for child in parent.children:
            if child.id == loop_node.id:
                break
            if child.type == "variable_declaration":
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            pre_vars.add(_decode(name_node))
            if child.type == "lexical_declaration":
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            pre_vars.add(_decode(name_node))
        return pre_vars

    def _find_js_augmented_assigns(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "augmented_assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = _decode(left)
                if name in outer_vars:
                    issues.append(
                        MutabilityIssue(
                            issue_type=MUTABILITY_LOOP_MUTATION,
                            line=left.start_point[0] + 1,
                            column=left.start_point[1],
                            variable_name=name,
                            severity=_SEVERITY_MAP[MUTABILITY_LOOP_MUTATION],
                            description=_DESCRIPTIONS[MUTABILITY_LOOP_MUTATION],
                            suggestion=_SUGGESTIONS[MUTABILITY_LOOP_MUTATION],
                        )
                    )

        for child in node.children:
            self._find_js_augmented_assigns(child, content, outer_vars, issues)

    # ------------------------------------------------------------------ #
    #  Java                                                                #
    # ------------------------------------------------------------------ #

    def _analyze_java(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[MutabilityIssue]:
        issues: list[MutabilityIssue] = []
        self._walk_java_scope(root, content, issues, scope_stack=None)
        return issues

    def _walk_java_scope(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]] | None,
    ) -> None:
        if scope_stack is None:
            scope_stack = [set()]

        is_new_scope = node.type in _JAVA_SCOPE_NODES
        if is_new_scope:
            scope_stack.append(set())

        if node.type in ("method_declaration", "constructor_declaration"):
            self._collect_java_assignments(node, content, issues, scope_stack)
            self._check_java_unused(node, content, issues)
            self._check_java_final_reassign(node, content, issues)
            self._check_java_loop_mutation(node, content, issues)

        if node.type in ("for_statement", "enhanced_for_statement", "while_statement", "if_statement", "catch_clause"):
            self._collect_java_block_assignments(node, content, issues, scope_stack)

        for child in node.children:
            self._walk_java_scope(child, content, issues, scope_stack)

        if is_new_scope:
            scope_stack.pop()

    def _collect_java_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]],
    ) -> None:
        if len(scope_stack) < 2:
            return

        outer_vars = set()
        for scope in scope_stack[:-1]:
            outer_vars.update(scope)
        inner_vars = scope_stack[-1]

        self._find_java_local_declarations(node, content, outer_vars, inner_vars, issues)
        scope_stack[-1].update(inner_vars)

    def _find_java_local_declarations(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        inner_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "local_variable_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node and name_node.type == "identifier":
                        name = _decode(name_node)
                        if name in outer_vars:
                            issues.append(
                                MutabilityIssue(
                                    issue_type=MUTABILITY_SHADOW,
                                    line=name_node.start_point[0] + 1,
                                    column=name_node.start_point[1],
                                    variable_name=name,
                                    severity=_SEVERITY_MAP[MUTABILITY_SHADOW],
                                    description=_DESCRIPTIONS[MUTABILITY_SHADOW],
                                    suggestion=_SUGGESTIONS[MUTABILITY_SHADOW],
                                )
                            )
                        inner_vars.add(name)

        for child in node.children:
            if child.type not in ("method_declaration", "constructor_declaration", "lambda_expression"):
                self._find_java_local_declarations(child, content, outer_vars, inner_vars, issues)

    def _collect_java_block_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]],
    ) -> None:
        if len(scope_stack) < 2:
            return

        outer_vars = set()
        for scope in scope_stack[:-1]:
            outer_vars.update(scope)
        inner_vars: set[str] = set()

        self._find_java_local_declarations(node, content, outer_vars, inner_vars, issues)
        scope_stack[-1].update(inner_vars)

    def _check_java_unused(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        assignments: dict[str, tree_sitter.Node] = {}
        references: set[str] = set()
        self._collect_java_assigns_and_refs(node, assignments, references)

        for name, assign_node in assignments.items():
            if name not in references:
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_UNUSED,
                        line=assign_node.start_point[0] + 1,
                        column=assign_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_UNUSED],
                        description=_DESCRIPTIONS[MUTABILITY_UNUSED],
                        suggestion=_SUGGESTIONS[MUTABILITY_UNUSED],
                    )
                )

    def _collect_java_assigns_and_refs(
        self,
        node: tree_sitter.Node,
        assignments: dict[str, tree_sitter.Node],
        references: set[str],
    ) -> None:
        if node.type == "local_variable_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node and name_node.type == "identifier":
                        name = _decode(name_node)
                        if name not in assignments:
                            assignments[name] = name_node
                    value = child.child_by_field_name("value")
                    if value:
                        self._collect_refs(value, references)
            return

        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = _decode(left)
                if name not in assignments:
                    assignments[name] = left
            right = node.child_by_field_name("right")
            if right:
                self._collect_refs(right, references)
            return

        if node.type == "identifier":
            references.add(_decode(node))
            return

        for child in node.children:
            if child.type not in ("method_declaration", "constructor_declaration", "lambda_expression"):
                self._collect_java_assigns_and_refs(child, assignments, references)

    def _check_java_final_reassign(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        final_vars: dict[str, tree_sitter.Node] = {}
        self._find_java_final_declarations(node, final_vars)

        reassign_targets: set[str] = set()
        self._find_java_reassigns(node, reassign_targets)

        for name, name_node in final_vars.items():
            if name in reassign_targets:
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_REASSIGNED_CONST,
                        line=name_node.start_point[0] + 1,
                        column=name_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_REASSIGNED_CONST],
                        description=_DESCRIPTIONS[MUTABILITY_REASSIGNED_CONST],
                        suggestion=_SUGGESTIONS[MUTABILITY_REASSIGNED_CONST],
                    )
                )

    def _find_java_final_declarations(
        self,
        node: tree_sitter.Node,
        final_vars: dict[str, tree_sitter.Node],
    ) -> None:
        if node.type == "local_variable_declaration":
            for child in node.children:
                if child.type in ("final", "public", "private", "protected"):
                    is_final = child.type == "final"
                    if is_final:
                        for sub in node.children:
                            if sub.type == "variable_declarator":
                                name_node = sub.child_by_field_name("name")
                                if name_node and name_node.type == "identifier":
                                    final_vars[_decode(name_node)] = name_node
                    break
            else:
                # Check for UPPER_SNAKE_CASE naming pattern as Java constant convention
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            name = _decode(name_node)
                            if _UPPER_SNAKE_RE.match(name):
                                final_vars[name] = name_node

        for child in node.children:
            self._find_java_final_declarations(child, final_vars)

    def _find_java_reassigns(
        self,
        node: tree_sitter.Node,
        targets: set[str],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                targets.add(_decode(left))

        for child in node.children:
            self._find_java_reassigns(child, targets)

    def _check_java_loop_mutation(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        self._walk_java_loops(node, content, issues)

    def _walk_java_loops(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type in ("for_statement", "enhanced_for_statement", "while_statement"):
            outer_vars = self._get_java_pre_loop_assignments(node, content)
            if outer_vars:
                body = node.child_by_field_name("body")
                if body:
                    self._find_java_augmented_assigns(body, content, outer_vars, issues)

        for child in node.children:
            self._walk_java_loops(child, content, issues)

    def _get_java_pre_loop_assignments(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
    ) -> set[str]:
        parent = loop_node.parent
        if parent is None:
            return set()

        pre_vars: set[str] = set()
        for child in parent.children:
            if child.id == loop_node.id:
                break
            if child.type == "local_variable_declaration":
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            pre_vars.add(_decode(name_node))
        return pre_vars

    def _find_java_augmented_assigns(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = _decode(left)
                if name in outer_vars:
                    # Only flag if it's augmented (+=, -=, etc.)
                    op = node.child_by_field_name("operator")
                    if op is None:
                        # Check by looking at children for operator tokens
                        for child in node.children:
                            child_text = _decode(child)
                            if child_text in ("+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="):
                                issues.append(
                                    MutabilityIssue(
                                        issue_type=MUTABILITY_LOOP_MUTATION,
                                        line=left.start_point[0] + 1,
                                        column=left.start_point[1],
                                        variable_name=name,
                                        severity=_SEVERITY_MAP[MUTABILITY_LOOP_MUTATION],
                                        description=_DESCRIPTIONS[MUTABILITY_LOOP_MUTATION],
                                        suggestion=_SUGGESTIONS[MUTABILITY_LOOP_MUTATION],
                                    )
                                )
                                break

        for child in node.children:
            self._find_java_augmented_assigns(child, content, outer_vars, issues)

    # ------------------------------------------------------------------ #
    #  Go                                                                  #
    # ------------------------------------------------------------------ #

    def _analyze_go(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[MutabilityIssue]:
        issues: list[MutabilityIssue] = []
        self._walk_go_scope(root, content, issues, scope_stack=None)
        return issues

    def _walk_go_scope(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]] | None,
    ) -> None:
        if scope_stack is None:
            scope_stack = [set()]

        is_new_scope = node.type in _GO_SCOPE_NODES
        if is_new_scope:
            scope_stack.append(set())

        if node.type in ("function_declaration", "method_declaration", "func_literal"):
            self._collect_go_assignments(node, content, issues, scope_stack)
            self._check_go_unused(node, content, issues)
            self._check_go_loop_mutation(node, content, issues)

        if node.type in ("if_statement",):
            self._collect_go_block_assignments(node, content, issues, scope_stack)

        for child in node.children:
            self._walk_go_scope(child, content, issues, scope_stack)

        if is_new_scope:
            scope_stack.pop()

    def _collect_go_block_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]],
    ) -> None:
        if len(scope_stack) < 2:
            return

        outer_vars = set()
        for scope in scope_stack[:-1]:
            outer_vars.update(scope)
        inner_vars: set[str] = set()

        self._find_go_short_vars(node, content, outer_vars, inner_vars, issues)
        scope_stack[-1].update(inner_vars)

    def _collect_go_assignments(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
        scope_stack: list[set[str]],
    ) -> None:
        if len(scope_stack) < 2:
            return

        outer_vars = set()
        for scope in scope_stack[:-1]:
            outer_vars.update(scope)
        inner_vars = scope_stack[-1]

        self._find_go_short_vars(node, content, outer_vars, inner_vars, issues)
        scope_stack[-1].update(inner_vars)

    def _find_go_short_vars(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        inner_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "short_var_declaration":
            for child in node.children:
                if child.type == "expression_list":
                    for expr in child.children:
                        if expr.type == "identifier":
                            name = _decode(expr)
                            if name in outer_vars:
                                issues.append(
                                    MutabilityIssue(
                                        issue_type=MUTABILITY_SHADOW,
                                        line=expr.start_point[0] + 1,
                                        column=expr.start_point[1],
                                        variable_name=name,
                                        severity=_SEVERITY_MAP[MUTABILITY_SHADOW],
                                        description=_DESCRIPTIONS[MUTABILITY_SHADOW],
                                        suggestion=_SUGGESTIONS[MUTABILITY_SHADOW],
                                    )
                                )
                            inner_vars.add(name)
                elif child.type == "identifier":
                    name = _decode(child)
                    if name in outer_vars:
                        issues.append(
                            MutabilityIssue(
                                issue_type=MUTABILITY_SHADOW,
                                line=child.start_point[0] + 1,
                                column=child.start_point[1],
                                variable_name=name,
                                severity=_SEVERITY_MAP[MUTABILITY_SHADOW],
                                description=_DESCRIPTIONS[MUTABILITY_SHADOW],
                                suggestion=_SUGGESTIONS[MUTABILITY_SHADOW],
                            )
                        )
                    inner_vars.add(name)

        for child in node.children:
            if child.type not in ("function_declaration", "method_declaration", "func_literal"):
                self._find_go_short_vars(child, content, outer_vars, inner_vars, issues)

    def _check_go_unused(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        assignments: dict[str, tree_sitter.Node] = {}
        references: set[str] = set()
        self._collect_go_assigns_and_refs(node, assignments, references)

        for name, assign_node in assignments.items():
            if name not in references and name != "_":
                issues.append(
                    MutabilityIssue(
                        issue_type=MUTABILITY_UNUSED,
                        line=assign_node.start_point[0] + 1,
                        column=assign_node.start_point[1],
                        variable_name=name,
                        severity=_SEVERITY_MAP[MUTABILITY_UNUSED],
                        description=_DESCRIPTIONS[MUTABILITY_UNUSED],
                        suggestion=_SUGGESTIONS[MUTABILITY_UNUSED],
                    )
                )

    def _collect_go_assigns_and_refs(
        self,
        node: tree_sitter.Node,
        assignments: dict[str, tree_sitter.Node],
        references: set[str],
    ) -> None:
        if node.type == "short_var_declaration":
            for child in node.children:
                if child.type == "expression_list":
                    for expr in child.children:
                        if expr.type == "identifier":
                            name = _decode(expr)
                            if name not in assignments and name != "_":
                                assignments[name] = expr
                elif child.type == "identifier":
                    name = _decode(child)
                    if name not in assignments and name != "_":
                        assignments[name] = child

            for child in node.children:
                if child.type not in ("expression_list", "identifier", ":="):
                    self._collect_refs(child, references)
            return

        if node.type == "var_declaration":
            for child in node.children:
                if child.type == "var_spec":
                    for sub in child.children:
                        if sub.type == "identifier":
                            name = _decode(sub)
                            if name not in assignments and name != "_":
                                assignments[name] = sub
            return

        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = _decode(left)
                if name not in assignments:
                    assignments[name] = left
            right = node.child_by_field_name("right")
            if right:
                self._collect_refs(right, references)
            return

        if node.type == "identifier":
            references.add(_decode(node))
            return

        for child in node.children:
            if child.type not in ("function_declaration", "method_declaration", "func_literal"):
                self._collect_go_assigns_and_refs(child, assignments, references)

    def _check_go_loop_mutation(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        self._walk_go_loops(node, content, issues)

    def _walk_go_loops(
        self,
        node: tree_sitter.Node,
        content: bytes,
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type == "for_statement":
            outer_vars = self._get_go_pre_loop_assignments(node, content)
            if outer_vars:
                body = node.child_by_field_name("body")
                if body:
                    self._find_go_assigns_to_outer(body, content, outer_vars, issues)

        for child in node.children:
            self._walk_go_loops(child, content, issues)

    def _get_go_pre_loop_assignments(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
    ) -> set[str]:
        parent = loop_node.parent
        if parent is None:
            return set()

        pre_vars: set[str] = set()
        for child in parent.children:
            if child.id == loop_node.id:
                break
            if child.type == "short_var_declaration":
                for sub in child.children:
                    if sub.type == "identifier":
                        pre_vars.add(_decode(sub))
                    if sub.type == "expression_list":
                        for expr in sub.children:
                            if expr.type == "identifier":
                                pre_vars.add(_decode(expr))
            if child.type == "var_declaration":
                for sub in child.children:
                    if sub.type == "var_spec":
                        for inner in sub.children:
                            if inner.type == "identifier":
                                pre_vars.add(_decode(inner))
        return pre_vars

    def _find_go_assigns_to_outer(
        self,
        node: tree_sitter.Node,
        content: bytes,
        outer_vars: set[str],
        issues: list[MutabilityIssue],
    ) -> None:
        if node.type in ("assignment_expression", "assignment_statement"):
            left = node.child_by_field_name("left")
            if left is None:
                for child in node.children:
                    if child.type == "expression_list":
                        left = child
                        break
            if left:
                for ident in self._extract_identifiers(left):
                    name = _decode(ident)
                    if name in outer_vars:
                        issues.append(
                            MutabilityIssue(
                                issue_type=MUTABILITY_LOOP_MUTATION,
                                line=ident.start_point[0] + 1,
                                column=ident.start_point[1],
                                variable_name=name,
                                severity=_SEVERITY_MAP[MUTABILITY_LOOP_MUTATION],
                                description=_DESCRIPTIONS[MUTABILITY_LOOP_MUTATION],
                                suggestion=_SUGGESTIONS[MUTABILITY_LOOP_MUTATION],
                            )
                        )

        for child in node.children:
            self._find_go_assigns_to_outer(child, content, outer_vars, issues)

    # ------------------------------------------------------------------ #
    #  Shared helpers                                                      #
    # ------------------------------------------------------------------ #

    def _extract_identifiers(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        results: list[tree_sitter.Node] = []
        if node.type == "identifier":
            results.append(node)
        elif node.type == "tuple":
            for child in node.children:
                results.extend(self._extract_identifiers(child))
        elif node.type == "pattern_list":
            for child in node.children:
                results.extend(self._extract_identifiers(child))
        elif node.type == "name":  # some languages use "name" node
            results.append(node)
        for child in node.children:
            if child.type == "identifier" and child not in results:
                results.append(child)
        return results
