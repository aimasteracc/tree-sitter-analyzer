"""Cross-mixin stubs — mypy attr-defined."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    import tree_sitter

    from ...models import (
        Class,
        CodeElement,
        Expression,
        Function,
        Import,
        Package,
        Variable,
    )


class _TypeScriptElementBase:
    current_file: Any
    source_code: Any
    content_lines: Any
    imports: Any
    exports: Any
    _node_text_cache: Any
    _processed_nodes: Any
    _element_cache: Any
    _file_encoding: Any
    _tsdoc_cache: Any
    _complexity_cache: Any
    is_module: Any
    is_tsx: Any
    framework_type: Any
    typescript_version: Any

    def _extract_class_optimized(self, node: tree_sitter.Node) -> Class | None:
        raise NotImplementedError

    def _extract_interface_optimized(self, node: tree_sitter.Node) -> Class | None:
        raise NotImplementedError

    def __init__(self) -> None:
        raise NotImplementedError

    def extract_functions(self, tree: tree_sitter.Tree, source_code: str) -> list[Function]:
        raise NotImplementedError

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        raise NotImplementedError

    def extract_variables(self, tree: tree_sitter.Tree, source_code: str) -> list[Variable]:
        raise NotImplementedError

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        raise NotImplementedError

    def _reset_caches(self) -> None:
        raise NotImplementedError

    def _detect_file_characteristics(self) -> None:
        raise NotImplementedError

    def _traverse_and_extract_iterative(self, root_node: tree_sitter.Node | None, extractors: dict[str, Any], results: list[Any], element_type: str) -> None:
        raise NotImplementedError

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
        raise NotImplementedError

    def _extract_arrow_function_optimized(self, node: tree_sitter.Node) -> Function | None:
        raise NotImplementedError

    def _extract_method_optimized(self, node: tree_sitter.Node) -> Function | None:
        raise NotImplementedError

    def _extract_method_signature_optimized(self, node: tree_sitter.Node) -> Function | None:
        raise NotImplementedError

    def _extract_generator_function_optimized(self, node: tree_sitter.Node) -> Function | None:
        raise NotImplementedError

    def _extract_lexical_variable_optimized(self, node: tree_sitter.Node) -> list[Variable]:
        raise NotImplementedError

    def _extract_property_optimized(self, node: tree_sitter.Node) -> Variable | None:
        raise NotImplementedError

    def _extract_property_signature_optimized(self, node: tree_sitter.Node) -> Variable | None:
        raise NotImplementedError

    def _parse_variable_declarator(self, node: tree_sitter.Node, kind: str, start_line: int, end_line: int) -> Variable | None:
        raise NotImplementedError

    def _parse_function_signature_optimized(self, node: tree_sitter.Node) -> tuple[str | None, list[str], bool, bool, str | None, list[str]] | None:
        raise NotImplementedError

    def _parse_method_signature_optimized(self, node: tree_sitter.Node) -> tuple[str | None, list[str], bool, bool, bool, bool, bool, str | None, str, list[str]] | None:
        raise NotImplementedError

    def _extract_parameters_with_types(self, params_node: tree_sitter.Node) -> list[str]:
        raise NotImplementedError

    def _extract_generics(self, type_params_node: tree_sitter.Node) -> list[str]:
        raise NotImplementedError

    def _extract_dynamic_import(self, node: tree_sitter.Node) -> Import | None:
        raise NotImplementedError

    def _extract_commonjs_requires(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        raise NotImplementedError

    def _is_framework_component(self, node: tree_sitter.Node, class_name: str) -> bool:
        raise NotImplementedError

    def _is_exported_class(self, class_name: str) -> bool:
        raise NotImplementedError

    def _infer_type_from_value(self, value: str | None) -> str:
        raise NotImplementedError

    def _extract_tsdoc_for_line(self, target_line: int) -> str | None:
        raise NotImplementedError

    def _clean_tsdoc(self, tsdoc_text: str) -> str:
        raise NotImplementedError

    def _calculate_complexity_optimized(self, node: tree_sitter.Node) -> int:
        raise NotImplementedError

    def extract_exports(self, tree: tree_sitter.Tree, source_code: str) -> list[Expression]:
        raise NotImplementedError

    def extract_patterns(self, tree: tree_sitter.Tree, source_code: str) -> list[Expression]:
        raise NotImplementedError

    def extract_namespaces(self, tree: tree_sitter.Tree, source_code: str) -> list[Package]:
        raise NotImplementedError

    def extract_ambient_declarations(self, tree: tree_sitter.Tree, source_code: str) -> list[Package]:
        raise NotImplementedError

    def extract_elements(self, tree: tree_sitter.Tree, source_code: str) -> list[CodeElement]:
        raise NotImplementedError

    def _extract_function_optimized(self, node: tree_sitter.Node) -> Function | None:
        raise NotImplementedError

    def _extract_function_signature_optimized(self, node: tree_sitter.Node) -> Function | None:
        raise NotImplementedError

    def _extract_import_info_simple(self, node: tree_sitter.Node) -> Import | None:
        raise NotImplementedError

    def _extract_import_names(self, import_clause_node: tree_sitter.Node, import_text: str) -> list[str]:
        raise NotImplementedError

    def _extract_type_alias_optimized(self, node: tree_sitter.Node) -> Class | None:
        raise NotImplementedError

    def _extract_enum_optimized(self, node: tree_sitter.Node) -> Class | None:
        raise NotImplementedError

    def _extract_variable_optimized(self, node: tree_sitter.Node) -> list[Variable]:
        raise NotImplementedError

    def _extract_variables_from_declaration(self, node: tree_sitter.Node, kind: str) -> list[Variable]:
        raise NotImplementedError
