from pathlib import Path as PathClass
from typing import Any, cast

from ..constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from .utils.file_metrics import compute_file_metrics
from .utils.shared_cache import get_shared_cache


class LegacyHandler:
    """Handles legacy operations for backward compatibility and testing."""

    def __init__(self, server: Any) -> None:
        """
        Initialize LegacyHandler.

        Args:
            server: The TreeSitterAnalyzerMCPServer instance
        """
        self.server = server

    async def analyze_code_scale(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Legacy method for analyzing code scale.
        Used by existing tests that mock server internals.
        """
        # For initialization-specific tests, we should raise MCPError instead of RuntimeError
        if not self.server.is_initialized():
            from .utils.error_handler import MCPError

            raise MCPError("Server is still initializing")

        # For specific initialization tests we allow delegating to universal tool
        if "file_path" not in arguments:
            universal_tool = getattr(self.server, "universal_analyze_tool", None)
            if universal_tool is not None:
                try:
                    result = await universal_tool.execute(arguments)
                    return dict(result)  # Ensure proper type casting
                except ValueError:
                    # Re-raise ValueError as-is for test compatibility
                    raise
            else:
                raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        include_complexity = arguments.get("include_complexity", True)
        include_details = arguments.get("include_details", False)

        # Use PathClass which is mocked in some tests
        base_root = getattr(
            getattr(self.server.security_validator, "boundary_manager", None),
            "project_root",
            None,
        )
        if not PathClass(file_path).is_absolute() and base_root:
            resolved_path = str((PathClass(base_root) / file_path).resolve())
        else:
            resolved_path = file_path

        # Security validation
        shared_cache = get_shared_cache()
        cached = shared_cache.get_security_validation(
            resolved_path, project_root=base_root
        )
        if cached is None:
            cached = self.server.security_validator.validate_file_path(resolved_path)
            shared_cache.set_security_validation(
                resolved_path, cached, project_root=base_root
            )
        is_valid, error_msg = cached
        if not is_valid:
            raise ValueError(f"Invalid file path: {error_msg}")

        # Use PathClass for existence check to respect mocks
        if not PathClass(resolved_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language if not specified
        from ..language_detector import detect_language_from_file

        if not language:
            language = detect_language_from_file(resolved_path, project_root=base_root)

        # Create analysis request
        from ..core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(
            file_path=resolved_path,
            language=language,
            include_complexity=include_complexity,
            include_details=include_details,
        )

        # Perform analysis
        analysis_result = await self.server.analysis_engine.analyze(request)

        if analysis_result is None or not analysis_result.success:
            error_msg = (
                analysis_result.error_message or "Unknown error"
                if analysis_result
                else "Unknown error"
            )
            raise RuntimeError(f"Failed to analyze file: {file_path} - {error_msg}")

        # Get element counts from the unified elements list
        elements = analysis_result.elements or []

        # Count elements by type using the new unified system
        classes_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
        )
        methods_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
        )
        fields_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
        )
        imports_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
        )
        packages_count = len(
            [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)]
        )
        total_elements = (
            classes_count
            + methods_count
            + fields_count
            + imports_count
            + packages_count
        )

        # Calculate unified file metrics (cached by content hash)
        file_metrics = compute_file_metrics(
            resolved_path, language=language, project_root=base_root
        )
        lines_code = file_metrics["code_lines"]
        lines_comment = file_metrics["comment_lines"]
        lines_blank = file_metrics["blank_lines"]

        result = {
            "file_path": file_path,
            "language": language,
            "metrics": {
                "lines_total": analysis_result.line_count,
                "lines_code": lines_code,
                "lines_comment": lines_comment,
                "lines_blank": lines_blank,
                "elements": {
                    "classes": classes_count,
                    "methods": methods_count,
                    "fields": fields_count,
                    "imports": imports_count,
                    "packages": packages_count,
                    "total": total_elements,
                },
            },
        }

        if include_complexity:
            # Add complexity metrics if available
            methods = [
                e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
            ]
            if methods:
                complexities = [getattr(m, "complexity_score", 0) for m in methods]
                result["metrics"]["complexity"] = {
                    "total": sum(complexities),
                    "average": round(
                        sum(complexities) / len(complexities) if complexities else 0, 2
                    ),
                    "max": max(complexities) if complexities else 0,
                }

        if include_details:
            # Convert elements to serializable format
            detailed_elements = []
            for elem in elements:
                if hasattr(elem, "__dict__"):
                    detailed_elements.append(elem.__dict__)
                else:
                    detailed_elements.append({"element": str(elem)})
            result["detailed_elements"] = detailed_elements

        return cast(dict[str, Any], result)
