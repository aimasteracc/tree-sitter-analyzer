#!/usr/bin/env python3
"""
Universal Analyze Tool for MCP

Universal code analysis through the MCP protocol, supporting multiple
programming languages with automatic language detection.
"""

from pathlib import Path
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file, is_language_supported
from ...mcp.utils import get_performance_monitor
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .universal_analyze_helpers import (
    TOOL_SCHEMA as _TOOL_SCHEMA,
)
from .universal_analyze_helpers import (
    count_dict_elements_by_type,
    count_elements_by_type,
    elements_to_summary,
)

logger = setup_logger(__name__)


class UniversalAnalyzeTool(BaseMCPTool):
    """Universal MCP Tool for code analysis across multiple languages."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)

    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self.analysis_engine = get_analysis_engine(project_path)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "analyze_code_universal",
            "description": (
                "SMART Workflow 'Analyze' step: Universal code analysis with automatic "
                "language detection. Supports basic, detailed, structure, and metrics modes."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")
        file_path = arguments["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")
        if not file_path.strip():
            raise ValueError("file_path cannot be empty")
        if "language" in arguments and not isinstance(arguments["language"], str):
            raise ValueError("language must be a string")
        if "analysis_type" in arguments:
            if not isinstance(arguments["analysis_type"], str):
                raise ValueError("analysis_type must be a string")
            valid = ["basic", "detailed", "structure", "metrics"]
            if arguments["analysis_type"] not in valid:
                raise ValueError(f"analysis_type must be one of {valid}")
        if "include_ast" in arguments and not isinstance(
            arguments["include_ast"], bool
        ):
            raise ValueError("include_ast must be a boolean")
        if "include_queries" in arguments and not isinstance(
            arguments["include_queries"], bool
        ):
            raise ValueError("include_queries must be a boolean")
        return True

    @handle_mcp_errors("universal_analyze")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        analysis_type = arguments.get("analysis_type", "basic")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)
        if analysis_type:
            analysis_type = self.security_validator.sanitize_input(
                analysis_type, max_length=50
            )

        if not Path(resolved).exists():
            raise ValueError("Invalid file path: file does not exist")

        if not language:
            language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
            if language == "unknown":
                raise ValueError(f"Could not detect language for file: {resolved}")

        if not is_language_supported(language):
            raise ValueError(f"Language '{language}' is not supported by tree-sitter")

        valid_types = ["basic", "detailed", "structure", "metrics"]
        if analysis_type not in valid_types:
            raise ValueError(
                f"Invalid analysis_type '{analysis_type}'. Valid: {', '.join(valid_types)}"
            )

        logger.info(
            f"Analyzing {resolved} (language: {language}, type: {analysis_type})"
        )

        try:
            monitor = get_performance_monitor()
            with monitor.measure_operation("universal_analyze"):
                if language == "java":
                    result = await self._analyze_advanced(
                        resolved, language, analysis_type, arguments
                    )
                else:
                    result = await self._analyze_universal(
                        resolved, language, analysis_type, arguments
                    )

                if arguments.get("include_queries", False):
                    result["available_queries"] = await self._get_available_queries(
                        language
                    )

                return apply_toon_format_to_response(result, output_format)
        except Exception as e:
            logger.error(f"Error analyzing {resolved}: {e}")
            raise

    async def _analyze_advanced(
        self,
        file_path: str,
        language: str,
        analysis_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze using the advanced analyzer (Java-specific)."""
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_complexity=True,
            include_details=True,
        )
        result = await self.analysis_engine.analyze(request)
        if result is None:
            raise RuntimeError(f"Failed to analyze file: {file_path}")

        base: dict[str, Any] = {
            "file_path": file_path,
            "language": language,
            "analyzer_type": "advanced",
            "analysis_type": analysis_type,
        }

        if analysis_type == "basic":
            base.update(self._extract_basic_metrics(result))
        elif analysis_type == "detailed":
            base.update(self._extract_detailed_metrics(result))
        elif analysis_type == "structure":
            base.update(self._extract_structure_info(result))
        elif analysis_type == "metrics":
            base.update(self._extract_comprehensive_metrics(result))

        if arguments.get("include_ast", False):
            base["ast_info"] = {"node_count": result.line_count, "depth": 0}

        return base

    async def _analyze_universal(
        self,
        file_path: str,
        language: str,
        analysis_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze using the universal analyzer."""
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_details=(analysis_type == "detailed"),
        )
        result = await self.analysis_engine.analyze(request)

        if not result or not result.success:
            msg = result.error_message if result else "Unknown error"
            raise RuntimeError(f"Failed to analyze file: {file_path} - {msg}")

        analysis_dict = result.to_dict()
        base: dict[str, Any] = {
            "file_path": file_path,
            "language": language,
            "analyzer_type": "universal",
            "analysis_type": analysis_type,
        }

        if analysis_type == "basic":
            base.update(self._extract_universal_basic_metrics(analysis_dict))
        elif analysis_type == "detailed":
            base.update(self._extract_universal_detailed_metrics(analysis_dict))
        elif analysis_type == "structure":
            base.update(self._extract_universal_structure_info(analysis_dict))
        elif analysis_type == "metrics":
            base.update(self._extract_universal_comprehensive_metrics(analysis_dict))

        if arguments.get("include_ast", False):
            base["ast_info"] = analysis_dict.get("ast_info", {})

        return base

    # -- Advanced analyzer extractors --

    def _extract_basic_metrics(self, result: Any) -> dict[str, Any]:
        stats = result.get_statistics()
        counts = count_elements_by_type(result.elements)
        return {
            "metrics": {
                "lines_total": result.line_count,
                "lines_code": stats.get("lines_of_code", 0),
                "lines_comment": stats.get("comment_lines", 0),
                "lines_blank": stats.get("blank_lines", 0),
                "elements": counts,
            }
        }

    def _extract_detailed_metrics(self, result: Any) -> dict[str, Any]:
        data = self._extract_basic_metrics(result)
        methods = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ]
        total_cx = sum(getattr(m, "complexity_score", 0) or 0 for m in methods)
        data["metrics"]["complexity"] = {
            "total": total_cx,
            "average": round(total_cx / len(methods) if methods else 0, 2),
            "max": max(
                (getattr(m, "complexity_score", 0) or 0 for m in methods), default=0
            ),
        }
        return data

    def _extract_structure_info(self, result: Any) -> dict[str, Any]:
        return {
            "structure": {
                "package": result.package.name if result.package else None,
                "classes": elements_to_summary(result.elements, ELEMENT_TYPE_CLASS),
                "methods": elements_to_summary(result.elements, ELEMENT_TYPE_FUNCTION),
                "fields": elements_to_summary(result.elements, ELEMENT_TYPE_VARIABLE),
                "imports": elements_to_summary(result.elements, ELEMENT_TYPE_IMPORT),
                "annotations": [
                    (
                        a.to_summary_item()
                        if hasattr(a, "to_summary_item")
                        else {"name": getattr(a, "name", "unknown")}
                    )
                    for a in getattr(result, "annotations", [])
                ],
            }
        }

    def _extract_comprehensive_metrics(self, result: Any) -> dict[str, Any]:
        data = self._extract_detailed_metrics(result)
        data.update(self._extract_structure_info(result))
        return data

    # -- Universal analyzer extractors --

    def _extract_universal_basic_metrics(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        elements = analysis_dict.get("elements", [])
        counts = count_dict_elements_by_type(elements)
        return {
            "metrics": {
                "lines_total": analysis_dict.get("line_count", 0),
                "lines_code": analysis_dict.get("line_count", 0),
                "lines_comment": 0,
                "lines_blank": 0,
                "elements": counts,
            }
        }

    def _extract_universal_detailed_metrics(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._extract_universal_basic_metrics(analysis_dict)
        if "query_results" in analysis_dict:
            data["query_results"] = analysis_dict["query_results"]
        return data

    def _extract_universal_structure_info(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "structure": analysis_dict.get("structure", {}),
            "queries_executed": analysis_dict.get("queries_executed", []),
        }

    def _extract_universal_comprehensive_metrics(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._extract_universal_detailed_metrics(analysis_dict)
        data.update(self._extract_universal_structure_info(analysis_dict))
        return data

    async def _get_available_queries(self, language: str) -> dict[str, Any]:
        try:
            if language == "java":
                return {
                    "language": language,
                    "queries": [],
                    "note": "Advanced analyzer uses built-in analysis logic",
                }
            queries = self.analysis_engine.get_supported_languages()
            return {"language": language, "queries": queries, "count": len(queries)}
        except Exception as e:
            logger.warning(f"Failed to get queries for {language}: {e}")
            return {"language": language, "queries": [], "error": str(e)}
