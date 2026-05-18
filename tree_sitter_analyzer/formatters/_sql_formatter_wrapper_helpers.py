"""Conversion helpers for SQL formatter wrapper."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..constants import (
    ELEMENT_TYPE_SQL_FUNCTION,
    ELEMENT_TYPE_SQL_INDEX,
    ELEMENT_TYPE_SQL_PROCEDURE,
    ELEMENT_TYPE_SQL_TABLE,
    ELEMENT_TYPE_SQL_TRIGGER,
    ELEMENT_TYPE_SQL_VIEW,
    get_element_type,
)
from ..models import (
    SQLElement,
    SQLFunction,
    SQLIndex,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
)

InfoExtractor = Callable[[str, str], dict[str, Any]]
_LOGGER = logging.getLogger("tree_sitter_analyzer.formatters.sql_formatter_wrapper")


@dataclass(frozen=True)
class _AnalysisElementFields:
    name: str
    start_line: Any
    end_line: Any
    raw_text: str
    language: str


@dataclass(frozen=True)
class _DictElementFields:
    element_type: str
    name: Any
    start_line: Any
    end_line: Any
    raw_text: Any
    language: Any


def element_to_dict(element: Any) -> dict[str, Any]:
    """Convert element object to the dictionary shape expected by SQL conversion."""
    return {
        "name": getattr(element, "name", str(element)),
        "type": getattr(element, "type", getattr(element, "sql_type", "unknown")),
        "start_line": getattr(element, "start_line", 0),
        "end_line": getattr(element, "end_line", 0),
        "raw_text": getattr(element, "raw_text", ""),
        "language": getattr(element, "language", "sql"),
    }


def convert_analysis_result_to_sql_elements(
    analysis_result: Any,
    *,
    extract_table_columns: InfoExtractor,
    extract_view_info: InfoExtractor,
    extract_procedure_info: InfoExtractor,
    extract_function_info: InfoExtractor,
    extract_trigger_info: InfoExtractor,
    extract_index_info: InfoExtractor,
) -> list[SQLElement]:
    """Convert AnalysisResult elements to SQL elements with extracted metadata."""
    sql_elements = []
    for element in analysis_result.elements:
        sql_element = _convert_analysis_element(
            element,
            extract_table_columns=extract_table_columns,
            extract_view_info=extract_view_info,
            extract_procedure_info=extract_procedure_info,
            extract_function_info=extract_function_info,
            extract_trigger_info=extract_trigger_info,
            extract_index_info=extract_index_info,
        )
        if sql_element is not None:
            sql_elements.append(sql_element)
    return sql_elements


def _convert_analysis_element(
    element: Any,
    *,
    extract_table_columns: InfoExtractor,
    extract_view_info: InfoExtractor,
    extract_procedure_info: InfoExtractor,
    extract_function_info: InfoExtractor,
    extract_trigger_info: InfoExtractor,
    extract_index_info: InfoExtractor,
) -> SQLElement | None:
    if isinstance(element, SQLElement):
        return element

    fields = _analysis_fields(element)
    element_type = get_element_type(element)
    if element_type == ELEMENT_TYPE_SQL_TABLE:
        return _sql_table_from_analysis(fields, extract_table_columns)
    if element_type == ELEMENT_TYPE_SQL_VIEW:
        return _sql_view_from_analysis(fields, extract_view_info)
    if element_type == ELEMENT_TYPE_SQL_PROCEDURE:
        return _sql_procedure_from_analysis(fields, extract_procedure_info)
    if element_type == ELEMENT_TYPE_SQL_FUNCTION:
        return _sql_function_from_analysis(fields, extract_function_info)
    if element_type == ELEMENT_TYPE_SQL_TRIGGER:
        return _sql_trigger_from_analysis(fields, extract_trigger_info)
    if element_type == ELEMENT_TYPE_SQL_INDEX:
        return _sql_index_from_analysis(fields, extract_index_info)
    return None


def _analysis_fields(element: Any) -> _AnalysisElementFields:
    return _AnalysisElementFields(
        name=getattr(element, "name", "unknown"),
        start_line=getattr(element, "start_line", 0),
        end_line=getattr(element, "end_line", 0),
        raw_text=getattr(element, "raw_text", ""),
        language=getattr(element, "language", "sql"),
    )


def _sql_table_from_analysis(
    fields: _AnalysisElementFields, extract_info: InfoExtractor
) -> SQLTable:
    info = extract_info(fields.raw_text, fields.name)
    return SQLTable(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        columns=info.get("columns", []),
        constraints=info.get("constraints", []),
        dependencies=[],
    )


def _sql_view_from_analysis(
    fields: _AnalysisElementFields, extract_info: InfoExtractor
) -> SQLView:
    info = extract_info(fields.raw_text, fields.name)
    source_tables = info.get("source_tables", [])
    return SQLView(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        source_tables=source_tables,
        columns=info.get("columns", []),
        dependencies=source_tables,
    )


def _sql_procedure_from_analysis(
    fields: _AnalysisElementFields, extract_info: InfoExtractor
) -> SQLProcedure:
    info = extract_info(fields.raw_text, fields.name)
    return SQLProcedure(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        parameters=info.get("parameters", []),
        dependencies=info.get("dependencies", []),
    )


def _sql_function_from_analysis(
    fields: _AnalysisElementFields, extract_info: InfoExtractor
) -> SQLFunction:
    info = extract_info(fields.raw_text, fields.name)
    return SQLFunction(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        parameters=info.get("parameters", []),
        return_type=info.get("return_type", ""),
        dependencies=info.get("dependencies", []),
    )


def _sql_trigger_from_analysis(
    fields: _AnalysisElementFields, extract_info: InfoExtractor
) -> SQLTrigger:
    info = extract_info(fields.raw_text, fields.name)
    return SQLTrigger(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        trigger_timing=info.get("timing", ""),
        trigger_event=info.get("event", ""),
        table_name=info.get("table_name", ""),
        dependencies=info.get("dependencies", []),
    )


def _sql_index_from_analysis(
    fields: _AnalysisElementFields, extract_info: InfoExtractor
) -> SQLIndex:
    info = extract_info(fields.raw_text, fields.name)
    table_name = info.get("table_name", "")
    return SQLIndex(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        table_name=table_name,
        indexed_columns=info.get("columns", []),
        is_unique=info.get("is_unique", False),
        dependencies=[table_name] if table_name else [],
    )


def create_sql_element_from_dict(element_dict: dict[str, Any]) -> SQLElement | None:
    """Create a SQL element from dictionary data, preserving soft-failure behavior."""
    try:
        fields = _dict_fields(element_dict)
        factory = _DICT_FACTORIES.get(fields.element_type, _sql_table_from_dict)
        return factory(fields)
    except Exception as exc:
        _LOGGER.warning(f"Failed to create SQL element from dict: {exc}")
        return None


def _dict_fields(element_dict: dict[str, Any]) -> _DictElementFields:
    return _DictElementFields(
        element_type=element_dict.get("type", "").lower(),
        name=element_dict.get("name", "unknown"),
        start_line=element_dict.get("start_line", 0),
        end_line=element_dict.get("end_line", 0),
        raw_text=element_dict.get("raw_text", ""),
        language=element_dict.get("language", "sql"),
    )


def _sql_table_from_dict(fields: _DictElementFields) -> SQLTable:
    return SQLTable(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        columns=[],
        constraints=[],
        dependencies=[],
    )


def _sql_view_from_dict(fields: _DictElementFields) -> SQLView:
    return SQLView(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        source_tables=[],
        columns=[],
        dependencies=[],
    )


def _sql_procedure_from_dict(fields: _DictElementFields) -> SQLProcedure:
    return SQLProcedure(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        parameters=[],
        dependencies=[],
    )


def _sql_function_from_dict(fields: _DictElementFields) -> SQLFunction:
    return SQLFunction(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        parameters=[],
        return_type="",
        dependencies=[],
    )


def _sql_trigger_from_dict(fields: _DictElementFields) -> SQLTrigger:
    return SQLTrigger(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        trigger_timing="",
        trigger_event="",
        table_name="",
        dependencies=[],
    )


def _sql_index_from_dict(fields: _DictElementFields) -> SQLIndex:
    return SQLIndex(
        name=fields.name,
        start_line=fields.start_line,
        end_line=fields.end_line,
        raw_text=fields.raw_text,
        language=fields.language,
        table_name="",
        indexed_columns=[],
        is_unique=False,
        dependencies=[],
    )


_DICT_FACTORIES: dict[str, Callable[[_DictElementFields], SQLElement]] = {
    "table": _sql_table_from_dict,
    "create_table": _sql_table_from_dict,
    "view": _sql_view_from_dict,
    "create_view": _sql_view_from_dict,
    "procedure": _sql_procedure_from_dict,
    "create_procedure": _sql_procedure_from_dict,
    "function": _sql_function_from_dict,
    "create_function": _sql_function_from_dict,
    "trigger": _sql_trigger_from_dict,
    "create_trigger": _sql_trigger_from_dict,
    "index": _sql_index_from_dict,
    "create_index": _sql_index_from_dict,
}
