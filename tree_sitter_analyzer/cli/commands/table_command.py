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
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
)
from ...output_manager import output_error, output_info
from ...table_formatter import create_table_formatter

def _get_html_element_type(element_name: str) -> str:
    """Get HTML element type based on element name"""
    element_name = element_name.lower()
    
    # Structure elements
    if element_name in ['html', 'head', 'body', 'header', 'footer', 'nav', 'main', 'section', 'article', 'aside']:
        return 'structure'
    
    # Form elements
    elif element_name in ['form', 'input', 'button', 'select', 'textarea', 'label', 'fieldset', 'legend', 'option', 'optgroup', 'datalist', 'output']:
        return 'form'
    
    # Heading elements
    elif element_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        return 'heading'
    
    # List elements
    elif element_name in ['ul', 'ol', 'li', 'dl', 'dt', 'dd']:
        return 'list'
    
    # Table elements
    elif element_name in ['table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col']:
        return 'table'
    
    # Media elements
    elif element_name in ['img', 'video', 'audio', 'source', 'track', 'canvas', 'svg', 'picture', 'figure', 'figcaption']:
        return 'media'
    
    # Text elements
    elif element_name in ['p', 'span', 'strong', 'em', 'b', 'i', 'u', 'small', 'mark', 'del', 'ins', 'sub', 'sup', 'code', 'pre', 'kbd', 'samp', 'var', 'abbr', 'dfn', 'time', 'data', 'q', 'cite', 'blockquote']:
        return 'text'
    
    # Interactive elements
    elif element_name in ['a', 'details', 'summary', 'dialog', 'menu', 'menuitem']:
        return 'interactive'
    
    # Metadata elements
    elif element_name in ['title', 'meta', 'link', 'style', 'script', 'noscript', 'base']:
        return 'metadata'
    
    # Container elements
    elif element_name in ['div', 'address']:
        return 'container'
    
    # Default
    else:
        return 'container'
from ...formatters.language_formatter_factory import create_language_formatter
from .base_command import BaseCommand


class TableCommand(BaseCommand):
    """Command for generating table format output."""

    def __init__(self, args):
        """Initialize the table command with QueryService."""
        super().__init__(args)
        from tree_sitter_analyzer.core.query_service import QueryService
        self.query_service = QueryService()

    async def execute_async(self, language: str) -> int:
        """Execute table format generation."""
        try:
            # Check if query filtering is requested
            if hasattr(self.args, "query_key") and self.args.query_key:
                # Use query filtering
                return await self._execute_with_query_filtering(language)
            else:
                # Use standard analysis
                return await self._execute_standard_analysis(language)

        except Exception as e:
            output_error(f"An error occurred during table format analysis: {e}")
            return 1

    async def _execute_with_query_filtering(self, language: str) -> int:
        """Execute table generation with query filtering."""
        try:
            # Get filter expression if provided
            filter_expression = getattr(self.args, "filter", None)
            
            # Execute query using QueryService
            results = await self.query_service.execute_query(
                self.args.file_path,
                language,
                query_key=self.args.query_key,
                filter_expression=filter_expression,
            )
            
            if not results:
                output_info("No results found matching the query.")
                return 0
            
            # Convert query results to analysis format for table formatting
            analysis_result = self._convert_query_results_to_analysis(results, language)
            
            # Generate table output
            return await self._generate_table_output(analysis_result, language)
            
        except Exception as e:
            output_error(f"Query filtering failed: {e}")
            return 1

    async def _execute_standard_analysis(self, language: str) -> int:
        """Execute standard table generation without query filtering."""
        try:
            # Perform standard analysis
            analysis_result = await self.analyze_file(language)
            if not analysis_result:
                return 1
            
            # Generate table output
            return await self._generate_table_output(analysis_result, language)
            
        except Exception as e:
            output_error(f"Standard analysis failed: {e}")
            return 1

    async def _generate_table_output(self, analysis_result: Any, language: str) -> int:
        """Generate table output from analysis result."""
        try:

            # Check if we have a language-specific formatter
            formatter = create_language_formatter(analysis_result.language)
            if formatter:
                # Use language-specific formatter
                table_type = getattr(self.args, 'table', 'full')
                formatted_output = formatter.format_table(self._convert_to_formatter_format(analysis_result), table_type)
                self._output_table(formatted_output)
                return 0

            # Fallback to original implementation for unsupported languages
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
            output_error(f"Table generation failed: {e}")
            return 1

    def _extract_element_name(self, result: dict) -> str:
        """QueryService結果から実際の要素名を抽出"""
        content = result.get("content", "")
        capture_name = result.get("capture_name", "unknown")
        
        # 言語別の名前抽出ロジック
        if capture_name == "method":
            # Java: メソッド宣言から名前抽出
            return self._extract_java_method_name(content)
        elif capture_name == "function":
            # JavaScript/TypeScript: 関数名抽出
            return self._extract_js_function_name(content)
        elif capture_name == "heading":
            # Markdown: 見出しテキスト抽出
            return self._extract_markdown_heading(content)
        elif capture_name == "form_element":
            # HTML: フォーム要素名抽出
            return self._extract_html_element_name(content)
        else:
            # デフォルト: contentの最初の単語を使用
            return content.split()[0] if content.strip() else capture_name

    def _extract_java_method_name(self, content: str) -> str:
        """Java メソッド宣言から名前を抽出"""
        import re
        # Java メソッド宣言パターン: [修飾子] 戻り値型 メソッド名(引数)
        pattern = r'(?:public|private|protected|static|\s)*\s*\w+\s+(\w+)\s*\('
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        
        # フォールバック: 括弧の前の単語を取得
        pattern = r'(\w+)\s*\('
        match = re.search(pattern, content)
        return match.group(1) if match else content.split()[0] if content.strip() else "unknown"

    def _extract_js_function_name(self, content: str) -> str:
        """JavaScript/TypeScript 関数名を抽出"""
        import re
        
        # function 宣言: function functionName(
        pattern = r'function\s+(\w+)\s*\('
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        
        # アロー関数: const functionName = (
        pattern = r'(?:const|let|var)\s+(\w+)\s*=\s*\('
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        
        # メソッド宣言: methodName(
        pattern = r'(\w+)\s*\('
        match = re.search(pattern, content)
        return match.group(1) if match else content.split()[0] if content.strip() else "unknown"

    def _extract_markdown_heading(self, content: str) -> str:
        """Markdown 見出しテキストを抽出"""
        import re
        # # 見出しテキスト
        pattern = r'^#+\s*(.+)$'
        match = re.search(pattern, content.strip(), re.MULTILINE)
        if match:
            return match.group(1).strip()
        return content.strip() if content.strip() else "unknown"

    def _extract_html_element_name(self, content: str) -> str:
        """HTML 要素名を抽出"""
        import re
        # <tagname または <tagname attributes>
        pattern = r'<(\w+)'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        
        # フォールバック: 最初の単語
        return content.split()[0] if content.strip() else "unknown"

    def _convert_query_results_to_analysis(self, results: list[dict], language: str) -> Any:
        """Convert query results to analysis format using signature parsers."""
        from tree_sitter_analyzer.models import AnalysisResult, Function
        from .signature_parsers import signature_parser_factory
        
        # Get appropriate signature parser for the language
        parser = signature_parser_factory.get_parser(language)
        
        # Create mock analysis result with query results
        elements = []
        for result in results:
            capture_name = result.get("capture_name", "")
            content = result.get("content", "")
            
            # Parse signature using language-specific parser
            signature_info = parser.parse_signature(content, capture_name)
            
            func = Function(
                name=signature_info['name'],
                start_line=result.get("start_line", 0),
                end_line=result.get("end_line", 0),
                raw_text=content,
                language=language,
                parameters=signature_info['parameters'],
                return_type=signature_info['return_type'],
                is_async=signature_info['is_async'],
                is_static=signature_info['is_static'],
                visibility=signature_info['visibility'],
                complexity_score=0,
                docstring="",
                element_type=result.get("element_type", "function"),  # Preserve element_type from query results
            )
            elements.append(func)
        
        # Create analysis result
        analysis_result = AnalysisResult(
            file_path=self.args.file_path,
            language=language,
            line_count=0,
            elements=elements,
            node_count=len(elements),
            query_results={},
            source_code="",
            package=None,
            analysis_time=0.0,
            success=True,
            error_message=None,
        )
        
        return analysis_result

    def _convert_to_formatter_format(self, analysis_result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to format expected by formatters."""
        elements = getattr(analysis_result, 'elements', [])
        if not elements:
            # If no elements attribute, try to get from functions
            elements = getattr(analysis_result, 'functions', [])
        
        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "elements": [
                {
                    "name": getattr(element, "name", getattr(element, "function_name", str(element))),
                    "type": _get_html_element_type(getattr(element, "name", str(element))) if analysis_result.language == "html" else get_element_type(element),
                    "element_type": _get_html_element_type(getattr(element, "name", str(element))) if analysis_result.language == "html" else getattr(element, "element_type", get_element_type(element)),
                    "start_line": getattr(element, "start_line", 0),
                    "end_line": getattr(element, "end_line", 0),
                    "text": getattr(element, "text", getattr(element, "raw_text", "")),
                    "raw_text": getattr(element, "raw_text", getattr(element, "text", "")),
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
                    }
                }
                for element in elements
            ],
            "analysis_metadata": {
                "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
                "language": analysis_result.language,
                "file_path": analysis_result.file_path,
                "analyzer_version": "2.0.0",
            }
        }

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
        elements = getattr(analysis_result, 'elements', [])
        if not elements:
            # If no elements attribute, try to get from functions
            elements = getattr(analysis_result, 'functions', [])
        
        for i, element in enumerate(elements):
            try:
                element_type = get_element_type(element)
                element_name = getattr(element, "name", None)

                if element_type == ELEMENT_TYPE_PACKAGE:
                    package_name = str(element_name)
                elif element_type == ELEMENT_TYPE_CLASS:
                    classes.append(self._convert_class_element(element, i))
                elif element_type == ELEMENT_TYPE_FUNCTION:
                    methods.append(self._convert_function_element(element, language))
                elif element_type == ELEMENT_TYPE_VARIABLE:
                    fields.append(self._convert_variable_element(element, language))
                elif element_type == ELEMENT_TYPE_IMPORT:
                    imports.append(self._convert_import_element(element))
                else:
                    # Handle HTML-specific element types and other custom types
                    # For HTML elements, treat them as methods/functions for table display
                    if language == "html" or element_type in ["structure", "form", "container", "heading", "list", "table", "media", "text", "interactive", "metadata"]:
                        methods.append(self._convert_function_element(element, language))
                    else:
                        # For unknown types, also treat as methods for compatibility
                        methods.append(self._convert_function_element(element, language))

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
            "type": _get_html_element_type(getattr(element, "name", str(element))) if language == "html" else getattr(element, "element_type", "function"),  # Preserve element_type
            "element_type": _get_html_element_type(getattr(element, "name", str(element))) if language == "html" else getattr(element, "element_type", "function"),  # Also keep as element_type
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
            "raw_text": getattr(element, "raw_text", ""),  # Preserve raw_text for HTML attributes
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
