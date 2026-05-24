"""SQL metadata extractors used by SQLFormatterWrapper."""

from __future__ import annotations

import re


def extract_table_columns(raw_text: str, table_name: str) -> dict:
    """Extract column information from CREATE TABLE statement."""
    columns = []
    constraints = []
    lines = raw_text.split("\n")
    in_table_def = False

    for line in lines:
        line = line.strip()
        if "CREATE TABLE" in line.upper():
            in_table_def = True
            continue
        if in_table_def and line == ");":
            break
        if in_table_def and line and not line.startswith("--"):
            _append_column_name(columns, line)

    upper_sql = raw_text.upper()
    if "PRIMARY KEY" in upper_sql:
        constraints.append("PRIMARY KEY")
    if "FOREIGN KEY" in upper_sql:
        constraints.append("FOREIGN KEY")
    if "UNIQUE" in upper_sql:
        constraints.append("UNIQUE")
    if "NOT NULL" in upper_sql:
        constraints.append("NOT NULL")

    return {"columns": columns, "constraints": constraints}


def _append_column_name(columns: list[str], line: str) -> None:
    words = line.split()
    if not words or words[0].upper() in {
        "PRIMARY",
        "FOREIGN",
        "KEY",
        "CONSTRAINT",
        "INDEX",
        "UNIQUE",
    }:
        return

    col_name = words[0].rstrip(",")
    if col_name and col_name.upper() not in {"PRIMARY", "FOREIGN", "KEY"}:
        columns.append(col_name)


def extract_view_info(raw_text: str, view_name: str) -> dict:
    """Extract view information from CREATE VIEW statement."""
    from_matches = re.findall(r"FROM\s+(\w+)", raw_text, re.IGNORECASE)
    join_matches = re.findall(r"JOIN\s+(\w+)", raw_text, re.IGNORECASE)
    return {"source_tables": sorted(set(from_matches + join_matches)), "columns": []}


def extract_procedure_info(raw_text: str, proc_name: str) -> dict:
    """Extract procedure information from CREATE PROCEDURE statement."""
    return {
        "parameters": _extract_procedure_parameters(raw_text, proc_name),
        "dependencies": _extract_table_dependencies(raw_text),
    }


def _extract_procedure_parameters(raw_text: str, proc_name: str) -> list[str]:
    param_section_pattern = (
        rf"CREATE\s+PROCEDURE\s+{re.escape(proc_name)}\s*\(([^)]*)\)"
    )
    param_match = re.search(param_section_pattern, raw_text, re.IGNORECASE | re.DOTALL)
    if not param_match:
        return []

    param_text = param_match.group(1).strip()
    if not param_text:
        return []

    parameters = []
    for param in param_text.split(","):
        formatted = _format_procedure_parameter(param)
        if formatted:
            parameters.append(formatted)
    return parameters


def _format_procedure_parameter(param: str) -> str | None:
    param = param.strip()
    if not param:
        return None

    param_pattern = r"(IN|OUT|INOUT)?\s*(\w+)\s+(\w+(?:\([^)]+\))?)"
    match = re.match(param_pattern, param, re.IGNORECASE)
    if not match:
        return None

    direction = match.group(1) if match.group(1) else "IN"
    param_name = match.group(2)
    param_type = match.group(3)
    return f"{direction} {param_name} {param_type}"


def extract_function_info(raw_text: str, func_name: str) -> dict:
    """Extract function information from CREATE FUNCTION statement."""
    return {
        "parameters": _extract_function_parameters(raw_text),
        "return_type": _extract_function_return_type(raw_text),
        "dependencies": sorted(set(_extract_from_dependencies(raw_text))),
    }


def _extract_function_return_type(raw_text: str) -> str:
    return_match = re.search(r"RETURNS\s+(\w+(?:\([^)]+\))?)", raw_text, re.IGNORECASE)
    return return_match.group(1) if return_match else ""


def _extract_function_parameters(raw_text: str) -> list[str]:
    parameters = []
    matches = re.findall(r"(\w+)\s+(\w+(?:\([^)]+\))?)", raw_text, re.IGNORECASE)
    ignored_names = {
        "CREATE",
        "FUNCTION",
        "RETURNS",
        "READS",
        "SQL",
        "DATA",
        "DETERMINISTIC",
        "BEGIN",
        "END",
        "DECLARE",
        "SELECT",
        "FROM",
        "WHERE",
        "RETURN",
    }

    for param_name, param_type in matches:
        if param_name.upper() not in ignored_names:
            parameters.append(f"{param_name} {param_type}")
    return parameters


def extract_trigger_info(raw_text: str, trigger_name: str) -> dict:
    """Extract trigger information from CREATE TRIGGER statement."""
    timing = ""
    event = ""
    table_name = ""
    dependencies = []

    trigger_pattern = r"(BEFORE|AFTER)\s+(INSERT|UPDATE|DELETE)\s+ON\s+(\w+)"
    match = re.search(trigger_pattern, raw_text, re.IGNORECASE)
    if match:
        timing = match.group(1)
        event = match.group(2)
        table_name = match.group(3)
        dependencies.append(table_name)

    _extend_unique(dependencies, _extract_table_dependencies(raw_text))
    return {
        "timing": timing,
        "event": event,
        "table_name": table_name,
        "dependencies": dependencies,
    }


def extract_index_info(raw_text: str, index_name: str) -> dict:
    """Extract index information from CREATE INDEX statement."""
    table_name = ""
    columns = []
    is_unique = "UNIQUE" in raw_text.upper()

    match = re.search(r"ON\s+(\w+)\s*\(([^)]+)\)", raw_text, re.IGNORECASE)
    if match:
        table_name = match.group(1)
        columns = [col.strip() for col in match.group(2).split(",")]

    return {"table_name": table_name, "columns": columns, "is_unique": is_unique}


def _extract_table_dependencies(raw_text: str) -> list[str]:
    table_pattern = r"FROM\s+(\w+)|UPDATE\s+(\w+)|INSERT\s+INTO\s+(\w+)"
    dependencies = []
    for tbl_match in re.findall(table_pattern, raw_text, re.IGNORECASE):
        _extend_unique(dependencies, [table for table in tbl_match if table])
    return dependencies


def _extract_from_dependencies(raw_text: str) -> list[str]:
    return re.findall(r"FROM\s+(\w+)", raw_text, re.IGNORECASE)


def _extend_unique(items: list[str], candidates: list[str]) -> None:
    for candidate in candidates:
        if candidate and candidate not in items:
            items.append(candidate)
