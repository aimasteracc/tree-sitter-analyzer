"""Staged tree walker for cache symbol extraction."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(slots=True)
class _SymbolWalker:
    source: str
    symbols: list[dict[str, Any]]
    language: str
    truncated_flag: list[bool] | None

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
        self.symbols.append(
            {
                "kind": "import",
                "text": _node_text(node, self.source),
                "line": node.start_point[0] + 1,
                "language": self.language,
            }
        )

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
        return {"symbols": symbols, "node_count": 0, "truncated_depth": False}
    root = tree.root_node
    truncated_flag = [False]
    _SymbolWalker(source_code, symbols, language, truncated_flag).walk(root)
    _annotate_canonical_complexity(symbols, tree, source_code, language)
    return {
        "symbols": symbols,
        "node_count": _count_nodes(root),
        "truncated_depth": truncated_flag[0],
    }


def _extract_imports(symbols: dict[str, Any]) -> list[str]:
    return [
        symbol["text"]
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
