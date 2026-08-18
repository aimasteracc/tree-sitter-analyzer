"""Staged tree walker for cache symbol extraction."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from ._symbol_declarations import (
    _go_package_constants,
    _php_constants,
    _python_docstring,
    _python_module_constant,
)
from ._symbol_metrics import (
    _annotate_canonical_complexity,
    _count_decision_points,
    _count_nodes,
)
from ._symbol_rules import (
    _CLASS_LIKE,
    _ENUM_LIKE,
    _FUNCTION_LIKE,
    _GO_CONST_LIKE,
    _IMPORT_LIKE,
    _RUST_CONST_LIKE,
    _SCALA_CLASS_LIKE,
    _SCOPE_BODY_NODES,
    _VAR_DECL_LIKE,
    _WALK_MAX_DEPTH,
)
from ._symbol_syntax import (
    _bash_subscript_base,
    _c_function_def_name,
    _extract_parent_classes,
    _find_parent_class,
    _node_text,
    _scala_symbol_from_node,
)

_CPP_MODULE_IMPORT_RE = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?import[ \t]+[^;\r\n]+[ \t]*;"
)


def _python_module_scope_statements(module: ast.Module) -> list[ast.stmt]:
    """Return statements executed in module scope, excluding nested scopes."""
    statements: list[ast.stmt] = []
    scope_nodes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def visit_children(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                statements.append(child)
                if isinstance(child, scope_nodes):
                    continue
            visit_children(child)

    for statement in module.body:
        statements.append(statement)
        if not isinstance(statement, scope_nodes):
            visit_children(statement)
    return statements


def _python_dynamic_loader_analysis(source: str) -> tuple[frozenset[str], bool]:
    """Return module loader aliases and whether their scope is unambiguous."""
    names = {"__import__", "importlib.import_module"}
    try:
        module = ast.parse(source)
    except SyntaxError:
        return frozenset(names), False
    module_statements = _python_module_scope_statements(module)
    for statement in module_statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "importlib":
                    names.add(f"{alias.asname or alias.name}.import_module")
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and statement.module == "importlib"
        ):
            for alias in statement.names:
                if alias.name == "import_module":
                    names.add(alias.asname or alias.name)
    assignments: list[tuple[list[ast.expr], ast.expr]] = []
    for statement in module_statements:
        if isinstance(statement, ast.Assign):
            assignments.append((statement.targets, statement.value))
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            assignments.append(([statement.target], statement.value))
    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            reference = _python_reference_name(value)
            if reference not in names:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    loader_roots = {name.split(".", 1)[0] for name in names}
    module_rebinding = any(
        isinstance(target, ast.Name)
        and target.id in loader_roots
        and _python_reference_name(value) not in names
        for targets, value in assignments
        for target in targets
    )
    nested_bindings: set[str] = set()
    nested_loader_alias = False
    for statement in module_statements:
        if not isinstance(
            statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        for node in ast.walk(statement):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                arguments = (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                nested_bindings.update(argument.arg for argument in arguments)
                if node.args.vararg is not None:
                    nested_bindings.add(node.args.vararg.arg)
                if node.args.kwarg is not None:
                    nested_bindings.add(node.args.kwarg.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                nested_bindings.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and isinstance(node.name, str):
                nested_bindings.add(node.name)
            elif isinstance(node, ast.Assign):
                bound = {
                    target.id for target in node.targets if isinstance(target, ast.Name)
                }
                nested_bindings.update(bound)
                nested_loader_alias = nested_loader_alias or (
                    _python_reference_name(node.value) in names and bool(bound)
                )
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                nested_bindings.add(node.target.id)
                nested_loader_alias = nested_loader_alias or (
                    node.value is not None
                    and _python_reference_name(node.value) in names
                )
            elif isinstance(node, ast.NamedExpr):
                nested_loader_alias = nested_loader_alias or (
                    isinstance(node.target, ast.Name)
                    and _python_reference_name(node.value) in names
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    nested_bindings.add(alias.asname or alias.name.split(".", 1)[0])
                    nested_loader_alias = (
                        nested_loader_alias or alias.name == "importlib"
                    )
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    nested_bindings.add(alias.asname or alias.name)
                    nested_loader_alias = nested_loader_alias or (
                        node.level == 0
                        and node.module == "importlib"
                        and alias.name == "import_module"
                    )
    complete = (
        not module_rebinding
        and not nested_loader_alias
        and not loader_roots.intersection(nested_bindings)
    )
    return frozenset(names), complete


def _python_dynamic_loader_names(source: str) -> frozenset[str]:
    """Return module-scoped Python dynamic-import call names."""

    return _python_dynamic_loader_analysis(source)[0]


def _python_reference_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _python_reference_name(node.value)
        return f"{owner}.{node.attr}" if owner else None
    return None


@dataclass(slots=True)
class _SymbolWalker:
    source: str
    symbols: list[dict[str, Any]]
    language: str
    truncated_flag: list[bool] | None
    python_dynamic_loaders: set[str] = field(init=False, repr=False)
    jsts_module_loaders: set[str] = field(init=False, repr=False)
    import_projection_complete: bool = field(init=False, repr=False, default=True)
    java_static_for_name: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        self.python_dynamic_loaders = set()
        self.jsts_module_loaders = {"require", "module.require", "import"}
        if self.language == "python":
            loaders, self.import_projection_complete = _python_dynamic_loader_analysis(
                self.source
            )
            self.python_dynamic_loaders.update(loaders)
        if self.language in {"javascript", "typescript"}:
            self.jsts_module_loaders.update(
                re.findall(
                    r"(?m)\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
                    r"(?:module\.)?require\b",
                    self.source,
                )
            )
        if self.language == "java":
            self.java_static_for_name = bool(
                re.search(
                    r"(?m)^\s*import\s+static\s+java\.lang\.Class\.forName\s*;",
                    self.source,
                )
            )

    def walk(self, node: Any, depth: int = 0, enclosed: bool = False) -> None:
        if depth > _WALK_MAX_DEPTH:
            if self.truncated_flag is not None:
                self.truncated_flag[0] = True
            return
        self._collect_node(node, depth, enclosed)
        child_enclosed = enclosed or node.type in _SCOPE_BODY_NODES.get(
            self.language, frozenset()
        )
        for child in node.children:
            self.walk(child, depth + 1, child_enclosed)

    def _collect_node(self, node: Any, depth: int, enclosed: bool) -> None:
        name_node = node.child_by_field_name("name")
        function_name = self._function_name(node, name_node)
        if function_name is not None:
            self._append_function(node, function_name)
            return
        if self._append_scala(node, enclosed):
            return
        if node.type in _CLASS_LIKE:
            self._append_class(node, name_node)
            return
        if node.type in _IMPORT_LIKE:
            self._append_import(node)
            return
        self._append_python_loader_assignment(node)
        if self._append_jsts_reexport(node):
            return
        if self._append_typescript_path_reference(node):
            return
        if self._append_jsts_module_call(node):
            return
        if self._append_python_module_call(node):
            return
        if self._append_java_reflective_load(node):
            return
        if self._is_variable(node, name_node, enclosed):
            self._append_variable(node, name_node, depth)
            return
        self._append_constant(node, name_node, enclosed)

    def _function_name(self, node: Any, name_node: Any) -> str | None:
        if node.type not in _FUNCTION_LIKE:
            return None
        if name_node is not None:
            return _node_text(name_node, self.source)
        if node.type == "function_definition" and self.language == "c":
            return _c_function_def_name(node, self.source)
        return None

    def _append_function(self, node: Any, name: str) -> None:
        params_node = node.child_by_field_name("parameters")
        symbol: dict[str, Any] = {
            "kind": "function",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "params": _node_text(params_node, self.source) if params_node else "",
            "language": self.language,
        }
        decision_points = _count_decision_points(node, self.language)
        if decision_points:
            symbol["decision_points"] = decision_points
        return_type = node.child_by_field_name("return_type")
        if return_type is not None:
            symbol["return_type"] = _node_text(return_type, self.source).lstrip(": ")
        self._add_python_docstring(symbol, node)
        parent_class = _find_parent_class(node, self.source)
        if parent_class:
            symbol["kind"] = "method"
            symbol["class"] = parent_class
        self.symbols.append(symbol)

    def _add_python_docstring(self, symbol: dict[str, Any], node: Any) -> None:
        if self.language != "python":
            return
        docstring = _python_docstring(node, self.source)
        if docstring is not None:
            symbol["docstring"] = docstring

    def _append_scala(self, node: Any, enclosed: bool) -> bool:
        if self.language != "scala" or node.type not in _SCALA_CLASS_LIKE or enclosed:
            return False
        symbol = _scala_symbol_from_node(node, self.source)
        if symbol is not None:
            self.symbols.append(symbol)
        return True

    def _append_class(self, node: Any, name_node: Any) -> None:
        effective_name = self._class_name_node(node, name_node)
        if effective_name is None:
            return
        name = _node_text(effective_name, self.source)
        if not name:
            return
        symbol: dict[str, Any] = {
            "kind": "enum" if node.type in _ENUM_LIKE else "class",
            "name": name,
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "language": self.language,
        }
        parents = _extract_parent_classes(node, self.source, self.language)
        if parents:
            symbol["parents"] = parents
        self._add_python_docstring(symbol, node)
        self.symbols.append(symbol)

    @staticmethod
    def _class_name_node(node: Any, name_node: Any) -> Any:
        if name_node is not None:
            return name_node
        for child in node.children:
            if child.type in ("type_identifier", "constant", "identifier"):
                return child
        return None

    def _append_import(self, node: Any) -> None:
        text = _node_text(node, self.source)
        if self.language == "python":
            self.python_dynamic_loaders.update(_python_dynamic_loader_names(text))
        self.symbols.append(
            {
                "kind": "import",
                "text": text,
                "line": node.start_point[0] + 1,
                "language": self.language,
            }
        )

    def _append_jsts_module_call(self, node: Any) -> bool:
        """Project JS/TS module loads so unresolved calls fail closed."""
        if self.language not in {"javascript", "typescript"}:
            return False
        if node.type != "call_expression":
            return False
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or arguments is None:
            return False
        if _node_text(function, self.source) not in self.jsts_module_loaders:
            return False
        self._append_import(node)
        return True

    def _append_jsts_reexport(self, node: Any) -> bool:
        """Project JS/TS re-exports that introduce module dependencies."""
        if self.language not in {"javascript", "typescript"}:
            return False
        if node.type != "export_statement":
            return False
        if node.child_by_field_name("source") is None:
            return False
        self._append_import(node)
        return True

    def _append_typescript_path_reference(self, node: Any) -> bool:
        """Project triple-slash declaration-file references as dependencies."""
        if self.language != "typescript" or node.type != "comment":
            return False
        text = _node_text(node, self.source)
        if (
            re.fullmatch(
                r"\s*///\s*<reference\b"
                r"(?=[^>]*\bpath\s*=\s*(['\"])[^'\"]+\1)[^>]*?/?>\s*",
                text,
            )
            is None
        ):
            return False
        self._append_import(node)
        return True

    def _append_python_module_call(self, node: Any) -> bool:
        """Project Python dynamic loads so unresolved calls fail closed."""
        if self.language != "python" or node.type != "call":
            return False
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or arguments is None:
            return False
        if _node_text(function, self.source) not in self.python_dynamic_loaders:
            return False
        self._append_import(node)
        return True

    def _append_python_loader_assignment(self, node: Any) -> bool:
        """Project simple aliases so snapshot readers can verify loader calls."""
        if self.language != "python" or node.type not in {
            "assignment",
            "annotated_assignment",
        }:
            return False
        try:
            body = ast.parse(_node_text(node, self.source)).body
        except SyntaxError:
            return False
        if len(body) != 1:
            return False
        statement = body[0]
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        else:
            return False
        if _python_reference_name(value) not in self.python_dynamic_loaders or not any(
            isinstance(target, ast.Name) for target in targets
        ):
            return False
        self._append_import(node)
        return True

    def _append_java_reflective_load(self, node: Any) -> bool:
        """Project Class.forName calls so reflection cannot hide dependencies."""
        if self.language != "java" or node.type != "method_invocation":
            return False
        name = node.child_by_field_name("name")
        object_node = node.child_by_field_name("object")
        arguments = node.child_by_field_name("arguments")
        if name is None or arguments is None:
            return False
        if _node_text(name, self.source) != "forName":
            return False
        if object_node is None:
            if not self.java_static_for_name:
                return False
        elif _node_text(object_node, self.source) not in {
            "Class",
            "java.lang.Class",
        }:
            return False
        self._append_import(node)
        return True

    def _is_variable(self, node: Any, name_node: Any, enclosed: bool) -> bool:
        if node.type not in _VAR_DECL_LIKE or name_node is None:
            return False
        if self.language in ("javascript", "typescript", "java", "csharp"):
            if enclosed:
                return False
        return not (
            node.type == "variable_assignment"
            and node.parent is not None
            and node.parent.type == "command"
        )

    def _append_variable(self, node: Any, name_node: Any, depth: int) -> None:
        if name_node.type == "subscript":
            name_node = _bash_subscript_base(name_node)
        name = _node_text(name_node, self.source) if name_node is not None else ""
        if name and (not name.startswith("_") or depth < 3):
            self.symbols.append(
                {
                    "kind": "variable",
                    "name": name,
                    "line": node.start_point[0] + 1,
                    "language": self.language,
                }
            )

    def _append_constant(self, node: Any, name_node: Any, enclosed: bool) -> None:
        if node.type == "assignment" and self.language == "python" and not enclosed:
            symbol = _python_module_constant(node, self.source)
            if symbol is not None:
                self.symbols.append(symbol)
            return
        if node.type in _GO_CONST_LIKE and self.language == "go" and not enclosed:
            self.symbols.extend(_go_package_constants(node, self.source))
            return
        if self._is_rust_constant(node, name_node, enclosed):
            self.symbols.append(
                {
                    "kind": "constant",
                    "name": _node_text(name_node, self.source),
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "language": "rust",
                }
            )
            return
        if node.type == "const_declaration" and self.language == "php" and not enclosed:
            self.symbols.extend(_php_constants(node, self.source))

    def _is_rust_constant(self, node: Any, name_node: Any, enclosed: bool) -> bool:
        return (
            node.type in _RUST_CONST_LIKE
            and self.language == "rust"
            and not enclosed
            and name_node is not None
            and _node_text(name_node, self.source) != "_"
        )


def _walk_for_symbols(
    node: Any,
    source: str,
    symbols: list[dict[str, Any]],
    language: str,
    depth: int = 0,
    enclosed: bool = False,
    _truncated_flag: list[bool] | None = None,
) -> None:
    """Walk an AST while preserving the historical helper signature."""
    _SymbolWalker(source, symbols, language, _truncated_flag).walk(
        node, depth, enclosed
    )


def _extract_symbols(tree: Any, source_code: str, language: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    if tree is None:
        return {
            "symbols": symbols,
            "node_count": 0,
            "truncated_depth": False,
            "import_projection_complete": True,
        }
    root = tree.root_node
    truncated_flag = [False]
    walker = _SymbolWalker(source_code, symbols, language, truncated_flag)
    walker.walk(root)
    if language == "cpp":
        projected = {
            (symbol.get("text"), symbol.get("line"))
            for symbol in symbols
            if symbol.get("kind") == "import"
        }
        for match in _CPP_MODULE_IMPORT_RE.finditer(source_code):
            text = match.group(0).strip()
            line = source_code.count("\n", 0, match.start()) + 1
            if (text, line) not in projected:
                symbols.append(
                    {
                        "kind": "import",
                        "text": text,
                        "line": line,
                        "language": language,
                    }
                )
    _annotate_canonical_complexity(symbols, tree, source_code, language)
    return {
        "symbols": symbols,
        "node_count": _count_nodes(root),
        "truncated_depth": truncated_flag[0],
        "import_projection_complete": walker.import_projection_complete,
    }


def _extract_imports(symbols: dict[str, Any]) -> list[dict[str, Any]]:
    """Return per-statement import entries carrying the source line.

    Entries are dicts with text and line keys so the ast_imports table can
    record the statement line instead of a constant zero; string consumers
    are still served by the text key (dogfood F5, #1275).
    """
    return [
        {
            "text": symbol["text"],
            "line": symbol.get("line", 0),
        }
        for symbol in symbols.get("symbols", [])
        if symbol.get("kind") == "import"
    ]


def _extract_structure(symbols: dict[str, Any]) -> dict[str, Any]:
    functions = [
        {"name": symbol["name"], "line": symbol["line"]}
        for symbol in symbols.get("symbols", [])
        if symbol["kind"] in ("function", "method")
    ]
    classes = [
        {"name": symbol["name"], "line": symbol["line"]}
        for symbol in symbols.get("symbols", [])
        if symbol["kind"] in ("class", "enum")
    ]
    return {"functions": functions, "classes": classes}
