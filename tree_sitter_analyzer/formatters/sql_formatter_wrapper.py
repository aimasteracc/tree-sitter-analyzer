#!/usr/bin/env python3
"""
SQL Formatter Wrapper

Wraps SQL-specific formatters to conform to the BaseFormatter interface
for integration with the CLI and MCP tools.
"""

from typing import Any

from ..models import SQLElement
from .base_formatter import BaseFormatter
from .sql_formatters import SQLCompactFormatter, SQLCSVFormatter, SQLFullFormatter


class SQLFormatterWrapper(BaseFormatter):
    """
    Wrapper for SQL-specific formatters to conform to BaseFormatter interface.

    This class bridges the gap between the generic BaseFormatter interface
    and the SQL-specific formatters, enabling seamless integration with
    the existing CLI and MCP infrastructure.
    """

    def __init__(self) -> None:
        """Initialize the SQL formatter wrapper."""
        super().__init__()
        self._formatters = {
            "full": SQLFullFormatter(),
            "compact": SQLCompactFormatter(),
            "csv": SQLCSVFormatter(),
        }

    def format_table(self, data: dict[str, Any], table_type: str = "full") -> str:
        """
        Format analysis data as table using SQL-specific formatters.

        Args:
            data: Analysis data containing SQL elements
            table_type: Type of table format (full, compact, csv)

        Returns:
            Formatted table string

        Raises:
            ValueError: If table_type is not supported
        """
        if table_type not in self._formatters:
            raise ValueError(
                f"Unsupported table type: {table_type}. Supported types: {list(self._formatters.keys())}"
            )

        # Convert generic analysis data to SQL elements
        sql_elements = self._convert_to_sql_elements(data)

        # Get the appropriate formatter
        formatter = self._formatters[table_type]

        # Format using SQL-specific formatter
        file_path = data.get("file_path", "unknown.sql")
        return formatter.format_elements(sql_elements, file_path)

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for SQL files - prevents degradation"""
        # Convert AnalysisResult to SQL elements directly
        sql_elements = self._convert_analysis_result_to_sql_elements(analysis_result)

        # Get the appropriate formatter
        if table_type not in self._formatters:
            table_type = "full"  # Default fallback

        formatter = self._formatters[table_type]
        return formatter.format_elements(sql_elements, analysis_result.file_path)

    def _convert_analysis_result_to_sql_elements(
        self, analysis_result: Any
    ) -> list[SQLElement]:
        """Convert AnalysisResult directly to SQL elements"""
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
            SQLFunction,
            SQLIndex,
            SQLProcedure,
            SQLTable,
            SQLTrigger,
            SQLView,
        )

        sql_elements = []

        for element in analysis_result.elements:
            # Check if element is already a SQL element
            if isinstance(element, SQLElement):
                sql_elements.append(element)
                continue

            element_type = get_element_type(element)
            name = getattr(element, "name", "unknown")
            start_line = getattr(element, "start_line", 0)
            end_line = getattr(element, "end_line", 0)
            raw_text = getattr(element, "raw_text", "")
            language = getattr(element, "language", "sql")

            # Create appropriate SQL element based on type with enhanced information extraction
            sql_element: SQLElement
            if element_type == ELEMENT_TYPE_SQL_TABLE:
                # Extract table information from raw_text
                columns_info = self._extract_table_columns(raw_text, name)
                sql_element = SQLTable(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    columns=columns_info.get("columns", []),
                    constraints=columns_info.get("constraints", []),
                    dependencies=getattr(element, "dependencies", []),
                )
            elif element_type == ELEMENT_TYPE_SQL_VIEW:
                # Extract view information from raw_text
                view_info = self._extract_view_info(raw_text, name)
                sql_element = SQLView(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    source_tables=view_info.get("source_tables", []),
                    columns=view_info.get("columns", []),
                    dependencies=view_info.get("source_tables", []),
                )
            elif element_type == ELEMENT_TYPE_SQL_PROCEDURE:
                # Extract procedure information from raw_text
                proc_info = self._extract_procedure_info(raw_text, name)
                sql_element = SQLProcedure(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    parameters=proc_info.get("parameters", []),
                    dependencies=proc_info.get("dependencies", []),
                )
            elif element_type == ELEMENT_TYPE_SQL_FUNCTION:
                # Extract function information from raw_text
                func_info = self._extract_function_info(raw_text, name)
                sql_element = SQLFunction(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    parameters=func_info.get("parameters", []),
                    return_type=func_info.get("return_type", ""),
                    dependencies=func_info.get("dependencies", []),
                )
            elif element_type == ELEMENT_TYPE_SQL_TRIGGER:
                # Extract trigger information from raw_text
                trigger_info = self._extract_trigger_info(raw_text, name)
                sql_element = SQLTrigger(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    trigger_timing=trigger_info.get("timing", ""),
                    trigger_event=trigger_info.get("event", ""),
                    table_name=trigger_info.get("table_name", ""),
                    dependencies=trigger_info.get("dependencies", []),
                )
            elif element_type == ELEMENT_TYPE_SQL_INDEX:
                # Extract index information from raw_text
                index_info = self._extract_index_info(raw_text, name)
                sql_element = SQLIndex(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    table_name=index_info.get("table_name", ""),
                    indexed_columns=index_info.get("columns", []),
                    is_unique=index_info.get("is_unique", False),
                    dependencies=(
                        [index_info.get("table_name", "")]
                        if index_info.get("table_name")
                        else []
                    ),
                )
            else:
                # Skip non-SQL elements
                continue

            sql_elements.append(sql_element)

        return sql_elements

    def _convert_to_sql_elements(self, data: dict[str, Any]) -> list[SQLElement]:
        """
        Convert generic analysis data to SQL elements.

        Args:
            data: Analysis data from the analysis engine

        Returns:
            List of SQL elements
        """
        sql_elements = []
        # Check both 'elements' and 'methods' for SQL elements
        elements = data.get("elements", [])
        methods = data.get("methods", [])

        # Combine elements and methods for processing
        all_elements = elements + methods

        for element in all_elements:
            # Check if element is already a SQL element
            if isinstance(element, SQLElement):
                sql_elements.append(element)
                continue

            # For non-SQL elements, convert them but preserve any existing metadata
            element_dict = (
                element if isinstance(element, dict) else self._element_to_dict(element)
            )
            sql_element = self._create_sql_element_from_dict(element_dict)

            if sql_element:
                sql_elements.append(sql_element)

        return sql_elements

    def _element_to_dict(self, element: Any) -> dict[str, Any]:
        """
        Convert element object to dictionary.

        Args:
            element: Element object from analysis

        Returns:
            Dictionary representation of element
        """
        return {
            "name": getattr(element, "name", str(element)),
            "type": getattr(element, "type", getattr(element, "sql_type", "unknown")),
            "start_line": getattr(element, "start_line", 0),
            "end_line": getattr(element, "end_line", 0),
            "raw_text": getattr(element, "raw_text", ""),
            "language": getattr(element, "language", "sql"),
        }

    def _create_sql_element_from_dict(
        self, element_dict: dict[str, Any]
    ) -> SQLElement | None:
        """
        Create SQL element from dictionary data.

        Args:
            element_dict: Dictionary containing element data

        Returns:
            SQL element or None if conversion fails
        """
        try:
            from ..models import (
                SQLFunction,
                SQLIndex,
                SQLProcedure,
                SQLTable,
                SQLTrigger,
                SQLView,
            )

            element_type = element_dict.get("type", "").lower()
            name = element_dict.get("name", "unknown")
            start_line = element_dict.get("start_line", 0)
            end_line = element_dict.get("end_line", 0)
            raw_text = element_dict.get("raw_text", "")
            language = element_dict.get("language", "sql")

            # Create appropriate SQL element based on type
            if element_type in ["table", "create_table"]:
                return SQLTable(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    columns=[],  # Will be populated by enhanced extraction
                    constraints=[],
                    dependencies=[],
                )
            elif element_type in ["view", "create_view"]:
                return SQLView(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    source_tables=[],
                    columns=[],
                    dependencies=[],
                )
            elif element_type in ["procedure", "create_procedure"]:
                return SQLProcedure(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    parameters=[],
                    dependencies=[],
                )
            elif element_type in ["function", "create_function"]:
                return SQLFunction(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    parameters=[],
                    return_type="",
                    dependencies=[],
                )
            elif element_type in ["trigger", "create_trigger"]:
                return SQLTrigger(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    trigger_timing="",
                    trigger_event="",
                    table_name="",
                    dependencies=[],
                )
            elif element_type in ["index", "create_index"]:
                return SQLIndex(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    table_name="",
                    indexed_columns=[],
                    is_unique=False,
                    dependencies=[],
                )
            else:
                # Create a generic SQL element for unknown types
                return SQLTable(  # Use SQLTable as fallback
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language=language,
                    columns=[],
                    constraints=[],
                    dependencies=[],
                )

        except Exception as e:
            # Log error but don't fail the entire formatting process
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to create SQL element from dict: {e}")
            return None

    def format_elements(self, elements: list[Any], format_type: str = "full") -> str:
        """
        Format elements using SQL-specific formatters.

        Args:
            elements: List of elements to format
            format_type: Format type (full, compact, csv)

        Returns:
            Formatted string
        """
        # Convert to SQL elements if needed
        sql_elements = []
        for element in elements:
            if isinstance(element, SQLElement):
                sql_elements.append(element)
            else:
                element_dict = (
                    element
                    if isinstance(element, dict)
                    else self._element_to_dict(element)
                )
                sql_element = self._create_sql_element_from_dict(element_dict)
                if sql_element:
                    sql_elements.append(sql_element)

        # Get the appropriate formatter
        if format_type not in self._formatters:
            format_type = "full"  # Default fallback

        formatter = self._formatters[format_type]
        return formatter.format_elements(sql_elements, "analysis.sql")

    def supports_language(self, language: str) -> bool:
        """
        Check if this formatter supports the given language.

        Args:
            language: Programming language name

        Returns:
            True if language is supported
        """
        return language.lower() == "sql"

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """
        Format summary output for SQL analysis.

        Args:
            analysis_result: Analysis result data

        Returns:
            Formatted summary string
        """
        # Convert to SQL elements and use compact formatter for summary
        return self.format_table(analysis_result, "compact")

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """
        Format structure analysis output for SQL.

        Args:
            analysis_result: Analysis result data

        Returns:
            Formatted structure string
        """
        # Use full formatter for detailed structure
        return self.format_table(analysis_result, "full")

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """
        Format advanced analysis output for SQL.

        Args:
            analysis_result: Analysis result data
            output_format: Output format (json, table, etc.)

        Returns:
            Formatted advanced analysis string
        """
        if output_format == "json":
            import json

            return json.dumps(analysis_result, indent=2, ensure_ascii=False)
        else:
            # Default to full table format for other formats
            return self.format_table(analysis_result, "full")

    def _extract_table_columns(self, raw_text: str, table_name: str) -> dict:
        """Extract column information from CREATE TABLE statement"""

        # Enhanced column extraction for better accuracy
        columns = []
        constraints = []

        # Extract column definitions more precisely
        # Look for lines that define columns (not keywords)
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
                # Extract column name (first word that's not a keyword)
                words = line.split()
                if words and words[0].upper() not in [
                    "PRIMARY",
                    "FOREIGN",
                    "KEY",
                    "CONSTRAINT",
                    "INDEX",
                    "UNIQUE",
                ]:
                    col_name = words[0].rstrip(",")
                    if col_name and col_name.upper() not in [
                        "PRIMARY",
                        "FOREIGN",
                        "KEY",
                    ]:
                        columns.append(col_name)

        # Extract constraints
        if "PRIMARY KEY" in raw_text.upper():
            constraints.append("PRIMARY KEY")
        if "FOREIGN KEY" in raw_text.upper():
            constraints.append("FOREIGN KEY")
        if "UNIQUE" in raw_text.upper():
            constraints.append("UNIQUE")
        if "NOT NULL" in raw_text.upper():
            constraints.append("NOT NULL")

        return {"columns": columns, "constraints": constraints}

    def _extract_view_info(self, raw_text: str, view_name: str) -> dict:
        """Extract view information from CREATE VIEW statement"""
        import re

        source_tables = []

        # Extract table names from FROM and JOIN clauses
        from_pattern = r"FROM\s+(\w+)"
        join_pattern = r"JOIN\s+(\w+)"

        from_matches = re.findall(from_pattern, raw_text, re.IGNORECASE)
        join_matches = re.findall(join_pattern, raw_text, re.IGNORECASE)

        source_tables.extend(from_matches)
        source_tables.extend(join_matches)

        return {"source_tables": sorted(set(source_tables)), "columns": []}

    def _extract_procedure_info(self, raw_text: str, proc_name: str) -> dict:
        """Extract procedure information from CREATE PROCEDURE statement"""
        import re

        parameters = []
        dependencies = []

        # Extract parameters from procedure definition more precisely
        # Look for the parameter list in parentheses after procedure name
        param_section_pattern = (
            rf"CREATE\s+PROCEDURE\s+{re.escape(proc_name)}\s*\(([^)]*)\)"
        )
        param_match = re.search(
            param_section_pattern, raw_text, re.IGNORECASE | re.DOTALL
        )

        if param_match:
            param_text = param_match.group(1).strip()
            if param_text:
                # Split by comma and process each parameter
                param_parts = param_text.split(",")
                for param in param_parts:
                    param = param.strip()
                    if param:
                        # Extract direction, name, and type
                        param_pattern = r"(IN|OUT|INOUT)?\s*(\w+)\s+(\w+(?:\([^)]+\))?)"
                        match = re.match(param_pattern, param, re.IGNORECASE)
                        if match:
                            direction = match.group(1) if match.group(1) else "IN"
                            param_name = match.group(2)
                            param_type = match.group(3)
                            parameters.append(f"{direction} {param_name} {param_type}")

        # Extract table dependencies
        table_pattern = r"FROM\s+(\w+)|UPDATE\s+(\w+)|INSERT\s+INTO\s+(\w+)"
        table_matches = re.findall(table_pattern, raw_text, re.IGNORECASE)

        for tbl_match in table_matches:
            for table in tbl_match:
                if table and table not in dependencies:
                    dependencies.append(table)

        return {"parameters": parameters, "dependencies": dependencies}

    def _extract_function_info(self, raw_text: str, func_name: str) -> dict:
        """Extract function information from CREATE FUNCTION statement"""
        import re

        parameters = []
        return_type = ""
        dependencies = []

        # Extract return type
        return_pattern = r"RETURNS\s+(\w+(?:\([^)]+\))?)"
        return_match = re.search(return_pattern, raw_text, re.IGNORECASE)
        if return_match:
            return_type = return_match.group(1)

        # Extract parameters
        param_pattern = r"(\w+)\s+(\w+(?:\([^)]+\))?)"
        matches = re.findall(param_pattern, raw_text, re.IGNORECASE)

        for match in matches:
            param_name = match[0]
            param_type = match[1]

            if param_name.upper() not in [
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
            ]:
                parameters.append(f"{param_name} {param_type}")

        # Extract table dependencies
        table_pattern = r"FROM\s+(\w+)"
        table_matches = re.findall(table_pattern, raw_text, re.IGNORECASE)
        dependencies.extend(table_matches)

        return {
            "parameters": parameters,
            "return_type": return_type,
            "dependencies": sorted(set(dependencies)),
        }

    def _extract_trigger_info(self, raw_text: str, trigger_name: str) -> dict:
        """Extract trigger information from CREATE TRIGGER statement"""
        import re

        timing = ""
        event = ""
        table_name = ""
        dependencies = []

        # Extract trigger timing and event
        trigger_pattern = r"(BEFORE|AFTER)\s+(INSERT|UPDATE|DELETE)\s+ON\s+(\w+)"
        match = re.search(trigger_pattern, raw_text, re.IGNORECASE)

        if match:
            timing = match.group(1)
            event = match.group(2)
            table_name = match.group(3)
            dependencies.append(table_name)

        # Extract additional table dependencies
        table_pattern = r"FROM\s+(\w+)|UPDATE\s+(\w+)|INSERT\s+INTO\s+(\w+)"
        table_matches = re.findall(table_pattern, raw_text, re.IGNORECASE)

        for tbl_match in table_matches:
            for table in tbl_match:
                if table and table not in dependencies:
                    dependencies.append(table)

        return {
            "timing": timing,
            "event": event,
            "table_name": table_name,
            "dependencies": dependencies,
        }

    def _extract_index_info(self, raw_text: str, index_name: str) -> dict:
        """Extract index information from CREATE INDEX statement"""
        import re

        table_name = ""
        columns = []
        is_unique = False

        # Check if it's a unique index
        if "UNIQUE" in raw_text.upper():
            is_unique = True

        # Extract table name and columns
        index_pattern = r"ON\s+(\w+)\s*\(([^)]+)\)"
        match = re.search(index_pattern, raw_text, re.IGNORECASE)

        if match:
            table_name = match.group(1)
            columns_str = match.group(2)
            columns = [col.strip() for col in columns_str.split(",")]

        return {"table_name": table_name, "columns": columns, "is_unique": is_unique}
