"""Shared method stubs for SQL extraction mixins — satisfies mypy strict attr-defined checks."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ...models import (
        Class,
        Expression,
        Function,
        Import,
        SQLColumn,
        SQLConstraint,
        SQLElement,
        SQLIndex,
        SQLParameter,
        Variable,
    )


class _SQLExtractorBase:
    """Declares cross-mixin methods for mypy attr-defined resolution."""

    source_code: str
    content_lines: list[str]

    def _get_node_text(self, node: tree_sitter.Node) -> str:
        raise NotImplementedError

    def _traverse_nodes(self, node: tree_sitter.Node) -> Any:
        raise NotImplementedError

    def _is_valid_identifier(self, name: str) -> bool:
        raise NotImplementedError

    # Table methods
    def _extract_tables(self, root_node: tree_sitter.Node, classes: list[Class]) -> None:
        raise NotImplementedError

    def _extract_sql_tables(self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]) -> None:
        raise NotImplementedError

    def _extract_table_columns(
        self, table_node: tree_sitter.Node, columns: list[SQLColumn], constraints: list[SQLConstraint]
    ) -> None:
        raise NotImplementedError

    def _split_column_definitions(self, content: str) -> list[str]:
        raise NotImplementedError

    def _parse_column_definition(self, col_def: str) -> SQLColumn | None:
        raise NotImplementedError

    # View methods
    def _extract_views(self, root_node: tree_sitter.Node, classes: list[Class]) -> None:
        raise NotImplementedError

    def _extract_sql_views(self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]) -> None:
        raise NotImplementedError

    def _extract_view_sources(self, view_node: tree_sitter.Node, source_tables: list[str]) -> None:
        raise NotImplementedError

    # Procedure methods
    def _extract_procedures(self, root_node: tree_sitter.Node, functions: list[Function]) -> None:
        raise NotImplementedError

    def _extract_sql_procedures(self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]) -> None:
        raise NotImplementedError

    def _extract_procedure_parameters(self, proc_text: str, parameters: list[SQLParameter]) -> None:
        raise NotImplementedError

    def _extract_procedure_dependencies(self, proc_node: tree_sitter.Node, dependencies: list[str]) -> None:
        raise NotImplementedError

    # Function methods
    def _extract_sql_functions(self, root_node: tree_sitter.Node, functions: list[Function]) -> None:
        raise NotImplementedError

    def _extract_sql_functions_enhanced(self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]) -> None:
        raise NotImplementedError

    def _extract_function_metadata(
        self, func_node: tree_sitter.Node, parameters: list[SQLParameter],
        return_type: str | None, dependencies: list[str]
    ) -> None:
        raise NotImplementedError

    # Trigger methods
    def _extract_triggers(self, root_node: tree_sitter.Node, functions: list[Function]) -> None:
        raise NotImplementedError

    def _extract_sql_triggers(self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]) -> None:
        raise NotImplementedError

    def _extract_trigger_metadata(self, trigger_text: str) -> tuple[str | None, str | None, str | None]:
        raise NotImplementedError

    # Index methods
    def _extract_indexes(self, root_node: tree_sitter.Node, variables: list[Variable]) -> None:
        raise NotImplementedError

    def _extract_sql_indexes(self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]) -> None:
        raise NotImplementedError

    def _extract_index_metadata(self, index_node: tree_sitter.Node, index: SQLIndex) -> None:
        raise NotImplementedError

    def _extract_indexes_with_regex(
        self, sql_elements: list[SQLElement], processed_indexes: set[str]
    ) -> None:
        raise NotImplementedError

    # DML methods
    def _extract_dml_statements(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_expressions(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_query_clauses(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_window_functions(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_transactions(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_comments(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_select_statements(self, root_node: tree_sitter.Node, elements: list[Expression]) -> None:
        raise NotImplementedError

    def _extract_schema_references(self, root_node: tree_sitter.Node, imports: list[Import]) -> None:
        raise NotImplementedError

    def _reset_caches(self) -> None:
        raise NotImplementedError
