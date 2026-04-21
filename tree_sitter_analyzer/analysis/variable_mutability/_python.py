"""Python variable mutability analysis mixin."""
from __future__ import annotations

import tree_sitter

from tree_sitter_analyzer.analysis.variable_mutability._base import (
        _MutabilityBase,
)
from tree_sitter_analyzer.analysis.variable_mutability._types import (
        _DESCRIPTIONS,
        _PYTHON_SCOPE_NODES,
        _SEVERITY_MAP,
        _SUGGESTIONS,
        _UPPER_SNAKE_RE,
        MUTABILITY_LOOP_MUTATION,
        MUTABILITY_REASSIGNED_CONST,
        MUTABILITY_SHADOW,
        MUTABILITY_UNUSED,
        MutabilityIssue,
        _decode,
)


class PythonMutabilityMixin(_MutabilityBase):
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
