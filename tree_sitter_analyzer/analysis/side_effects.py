"""
Side Effect Analyzer.

Detects functions with side effects that reduce testability and predictability.
Identifies two key patterns: global state mutation and parameter mutation.

Issues detected:
  - global_state_mutation: function modifies global/module-level variables
  - parameter_mutation: function modifies passed-in parameters (attr assign,
    list/dict mutation, etc.)

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_GLOBAL_MUTATION = "global_state_mutation"
ISSUE_PARAMETER_MUTATION = "parameter_mutation"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_GLOBAL_MUTATION: SEVERITY_HIGH,
    ISSUE_PARAMETER_MUTATION: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_GLOBAL_MUTATION: "Function modifies global/module-level state",
    ISSUE_PARAMETER_MUTATION: "Function mutates a passed-in parameter",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_GLOBAL_MUTATION: "Return new state instead of mutating globals, or use dependency injection",
    ISSUE_PARAMETER_MUTATION: "Return a new value instead of mutating the parameter",
}

_MUTATING_METHODS_PY: frozenset[str] = frozenset({
    "append", "extend", "insert", "remove", "pop", "clear",
    "sort", "reverse", "update", "setdefault", "add", "discard",
})

_MUTATING_METHODS_JS: frozenset[str] = frozenset({
    "push", "pop", "shift", "unshift", "splice", "sort",
    "reverse", "fill", "copyWithin", "set", "add", "delete",
    "clear",
})

def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""

@dataclass(frozen=True)
class SideEffectIssue:
    """A single side effect issue found in code."""

    line: int
    issue_type: str
    severity: str
    function_name: str
    variable: str
    description: str
    suggestion: str

@dataclass(frozen=True)
class SideEffectResult:
    """Aggregated side effect analysis result for a file."""

    issues: tuple[SideEffectIssue, ...]
    total_issues: int
    high_severity: int
    medium_severity: int
    low_severity: int
    file_path: str
    language: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_issues": self.total_issues,
            "high_severity": self.high_severity,
            "medium_severity": self.medium_severity,
            "low_severity": self.low_severity,
            "issues": [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "function_name": i.function_name,
                    "variable": i.variable,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }

    def get_issues_by_severity(self, severity: str) -> tuple[SideEffectIssue, ...]:
        return tuple(i for i in self.issues if i.severity == severity)

    def get_issues_by_type(self, issue_type: str) -> tuple[SideEffectIssue, ...]:
        return tuple(i for i in self.issues if i.issue_type == issue_type)

def _empty_result(file_path: str, language: str) -> SideEffectResult:
    return SideEffectResult(
        issues=(),
        total_issues=0,
        high_severity=0,
        medium_severity=0,
        low_severity=0,
        file_path=file_path,
        language=language,
    )

def _severity_counts(
    issues: tuple[SideEffectIssue, ...],
) -> tuple[int, int, int]:
    high = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
    medium = sum(1 for i in issues if i.severity == SEVERITY_MEDIUM)
    low = sum(1 for i in issues if i.severity == SEVERITY_LOW)
    return high, medium, low

class SideEffectAnalyzer(BaseAnalyzer):
    """Analyzes source code for side effects in functions."""

    def analyze_file(self, file_path: Path | str) -> SideEffectResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language_map: dict[str, str] = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go",
        }
        lang = language_map.get(ext, "unknown")

        content = path.read_bytes()
        text = content.decode("utf-8", errors="replace")

        if ext == ".py":
            issues = self._analyze_python(content, text)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(content, text)
        elif ext == ".java":
            issues = self._analyze_java(content, text)
        elif ext == ".go":
            issues = self._analyze_go(content, text)
        else:
            issues = []

        issue_tuple = tuple(issues)
        high, medium, low = _severity_counts(issue_tuple)
        return SideEffectResult(
            issues=issue_tuple,
            total_issues=len(issue_tuple),
            high_severity=high,
            medium_severity=medium,
            low_severity=low,
            file_path=str(path),
            language=lang,
        )

    # -- Python analysis --------------------------------------------------

    def _analyze_python(
        self, content: bytes, text: str
    ) -> list[SideEffectIssue]:
        language, parser = self._get_parser(".py")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SideEffectIssue] = []

        module_vars = self._collect_python_module_vars(tree.root_node)
        functions = self._collect_python_functions(tree.root_node)

        for func_node, func_name in functions:
            params = self._collect_python_params(func_node)
            global_names = self._collect_python_globals(func_node)
            func_issues = self._check_python_function(
                func_node, func_name, params, global_names, module_vars,
            )
            issues.extend(func_issues)

        return issues

    def _collect_python_module_vars(
        self, node: tree_sitter.Node
    ) -> set[str]:
        names: set[str] = set()
        for child in node.children:
            if child.type == "assignment":
                left = child.child_by_field_name("left")
                if left and left.type == "identifier":
                    names.add(_txt(left))
            elif child.type in (
                "variable_declaration", "expression_statement",
            ):
                text = _txt(child)
                assign_match = re.match(
                    r"^([A-Za-z_]\w*)\s*=", text,
                )
                if assign_match:
                    candidate = assign_match.group(1)
                    if not candidate.startswith("_"):
                        names.add(candidate)
        return names

    def _collect_python_functions(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str]]:
        funcs: list[tuple[tree_sitter.Node, str]] = []
        if node.type == "function_definition":
            name = ""
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child)
                    break
            funcs.append((node, name))
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    funcs.extend(
                        self._collect_python_functions(child)
                    )
        else:
            for child in node.children:
                funcs.extend(
                    self._collect_python_functions(child)
                )
        return funcs

    def _collect_python_params(
        self, func_node: tree_sitter.Node
    ) -> set[str]:
        params: set[str] = set()
        params_node = func_node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "identifier":
                    params.add(_txt(child))
                elif child.type == "typed_parameter":
                    for sc in child.children:
                        if sc.type == "identifier":
                            params.add(_txt(sc))
                elif child.type == "default_parameter":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        params.add(_txt(name_node))
                elif child.type == "list_splat_pattern":
                    for sc in child.children:
                        if sc.type == "identifier":
                            params.add(_txt(sc))
                elif child.type == "dictionary_splat_pattern":
                    for sc in child.children:
                        if sc.type == "identifier":
                            params.add(_txt(sc))
        return params

    def _collect_python_globals(
        self, func_node: tree_sitter.Node
    ) -> set[str]:
        globals_seen: set[str] = set()
        for child in func_node.children:
            if child.type == "global_statement":
                for sc in child.children:
                    if sc.type == "identifier":
                        globals_seen.add(_txt(sc))
        return globals_seen

    def _check_python_function(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        global_names: set[str],
        module_vars: set[str],
    ) -> list[SideEffectIssue]:
        issues: list[SideEffectIssue] = []

        body = func_node.child_by_field_name("body")
        if not body:
            return issues

        mutable_params = params - {"self", "cls"}
        self._walk_python_side_effects(
            body, func_name, mutable_params, global_names, module_vars, issues,
        )
        return issues

    def _walk_python_side_effects(
        self,
        node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        global_names: set[str],
        module_vars: set[str],
        issues: list[SideEffectIssue],
    ) -> None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left).strip()
                base_name = left_text.split(".")[0].split("[")[0]
                if base_name in global_names or (
                    base_name in module_vars
                    and base_name not in params
                ):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_GLOBAL_MUTATION,
                        severity=SEVERITY_HIGH,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' modifies "
                            f"global variable '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_GLOBAL_MUTATION],
                    ))
                elif base_name in params and "." in left_text:
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' mutates "
                            f"parameter '{base_name}' "
                            f"(attribute assignment)"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))
                elif base_name in params and "[" in left_text:
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' mutates "
                            f"parameter '{base_name}' "
                            f"(index/key assignment)"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))

        elif node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            if left:
                base_name = _txt(left).split(".")[0].split("[")[0].strip()
                if base_name in global_names or (
                    base_name in module_vars
                    and base_name not in params
                ):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_GLOBAL_MUTATION,
                        severity=SEVERITY_HIGH,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' modifies "
                            f"global variable '{base_name}' (augmented assign)"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_GLOBAL_MUTATION],
                    ))

        elif node.type == "call":
            self._check_python_call_mutation(
                node, func_name, params, issues,
            )

        for child in node.children:
            self._walk_python_side_effects(
                child, func_name, params, global_names, module_vars, issues,
            )

    def _check_python_call_mutation(
        self,
        node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        issues: list[SideEffectIssue],
    ) -> None:
        text = _txt(node)
        for param in params:
            for method in _MUTATING_METHODS_PY:
                pattern = rf"\b{re.escape(param)}\.{method}\s*\("
                if re.search(pattern, text):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=func_name,
                        variable=param,
                        description=(
                            f"Function '{func_name}' mutates "
                            f"parameter '{param}' "
                            f"(calling .{method}())"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))
                    break

    # -- JavaScript/TypeScript analysis -----------------------------------

    def _analyze_javascript(
        self, content: bytes, text: str
    ) -> list[SideEffectIssue]:
        language, parser = self._get_parser(".js")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SideEffectIssue] = []

        module_vars = self._collect_js_module_vars(tree.root_node)
        functions = self._collect_js_functions(tree.root_node)

        for func_node, func_name, params in functions:
            func_issues = self._check_js_function(
                func_node, func_name, params, module_vars,
            )
            issues.extend(func_issues)

        return issues

    def _collect_js_module_vars(
        self, node: tree_sitter.Node
    ) -> set[str]:
        names: set[str] = set()
        for child in node.children:
            if child.type in (
                "variable_declaration",
                "lexical_declaration",
            ):
                for declarator in child.children:
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            name_text = _txt(name_node)
                            text = _txt(child)
                            if "let " in text or "var " in text:
                                names.add(name_text)
        return names

    def _collect_js_functions(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str, set[str]]]:
        funcs: list[tuple[tree_sitter.Node, str, set[str]]] = []

        if node.type == "function_declaration":
            name = ""
            params: set[str] = set()
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _txt(name_node)
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for p in params_node.children:
                    if p.type == "identifier":
                        params.add(_txt(p))
            funcs.append((node, name, params))

        elif node.type in (
            "arrow_function", "function_expression",
        ):
            arrow_params: set[str] = set()
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for p in params_node.children:
                    if p.type == "identifier":
                        arrow_params.add(_txt(p))
            parent_name = ""
            parent = node.parent
            if parent and parent.type == "variable_declarator":
                name_node = parent.child_by_field_name("name")
                if name_node:
                    parent_name = _txt(name_node)
            funcs.append((node, parent_name, arrow_params))

        if node.type not in (
            "function_declaration", "arrow_function",
            "function_expression",
        ):
            for child in node.children:
                funcs.extend(self._collect_js_functions(child))

        return funcs

    def _check_js_function(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        module_vars: set[str],
    ) -> list[SideEffectIssue]:
        issues: list[SideEffectIssue] = []
        body = func_node.child_by_field_name("body")
        if not body:
            return issues
        self._walk_js_side_effects(
            body, func_name, params, module_vars, issues,
        )
        return issues

    def _walk_js_side_effects(
        self,
        node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        module_vars: set[str],
        issues: list[SideEffectIssue],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                base_name = left_text.split(".")[0].split("[")[0]
                if base_name in module_vars and base_name not in params:
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_GLOBAL_MUTATION,
                        severity=SEVERITY_HIGH,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' modifies "
                            f"module variable '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_GLOBAL_MUTATION],
                    ))
                elif base_name in params and (
                    "." in left_text or "[" in left_text
                ):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' mutates "
                            f"parameter '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))

        elif node.type == "call_expression":
            self._check_js_call_mutation(
                node, func_name, params, issues,
            )

        for child in node.children:
            self._walk_js_side_effects(
                child, func_name, params, module_vars, issues,
            )

    def _check_js_call_mutation(
        self,
        node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        issues: list[SideEffectIssue],
    ) -> None:
        text = _txt(node)
        for param in params:
            for method in _MUTATING_METHODS_JS:
                pattern = rf"\b{re.escape(param)}\.{method}\s*\("
                if re.search(pattern, text):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=func_name,
                        variable=param,
                        description=(
                            f"Function '{func_name}' mutates "
                            f"parameter '{param}' "
                            f"(calling .{method}())"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))
                    break

    # -- Java analysis ----------------------------------------------------

    def _analyze_java(
        self, content: bytes, text: str
    ) -> list[SideEffectIssue]:
        language, parser = self._get_parser(".java")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SideEffectIssue] = []

        static_fields = self._collect_java_static_fields(tree.root_node)
        methods = self._collect_java_methods(tree.root_node)

        for method_node, method_name, params in methods:
            func_issues = self._check_java_method(
                method_node, method_name, params, static_fields,
            )
            issues.extend(func_issues)

        return issues

    def _collect_java_static_fields(
        self, node: tree_sitter.Node
    ) -> set[str]:
        fields: set[str] = set()
        if node.type == "field_declaration":
            text = _txt(node)
            if "static" in text and "final" not in text:
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            fields.add(_txt(name_node))
        for child in node.children:
            fields.update(self._collect_java_static_fields(child))
        return fields

    def _collect_java_methods(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str, set[str]]]:
        methods: list[tuple[tree_sitter.Node, str, set[str]]] = []
        if node.type == "method_declaration":
            name = ""
            params: set[str] = set()
            for child in node.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                elif child.type == "formal_parameters":
                    for param in child.children:
                        if param.type == "formal_parameter":
                            for pc in param.children:
                                if pc.type == "identifier":
                                    params.add(_txt(pc))
                                    break
            methods.append((node, name, params))

        if node.type != "method_declaration":
            for child in node.children:
                methods.extend(self._collect_java_methods(child))
        return methods

    def _check_java_method(
        self,
        method_node: tree_sitter.Node,
        method_name: str,
        params: set[str],
        static_fields: set[str],
    ) -> list[SideEffectIssue]:
        issues: list[SideEffectIssue] = []
        body = method_node.child_by_field_name("body")
        if not body:
            return issues
        self._walk_java_side_effects(
            body, method_name, params, static_fields, issues,
        )
        return issues

    def _walk_java_side_effects(
        self,
        node: tree_sitter.Node,
        method_name: str,
        params: set[str],
        static_fields: set[str],
        issues: list[SideEffectIssue],
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                base_name = left_text.split(".")[0]
                if base_name in static_fields:
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_GLOBAL_MUTATION,
                        severity=SEVERITY_HIGH,
                        function_name=method_name,
                        variable=base_name,
                        description=(
                            f"Method '{method_name}' modifies "
                            f"static field '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_GLOBAL_MUTATION],
                    ))
                elif base_name in params and "." in left_text:
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=method_name,
                        variable=base_name,
                        description=(
                            f"Method '{method_name}' mutates "
                            f"parameter '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))

        elif node.type == "method_invocation":
            text = _txt(node)
            for param in params:
                if re.search(
                    rf"\b{re.escape(param)}\.set\w+\s*\(", text,
                ):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=method_name,
                        variable=param,
                        description=(
                            f"Method '{method_name}' mutates "
                            f"parameter '{param}' (setter call)"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))
                    break

        for child in node.children:
            self._walk_java_side_effects(
                child, method_name, params, static_fields, issues,
            )

    # -- Go analysis ------------------------------------------------------

    def _analyze_go(
        self, content: bytes, text: str
    ) -> list[SideEffectIssue]:
        language, parser = self._get_parser(".go")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SideEffectIssue] = []

        package_vars = self._collect_go_package_vars(tree.root_node)
        functions = self._collect_go_functions(tree.root_node)

        for func_node, func_name, params in functions:
            func_issues = self._check_go_function(
                func_node, func_name, params, package_vars,
            )
            issues.extend(func_issues)

        return issues

    def _collect_go_package_vars(
        self, node: tree_sitter.Node
    ) -> set[str]:
        names: set[str] = set()
        for child in node.children:
            if child.type == "var_declaration":
                for spec in child.children:
                    if spec.type == "var_spec":
                        for sc in spec.children:
                            if sc.type == "identifier":
                                names.add(_txt(sc))
        return names

    def _collect_go_functions(
        self, node: tree_sitter.Node
    ) -> list[tuple[tree_sitter.Node, str, set[str]]]:
        funcs: list[tuple[tree_sitter.Node, str, set[str]]] = []
        if node.type == "function_declaration":
            name = ""
            params: set[str] = set()
            for child in node.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                elif child.type == "parameter_list":
                    for param in child.children:
                        if param.type in (
                            "parameter_declaration",
                            "variadic_parameter_declaration",
                        ):
                            for pc in param.children:
                                if pc.type == "identifier":
                                    params.add(_txt(pc))
                                    break
            funcs.append((node, name, params))

        if node.type != "function_declaration":
            for child in node.children:
                funcs.extend(self._collect_go_functions(child))
        return funcs

    def _check_go_function(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        package_vars: set[str],
    ) -> list[SideEffectIssue]:
        issues: list[SideEffectIssue] = []
        body = func_node.child_by_field_name("body")
        if not body:
            return issues
        self._walk_go_side_effects(
            body, func_name, params, package_vars, issues,
        )
        return issues

    def _walk_go_side_effects(
        self,
        node: tree_sitter.Node,
        func_name: str,
        params: set[str],
        package_vars: set[str],
        issues: list[SideEffectIssue],
    ) -> None:
        if node.type == "assignment_statement":
            left = node.child_by_field_name("left")
            if left:
                left_text = _txt(left)
                base_name = left_text.split(".")[0].split("[")[0]
                if base_name in package_vars and base_name not in params:
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_GLOBAL_MUTATION,
                        severity=SEVERITY_HIGH,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' modifies "
                            f"package variable '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_GLOBAL_MUTATION],
                    ))
                elif base_name in params and (
                    "." in left_text or "[" in left_text
                ):
                    issues.append(SideEffectIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_PARAMETER_MUTATION,
                        severity=SEVERITY_MEDIUM,
                        function_name=func_name,
                        variable=base_name,
                        description=(
                            f"Function '{func_name}' mutates "
                            f"parameter '{base_name}'"
                        ),
                        suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                    ))

        elif node.type == "call_expression":
            text = _txt(node)
            for param in params:
                if re.search(
                    rf"\b{re.escape(param)}\b", text,
                ):
                    call_text = text
                    if re.search(
                        rf"\bappend\s*\(\s*{re.escape(param)}\b", call_text,
                    ):
                        issues.append(SideEffectIssue(
                            line=node.start_point[0] + 1,
                            issue_type=ISSUE_PARAMETER_MUTATION,
                            severity=SEVERITY_MEDIUM,
                            function_name=func_name,
                            variable=param,
                            description=(
                                f"Function '{func_name}' may mutate "
                                f"parameter '{param}' (append)"
                            ),
                            suggestion=_SUGGESTIONS[ISSUE_PARAMETER_MUTATION],
                        ))
                        break

        for child in node.children:
            self._walk_go_side_effects(
                child, func_name, params, package_vars, issues,
            )
