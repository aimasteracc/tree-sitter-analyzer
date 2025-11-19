#!/usr/bin/env python3
"""
SQL-Specific Formatters

Provides SQL-specific output formatting to replace generic class-based format
with database-appropriate terminology and comprehensive element representation.
"""

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


class SQLFormatterBase:
    """Base class for SQL-specific formatters"""

    def format_elements(self, elements: list[SQLElement], file_path: str = "") -> str:
        """Format SQL elements with appropriate terminology"""
        if not elements:
            return self._format_empty_file(file_path)

        # Group elements by type
        grouped_elements = self.group_elements_by_type(elements)

        # Format based on specific formatter type
        return self._format_grouped_elements(grouped_elements, file_path)

    def group_elements_by_type(
        self, elements: list[SQLElement]
    ) -> dict[SQLElementType, list[SQLElement]]:
        """Group elements by SQL type"""
        grouped: dict[SQLElementType, list[SQLElement]] = {}
        for element in elements:
            element_type = element.sql_element_type
            if element_type not in grouped:
                grouped[element_type] = []
            grouped[element_type].append(element)
        return grouped

    def _format_empty_file(self, file_path: str) -> str:
        """Format empty SQL file"""
        filename = file_path.split("/")[-1] if file_path else "unknown.sql"
        return f"# {filename}\n\nNo SQL elements found."

    def _format_grouped_elements(
        self, grouped_elements: dict[SQLElementType, list[SQLElement]], file_path: str
    ) -> str:
        """Format grouped elements - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _format_grouped_elements")


class SQLFullFormatter(SQLFormatterBase):
    """Comprehensive SQL format with detailed metadata"""

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for SQL files."""
        if not analysis_result or not analysis_result.elements:
            return self._format_empty_file(
                analysis_result.file_path if analysis_result else ""
            )

        # Filter only SQL elements
        sql_elements = [
            e for e in analysis_result.elements if hasattr(e, "sql_element_type")
        ]

        if not sql_elements:
            return self._format_empty_file(analysis_result.file_path)

        return self.format_elements(sql_elements, analysis_result.file_path)

    def _format_grouped_elements(
        self, grouped_elements: dict[SQLElementType, list[SQLElement]], file_path: str
    ) -> str:
        """Format elements in full detail format"""
        filename = file_path.split("/")[-1] if file_path else "unknown.sql"
        output = [f"# {filename}", ""]

        # Overview table
        output.extend(self._format_overview_table(grouped_elements))
        output.append("")

        # Detailed sections for each element type
        type_order = [
            SQLElementType.TABLE,
            SQLElementType.VIEW,
            SQLElementType.PROCEDURE,
            SQLElementType.FUNCTION,
            SQLElementType.TRIGGER,
            SQLElementType.INDEX,
        ]

        for element_type in type_order:
            if element_type in grouped_elements:
                section = self._format_element_section(
                    element_type, grouped_elements[element_type]
                )
                if section:
                    output.extend(section)
                    output.append("")

        return "\n".join(output).rstrip() + "\n"

    def _format_overview_table(
        self, grouped_elements: dict[SQLElementType, list[SQLElement]]
    ) -> list[str]:
        """Create overview table with SQL terminology"""
        output = [
            "## Database Schema Overview",
            "| Element | Type | Lines | Columns/Parameters | Dependencies |",
            "|---------|------|-------|-------------------|--------------|",
        ]

        # Sort elements by line number for consistent output
        all_elements = []
        for elements in grouped_elements.values():
            all_elements.extend(elements)
        all_elements.sort(key=lambda x: x.start_line)

        for element in all_elements:
            line_range = f"{element.start_line}-{element.end_line}"

            # Format columns/parameters info
            if hasattr(element, "columns") and element.columns:
                details = f"{len(element.columns)} columns"
            elif hasattr(element, "parameters") and element.parameters:
                # Clean parameter names for display
                param_names = []
                for param in element.parameters:
                    if hasattr(param, "name") and param.name:
                        # Only include valid parameter names, skip SQL keywords
                        if param.name.upper() not in (
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
                        ):
                            param_names.append(param.name)
                if param_names:
                    details = f"({', '.join(param_names)})"
                else:
                    details = f"{len(element.parameters)} parameters"
            elif hasattr(element, "indexed_columns") and element.indexed_columns:
                col_info = f"({', '.join(element.indexed_columns)})"
                if hasattr(element, "table_name") and element.table_name:
                    col_info = f"{element.table_name}{col_info}"
                details = col_info
            elif hasattr(element, "source_tables") and element.source_tables:
                details = f"from {', '.join(element.source_tables)}"
            else:
                details = "-"

            # Format dependencies
            deps = ", ".join(element.dependencies) if element.dependencies else "-"

            output.append(
                f"| {element.name} | {element.sql_element_type.value} | {line_range} | {details} | {deps} |"
            )

        return output

    def _format_element_section(
        self, element_type: SQLElementType, elements: list[SQLElement]
    ) -> list[str]:
        """Format detailed section for specific element type"""
        if not elements:
            return []

        section_title = self._get_section_title(element_type)
        output = [f"## {section_title}"]

        for element in sorted(elements, key=lambda x: x.start_line):
            output.extend(self._format_element_details(element))
            output.append("")

        return output[:-1]  # Remove last empty line

    def _get_section_title(self, element_type: SQLElementType) -> str:
        """Get section title for element type"""
        titles = {
            SQLElementType.TABLE: "Tables",
            SQLElementType.VIEW: "Views",
            SQLElementType.PROCEDURE: "Procedures",
            SQLElementType.FUNCTION: "Functions",
            SQLElementType.TRIGGER: "Triggers",
            SQLElementType.INDEX: "Indexes",
        }
        return titles.get(element_type, element_type.value.title() + "s")

    def _format_element_details(self, element: SQLElement) -> list[str]:
        """Format detailed information for a single element"""
        output = [f"### {element.name} ({element.start_line}-{element.end_line})"]

        if isinstance(element, SQLTable):
            output.extend(self._format_table_details(element))
        elif isinstance(element, SQLView):
            output.extend(self._format_view_details(element))
        elif isinstance(element, SQLProcedure):
            output.extend(self._format_procedure_details(element))
        elif isinstance(element, SQLFunction):
            output.extend(self._format_function_details(element))
        elif isinstance(element, SQLTrigger):
            output.extend(self._format_trigger_details(element))
        elif isinstance(element, SQLIndex):
            output.extend(self._format_index_details(element))

        return output

    def _format_table_details(self, table: SQLTable) -> list[str]:
        """Format table-specific details"""
        output = []

        if table.columns:
            column_names = [col.name for col in table.columns]
            output.append(f"**Columns**: {', '.join(column_names)}")

            # Primary keys
            pk_columns = table.get_primary_key_columns()
            if pk_columns:
                output.append(f"**Primary Key**: {', '.join(pk_columns)}")

            # Foreign keys
            fk_columns = table.get_foreign_key_columns()
            if fk_columns:
                fk_details = []
                for col in table.columns:
                    if col.is_foreign_key and col.foreign_key_reference:
                        fk_details.append(f"{col.name} → {col.foreign_key_reference}")
                if fk_details:
                    output.append(f"**Foreign Keys**: {', '.join(fk_details)}")

        if table.constraints:
            constraint_types = [c.constraint_type for c in table.constraints]
            output.append(f"**Constraints**: {', '.join(set(constraint_types))}")

        return output

    def _format_view_details(self, view: SQLView) -> list[str]:
        """Format view-specific details"""
        output = []

        if view.source_tables:
            output.append(f"**Source Tables**: {', '.join(view.source_tables)}")

        if view.columns:
            column_names = [col.name for col in view.columns]
            output.append(f"**Columns**: {', '.join(column_names)}")

        return output

    def _format_procedure_details(self, procedure: SQLProcedure) -> list[str]:
        """Format procedure-specific details"""
        output = []

        if procedure.parameters:
            param_details = []
            for param in procedure.parameters:
                param_str = f"{param.name} {param.data_type}"
                if param.direction != "IN":
                    param_str = f"{param.direction} {param_str}"
                param_details.append(param_str)
            output.append(f"**Parameters**: {', '.join(param_details)}")

        if procedure.dependencies:
            output.append(f"**Dependencies**: {', '.join(procedure.dependencies)}")

        return output

    def _format_function_details(self, function: SQLFunction) -> list[str]:
        """Format function-specific details"""
        output = []

        if function.parameters:
            param_details = []
            for param in function.parameters:
                param_str = f"{param.name} {param.data_type}"
                if param.direction != "IN":
                    param_str = f"{param.direction} {param_str}"
                param_details.append(param_str)
            output.append(f"**Parameters**: {', '.join(param_details)}")

        if function.return_type:
            output.append(f"**Returns**: {function.return_type}")

        if function.dependencies:
            output.append(f"**Dependencies**: {', '.join(function.dependencies)}")

        return output

    def _format_trigger_details(self, trigger: SQLTrigger) -> list[str]:
        """Format trigger-specific details"""
        output = []

        if trigger.trigger_timing and trigger.trigger_event:
            output.append(
                f"**Event**: {trigger.trigger_timing} {trigger.trigger_event}"
            )

        if trigger.table_name:
            output.append(f"**Target Table**: {trigger.table_name}")

        if trigger.dependencies:
            output.append(f"**Dependencies**: {', '.join(trigger.dependencies)}")

        return output

    def _format_index_details(self, index: SQLIndex) -> list[str]:
        """Format index-specific details"""
        output = []

        if index.table_name:
            output.append(f"**Table**: {index.table_name}")

        if index.indexed_columns:
            output.append(f"**Columns**: {', '.join(index.indexed_columns)}")

        if index.is_unique:
            output.append("**Type**: Unique index")
        else:
            output.append("**Type**: Standard index")

        return output


class SQLCompactFormatter(SQLFormatterBase):
    """Compact SQL format for quick overview"""

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "compact"
    ) -> str:
        """Format AnalysisResult directly for SQL files."""
        if not analysis_result or not analysis_result.elements:
            return self._format_empty_file(
                analysis_result.file_path if analysis_result else ""
            )

        # Filter only SQL elements
        sql_elements = [
            e for e in analysis_result.elements if hasattr(e, "sql_element_type")
        ]

        if not sql_elements:
            return self._format_empty_file(analysis_result.file_path)

        return self.format_elements(sql_elements, analysis_result.file_path)

    def _format_grouped_elements(
        self, grouped_elements: dict[SQLElementType, list[SQLElement]], file_path: str
    ) -> str:
        """Format elements in compact table format"""
        filename = file_path.split("/")[-1] if file_path else "unknown.sql"
        output = [
            f"# {filename}",
            "",
            "| Element | Type | Lines | Details |",
            "|---------|------|-------|---------|",
        ]

        # Sort all elements by line number
        all_elements = []
        for elements in grouped_elements.values():
            all_elements.extend(elements)
        all_elements.sort(key=lambda x: x.start_line)

        for element in all_elements:
            line_range = f"{element.start_line}-{element.end_line}"
            details = self._format_compact_details(element)
            output.append(
                f"| {element.name} | {element.sql_element_type.value} | {line_range} | {details} |"
            )

        return "\n".join(output) + "\n"

    def _format_compact_details(self, element: SQLElement) -> str:
        """Format compact details for an element"""
        if isinstance(element, SQLTable):
            details = []
            if element.columns:
                details.append(f"{len(element.columns)} cols")
            pk_columns = element.get_primary_key_columns()
            if pk_columns:
                details.append(f"PK: {', '.join(pk_columns)}")
            return ", ".join(details) if details else "-"

        elif isinstance(element, SQLView):
            if element.source_tables:
                return f"from {', '.join(element.source_tables)}"
            return "view"

        elif isinstance(element, SQLProcedure):
            if element.parameters:
                return f"{len(element.parameters)} params"
            return "procedure"

        elif isinstance(element, SQLFunction):
            details = []
            if element.parameters:
                details.append(f"{len(element.parameters)} params")
            if element.return_type:
                details.append(f"-> {element.return_type}")
            return ", ".join(details) if details else "function"

        elif isinstance(element, SQLTrigger):
            details = []
            if element.trigger_timing and element.trigger_event:
                details.append(f"{element.trigger_timing} {element.trigger_event}")
            if element.table_name:
                details.append(f"on {element.table_name}")
            return ", ".join(details) if details else "trigger"

        elif isinstance(element, SQLIndex):
            details = []
            if element.table_name:
                details.append(f"on {element.table_name}")
            if element.indexed_columns:
                details.append(f"({', '.join(element.indexed_columns)})")
            if element.is_unique:
                details.append("UNIQUE")
            return ", ".join(details) if details else "index"

        return "-"


class SQLCSVFormatter(SQLFormatterBase):
    """CSV format for data processing"""

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "csv"
    ) -> str:
        """Format AnalysisResult directly for SQL files."""
        if not analysis_result or not analysis_result.elements:
            return "Element,Type,Lines,Columns_Parameters,Dependencies\n"

        # Filter only SQL elements
        sql_elements = [
            e for e in analysis_result.elements if hasattr(e, "sql_element_type")
        ]

        if not sql_elements:
            return "Element,Type,Lines,Columns_Parameters,Dependencies\n"

        return self.format_elements(sql_elements, analysis_result.file_path)

    def format_elements(self, elements: list[SQLElement], file_path: str = "") -> str:
        """Format SQL elements as CSV - override to always include header"""
        if not elements:
            # For CSV, always include header even with empty elements
            return "Element,Type,Lines,Columns_Parameters,Dependencies\n"

        # Group elements by type
        grouped_elements = self.group_elements_by_type(elements)

        # Format based on specific formatter type
        return self._format_grouped_elements(grouped_elements, file_path)

    def _format_grouped_elements(
        self, grouped_elements: dict[SQLElementType, list[SQLElement]], file_path: str
    ) -> str:
        """Format elements as CSV"""
        output = ["Element,Type,Lines,Columns_Parameters,Dependencies"]

        # Sort all elements by line number
        all_elements = []
        for elements in grouped_elements.values():
            all_elements.extend(elements)
        all_elements.sort(key=lambda x: x.start_line)

        for element in all_elements:
            line_range = f"{element.start_line}-{element.end_line}"

            # Format columns/parameters
            if hasattr(element, "columns") and element.columns:
                details = f"{len(element.columns)} columns"
            elif hasattr(element, "parameters") and element.parameters:
                # Clean parameter names for CSV display
                param_names = []
                for param in element.parameters:
                    if hasattr(param, "name") and param.name:
                        # Only include valid parameter names, skip SQL keywords
                        if param.name.upper() not in (
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
                        ):
                            param_names.append(param.name)
                if param_names:
                    details = f"{len(param_names)} parameters"
                else:
                    details = f"{len(element.parameters)} parameters"
            elif hasattr(element, "indexed_columns") and element.indexed_columns:
                details = f"{';'.join(element.indexed_columns)}"
            else:
                details = ""

            # Format dependencies - ensure no line breaks in CSV
            deps = ""
            if element.dependencies:
                # Clean dependencies and join with semicolon
                clean_deps = []
                for dep in element.dependencies:
                    if dep and isinstance(dep, str):
                        # Remove any line breaks or extra whitespace
                        clean_dep = dep.replace("\n", "").replace("\r", "").strip()
                        if clean_dep:
                            clean_deps.append(clean_dep)
                deps = ";".join(clean_deps)

            output.append(
                f"{element.name},{element.sql_element_type.value},{line_range},{details},{deps}"
            )

        return "\n".join(output) + "\n"
