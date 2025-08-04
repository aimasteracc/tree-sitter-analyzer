#!/usr/bin/env python3
"""
Table Command

Handles table format output generation.
"""

import sys
from typing import Any

from ...output_manager import output_error
from ...table_formatter import create_table_formatter
from .base_command import BaseCommand


class TableCommand(BaseCommand):
    """Command for generating table format output."""

    async def execute_async(self, language: str) -> int:
        """Execute table format generation."""
        try:
            # Perform analysis
            analysis_result = await self.analyze_file(language)
            if not analysis_result:
                return 1

            # Convert analysis result to structure format
            structure_result = self._convert_to_structure_format(
                analysis_result, language
            )

            # Create table formatter
            include_javadoc = getattr(self.args, "include_javadoc", False)
            formatter = create_table_formatter(
                self.args.table, language, include_javadoc
            )
            table_output = formatter.format_structure(structure_result)

            # Output table
            self._output_table(table_output)

            return 0

        except Exception as e:
            output_error(f"An error occurred during table format analysis: {e}")
            return 1

    def _convert_to_structure_format(
        self, analysis_result: Any, language: str
    ) -> dict[str, Any]:
        """Convert AnalysisResult to the format expected by table formatter."""
        classes = []
        methods = []
        fields = []
        imports = []
        package_name = "unknown"

        # Process each element
        for i, element in enumerate(analysis_result.elements):
            try:
                element_type = getattr(element, "__class__", type(element)).__name__
                element_name = getattr(element, "name", None)

                if element_type == "Package":
                    package_name = str(element_name)
                elif element_type == "Class":
                    classes.append(self._convert_class_element(element, i))
                elif element_type == "Function":
                    methods.append(self._convert_function_element(element, language))
                elif element_type == "Variable":
                    fields.append(self._convert_variable_element(element, language))
                elif element_type == "Import":
                    imports.append(self._convert_import_element(element))

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

    def _convert_class_element(self, element: Any, index: int) -> dict[str, Any]:
        """Convert class element to table format."""
        element_name = getattr(element, "name", None)
        final_name = element_name if element_name else f"UnknownClass_{index}"

        return {
            "name": final_name,
            "type": "class",
            "visibility": "public",
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
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": javadoc,
        }

    def _convert_import_element(self, element: Any) -> dict[str, Any]:
        """Convert import element to table format."""
        return {
            "statement": getattr(element, "name", str(element)),
            "name": getattr(element, "name", str(element)),
        }

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
                    if language == "python":
                        # Python format: "name: type"
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
