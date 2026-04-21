"""Go variable mutability analysis mixin."""
from __future__ import annotations

import tree_sitter

from tree_sitter_analyzer.analysis.variable_mutability._base import (
        _MutabilityBase,
)
from tree_sitter_analyzer.analysis.variable_mutability._types import (
        _DESCRIPTIONS,
        _GO_SCOPE_NODES,
        _SEVERITY_MAP,
        _SUGGESTIONS,
        MUTABILITY_LOOP_MUTATION,
        MUTABILITY_SHADOW,
        MUTABILITY_UNUSED,
        MutabilityIssue,
        _decode,
)


class GoMutabilityMixin(_MutabilityBase):
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
