"""Legacy code scale analysis handler — extracted from server.py."""

from pathlib import Path as PathClass
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...utils import setup_logger
from ..utils.file_metrics import compute_file_metrics
from ..utils.shared_cache import get_shared_cache

logger = setup_logger(__name__)


async def analyze_code_scale(
    arguments: dict[str, Any],
    *,
    analysis_engine: Any,
    security_validator: Any,
    universal_analyze_tool: Any | None = None,
    initialization_complete: bool = True,
) -> dict[str, Any]:
    """Handle check_code_scale tool execution with full validation."""
    if not initialization_complete:
        from ..utils.error_handler import MCPError

        raise MCPError("Server is still initializing")

    if "file_path" not in arguments:
        if universal_analyze_tool is not None:
            try:
                universal_result = await universal_analyze_tool.execute(arguments)
                return dict(universal_result)
            except ValueError:
                raise
        raise ValueError("file_path is required")

    file_path = arguments["file_path"]
    language = arguments.get("language")
    include_complexity = arguments.get("include_complexity", True)
    include_details = arguments.get("include_details", False)

    base_root = _get_base_root(security_validator)
    resolved_path = _resolve_path(file_path, base_root)

    _validate_security(resolved_path, base_root, security_validator)

    if not PathClass(resolved_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    from ...language_detector import detect_language_from_file

    if not language:
        language = detect_language_from_file(resolved_path, project_root=base_root)

    from ...core.analysis_engine import AnalysisRequest

    request = AnalysisRequest(
        file_path=resolved_path,
        language=language,
        include_complexity=include_complexity,
        include_details=include_details,
    )

    analysis_result = await analysis_engine.analyze(request)

    if analysis_result is None or not analysis_result.success:
        error_msg = (
            analysis_result.error_message or "Unknown error"
            if analysis_result
            else "Unknown error"
        )
        raise RuntimeError(f"Failed to analyze file: {file_path} - {error_msg}")

    elements = analysis_result.elements or []
    counts = _count_elements(elements)

    file_metrics = compute_file_metrics(
        resolved_path, language=language, project_root=base_root
    )

    result: dict[str, Any] = {
        "file_path": file_path,
        "language": language,
        "metrics": {
            "lines_total": analysis_result.line_count,
            "lines_code": file_metrics["code_lines"],
            "lines_comment": file_metrics["comment_lines"],
            "lines_blank": file_metrics["blank_lines"],
            "elements": counts,
        },
    }

    if include_complexity:
        methods = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
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
        detailed_elements = []
        for elem in elements:
            if hasattr(elem, "__dict__"):
                detailed_elements.append(elem.__dict__)
            else:
                detailed_elements.append({"element": str(elem)})
        result["detailed_elements"] = detailed_elements

    return result


def _get_base_root(security_validator: Any) -> str | None:
    return getattr(
        getattr(security_validator, "boundary_manager", None),
        "project_root",
        None,
    )


def _resolve_path(file_path: str, base_root: str | None) -> str:
    if not PathClass(file_path).is_absolute() and base_root:
        return str((PathClass(base_root) / file_path).resolve())
    return file_path


def _validate_security(
    resolved_path: str, base_root: str | None, security_validator: Any
) -> None:
    shared_cache = get_shared_cache()
    cached = shared_cache.get_security_validation(resolved_path, project_root=base_root)
    if cached is None:
        cached = security_validator.validate_file_path(resolved_path)
        shared_cache.set_security_validation(
            resolved_path, cached, project_root=base_root
        )
    is_valid, error_msg = cached
    if not is_valid:
        raise ValueError(f"Invalid file path: {error_msg}")


def _count_elements(elements: list[Any]) -> dict[str, int]:
    classes = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)])
    methods = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)])
    fields = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)])
    imports = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)])
    packages = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)])
    return {
        "classes": classes,
        "methods": methods,
        "fields": fields,
        "imports": imports,
        "packages": packages,
        "total": classes + methods + fields + imports + packages,
    }
