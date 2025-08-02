#!/usr/bin/env python3
"""
MCP Adapter for Tree-Sitter Analyzer

This module provides an adapter interface for integrating with the MCP protocol.
"""

from typing import Any

from ..models import AnalysisResult


def get_analysis_engine():
    """Get analysis engine instance for testing compatibility."""
    from ..core.analysis_engine import AnalysisEngine

    return AnalysisEngine()


def handle_mcp_resource_request(uri):
    """Handle MCP resource request for testing compatibility."""
    return {
        "contents": [
            {"mimeType": "application/json", "text": {"mock": "resource"}, "uri": uri}
        ]
    }


def read_file_safe(file_path: str) -> str:
    """Read file safely for MCP resource requests."""
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise FileNotFoundError(f"Could not read file {file_path}: {e}") from e


class MCPAdapter:
    """MCP Adapter for testing compatibility."""

    def __init__(self):
        """Initialize MCP Adapter."""
        from ..core.analysis_engine import UnifiedAnalysisEngine

        self.engine = UnifiedAnalysisEngine()

    async def analyze_file_async(self, file_path: str, **kwargs) -> "AnalysisResult":
        """Analyze file asynchronously."""
        from ..core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(
            file_path=file_path,
            language=kwargs.get("language"),
            include_complexity=kwargs.get("include_complexity", False),
            include_details=kwargs.get("include_details", True),
            format_type=kwargs.get("format_type", "standard"),
        )
        return await self.engine.analyze(request)

    async def get_file_structure_async(
        self, file_path: str, **kwargs
    ) -> dict[str, Any]:
        """Get file structure asynchronously."""
        result = await self.analyze_file_async(file_path, **kwargs)
        return {
            "file_path": result.file_path,
            "language": result.language,
            "structure": {
                "classes": [cls.to_dict() for cls in result.classes],
                "methods": [method.to_dict() for method in result.methods],
                "fields": [field.to_dict() for field in result.fields],
                "imports": [imp.to_dict() for imp in result.imports],
                "annotations": [ann.to_dict() for ann in result.annotations],
            },
            "metadata": {
                "analysis_time": result.analysis_time,
                "success": result.success,
                "error_message": result.error_message,
                "package": result.package,
                "class_count": len(result.classes),
                "method_count": len(result.methods),
                "field_count": len(result.fields),
                "import_count": len(result.imports),
                "annotation_count": len(result.annotations),
            },
        }

    async def analyze_batch_async(
        self, file_paths: list[str], **kwargs
    ) -> list["AnalysisResult"]:
        """Analyze multiple files asynchronously."""
        results = []
        for file_path in file_paths:
            try:
                result = await self.analyze_file_async(file_path, **kwargs)
                results.append(result)
            except Exception as e:
                # Create error result
                from ..models import AnalysisResult

                error_result = AnalysisResult(
                    file_path=file_path,
                    language="unknown",
                    line_count=0,
                    elements=[],
                    node_count=0,
                    query_results={},
                    source_code="",
                    package=None,
                    imports=[],
                    classes=[],
                    methods=[],
                    fields=[],
                    annotations=[],
                    analysis_time=0.0,
                    success=False,
                    error_message=str(e),
                )
                results.append(error_result)
        return results

    async def handle_mcp_tool_request(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle MCP tool request."""
        if tool_name == "analyze_file":
            file_path = arguments.get("file_path")
            if not file_path:
                return {"error": "file_path is required"}

            try:
                result = await self.analyze_file_async(file_path)
                return {"success": True, "result": result.to_dict()}
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Unknown tool: {tool_name}"}

    async def handle_mcp_resource_request(self, uri: str) -> dict[str, Any]:
        """Handle MCP resource request."""
        if uri.startswith("code://"):
            # Extract file path from URI
            file_path = uri.replace("code://", "")
            try:
                content = read_file_safe(file_path)
                return {"uri": uri, "content": content, "mimeType": "text/plain"}
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Unsupported URI: {uri}"}

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass

    async def aclose(self) -> None:
        """Async cleanup."""
        pass

    def analyze_with_mcp_request(self, arguments):
        """Analyze with MCP request."""
        if "file_path" not in arguments:
            raise KeyError("file_path is required in MCP request")
        return self.analyze_file_async(arguments["file_path"])


class MCPServerAdapter:
    """MCP Server Adapter for testing compatibility."""

    def __init__(self):
        """Initialize MCP Server Adapter."""
        self.mcp_adapter = MCPAdapter()

    async def handle_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle MCP request."""
        if not params:
            return {"error": "params are required"}
        return await self.mcp_adapter.handle_mcp_tool_request(method, params)
