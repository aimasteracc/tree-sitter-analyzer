"""Java variable mutability analysis mixin."""
from __future__ import annotations

import tree_sitter

from tree_sitter_analyzer.analysis.variable_mutability._base import (
        _MutabilityBase,
)
from tree_sitter_analyzer.analysis.variable_mutability._types import (
        _DESCRIPTIONS,
        _JAVA_SCOPE_NODES,
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


class JavaMutabilityMixin(_MutabilityBase):
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
