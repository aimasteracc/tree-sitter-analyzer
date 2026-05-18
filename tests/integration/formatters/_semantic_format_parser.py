"""Parsers for semantic formatter validation."""

import csv
import io

from ._enhanced_assertion_models import FormatElement


def parse_format_elements(output: str, format_type: str) -> list[FormatElement]:
    """Parse format output into structured elements."""
    if format_type == "csv":
        return parse_csv_elements(output)
    return parse_markdown_elements(output)


def parse_csv_elements(output: str) -> list[FormatElement]:
    """Parse CSV format elements."""
    elements = []

    try:
        reader = csv.DictReader(io.StringIO(output))
        for line_num, row in enumerate(reader, start=2):
            elements.append(_csv_row_element(row, line_num))
    except Exception as exc:
        elements.append(
            FormatElement(
                element_type="error",
                name="csv_parse_error",
                content=str(exc),
                line_number=1,
                column_number=1,
                attributes={},
            )
        )

    return elements


def _csv_row_element(row: dict[str, str | None], line_num: int) -> FormatElement:
    return FormatElement(
        element_type=row.get("Type", "") or "",
        name=row.get("Name", "") or "",
        content=str(row),
        line_number=line_num,
        column_number=1,
        attributes={
            "return_type": row.get("ReturnType", "") or "",
            "parameters": row.get("Parameters", "") or "",
            "access": row.get("Access", "") or "",
            "static": row.get("Static", "") or "",
            "final": row.get("Final", "") or "",
            "line": row.get("Line", "") or "",
        },
    )


def parse_markdown_elements(output: str) -> list[FormatElement]:
    """Parse Markdown format elements."""
    elements: list[FormatElement] = []
    current_section = None
    current_table: list[FormatElement] = []
    in_table = False

    for line_num, raw_line in enumerate(output.split("\n"), start=1):
        line = raw_line.strip()

        if line.startswith("##"):
            current_section = line.replace("#", "").strip()
            elements.append(_markdown_section_element(current_section, line, line_num))
            current_table = []
            in_table = False
            continue

        if _is_markdown_table_row(line):
            if not in_table:
                current_table = []
                in_table = True
            table_row = _markdown_table_row(
                line, line_num, current_section, current_table
            )
            if table_row:
                elements.append(table_row)
                current_table.append(table_row)
            continue

        if line.startswith("|--"):
            continue

        if in_table and not line:
            in_table = False

    return elements


def _markdown_section_element(
    current_section: str, line: str, line_num: int
) -> FormatElement:
    return FormatElement(
        element_type="section",
        name=current_section,
        content=line,
        line_number=line_num,
        column_number=1,
        attributes={"section_type": current_section},
    )


def _is_markdown_table_row(line: str) -> bool:
    return "|" in line and not line.startswith("|--")


def _markdown_table_row(
    line: str,
    line_num: int,
    current_section: str | None,
    current_table: list[FormatElement],
) -> FormatElement | None:
    cells = [cell.strip() for cell in line.split("|") if cell.strip()]
    if not cells:
        return None
    return FormatElement(
        element_type="table_row",
        name=cells[0] if cells else "",
        content=line,
        line_number=line_num,
        column_number=1,
        attributes={
            "cells": cells,
            "section": current_section,
            "table_index": len(current_table),
        },
    )
