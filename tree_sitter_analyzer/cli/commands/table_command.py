#!/usr/bin/env python3
"""
Table Command

Handles table format output generation.
"""

import sys
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_SQL_FUNCTION,
    ELEMENT_TYPE_SQL_INDEX,
    ELEMENT_TYPE_SQL_PROCEDURE,
    ELEMENT_TYPE_SQL_TABLE,
    ELEMENT_TYPE_SQL_TRIGGER,
    ELEMENT_TYPE_SQL_VIEW,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
)
from ...output_manager import output_error
from .base_command import BaseCommand


class TableCommand(BaseCommand):
    """Command for generating table format output."""

    def __init__(self, args: Any) -> None:
        """Initialize the table command."""
        super().__init__(args)

    async def execute_async(self, language: str) -> int:
        """Execute table format generation."""
        try:
            # Perform standard analysis
            analysis_result = await self.analyze_file(language)
            if not analysis_result:
                return 1

            table_type = getattr(self.args, "table", "full")

            # Handle TOON format separately
            if table_type == "toon":
                formatted_output = self._format_as_toon(analysis_result)
            else:
                # Get appropriate formatter using unified FormatterRegistry
                from ...formatters.formatter_registry import FormatterRegistry

                formatter = FormatterRegistry.get_formatter_for_language(
                    analysis_result.language,
                    table_type,
                    include_javadoc=getattr(self.args, "include_javadoc", False),
                )

                # Check if formatter has a method to handle AnalysisResult directly
                if hasattr(formatter, "format_analysis_result"):
                    formatted_output = formatter.format_analysis_result(
                        analysis_result, table_type
                    )
                else:
                    # Convert to structure format that the formatter expects
                    formatted_data = self._convert_to_structure_format(
                        analysis_result, language
                    )
                    formatted_output = formatter.format_structure(formatted_data)

            self._output_table(formatted_output)
            return 0

        except Exception as e:
            output_error(f"An error occurred during table format analysis: {e}")
            return 1

    def _format_as_toon(self, analysis_result: Any) -> str:
        """Format analysis result as TOON."""
        from ...formatters.toon_formatter import ToonFormatter

        use_tabs = getattr(self.args, "toon_use_tabs", False)
        formatter = ToonFormatter(use_tabs=use_tabs)

        # Convert to structure format for TOON
        structure_data = self._convert_to_toon_format(analysis_result)
        return formatter.format(structure_data)

    def _convert_to_toon_format(self, analysis_result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to TOON-friendly format with position info."""
        classes = []
        methods = []
        fields = []
        imports = []

        for element in analysis_result.elements:
            element_type = get_element_type(element)

            if element_type == ELEMENT_TYPE_CLASS:
                classes.append(
                    {
                        "name": getattr(element, "name", "unknown"),
                        "visibility": getattr(element, "visibility", "public"),
                        "line_range": (
                            getattr(element, "start_line", 0),
                            getattr(element, "end_line", 0),
                        ),
                    }
                )
            elif element_type == ELEMENT_TYPE_FUNCTION:
                methods.append(
                    {
                        "name": getattr(element, "name", "unknown"),
                        "visibility": getattr(element, "visibility", "public"),
                        "line_range": (
                            getattr(element, "start_line", 0),
                            getattr(element, "end_line", 0),
                        ),
                    }
                )
            elif element_type == ELEMENT_TYPE_VARIABLE:
                fields.append(
                    {
                        "name": getattr(element, "name", "unknown"),
                        "type": getattr(element, "type_annotation", ""),
                        "line_range": (
                            getattr(element, "start_line", 0),
                            getattr(element, "end_line", 0),
                        ),
                    }
                )
            elif element_type == ELEMENT_TYPE_IMPORT:
                imports.append(
                    {
                        "name": getattr(element, "name", "unknown"),
                        "is_static": getattr(element, "is_static", False),
                        "is_wildcard": getattr(element, "is_wildcard", False),
                        "statement": getattr(element, "import_statement", ""),
                        "line_range": (
                            getattr(element, "start_line", 0),
                            getattr(element, "end_line", 0),
                        ),
                    }
                )

        # Get package info
        packages = [
            e
            for e in analysis_result.elements
            if get_element_type(e) == ELEMENT_TYPE_PACKAGE
        ]
        package_info = None
        if packages:
            pkg = packages[0]
            package_info = {
                "name": getattr(pkg, "name", ""),
                "line_range": (
                    getattr(pkg, "start_line", 0),
                    getattr(pkg, "end_line", 0),
                ),
            }

        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "package": package_info,
            "classes": classes,
            "methods": methods,
            "fields": fields,
            "imports": imports,
            "statistics": {
                "class_count": len(classes),
                "method_count": len(methods),
                "field_count": len(fields),
                "import_count": len(imports),
                "total_lines": analysis_result.line_count,
            },
        }

    def _convert_to_formatter_format(self, analysis_result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to format expected by formatters."""
        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "elements": [
                {
                    "name": getattr(element, "name", str(element)),
                    "type": get_element_type(element),
                    "start_line": getattr(element, "start_line", 0),
                    "end_line": getattr(element, "end_line", 0),
                    "text": getattr(element, "text", ""),
                    "level": getattr(element, "level", 1),
                    "url": getattr(element, "url", ""),
                    "alt": getattr(element, "alt", ""),
                    "language": getattr(element, "language", ""),
                    "line_count": getattr(element, "line_count", 0),
                    "list_type": getattr(element, "list_type", ""),
                    "item_count": getattr(element, "item_count", 0),
                    "column_count": getattr(element, "column_count", 0),
                    "row_count": getattr(element, "row_count", 0),
                    "line_range": {
                        "start": getattr(element, "start_line", 0),
                        "end": getattr(element, "end_line", 0),
                    },
                }
                for element in analysis_result.elements
            ],
            "analysis_metadata": {
                "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
                "language": analysis_result.language,
                "file_path": analysis_result.file_path,
                "analyzer_version": "2.0.0",
            },
        }

    def _get_default_package_name(self, language: str) -> str:
        """
        Get default package name for language.

        Only Java-like languages have package concept.
        Other languages (JS, TS, Python) don't need package prefix.

        Args:
            language: Programming language name

        Returns:
            Default package name ("unknown" for Java-like, "" for others)
        """
        # Languages with package/namespace concept
        PACKAGED_LANGUAGES = {"java", "kotlin", "scala", "csharp", "cpp", "c++"}

        if language.lower() in PACKAGED_LANGUAGES:
            return "unknown"

        return ""  # No package for JS, TS, Python, etc.

    def _convert_to_structure_format(
        self, analysis_result: Any, language: str
    ) -> dict[str, Any]:
        """Convert AnalysisResult to the format expected by table formatter."""
        classes = []
        methods = []
        fields = []
        imports = []

        # Try to get package from analysis_result.package attribute first
        package_obj = getattr(analysis_result, "package", None)
        if package_obj and hasattr(package_obj, "name"):
            package_name = str(package_obj.name)
        else:
            # Fall back to default or scanning elements
            package_name = self._get_default_package_name(language)

        # Process each element
        for i, element in enumerate(analysis_result.elements):
            try:
                element_type = get_element_type(element)
                element_name = getattr(element, "name", None)

                if element_type == ELEMENT_TYPE_PACKAGE:
                    package_name = str(element_name)
                elif element_type == ELEMENT_TYPE_CLASS:
                    classes.append(self._convert_class_element(element, i, language))
                elif element_type == ELEMENT_TYPE_FUNCTION:
                    methods.append(self._convert_function_element(element, language))
                elif element_type == ELEMENT_TYPE_VARIABLE:
                    fields.append(self._convert_variable_element(element, language))
                elif element_type == ELEMENT_TYPE_IMPORT:
                    imports.append(self._convert_import_element(element))
                # SQL element types
                elif element_type in [
                    ELEMENT_TYPE_SQL_TABLE,
                    ELEMENT_TYPE_SQL_VIEW,
                    ELEMENT_TYPE_SQL_PROCEDURE,
                    ELEMENT_TYPE_SQL_FUNCTION,
                    ELEMENT_TYPE_SQL_TRIGGER,
                    ELEMENT_TYPE_SQL_INDEX,
                ]:
                    methods.append(self._convert_sql_element(element, language))

            except Exception as element_error:
                output_error(f"ERROR: Element {i} processing failed: {element_error}")
                continue

        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "package": {"name": package_name},
            "classes": classes,
            "methods": methods,
            "fields": fields,
            "imports": imports,
            "statistics": {
                "method_count": len(methods),
                "field_count": len(fields),
                "class_count": len(classes),
                "import_count": len(imports),
            },
        }

    def _convert_class_element(
        self, element: Any, index: int, language: str
    ) -> dict[str, Any]:
        """Convert class element to table format."""
        element_name = getattr(element, "name", None)
        final_name = element_name if element_name else f"UnknownClass_{index}"

        # Get class type from element (interface, enum, or class)
        class_type = getattr(element, "class_type", "class")

        # Get visibility from element with language-specific default
        # Java and C++ have package-private/private default, others have public default
        default_visibility = "package" if language in ["java", "cpp", "c"] else "public"
        visibility = getattr(element, "visibility", default_visibility)

        return {
            "name": final_name,
            "type": class_type,
            "visibility": visibility,
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
        }

    def _convert_function_element(self, element: Any, language: str) -> dict[str, Any]:
        """Convert function element to table format."""
        # Process parameters based on language
        params = getattr(element, "parameters", [])
        processed_params = self._process_parameters(params, language)

        # Get visibility
        visibility = self._get_element_visibility(element)

        # Get JavaDoc if enabled
        include_javadoc = getattr(self.args, "include_javadoc", False)
        javadoc = getattr(element, "docstring", "") or "" if include_javadoc else ""

        return {
            "name": getattr(element, "name", str(element)),
            "visibility": visibility,
            "return_type": getattr(element, "return_type", "Any"),
            "parameters": processed_params,
            "is_constructor": getattr(element, "is_constructor", False),
            "is_static": getattr(element, "is_static", False),
            "complexity_score": getattr(element, "complexity_score", 1),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": javadoc,
        }

    def _convert_variable_element(self, element: Any, language: str) -> dict[str, Any]:
        """Convert variable element to table format."""
        # Get field type based on language
        if language == "python":
            field_type = getattr(element, "variable_type", "") or ""
        else:
            field_type = getattr(element, "variable_type", "") or getattr(
                element, "field_type", ""
            )

        # Get visibility
        field_visibility = self._get_element_visibility(element)

        # Get JavaDoc if enabled
        include_javadoc = getattr(self.args, "include_javadoc", False)
        javadoc = getattr(element, "docstring", "") or "" if include_javadoc else ""

        return {
            "name": getattr(element, "name", str(element)),
            "type": field_type,
            "visibility": field_visibility,
            "modifiers": getattr(element, "modifiers", []),
            "is_static": getattr(element, "is_static", False),
            "is_readonly": getattr(element, "is_readonly", False),
            "is_final": getattr(element, "is_final", False),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": javadoc,
        }

    def _convert_import_element(self, element: Any) -> dict[str, Any]:
        """Convert import element to table format."""
        # Try to get the full import statement from raw_text
        raw_text = getattr(element, "raw_text", "")
        if raw_text:
            statement = raw_text
        else:
            # Fallback to constructing from name
            statement = f"import {getattr(element, 'name', str(element))}"

        return {
            "statement": statement,
            "raw_text": statement,  # PythonTableFormatter expects raw_text
            "name": getattr(element, "name", str(element)),
            "module_name": getattr(element, "module_name", ""),
        }

    def _convert_sql_element(self, element: Any, language: str) -> dict[str, Any]:
        """Convert SQL element to table format."""
        element_name = getattr(element, "name", str(element))
        element_type = get_element_type(element)

        # Get SQL-specific attributes
        columns = getattr(element, "columns", [])
        parameters = getattr(element, "parameters", [])
        dependencies = getattr(element, "dependencies", [])
        source_tables = getattr(element, "source_tables", [])
        return_type = getattr(element, "return_type", "")

        return {
            "name": element_name,
            "visibility": "public",  # SQL elements are typically public
            "return_type": (
                return_type if return_type else ""
            ),  # Don't fallback to element_type
            "parameters": self._process_sql_parameters(parameters),
            "is_constructor": False,
            "is_static": False,
            "complexity_score": 1,
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": "",
            "sql_type": element_type,
            "columns": columns,
            "dependencies": dependencies,
            "source_tables": source_tables,
        }

    def _process_sql_parameters(self, params: Any) -> list[dict[str, str]]:
        """Process SQL parameters."""
        if not params:
            return []

        if isinstance(params, list):
            param_list = []
            for param in params:
                if isinstance(param, dict):
                    param_list.append(param)
                else:
                    param_list.append({"name": str(param), "type": "Any"})
            return param_list
        else:
            return [{"name": str(params), "type": "Any"}]

    def _process_parameters(self, params: Any, language: str) -> list[dict[str, str]]:
        """Process parameters based on language syntax."""
        if isinstance(params, str):
            param_list = []
            if params.strip():
                param_names = [p.strip() for p in params.split(",") if p.strip()]
                param_list = [{"name": name, "type": "Any"} for name in param_names]
            return param_list
        elif isinstance(params, list):
            param_list = []
            for param in params:
                if isinstance(param, str):
                    param = param.strip()
                    # Languages using "name: type" syntax
                    TYPE_SUFFIX_LANGUAGES = {
                        "python",
                        "rust",
                        "kotlin",
                        "typescript",
                        "ts",
                        "scala",
                    }

                    if language.lower() in TYPE_SUFFIX_LANGUAGES:
                        # Format: "name: type"
                        if ":" in param:
                            parts = param.split(":", 1)
                            param_name = parts[0].strip()
                            param_type = parts[1].strip() if len(parts) > 1 else "Any"
                            param_list.append({"name": param_name, "type": param_type})
                        else:
                            param_list.append({"name": param, "type": "Any"})
                    else:
                        # Java format: "Type name"
                        last_space_idx = param.rfind(" ")
                        if last_space_idx != -1:
                            param_type = param[:last_space_idx].strip()
                            param_name = param[last_space_idx + 1 :].strip()
                            if param_type and param_name:
                                param_list.append(
                                    {"name": param_name, "type": param_type}
                                )
                            else:
                                param_list.append({"name": param, "type": "Any"})
                        else:
                            param_list.append({"name": param, "type": "Any"})
                elif isinstance(param, dict):
                    param_list.append(param)
                else:
                    param_list.append({"name": str(param), "type": "Any"})
            return param_list
        else:
            return []

    def _get_element_visibility(self, element: Any) -> str:
        """Get element visibility."""
        visibility = getattr(element, "visibility", "public")
        if hasattr(element, "is_private") and getattr(element, "is_private", False):
            visibility = "private"
        elif hasattr(element, "is_public") and getattr(element, "is_public", False):
            visibility = "public"
        return visibility

    def _output_table(self, table_output: str) -> None:
        """Output the table with proper encoding."""
        try:
            # Windows support: Output with UTF-8 encoding
            sys.stdout.buffer.write(table_output.encode("utf-8"))
        except (AttributeError, UnicodeEncodeError):
            # Fallback: Normal print
            print(table_output, end="")
