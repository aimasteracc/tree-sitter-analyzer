#!/usr/bin/env python3
"""Python Element Extractor — AST traversal and element extraction."""

from typing import Any

from ...encoding_utils import extract_text_slice, safe_encode
from ...plugins.base import ElementExtractor
from ...utils import log_debug, log_error, log_warning
from ._class_extractor_mixin import PythonClassExtractionMixin
from ._core_extractor_mixin import PythonExtractorCoreMixin
from ._extractor import (
    calculate_complexity,
    extract_class_attribute_info,
    extract_decorators_from_node,
    extract_function_body,
    extract_name_from_node,
    extract_parameters_from_node,
    extract_superclasses_from_node,
    parse_from_import,
    parse_simple_import,
    validate_node,
)
from ._function_extractor_mixin import PythonFunctionExtractionMixin
from ._import_package_mixin import PythonImportPackageMixin

__all__ = [
    "PythonElementExtractor",
    "extract_text_slice",
    "log_debug",
    "log_error",
    "log_warning",
    "safe_encode",
]


class PythonElementExtractor(
    PythonFunctionExtractionMixin,
    PythonClassExtractionMixin,
    PythonImportPackageMixin,
    PythonExtractorCoreMixin,
    ElementExtractor,
):
    """Enhanced Python-specific element extractor with comprehensive feature support."""

    _extract_class_attribute_info = staticmethod(extract_class_attribute_info)
    _parse_simple_import = staticmethod(parse_simple_import)
    _parse_from_import = staticmethod(parse_from_import)
    _validate_node = staticmethod(validate_node)
    _extract_name_from_node = staticmethod(extract_name_from_node)
    _extract_parameters_from_node = staticmethod(extract_parameters_from_node)
    _extract_decorators_from_node = staticmethod(extract_decorators_from_node)
    _extract_function_body = staticmethod(extract_function_body)
    _extract_superclasses_from_node = staticmethod(extract_superclasses_from_node)
    _calculate_complexity = staticmethod(calculate_complexity)

    def __init__(self) -> None:
        """Initialize the Python element extractor."""
        self.current_module: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.imports: list[str] = []
        self.exports: list[dict[str, Any]] = []

        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._docstring_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

        self.is_module: bool = False
        self.framework_type: str = ""
        self.python_version: str = "3.8"
