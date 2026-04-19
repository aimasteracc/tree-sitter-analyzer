"""Variable Shadowing Detector.

Detects inner-scope variables that shadow outer-scope variables of the same name:
  - param_shadows_outer: function/method parameter shadows an outer variable
  - local_shadows_param: local variable shadows a function parameter
  - local_shadows_outer: local variable in inner scope shadows outer local
  - comprehension_shadows: list/dict/set comprehension variable shadows outer

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

ISSUE_PARAM_SHADOWS_OUTER = "param_shadows_outer"
ISSUE_LOCAL_SHADOWS_PARAM = "local_shadows_param"
ISSUE_LOCAL_SHADOWS_OUTER = "local_shadows_outer"
ISSUE_COMPREHENSION_SHADOWS = "comprehension_shadows"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_PARAM_SHADOWS_OUTER: SEVERITY_MEDIUM,
    ISSUE_LOCAL_SHADOWS_PARAM: SEVERITY_MEDIUM,
    ISSUE_LOCAL_SHADOWS_OUTER: SEVERITY_LOW,
    ISSUE_COMPREHENSION_SHADOWS: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_PARAM_SHADOWS_OUTER: "Function parameter shadows variable in outer scope",
    ISSUE_LOCAL_SHADOWS_PARAM: "Local variable shadows function parameter",
    ISSUE_LOCAL_SHADOWS_OUTER: "Variable in inner scope shadows outer scope variable",
    ISSUE_COMPREHENSION_SHADOWS: "Comprehension variable shadows outer scope variable",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_PARAM_SHADOWS_OUTER: "Rename the parameter to avoid confusion with the outer variable.",
    ISSUE_LOCAL_SHADOWS_PARAM: "Rename the local variable to avoid hiding the parameter.",
    ISSUE_LOCAL_SHADOWS_OUTER: "Rename the variable or use a different name for clarity.",
    ISSUE_COMPREHENSION_SHADOWS: "Rename the comprehension variable to avoid shadowing.",
}

# Node types that create a new scope per language
_SCOPE_CREATORS: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "function_definition", "lambda", "class_definition",
        "list_comprehension", "set_comprehension",
        "dictionary_comprehension", "generator_expression",
    }),
    ".js": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration", "class_expression",
        "block_statement", "for_statement", "for_in_statement",
    }),
    ".jsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration", "class_expression",
        "block_statement", "for_statement", "for_in_statement",
    }),
    ".ts": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration", "class_expression",
        "block_statement", "for_statement", "for_in_statement",
    }),
    ".tsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration", "class_expression",
        "block_statement", "for_statement", "for_in_statement",
    }),
    ".java": frozenset({
        "method_declaration", "constructor_declaration",
        "lambda_expression", "class_declaration",
        "interface_declaration", "catch_clause",
        "for_statement", "enhanced_for_statement",
    }),
    ".go": frozenset({
        "function_declaration", "method_declaration",
        "if_statement", "for_statement",
        "block", "func_literal",
    }),
}

# Node types that declare a variable per language
_VARIABLE_DECLARATORS: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "assignment", "augmented_assignment",
        "for_statement", "with_statement",
        "named_expression",
    }),
    ".js": frozenset({
        "variable_declarator",
    }),
    ".jsx": frozenset({
        "variable_declarator",
    }),
    ".ts": frozenset({
        "variable_declarator",
    }),
    ".tsx": frozenset({
        "variable_declarator",
    }),
    ".java": frozenset({
        "local_variable_declaration", "variable_declarator",
    }),
    ".go": frozenset({
        "short_var_declaration", "var_declaration",
        "var_spec",
    }),
}

_COMPREHENSION_SCOPES: frozenset[str] = frozenset({
    "list_comprehension", "set_comprehension",
    "dictionary_comprehension", "generator_expression",
})


def _safe_text(node: tree_sitter.Node) -> str:
    """Safely decode node text, returning empty string if None."""
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class ShadowIssue:
    """A single variable shadowing issue."""

    line_number: int
    issue_type: str
    variable_name: str
    outer_scope: str
    inner_scope: str
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
            "outer_scope": self.outer_scope,
            "inner_scope": self.inner_scope,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ShadowResult:
    """Aggregated variable shadowing analysis result."""

    total_scopes: int
    issues: tuple[ShadowIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_scopes": self.total_scopes,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _extract_name(node: tree_sitter.Node) -> str | None:
    """Extract variable name from a node."""
    if node.type == "identifier":
        return _safe_text(node) or None
    if node.type == "pattern_list":
        first = node.children[0] if node.children else None
        if first is not None and first.type == "identifier":
            name = _safe_text(first)
            return name or None
    return None


def _get_declared_name(node: tree_sitter.Node, ext: str) -> str | None:
    """Extract the variable name being declared by a node."""
    if ext == ".py":
        if node.type == "for_statement":
            target = node.child_by_field_name("left")
            if target is not None:
                return _extract_name(target)
        elif node.type in ("assignment", "augmented_assignment"):
            target = node.child_by_field_name("left")
            if target is not None:
                return _extract_name(target)
        elif node.type == "named_expression":
            target = node.child_by_field_name("name")
            if target is not None:
                return _extract_name(target)
        elif node.type == "with_statement":
            for child in node.children:
                if child.type == "as_pattern":
                    name_node = child.child_by_field_name("name")
                    if name_node is not None:
                        return _extract_name(name_node)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return _extract_name(name_node)
    elif ext == ".java":
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return _extract_name(name_node)
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
        elif node.type in ("var_spec", "var_declaration"):
            for child in node.children:
                if child.type == "var_spec":
                    for gc in child.children:
                        if gc.type == "identifier":
                            name = _safe_text(gc)
                            return name or None
                elif child.type == "identifier":
                    name = _safe_text(child)
                    return name or None
    return None


def _get_parameters(node: tree_sitter.Node, ext: str) -> set[str]:
    """Extract parameter names from a function/method definition."""
    params: set[str] = set()
    params_node: tree_sitter.Node | None = None

    if ext == ".py":
        if node.type in ("function_definition", "lambda"):
            params_node = node.child_by_field_name("parameters")
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        if node.type in (
            "function_declaration", "function_expression",
            "arrow_function", "method_definition",
        ):
            for child in node.children:
                if child.type == "formal_parameters":
                    params_node = child
                    break
    elif ext == ".java":
        if node.type in ("method_declaration", "constructor_declaration"):
            for child in node.children:
                if child.type == "formal_parameters":
                    params_node = child
                    break
        elif node.type == "lambda_expression":
            for child in node.children:
                if child.type in (
                    "formal_parameters", "identifier",
                    "inferred_parameters",
                ):
                    params_node = child
                    break
    elif ext == ".go":
        if node.type in (
            "function_declaration", "method_declaration",
            "func_literal",
        ):
            for child in node.children:
                if child.type == "parameter_list":
                    params_node = child
                    break

    if params_node is None:
        return params

    _collect_identifiers(params_node, params)
    return params


def _collect_identifiers(
    node: tree_sitter.Node,
    names: set[str],
) -> None:
    """Recursively collect all identifier names from a node."""
    if node.type == "identifier":
        name = _safe_text(node)
        if name:
            names.add(name)
        return
    for child in node.children:
        _collect_identifiers(child, names)


def _find_outer_scope(
    name: str,
    scope_stack: list[tuple[str, set[str]]],
) -> str:
    """Find which outer scope contains the given variable name."""
    for scope_name, scope_names in reversed(scope_stack):
        if name in scope_names:
            return scope_name
    return "<module>"


def _collect_module_vars(
    root: tree_sitter.Node,
    ext: str,
) -> set[str]:
    """Collect top-level variable declarations at module/file scope."""
    names: set[str] = set()
    scope_creators = _SCOPE_CREATORS.get(ext, frozenset())
    declarators = _VARIABLE_DECLARATORS.get(ext, frozenset())

    def walk(node: tree_sitter.Node, depth: int) -> None:
        if depth > 2:
            return
        if node.type in scope_creators:
            return
        if node.type in declarators:
            declared = _get_declared_name(node, ext)
            if declared is not None:
                names.add(declared)
                return
            for child in node.children:
                walk(child, depth + 1)
            return
        for child in node.children:
            walk(child, depth + 1)

    for child in root.children:
        walk(child, 0)

    return names


def _check_declarations(
    node: tree_sitter.Node,
    ext: str,
    scope_stack: list[tuple[str, set[str]]],
    current_scope_type: str,
    current_params: set[str],
    current_scope_names: set[str] | None,
    issues: list[ShadowIssue],
) -> None:
    """Check variable declarations for shadowing and track them."""
    declarators = _VARIABLE_DECLARATORS.get(ext, frozenset())
    scope_creators = _SCOPE_CREATORS.get(ext, frozenset())

    if node.type in declarators:
        declared_name = _get_declared_name(node, ext)
        if declared_name is not None:
            if declared_name in current_params:
                issues.append(ShadowIssue(
                    line_number=node.start_point[0] + 1,
                    issue_type=ISSUE_LOCAL_SHADOWS_PARAM,
                    variable_name=declared_name,
                    outer_scope="parameter",
                    inner_scope=current_scope_type,
                    severity=_SEVERITY_MAP.get(
                        ISSUE_LOCAL_SHADOWS_PARAM, SEVERITY_MEDIUM,
                    ),
                    description=_DESCRIPTIONS.get(
                        ISSUE_LOCAL_SHADOWS_PARAM, "",
                    ),
                ))
            else:
                for scope_name, scope_names in reversed(scope_stack):
                    if declared_name in scope_names:
                        issues.append(ShadowIssue(
                            line_number=node.start_point[0] + 1,
                            issue_type=ISSUE_LOCAL_SHADOWS_OUTER,
                            variable_name=declared_name,
                            outer_scope=scope_name,
                            inner_scope=current_scope_type,
                            severity=_SEVERITY_MAP.get(
                                ISSUE_LOCAL_SHADOWS_OUTER, SEVERITY_LOW,
                            ),
                            description=_DESCRIPTIONS.get(
                                ISSUE_LOCAL_SHADOWS_OUTER, "",
                            ),
                        ))
                        break

            if current_scope_names is not None:
                current_scope_names.add(declared_name)
            return

    if node.type in scope_creators:
        return

    for child in node.children:
        _check_declarations(
            child, ext, scope_stack, current_scope_type,
            current_params, current_scope_names, issues,
        )


def _get_comprehension_var(
    node: tree_sitter.Node,
) -> str | None:
    """Extract the iteration variable from a Python comprehension."""
    for child in node.children:
        if child.type == "for_in_clause":
            target = child.child_by_field_name("left")
            if target is not None:
                return _extract_name(target)
    return None


def _get_loop_var(
    node: tree_sitter.Node,
    ext: str,
) -> str | None:
    """Extract the loop variable from a for statement."""
    if ext == ".py":
        target = node.child_by_field_name("left")
        if target is not None:
            return _extract_name(target)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        for child in node.children:
            if child.type == "identifier":
                name = _safe_text(child)
                return name or None
            if child.type in ("object_pattern", "array_pattern"):
                first = child.children[0] if child.children else None
                if first is not None and first.type == "identifier":
                    name = _safe_text(first)
                    return name or None
    elif ext == ".java":
        for child in node.children:
            if child.type == "identifier":
                name = _safe_text(child)
                return name or None
    elif ext == ".go":
        for child in node.children:
            if child.type == "assignment_statement":
                for gc in child.children:
                    if gc.type == "expression_list":
                        for ggc in gc.children:
                            if ggc.type == "identifier":
                                name = _safe_text(ggc)
                                return name or None
                    elif gc.type == "identifier":
                        name = _safe_text(gc)
                        return name or None
            if child.type == "var_spec":
                for gc in child.children:
                    if gc.type == "identifier":
                        name = _safe_text(gc)
                        return name or None
    return None


class VariableShadowingAnalyzer(BaseAnalyzer):
    """Analyzes code for variable shadowing issues."""

    def analyze_file(self, file_path: Path | str) -> ShadowResult:
        path = Path(file_path)
        if not path.exists():
            return ShadowResult(
                total_scopes=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return ShadowResult(
                total_scopes=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> ShadowResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ShadowResult(
                total_scopes=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        scope_creators = _SCOPE_CREATORS.get(ext, frozenset())
        issues: list[ShadowIssue] = []
        total_scopes = 0

        module_vars = _collect_module_vars(tree.root_node, ext)
        initial_stack: list[tuple[str, set[str]]] = [
            ("<module>", module_vars),
        ]

        def visit(
            node: tree_sitter.Node,
            scope_stack: list[tuple[str, set[str]]],
        ) -> None:
            nonlocal total_scopes

            if node.type in scope_creators:
                total_scopes += 1
                outer_names: set[str] = set()
                for _sn, names in scope_stack:
                    outer_names.update(names)

                scope_label = node.type
                scope_params = _get_parameters(node, ext)
                scope_names: set[str] = set(scope_params)

                for param in scope_params:
                    if param in outer_names:
                        issues.append(ShadowIssue(
                            line_number=node.start_point[0] + 1,
                            issue_type=ISSUE_PARAM_SHADOWS_OUTER,
                            variable_name=param,
                            outer_scope=_find_outer_scope(
                                param, scope_stack,
                            ),
                            inner_scope=scope_label,
                            severity=_SEVERITY_MAP.get(
                                ISSUE_PARAM_SHADOWS_OUTER,
                                SEVERITY_MEDIUM,
                            ),
                            description=_DESCRIPTIONS.get(
                                ISSUE_PARAM_SHADOWS_OUTER, "",
                            ),
                        ))

                if ext == ".py" and node.type in _COMPREHENSION_SCOPES:
                    comp_var = _get_comprehension_var(node)
                    if comp_var is not None:
                        scope_names.add(comp_var)
                        if comp_var in outer_names:
                            issues.append(ShadowIssue(
                                line_number=node.start_point[0] + 1,
                                issue_type=ISSUE_COMPREHENSION_SHADOWS,
                                variable_name=comp_var,
                                outer_scope=_find_outer_scope(
                                    comp_var, scope_stack,
                                ),
                                inner_scope=node.type,
                                severity=_SEVERITY_MAP.get(
                                    ISSUE_COMPREHENSION_SHADOWS,
                                    SEVERITY_HIGH,
                                ),
                                description=_DESCRIPTIONS.get(
                                    ISSUE_COMPREHENSION_SHADOWS, "",
                                ),
                            ))

                if node.type in (
                    "for_statement", "for_in_statement",
                    "enhanced_for_statement",
                ):
                    loop_var = _get_loop_var(node, ext)
                    if loop_var is not None:
                        scope_names.add(loop_var)
                        if loop_var in outer_names:
                            issues.append(ShadowIssue(
                                line_number=node.start_point[0] + 1,
                                issue_type=ISSUE_LOCAL_SHADOWS_OUTER,
                                variable_name=loop_var,
                                outer_scope=_find_outer_scope(
                                    loop_var, scope_stack,
                                ),
                                inner_scope=node.type,
                                severity=_SEVERITY_MAP.get(
                                    ISSUE_LOCAL_SHADOWS_OUTER,
                                    SEVERITY_LOW,
                                ),
                                description=_DESCRIPTIONS.get(
                                    ISSUE_LOCAL_SHADOWS_OUTER, "",
                                ),
                            ))

                new_stack = scope_stack + [(scope_label, scope_names)]
                for child in node.children:
                    _check_declarations(
                        child, ext, new_stack, node.type,
                        scope_params, scope_names, issues,
                    )
                    visit(child, new_stack)
                return

            for child in node.children:
                visit(child, scope_stack)

        visit(tree.root_node, initial_stack)

        return ShadowResult(
            total_scopes=total_scopes,
            issues=tuple(issues),
            file_path=str(path),
        )
