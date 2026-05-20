"""Shared helpers for SQL formatter output."""

from collections.abc import Iterable
from typing import Any

from ..models import (
    SQLElement,
    SQLElementType,
    SQLFunction,
    SQLIndex,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
)

SQL_PARAMETER_KEYWORDS = {
    "SELECT",
    "FROM",
    "WHERE",
    "INTO",
    "VALUES",
    "SET",
    "UPDATE",
    "INSERT",
    "DELETE",
    "PENDING",
}


def iter_sql_elements_by_line(
    grouped_elements: dict[SQLElementType, list[SQLElement]],
) -> list[SQLElement]:
    """Return grouped SQL elements sorted by source line."""
    all_elements = []
    for elements in grouped_elements.values():
        all_elements.extend(elements)
    return sorted(all_elements, key=lambda element: element.start_line)


def format_sql_overview_details(element: SQLElement) -> str:
    """Format details for the full formatter overview table."""
    if hasattr(element, "columns") and element.columns:
        return f"{len(element.columns)} columns"

    if hasattr(element, "parameters") and element.parameters:
        param_names = _valid_parameter_names(element.parameters)
        if param_names:
            return f"({', '.join(param_names)})"
        return f"{len(element.parameters)} parameters"

    if hasattr(element, "indexed_columns") and element.indexed_columns:
        col_info = f"({', '.join(element.indexed_columns)})"
        if hasattr(element, "table_name") and element.table_name:
            return f"{element.table_name}{col_info}"
        return col_info

    if hasattr(element, "source_tables") and element.source_tables:
        return f"from {', '.join(element.source_tables)}"

    return "-"


def format_sql_compact_details(element: SQLElement) -> str:
    """Format compact details for a SQL element."""
    detail_formatters = (
        (SQLTable, _format_compact_table_details),
        (SQLView, _format_compact_view_details),
        (SQLProcedure, _format_compact_procedure_details),
        (SQLFunction, _format_compact_function_details),
        (SQLTrigger, _format_compact_trigger_details),
        (SQLIndex, _format_compact_index_details),
    )

    for element_type, formatter in detail_formatters:
        if isinstance(element, element_type):
            return formatter(element)
    return "-"


def format_sql_table_foreign_keys(table: SQLTable) -> str | None:
    """Format table foreign-key details when present."""
    fk_details = [
        f"{col.name} \u2192 {col.foreign_key_reference}"
        for col in table.columns
        if col.is_foreign_key and col.foreign_key_reference
    ]
    if not fk_details:
        return None
    return f"**Foreign Keys**: {', '.join(fk_details)}"


def format_sql_parameter_details(parameters: Iterable[Any]) -> list[str]:
    """Format SQL routine parameters for detail sections."""
    details = []
    for param in parameters:
        param_str = f"{param.name} {param.data_type}"
        if param.direction != "IN":
            param_str = f"{param.direction} {param_str}"
        details.append(param_str)
    return details


def format_sql_csv_details(element: SQLElement) -> str:
    """Format the columns/parameters field for CSV output."""
    if hasattr(element, "columns") and element.columns:
        return f"{len(element.columns)} columns"

    if hasattr(element, "parameters") and element.parameters:
        param_names = _valid_parameter_names(element.parameters)
        if param_names:
            return f"{len(param_names)} parameters"
        return f"{len(element.parameters)} parameters"

    if hasattr(element, "indexed_columns") and element.indexed_columns:
        return ";".join(element.indexed_columns)

    return ""


def format_sql_csv_dependencies(element: SQLElement) -> str:
    """Format dependencies for a single-line CSV field."""
    if not element.dependencies:
        return ""

    clean_deps = []
    for dep in element.dependencies:
        if dep and isinstance(dep, str):
            clean_dep = dep.replace("\n", "").replace("\r", "").strip()
            if clean_dep:
                clean_deps.append(clean_dep)
    return ";".join(clean_deps)


def _valid_parameter_names(parameters: Iterable[Any]) -> list[str]:
    names = []
    for param in parameters:
        if hasattr(param, "name") and param.name:
            if param.name.upper() not in SQL_PARAMETER_KEYWORDS:
                names.append(param.name)
    return names


def _format_compact_table_details(table: SQLTable) -> str:
    details = []
    if table.columns:
        details.append(f"{len(table.columns)} cols")
    pk_columns = table.get_primary_key_columns()
    if pk_columns:
        details.append(f"PK: {', '.join(pk_columns)}")
    return ", ".join(details) if details else "-"


def _format_compact_view_details(view: SQLView) -> str:
    if view.source_tables:
        return f"from {', '.join(view.source_tables)}"
    return "view"


def _format_compact_procedure_details(procedure: SQLProcedure) -> str:
    if procedure.parameters:
        return f"{len(procedure.parameters)} params"
    return "procedure"


def _format_compact_function_details(function: SQLFunction) -> str:
    details = []
    if function.parameters:
        details.append(f"{len(function.parameters)} params")
    if function.return_type:
        details.append(f"-> {function.return_type}")
    return ", ".join(details) if details else "function"


def _format_compact_trigger_details(trigger: SQLTrigger) -> str:
    details = []
    if trigger.trigger_timing and trigger.trigger_event:
        details.append(f"{trigger.trigger_timing} {trigger.trigger_event}")
    if trigger.table_name:
        details.append(f"on {trigger.table_name}")
    return ", ".join(details) if details else "trigger"


def _format_compact_index_details(index: SQLIndex) -> str:
    details = []
    if index.table_name:
        details.append(f"on {index.table_name}")
    if index.indexed_columns:
        details.append(f"({', '.join(index.indexed_columns)})")
    if index.is_unique:
        details.append("UNIQUE")
    return ", ".join(details) if details else "index"
