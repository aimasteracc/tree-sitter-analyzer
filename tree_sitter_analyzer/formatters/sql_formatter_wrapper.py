#!/usr/bin/env python3
"""
SQL Formatter Wrapper

Wraps SQL-specific formatters to conform to the BaseFormatter interface
for integration with the CLI and MCP tools.
"""

from typing import Any

from ..models import SQLElement
from ._sql_formatter_wrapper_extractors import (
    extract_function_info,
    extract_index_info,
    extract_procedure_info,
    extract_table_columns,
    extract_trigger_info,
    extract_view_info,
)
from ._sql_formatter_wrapper_helpers import (
    convert_analysis_result_to_sql_elements,
    create_sql_element_from_dict,
    element_to_dict,
)
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

    # Format data for output: format_table
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

    # Format data for output: format_analysis_result
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

    # Convert between formats: _convert_analysis_result_to_sql_elements
    def _convert_analysis_result_to_sql_elements(
        self, analysis_result: Any
    ) -> list[SQLElement]:
        """Convert AnalysisResult directly to SQL elements"""
        return convert_analysis_result_to_sql_elements(
            analysis_result,
            extract_table_columns=self._extract_table_columns,
            extract_view_info=self._extract_view_info,
            extract_procedure_info=self._extract_procedure_info,
            extract_function_info=self._extract_function_info,
            extract_trigger_info=self._extract_trigger_info,
            extract_index_info=self._extract_index_info,
        )

    # Convert between formats: _convert_to_sql_elements
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
        return element_to_dict(element)

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
        return create_sql_element_from_dict(element_dict)

    # Format data for output: format_elements
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

    # Format data for output: format_summary
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

    # Format data for output: format_structure
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

    # Format data for output: format_advanced
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

    # Extract elements from AST: _extract_table_columns
    def _extract_table_columns(self, raw_text: str, table_name: str) -> dict:
        """Extract column information from CREATE TABLE statement"""
        return extract_table_columns(raw_text, table_name)

    # Extract elements from AST: _extract_view_info
    def _extract_view_info(self, raw_text: str, view_name: str) -> dict:
        """Extract view information from CREATE VIEW statement"""
        return extract_view_info(raw_text, view_name)

    # Extract elements from AST: _extract_procedure_info
    def _extract_procedure_info(self, raw_text: str, proc_name: str) -> dict:
        """Extract procedure information from CREATE PROCEDURE statement"""
        return extract_procedure_info(raw_text, proc_name)

    # Extract elements from AST: _extract_function_info
    def _extract_function_info(self, raw_text: str, func_name: str) -> dict:
        """Extract function information from CREATE FUNCTION statement"""
        return extract_function_info(raw_text, func_name)

    # Extract elements from AST: _extract_trigger_info
    def _extract_trigger_info(self, raw_text: str, trigger_name: str) -> dict:
        """Extract trigger information from CREATE TRIGGER statement"""
        return extract_trigger_info(raw_text, trigger_name)

    # Extract elements from AST: _extract_index_info
    def _extract_index_info(self, raw_text: str, index_name: str) -> dict:
        """Extract index information from CREATE INDEX statement"""
        return extract_index_info(raw_text, index_name)
