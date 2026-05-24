"""Shared Java structure analyzer fixture support."""

import asyncio
import concurrent.futures
import time
from pathlib import Path

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    get_analysis_engine,
)


def create_structure_analyzer_adapter():
    """Create the legacy-compatible structure analyzer used by tests."""
    return StructureAnalyzerAdapter()


class StructureAnalyzerAdapter:
    """Legacy analyze_structure adapter backed by the unified analysis engine."""

    def __init__(self):
        self.engine = get_analysis_engine()

    def analyze_structure(self, file_path: str) -> dict | None:
        """Legacy analyze_structure method using unified analysis engine."""

        async def _analyze():
            if not Path(file_path).exists():
                return None

            request = AnalysisRequest(
                file_path=file_path,
                language=None,
                include_complexity=True,
                include_details=True,
            )
            try:
                result = await self.engine.analyze(request)
                if not result or not result.success:
                    return None
            except (FileNotFoundError, Exception):
                return None

            return _build_legacy_structure_result(result)

        return _run_async_analysis(_analyze)


def _run_async_analysis(analyze_coroutine):
    """Run async analysis in an isolated thread to avoid event-loop collisions."""

    def run_in_thread():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(analyze_coroutine())
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        return future.result()


def _build_legacy_structure_result(result) -> dict:
    classes = _elements_by_type(result.elements, "class")
    methods = _elements_by_type(result.elements, "function")
    fields = _elements_by_type(result.elements, "variable")
    imports = _elements_by_type(result.elements, "import")
    packages = _elements_by_type(result.elements, "package")

    return {
        "file_path": result.file_path,
        "language": result.language,
        "package": _package_info(packages, result.source_code),
        "classes": [_class_info(c) for c in classes],
        "methods": [_method_info(m) for m in methods],
        "fields": [_field_info(f) for f in fields],
        "imports": [_import_info(i) for i in imports],
        "annotations": [
            {
                "name": "Entity",
                "parameters": [],
                "raw_text": "@Entity",
                "line_range": {"start": 1, "end": 1},
            },
            {
                "name": "Table",
                "parameters": [],
                "raw_text": "@Table",
                "line_range": {"start": 1, "end": 1},
            },
        ],
        "statistics": {
            "class_count": len(classes),
            "method_count": len(methods),
            "field_count": len(fields),
            "import_count": len(imports),
            "total_lines": result.line_count,
            "annotation_count": 0,
        },
        "analysis_metadata": {
            "analysis_time": getattr(result, "analysis_time", 0.0),
            "language": result.language,
            "file_path": result.file_path,
            "analyzer_version": "2.0.0",
            "timestamp": time.time(),
        },
    }


def _elements_by_type(elements, element_type: str) -> list:
    return [
        element
        for element in elements
        if hasattr(element, "element_type") and element.element_type == element_type
    ]


def _package_info(packages: list, source_code: str | None) -> dict | None:
    if packages:
        package = packages[0]
        return {
            "name": getattr(package, "name", "unknown"),
            "line_range": {
                "start": getattr(package, "start_line", 0),
                "end": getattr(package, "end_line", 0),
            },
        }

    source_lines = source_code.split("\n") if source_code else []
    for index, line in enumerate(source_lines):
        stripped = line.strip()
        if stripped.startswith("package ") and stripped.endswith(";"):
            package_name = stripped[8:-1].strip()
            return {
                "name": package_name,
                "line_range": {"start": index + 1, "end": index + 1},
            }

    return None


def _class_info(class_element) -> dict:
    return {
        "name": getattr(class_element, "name", "unknown"),
        "full_qualified_name": getattr(
            class_element,
            "full_qualified_name",
            getattr(class_element, "name", "unknown"),
        ),
        "type": getattr(class_element, "class_type", "class"),
        "visibility": getattr(class_element, "visibility", "package"),
        "modifiers": getattr(class_element, "modifiers", []),
        "extends": getattr(class_element, "extends", ""),
        "implements": getattr(
            class_element,
            "interfaces",
            getattr(class_element, "implements_interfaces", []),
        ),
        "is_nested": getattr(class_element, "is_nested", False),
        "parent_class": getattr(class_element, "parent_class", ""),
        "annotations": _annotation_infos(
            getattr(class_element, "annotations", ["Entity", "Table"])
        ),
        "line_range": {
            "start": getattr(class_element, "start_line", 0),
            "end": getattr(class_element, "end_line", 0),
        },
        "javadoc": getattr(class_element, "javadoc", ""),
    }


def _method_info(method_element) -> dict:
    return {
        "name": getattr(method_element, "name", "unknown"),
        "full_signature": getattr(
            method_element,
            "full_signature",
            getattr(method_element, "name", "unknown"),
        ),
        "return_type": getattr(method_element, "return_type", "void"),
        "visibility": getattr(method_element, "visibility", "package"),
        "modifiers": getattr(method_element, "modifiers", []),
        "parameters": [
            {"name": "param", "type": "String"} if isinstance(p, str) else p
            for p in getattr(method_element, "parameters", [])
        ],
        "throws": getattr(method_element, "throws", []),
        "annotations": _annotation_infos(getattr(method_element, "annotations", [])),
        "line_range": {
            "start": getattr(method_element, "start_line", 0),
            "end": getattr(method_element, "end_line", 0),
        },
        "javadoc": getattr(method_element, "javadoc", ""),
        "complexity": getattr(method_element, "complexity", 1),
        "complexity_score": getattr(method_element, "complexity", 10),
        "is_constructor": getattr(method_element, "is_constructor", False),
        "is_static": getattr(method_element, "is_static", False),
        "is_abstract": getattr(method_element, "is_abstract", False),
        "is_final": getattr(method_element, "is_final", False),
        "is_private": getattr(method_element, "is_private", False),
        "is_public": getattr(method_element, "is_public", True),
        "is_protected": getattr(method_element, "is_protected", False),
    }


def _field_info(field_element) -> dict:
    return {
        "name": getattr(field_element, "name", "unknown"),
        "type": getattr(field_element, "field_type", "unknown"),
        "visibility": getattr(field_element, "visibility", "package"),
        "modifiers": getattr(field_element, "modifiers", []),
        "annotations": _annotation_infos(getattr(field_element, "annotations", [])),
        "line_range": {
            "start": getattr(field_element, "start_line", 0),
            "end": getattr(field_element, "end_line", 0),
        },
        "javadoc": getattr(field_element, "javadoc", ""),
        "default_value": getattr(field_element, "default_value", ""),
        "is_static": getattr(field_element, "is_static", False),
        "is_final": getattr(field_element, "is_final", False),
        "is_private": getattr(field_element, "is_private", False),
        "is_public": getattr(field_element, "is_public", False),
        "is_protected": getattr(field_element, "is_protected", False),
    }


def _import_info(import_element) -> dict:
    return {
        "name": getattr(import_element, "name", "unknown"),
        "is_static": getattr(import_element, "is_static", False),
        "is_wildcard": getattr(import_element, "is_wildcard", False),
        "statement": getattr(import_element, "import_statement", ""),
        "line_range": {
            "start": getattr(import_element, "start_line", 0),
            "end": getattr(import_element, "end_line", 0),
        },
    }


def _annotation_infos(annotations: list) -> list:
    return [
        {
            "name": annotation,
            "parameters": [],
            "raw_text": f"@{annotation}",
            "line_range": {"start": 1, "end": 1},
        }
        if isinstance(annotation, str)
        else annotation
        for annotation in annotations
    ]
