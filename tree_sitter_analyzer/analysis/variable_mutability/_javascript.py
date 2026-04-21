"""JavaScript/TypeScript variable mutability analysis mixin."""
from __future__ import annotations

import tree_sitter

from tree_sitter_analyzer.analysis.variable_mutability._base import (
        _MutabilityBase,
)
from tree_sitter_analyzer.analysis.variable_mutability._types import (
        _DESCRIPTIONS,
        _JS_SCOPE_NODES,
        _SEVERITY_MAP,
        _SUGGESTIONS,
        MUTABILITY_LOOP_MUTATION,
        MUTABILITY_REASSIGNED_CONST,
        MUTABILITY_SHADOW,
        MUTABILITY_UNUSED,
        MutabilityIssue,
        _decode,
)


class JavaScriptMutabilityMixin(_MutabilityBase):
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
