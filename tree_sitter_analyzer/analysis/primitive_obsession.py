"""Primitive Obsession Detector.

Detects overuse of primitive types (str, int, float, bool) where value objects
would be more appropriate. Identifies Fowler's "Primitive Obsession" code smell.

Issues detected:
  - primitive_heavy_params: function with 4+ parameters all of primitive types
  - primitive_soup: function body with 8+ local variables of primitive types
  - anemic_value_object: data class with only primitive fields and no methods
  - type_hint_code_smell: string/integer used to encode type information

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

from .base import BaseAnalyzer

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

def _txt(node: tree_sitter.Node) -> str:
    """Safely extract text from a tree-sitter node."""
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_PRIMITIVE_HEAVY_PARAMS = "primitive_heavy_params"
ISSUE_PRIMITIVE_SOUP = "primitive_soup"
ISSUE_ANEMIC_VALUE_OBJECT = "anemic_value_object"
ISSUE_TYPE_HINT_CODE_SMELL = "type_hint_code_smell"

SEVERITY_MAP: dict[str, str] = {
    ISSUE_PRIMITIVE_HEAVY_PARAMS: SEVERITY_MEDIUM,
    ISSUE_PRIMITIVE_SOUP: SEVERITY_MEDIUM,
    ISSUE_ANEMIC_VALUE_OBJECT: SEVERITY_LOW,
    ISSUE_TYPE_HINT_CODE_SMELL: SEVERITY_HIGH,
}

DESCRIPTIONS: dict[str, str] = {
    ISSUE_PRIMITIVE_HEAVY_PARAMS: (
        "Function has 4+ parameters all of primitive types"
    ),
    ISSUE_PRIMITIVE_SOUP: (
        "Function body has 8+ local variables of primitive types"
    ),
    ISSUE_ANEMIC_VALUE_OBJECT: (
        "Data class has only primitive fields and no behavior methods"
    ),
    ISSUE_TYPE_HINT_CODE_SMELL: (
        "String or integer used to encode type information instead of enum/class"
    ),
}

SUGGESTIONS: dict[str, str] = {
    ISSUE_PRIMITIVE_HEAVY_PARAMS: (
        "Extract related parameters into a value object or data class"
    ),
    ISSUE_PRIMITIVE_SOUP: (
        "Group related primitive variables into a value object"
    ),
    ISSUE_ANEMIC_VALUE_OBJECT: (
        "Add behavior methods to this class or convert to a proper value object"
    ),
    ISSUE_TYPE_HINT_CODE_SMELL: (
        "Replace string/integer type encoding with enum or class-based types"
    ),
}

DEFAULT_MIN_PRIMITIVE_PARAMS = 4
DEFAULT_MIN_PRIMITIVE_LOCALS = 8
DEFAULT_MIN_ANEMIC_FIELDS = 3

PYTHON_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "str", "int", "float", "bool", "bytes", "None", "none",
    "list", "dict", "tuple", "set", "frozenset",
    "List", "Dict", "Tuple", "Set", "FrozenSet",
    "Optional", "Union", "Any",
})

JAVA_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "int", "long", "float", "double", "boolean", "byte", "short", "char",
    "String", "Integer", "Long", "Float", "Double", "Boolean", "Byte",
    "Short", "Character", "Object",
})

JS_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "string", "number", "boolean", "null", "undefined", "void", "any",
    "object", "symbol", "bigint", "never", "unknown",
})

GO_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "int", "int8", "int16", "int32", "int64",
    "uint", "uint8", "uint16", "uint32", "uint64",
    "float32", "float64", "complex64", "complex128",
    "string", "bool", "byte", "rune", "uintptr",
    "any",
})

PRIMITIVE_TYPES_BY_LANG: dict[str, frozenset[str]] = {
    ".py": PYTHON_PRIMITIVE_TYPES,
    ".js": JS_PRIMITIVE_TYPES,
    ".jsx": JS_PRIMITIVE_TYPES,
    ".ts": JS_PRIMITIVE_TYPES,
    ".tsx": JS_PRIMITIVE_TYPES,
    ".java": JAVA_PRIMITIVE_TYPES,
    ".go": GO_PRIMITIVE_TYPES,
}

_VARIABLE_NAME_PRIMITIVES: frozenset[str] = frozenset({
    "name", "title", "label", "description", "type", "status", "kind",
    "count", "size", "length", "width", "height", "weight", "age",
    "price", "amount", "total", "sum", "value", "score", "rate",
    "flag", "enabled", "active", "visible", "checked", "selected",
    "id", "uid", "pid", "gid", "uuid", "key", "code", "index",
    "x", "y", "z", "i", "j", "k", "n", "m",
    "color", "email", "phone", "address", "url", "path", "file",
    "role", "level", "grade", "rank", "step", "version", "tag",
    "token", "secret", "password", "username", "first_name", "last_name",
    "city", "state", "country", "zip", "zip_code", "street",
    "source", "target", "category", "action", "method", "format",
    "message", "comment", "note", "text", "content", "subject",
    "start", "end", "from", "to", "min", "max", "default",
})

_FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"function_declaration", "method_definition",
                      "arrow_function", "function_expression"}),
    ".jsx": frozenset({"function_declaration", "method_definition",
                       "arrow_function", "function_expression"}),
    ".ts": frozenset({"function_declaration", "method_definition",
                      "arrow_function", "function_expression"}),
    ".tsx": frozenset({"function_declaration", "method_definition",
                       "arrow_function", "function_expression"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}

_CLASS_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration"}),
    ".tsx": frozenset({"class_declaration"}),
    ".java": frozenset({"class_declaration", "record_declaration"}),
    ".go": frozenset({"type_declaration"}),
}

@dataclass(frozen=True)
class PrimitiveObsessionIssue:
    """A single primitive obsession issue."""

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
class PrimitiveObsessionResult:
    """Aggregated result of primitive obsession analysis."""

    issues: tuple[PrimitiveObsessionIssue, ...]
    functions_analyzed: int
    classes_analyzed: int
    total_issues: int
    high_severity_count: int
    file_path: str

    def get_issues_by_severity(self, severity: str) -> list[PrimitiveObsessionIssue]:
        return [i for i in self.issues if i.severity == severity]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "functions_analyzed": self.functions_analyzed,
            "classes_analyzed": self.classes_analyzed,
            "total_issues": self.total_issues,
            "high_severity_count": self.high_severity_count,
            "issues": [i.to_dict() for i in self.issues],
        }

class PrimitiveObsessionAnalyzer(BaseAnalyzer):
    """Detects primitive obsession patterns in source code."""

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    def __init__(
        self,
        min_primitive_params: int = DEFAULT_MIN_PRIMITIVE_PARAMS,
        min_primitive_locals: int = DEFAULT_MIN_PRIMITIVE_LOCALS,
        min_anemic_fields: int = DEFAULT_MIN_ANEMIC_FIELDS,
    ) -> None:
        super().__init__()
        self.min_primitive_params = min_primitive_params
        self.min_primitive_locals = min_primitive_locals
        self.min_anemic_fields = min_anemic_fields

    def analyze_file(self, file_path: str) -> PrimitiveObsessionResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in SUPPORTED_EXTENSIONS:
            return PrimitiveObsessionResult(
                issues=(),
                functions_analyzed=0,
                classes_analyzed=0,
                total_issues=0,
                high_severity_count=0,
                file_path=file_path,
            )

        source = path.read_bytes()
        _, parser = self._get_parser(ext)
        if parser is None:
            return PrimitiveObsessionResult(
                issues=(),
                functions_analyzed=0,
                classes_analyzed=0,
                total_issues=0,
                high_severity_count=0,
                file_path=file_path,
            )
        tree = parser.parse(source)
        root = tree.root_node

        issues: list[PrimitiveObsessionIssue] = []
        functions_analyzed = 0
        classes_analyzed = 0

        func_types = _FUNCTION_NODE_TYPES.get(ext, frozenset())
        class_types = _CLASS_NODE_TYPES.get(ext, frozenset())

        def _walk(n: tree_sitter.Node) -> None:
            nonlocal functions_analyzed, classes_analyzed

            if n.type in func_types:
                functions_analyzed += 1
                issues.extend(
                    self._check_primitive_heavy_params(n, ext, file_path)
                )
                issues.extend(
                    self._check_primitive_soup(n, ext, file_path)
                )
                issues.extend(
                    self._check_type_hint_code_smell(n, ext, file_path)
                )

            if n.type in class_types:
                classes_analyzed += 1
                issues.extend(
                    self._check_anemic_value_object(n, ext, file_path)
                )

            for child in n.children:
                _walk(child)

        _walk(root)

        high_count = sum(1 for i in issues if i.severity == SEVERITY_HIGH)
        return PrimitiveObsessionResult(
            issues=tuple(issues),
            functions_analyzed=functions_analyzed,
            classes_analyzed=classes_analyzed,
            total_issues=len(issues),
            high_severity_count=high_count,
            file_path=file_path,
        )

    def _is_primitive_type(self, type_str: str, ext: str) -> bool:
        primitives = PRIMITIVE_TYPES_BY_LANG.get(ext, frozenset())
        return type_str in primitives or type_str.lower() in {
            p.lower() for p in primitives
        }

    def _is_primitive_by_name(self, name: str) -> bool:
        lower = name.lower()
        return lower in _VARIABLE_NAME_PRIMITIVES

    def _extract_param_info(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> list[tuple[str, str | None]]:
        """Extract (name, type_hint_or_None) for each parameter."""
        params: list[tuple[str, str | None]] = []
        skipped = {"self", "cls", "this", "super"}

        for child in func_node.children:
            if child.type in {"parameters", "parameter_list", "formal_parameters"}:
                params = self._extract_from_param_list(child, ext, skipped)
                break

        return params

    def _extract_from_param_list(
        self,
        param_list: tree_sitter.Node,
        ext: str,
        skipped: set[str],
    ) -> list[tuple[str, str | None]]:
        params: list[tuple[str, str | None]] = []

        for param in param_list.children:
            name, type_hint = self._get_param_name_type(param, ext)
            if name and name not in skipped:
                params.append((name, type_hint))

        return params

    def _get_param_name_type(
        self, param: tree_sitter.Node, ext: str,
    ) -> tuple[str | None, str | None]:
        name: str | None = None
        type_hint: str | None = None

        if param.type == "identifier":
            name = _txt(param)
        elif param.type in {
            "typed_parameter", "typed_default_parameter",
            "default_parameter",
        }:
            for child in param.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                if child.type == "type":
                    type_hint = _txt(child)
        elif param.type in {
            "required_parameter", "assignment_pattern",
            "rest_parameter",
        }:
            for child in param.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                if child.type in {
                    "type_identifier", "predefined_type",
                }:
                    type_hint = _txt(child)
                if child.type == "type_annotation":
                    for tc in child.children:
                        if tc.type in {
                            "type_identifier", "predefined_type",
                        }:
                            type_hint = _txt(tc)
        elif param.type == "formal_parameter":
            for child in param.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                if child.type in {
                    "type_identifier", "generic_type",
                    "array_type", "integral_type",
                    "floating_point_type", "boolean_type",
                }:
                    type_hint = _txt(child)
        elif param.type == "spread_parameter":
            for child in param.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                if child.type in {"type_identifier", "generic_type"}:
                    type_hint = _txt(child)
        elif param.type == "parameter_declaration":
            for child in param.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                if child.type in {
                    "type_identifier", "array_type",
                    "slice_type", "pointer_type",
                    "qualified_type", "generic_type",
                    "interface_type",
                }:
                    type_hint = _txt(child)
                for primitive_type in (
                    "int", "int8", "int16", "int32", "int64",
                    "uint", "uint8", "uint16", "uint32", "uint64",
                    "float32", "float64", "string", "bool",
                    "byte", "rune", "uintptr", "any",
                ):
                    if (
                        child.type == primitive_type
                        or _txt(child) == primitive_type
                    ):
                        type_hint = primitive_type
        elif param.type == "parameter_list":
            for child in param.children:
                child_name, child_type = self._get_go_param(child, ext)
                if child_name:
                    return child_name, child_type

        return name, type_hint

    def _get_go_param(
        self, node: tree_sitter.Node, ext: str,
    ) -> tuple[str | None, str | None]:
        if node.type in {"identifier", "parameter_declaration"}:
            name: str | None = None
            type_hint: str | None = None
            for child in node.children:
                if child.type == "identifier" and not name:
                    name = _txt(child)
                if child.type in {
                    "type_identifier", "array_type",
                    "slice_type", "pointer_type",
                    "qualified_type",
                }:
                    type_hint = _txt(child)
                for primitive in (
                    "int", "string", "bool", "float64", "float32",
                    "byte", "rune",
                ):
                    if _txt(child) == primitive:
                        type_hint = primitive
            return name, type_hint
        return None, None

    def _count_primitive_params(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> tuple[int, list[str]]:
        """Count how many params are primitive. Return (count, param_names)."""
        param_info = self._extract_param_info(func_node, ext)
        primitive_names: list[str] = []

        for name, type_hint in param_info:
            if type_hint:
                if self._is_primitive_type(type_hint.strip(), ext):
                    primitive_names.append(name)
            else:
                if self._is_primitive_by_name(name):
                    primitive_names.append(name)

        return len(primitive_names), primitive_names

    def _check_primitive_heavy_params(
        self, func_node: tree_sitter.Node, ext: str, file_path: str,
    ) -> list[PrimitiveObsessionIssue]:
        count, names = self._count_primitive_params(func_node, ext)
        self._extract_param_info(func_node, ext)

        if count >= self.min_primitive_params:
            func_name = self._get_func_name(func_node, ext)
            return [PrimitiveObsessionIssue(
                issue_type=ISSUE_PRIMITIVE_HEAVY_PARAMS,
                line=func_node.start_point[0] + 1,
                message=(
                    f"'{func_name}' has {count} parameters all of "
                    f"primitive types: {', '.join(names)}"
                ),
                severity=SEVERITY_MAP[ISSUE_PRIMITIVE_HEAVY_PARAMS],
                details=f"Parameters: {', '.join(names)}",
                suggestion=SUGGESTIONS[ISSUE_PRIMITIVE_HEAVY_PARAMS],
            )]
        return []

    def _get_func_name(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> str:
        for child in func_node.children:
            if child.type == "identifier":
                return _txt(child)
            if child.type == "property_identifier":
                return _txt(child)
            if child.type == "name":
                return _txt(child)
        return "<anonymous>"

    def _count_primitive_locals(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> tuple[int, list[str]]:
        """Count local variable declarations with primitive types."""
        primitive_vars: list[str] = []
        self._walk_for_locals(func_node, ext, primitive_vars, set())
        return len(primitive_vars), primitive_vars

    def _walk_for_locals(
        self,
        node: tree_sitter.Node,
        ext: str,
        primitive_vars: list[str],
        visited: set[int],
    ) -> None:
        if node.id in visited:
            return
        visited.add(node.id)

        if ext == ".py" and node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and left.type == "identifier":
                var_name = _txt(left)
                if self._is_primitive_by_name(var_name):
                    if right:
                        right_text = _txt(right)
                        if self._looks_primitive_value(right_text, ext):
                            primitive_vars.append(var_name)
                    else:
                        primitive_vars.append(var_name)
        elif ext in {".js", ".jsx", ".ts", ".tsx"} and node.type in {
            "variable_declarator", "lexical_declaration",
        }:
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node:
                var_name = _txt(name_node)
                if self._is_primitive_by_name(var_name):
                    primitive_vars.append(var_name)
                elif value_node:
                    val_text = _txt(value_node)
                    if self._looks_primitive_value(val_text, ext):
                        primitive_vars.append(var_name)
        elif ext == ".java" and node.type in {
            "local_variable_declaration",
            "variable_declarator",
        }:
            for child in node.children:
                if child.type == "type_identifier":
                    type_str = _txt(child)
                    if self._is_primitive_type(type_str, ext):
                        for c2 in node.children:
                            if c2.type == "identifier":
                                var_name = _txt(c2)
                                primitive_vars.append(var_name)
                                break
                        break
        elif ext == ".go" and node.type in {"short_var_declaration", "var_declaration"}:
            for child in node.children:
                if child.type == "expression_list":
                    for expr in child.children:
                        if expr.type == "identifier":
                            var_name = _txt(expr)
                            if self._is_primitive_by_name(var_name):
                                primitive_vars.append(var_name)
                if child.type == "identifier":
                    var_name = _txt(child)
                    if self._is_primitive_by_name(var_name):
                        primitive_vars.append(var_name)

        for child in node.children:
            if child.type in _FUNCTION_NODE_TYPES.get(ext, frozenset()):
                continue
            self._walk_for_locals(child, ext, primitive_vars, visited)

    def _looks_primitive_value(self, value_text: str, ext: str) -> bool:
        stripped = value_text.strip()
        if stripped.startswith(('"', "'", "`")):
            return True
        if stripped in {"True", "False", "true", "false", "None", "null"}:
            return True
        try:
            float(stripped)
            return True
        except ValueError:
            pass
        return False

    def _check_primitive_soup(
        self, func_node: tree_sitter.Node, ext: str, file_path: str,
    ) -> list[PrimitiveObsessionIssue]:
        count, names = self._count_primitive_locals(func_node, ext)
        if count >= self.min_primitive_locals:
            func_name = self._get_func_name(func_node, ext)
            return [PrimitiveObsessionIssue(
                issue_type=ISSUE_PRIMITIVE_SOUP,
                line=func_node.start_point[0] + 1,
                message=(
                    f"'{func_name}' has {count} primitive-type "
                    f"local variables: {', '.join(names[:5])}..."
                ),
                severity=SEVERITY_MAP[ISSUE_PRIMITIVE_SOUP],
                details=f"Variables: {', '.join(names)}",
                suggestion=SUGGESTIONS[ISSUE_PRIMITIVE_SOUP],
            )]
        return []

    def _check_type_hint_code_smell(
        self, func_node: tree_sitter.Node, ext: str, file_path: str,
    ) -> list[PrimitiveObsessionIssue]:
        """Detect string/int used to encode type information."""
        issues: list[PrimitiveObsessionIssue] = []

        if ext == ".py":
            issues.extend(self._check_py_type_smell(func_node))
        elif ext in {".js", ".jsx", ".ts", ".tsx"}:
            issues.extend(self._check_js_type_smell(func_node))
        elif ext == ".java":
            issues.extend(self._check_java_type_smell(func_node))
        elif ext == ".go":
            issues.extend(self._check_go_type_smell(func_node))

        return issues

    def _check_py_type_smell(
        self, func_node: tree_sitter.Node,
    ) -> list[PrimitiveObsessionIssue]:
        issues: list[PrimitiveObsessionIssue] = []
        visited: set[int] = set()

        def _walk(node: tree_sitter.Node) -> None:
            if node.id in visited:
                return
            visited.add(node.id)

            if node.type == "comparison_operator":
                children_text = [
                    _txt(c)
                    for c in node.children
                ]
                type_fields = {"type", "kind", "status", "category"}
                for text in children_text:
                    stripped = text.strip()
                    field_name = stripped.split(".")[-1] if "." in stripped else stripped
                    if field_name in type_fields:
                        func_name = self._get_func_name(func_node, ".py")
                        issues.append(PrimitiveObsessionIssue(
                            issue_type=ISSUE_TYPE_HINT_CODE_SMELL,
                            line=node.start_point[0] + 1,
                            message=(
                                f"'{func_name}' compares type field "
                                f"'{field_name}' as string"
                            ),
                            severity=SEVERITY_MAP[ISSUE_TYPE_HINT_CODE_SMELL],
                            details=f"Comparison: {' '.join(children_text)}",
                            suggestion=SUGGESTIONS[ISSUE_TYPE_HINT_CODE_SMELL],
                        ))
                        break

            for child in node.children:
                _walk(child)

        _walk(func_node)
        return issues

    def _check_js_type_smell(
        self, func_node: tree_sitter.Node,
    ) -> list[PrimitiveObsessionIssue]:
        issues: list[PrimitiveObsessionIssue] = []
        visited: set[int] = set()

        def _walk(node: tree_sitter.Node) -> None:
            if node.id in visited:
                return
            visited.add(node.id)

            if node.type == "binary_expression":
                left = node.child_by_field_name("left")
                op = node.child_by_field_name("operator")
                if (
                    left
                    and op
                    and _txt(op) in {"===", "=="}
                    and left.type == "member_expression"
                ):
                    prop = left.child_by_field_name("property")
                    if prop:
                        prop_text = _txt(prop)
                        if prop_text in {"type", "kind", "status", "category"}:
                            func_name = self._get_func_name(func_node, ".js")
                            issues.append(PrimitiveObsessionIssue(
                                issue_type=ISSUE_TYPE_HINT_CODE_SMELL,
                                line=node.start_point[0] + 1,
                                message=(
                                    f"'{func_name}' compares .{prop_text} "
                                    f"as string/number"
                                ),
                                severity=SEVERITY_MAP[ISSUE_TYPE_HINT_CODE_SMELL],
                                details=f"Property access: .{prop_text}",
                                suggestion=SUGGESTIONS[ISSUE_TYPE_HINT_CODE_SMELL],
                            ))

            for child in node.children:
                _walk(child)

        _walk(func_node)
        return issues

    def _check_java_type_smell(
        self, func_node: tree_sitter.Node,
    ) -> list[PrimitiveObsessionIssue]:
        issues: list[PrimitiveObsessionIssue] = []
        visited: set[int] = set()

        def _walk(node: tree_sitter.Node) -> None:
            if node.id in visited:
                return
            visited.add(node.id)

            if node.type == "method_invocation":
                obj = node.child_by_field_name("object")
                method = node.child_by_field_name("name")
                if method:
                    method_text = _txt(method)
                    if method_text == "equals" and obj:
                        obj_text = _txt(obj)
                        if obj_text in {"type", "kind", "status", "category"}:
                            func_name = self._get_func_name(func_node, ".java")
                            issues.append(PrimitiveObsessionIssue(
                                issue_type=ISSUE_TYPE_HINT_CODE_SMELL,
                                line=node.start_point[0] + 1,
                                message=(
                                    f"'{func_name}' compares "
                                    f'{obj_text}.equals() as String'
                                ),
                                severity=SEVERITY_MAP[ISSUE_TYPE_HINT_CODE_SMELL],
                                details=f"String comparison: {obj_text}.equals()",
                                suggestion=SUGGESTIONS[ISSUE_TYPE_HINT_CODE_SMELL],
                            ))

            for child in node.children:
                _walk(child)

        _walk(func_node)
        return issues

    def _check_go_type_smell(
        self, func_node: tree_sitter.Node,
    ) -> list[PrimitiveObsessionIssue]:
        issues: list[PrimitiveObsessionIssue] = []
        visited: set[int] = set()

        def _walk(node: tree_sitter.Node) -> None:
            if node.id in visited:
                return
            visited.add(node.id)

            if node.type == "binary_expression":
                left = node.child_by_field_name("left")
                op = node.child_by_field_name("operator")
                if (
                    left
                    and op
                    and _txt(op) == "=="
                    and left.type == "selector_expression"
                ):
                    field = left.child_by_field_name("field")
                    if field:
                        field_text = _txt(field)
                        if field_text in {"Type", "Kind", "Status", "Category"}:
                            func_name = self._get_func_name(func_node, ".go")
                            issues.append(PrimitiveObsessionIssue(
                                issue_type=ISSUE_TYPE_HINT_CODE_SMELL,
                                line=node.start_point[0] + 1,
                                message=(
                                    f"'{func_name}' compares .{field_text} "
                                    f"as string"
                                ),
                                severity=SEVERITY_MAP[ISSUE_TYPE_HINT_CODE_SMELL],
                                details=f"Field comparison: .{field_text}",
                                suggestion=SUGGESTIONS[ISSUE_TYPE_HINT_CODE_SMELL],
                            ))

            for child in node.children:
                _walk(child)

        _walk(func_node)
        return issues

    def _check_anemic_value_object(
        self, class_node: tree_sitter.Node, ext: str, file_path: str,
    ) -> list[PrimitiveObsessionIssue]:
        """Check if a class is anemic (only primitive fields, no methods)."""
        class_name = self._get_class_name(class_node, ext)
        if not class_name:
            return []

        fields: list[str] = []
        visited: set[int] = set()

        self._walk_class_body(class_node, ext, fields, has_methods_ref=[False], visited=visited)

        if (
            len(fields) >= self.min_anemic_fields
            and not self._has_behavior(class_node, ext)
        ):
            return [PrimitiveObsessionIssue(
                issue_type=ISSUE_ANEMIC_VALUE_OBJECT,
                line=class_node.start_point[0] + 1,
                message=(
                    f"'{class_name}' has {len(fields)} primitive fields "
                    f"and no behavior methods"
                ),
                severity=SEVERITY_MAP[ISSUE_ANEMIC_VALUE_OBJECT],
                details=f"Fields: {', '.join(fields[:10])}",
                suggestion=SUGGESTIONS[ISSUE_ANEMIC_VALUE_OBJECT],
            )]
        return []

    def _get_class_name(
        self, class_node: tree_sitter.Node, ext: str,
    ) -> str:
        for child in class_node.children:
            if child.type == "identifier":
                return _txt(child)
            if child.type == "name":
                return _txt(child)
            if child.type == "type_identifier":
                return _txt(child)
            if child.type == "type_spec":
                for spec_child in child.children:
                    if spec_child.type == "type_identifier":
                        return _txt(spec_child)
        return ""

    def _walk_class_body(
        self,
        node: tree_sitter.Node,
        ext: str,
        fields: list[str],
        has_methods_ref: list[bool],
        visited: set[int],
    ) -> None:
        if node.id in visited:
            return
        visited.add(node.id)

        if ext == ".py":
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                if left and left.type == "identifier":
                    name = _txt(left)
                    if not name.startswith("_"):
                        fields.append(name)
            if node.type in {
                "function_definition", "decorated_definition",
            }:
                has_methods_ref[0] = True

        elif ext in {".js", ".jsx", ".ts", ".tsx"}:
            if node.type == "public_field_definition":
                for child in node.children:
                    if child.type == "property_identifier":
                        fields.append(
                            _txt(child)
                        )
                        break
            if node.type in {
                "method_definition", "function_declaration",
                "generator_function_declaration",
            }:
                has_methods_ref[0] = True

        elif ext == ".java":
            if node.type == "field_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        for vc in child.children:
                            if vc.type == "identifier":
                                fields.append(
                                    _txt(vc)
                                )
                                break
                        break
            if node.type in {"method_declaration"}:
                name_node = node.child_by_field_name("name")
                if name_node:
                    method_name = _txt(name_node)
                    if method_name not in {
                        "equals", "hashCode", "toString",
                        "getter", "setter",
                    }:
                        has_methods_ref[0] = True

        elif ext == ".go":
            if node.type == "field_declaration":
                for child in node.children:
                    if child.type == "field_identifier":
                        fields.append(
                            _txt(child)
                        )
                        break
            if node.type == "method_declaration":
                has_methods_ref[0] = True

        for child in node.children:
            self._walk_class_body(
                child, ext, fields, has_methods_ref, visited,
            )

    def _has_behavior(
        self, class_node: tree_sitter.Node, ext: str,
    ) -> bool:
        has_methods_ref = [False]
        self._walk_class_body(
            class_node, ext, [], has_methods_ref, set(),
        )
        return has_methods_ref[0]
