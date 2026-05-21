#!/usr/bin/env python3
"""
Table Command

Handles table format output generation.
"""

import sys
from typing import Any

from ...constants import (
    get_element_type,
)
from ...output_manager import output_error
from .base_command import BaseCommand
from .table_command_helpers import (
    StructureConverters,
    build_structure_format,
    collect_structure_elements,
    convert_to_toon_format,
    get_default_package_name,
    process_parameters,
    resolve_structure_package_name,
)


class TableCommand(BaseCommand):
    """Command for generating table format output."""

    def __init__(self, args: Any) -> None:
        """Initialize the table command."""
        super().__init__(args)

    # Main entry point - dispatches to handler: execute_async
    async def execute_async(self, language: str) -> int:
        """Execute table format generation."""
        try:
            # Perform standard analysis
            analysis_result = await self.analyze_file(language)
            if not analysis_result:
                return 1

            table_type = getattr(self.args, "table", "full")
            # K11: capture the user's original ``--table`` intent (pre-
            # override) so we can warn when ``--format`` silently wins
            # and stamp ``effective_table`` on the JSON envelope for
            # programmatic callers.
            user_table_request = table_type
            table_was_user_specified = "--table" in " ".join(sys.argv[1:])

            # DOG-3 fix: --output-format used to be silently ignored when
            # --table was also set. The global format flag now wins for the
            # encoding choice — but only when the user *explicitly* provided
            # it. Argparse leaves --output-format at its default ("json") for
            # every invocation, so checking the value alone would silently
            # break "--table=full" without --output-format. Instead we
            # inspect sys.argv: only honor --output-format / --format when
            # the literal flag appears.
            output_format = ""
            argv_tokens = " ".join(sys.argv[1:])
            if "--output-format" in argv_tokens or "--format" in argv_tokens:
                output_format = (
                    getattr(self.args, "format", None)
                    or getattr(self.args, "output_format", None)
                    or ""
                ).lower()
            if output_format == "toon" and table_type != "toon":
                table_type = "toon"
            elif output_format == "json" and table_type != "json":
                table_type = "json"

            # K11 (round-24 dogfood): warn on stderr when ``--table`` is
            # silently overridden by ``--format`` so the user knows the
            # explicit ``--table=compact`` did not take effect. Pre-K11,
            # ``--table=full|compact|csv`` all produced byte-identical JSON
            # output. Symmetric to DOG-3's TOON warning.
            table_was_overridden = (
                table_was_user_specified
                and output_format in ("json", "toon")
                and user_table_request != table_type
            )
            if table_was_overridden:
                print(
                    f"Warning: --table={user_table_request} is ignored when "
                    f"--format={output_format} (effective_table={table_type})",
                    file=sys.stderr,
                )

            if table_type == "json":
                formatted_data = self._convert_to_structure_format(
                    analysis_result, language
                )
                # K11: surface the effective table view to programmatic
                # callers. ``effective_table`` carries the actual view
                # produced (always ``json`` when --format=json wins);
                # ``requested_table`` echoes the user's original
                # ``--table`` intent so they can detect the override.
                if isinstance(formatted_data, dict):
                    formatted_data["effective_table"] = table_type
                    if table_was_user_specified:
                        formatted_data["requested_table"] = user_table_request
                import json

                formatted_output = json.dumps(
                    formatted_data, indent=2, ensure_ascii=False
                )
            elif table_type == "toon":
                formatted_output = self._format_as_toon(
                    analysis_result,
                    effective_table=table_type,
                    requested_table=(
                        user_table_request if table_was_user_specified else None
                    ),
                )
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

    # Format data for output: _format_as_toon
    def _format_as_toon(
        self,
        analysis_result: Any,
        effective_table: str | None = None,
        requested_table: str | None = None,
    ) -> str:
        """Format analysis result as TOON.

        K11: when ``--table`` is silently overridden by ``--format=toon``
        the structure carries ``effective_table`` / ``requested_table``
        so programmatic callers can detect the override symmetrically
        to the JSON path.
        """
        from ...formatters.toon_formatter import ToonFormatter

        use_tabs = getattr(self.args, "toon_use_tabs", False)
        formatter = ToonFormatter(use_tabs=use_tabs)

        # Convert to structure format for TOON
        structure_data = self._convert_to_toon_format(analysis_result)
        if effective_table is not None and isinstance(structure_data, dict):
            structure_data["effective_table"] = effective_table
            if requested_table is not None:
                structure_data["requested_table"] = requested_table
        return formatter.format(structure_data)

    # Format data for output: _convert_to_toon_format
    def _convert_to_toon_format(self, analysis_result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to TOON-friendly format with position info."""
        return convert_to_toon_format(analysis_result)

    # Format data for output: _convert_to_formatter_format
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
        return get_default_package_name(language)

    # Format data for output: _convert_to_structure_format
    def _convert_to_structure_format(
        self, analysis_result: Any, language: str
    ) -> dict[str, Any]:
        """Convert AnalysisResult to the format expected by table formatter."""
        package_name = resolve_structure_package_name(analysis_result, language)
        converters = StructureConverters(
            class_element=self._convert_class_element,
            function_element=self._convert_function_element,
            variable_element=self._convert_variable_element,
            import_element=self._convert_import_element,
            sql_element=self._convert_sql_element,
        )
        package_name, classes, methods, fields, imports = collect_structure_elements(
            analysis_result,
            language,
            package_name,
            converters,
            output_error,
        )
        return build_structure_format(
            analysis_result, package_name, classes, methods, fields, imports
        )

    # Convert between formats: _convert_class_element
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

    # Convert between formats: _convert_function_element
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

    # Convert between formats: _convert_variable_element
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

    # Convert between formats: _convert_import_element
    def _convert_import_element(self, element: Any) -> dict[str, Any]:
        """Convert import element to table format.

        Produces the K2 canonical import shape so JSON output matches the
        TOON ``_toon_import`` projection key-for-key. ``raw_text`` is kept
        as a backward-compat alias for downstream language formatters
        (python/php/csharp/ruby/go) that still read it directly.
        """
        # Try to get the full import statement from raw_text first; fall back
        # to the structured ``import_statement`` attribute (string only — skip
        # non-string sentinels so MagicMock-based tests still hit the
        # synthetic fallback), then to a synthetic ``import <name>``. This
        # is the only field that varies by source.
        raw_text = getattr(element, "raw_text", "")
        import_statement_attr = getattr(element, "import_statement", "")
        if raw_text and isinstance(raw_text, str):
            statement = raw_text
        elif isinstance(import_statement_attr, str) and import_statement_attr:
            statement = import_statement_attr
        else:
            statement = f"import {getattr(element, 'name', str(element))}"

        return {
            "name": getattr(element, "name", str(element)),
            "module_name": getattr(element, "module_name", ""),
            "statement": statement,
            "is_static": bool(getattr(element, "is_static", False)),
            "is_wildcard": bool(getattr(element, "is_wildcard", False)),
            "line_range": [
                int(getattr(element, "start_line", 0)),
                int(getattr(element, "end_line", 0)),
            ],
            "imported_names": list(getattr(element, "imported_names", []) or []),
            # Backward-compat alias retained for downstream formatters
            # (python/php/csharp/ruby/go) that still read ``raw_text``.
            "raw_text": statement,
        }

    # Convert between formats: _convert_sql_element
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

    # Process data through pipeline: _process_sql_parameters
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

    # Process data through pipeline: _process_parameters
    def _process_parameters(self, params: Any, language: str) -> list[dict[str, str]]:
        """Process parameters based on language syntax."""
        return process_parameters(params, language)

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
