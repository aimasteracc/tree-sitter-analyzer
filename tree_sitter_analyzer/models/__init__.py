#!/usr/bin/env python3
"""
Data Models for Multi-Language Code Analysis

Backward-compatible re-export of every public symbol from the original
``models.py``.  Import paths such as::

    from tree_sitter_analyzer.models import JavaMethod, SQLTable

continue to work unchanged.
"""

from ._result_helpers import (
    _group_elements_by_type,
    _mcp_annotation_entries,
    _mcp_class_entries,
    _mcp_field_entries,
    _mcp_import_entries,
    _mcp_line_range,
    _mcp_metadata_block,
    _mcp_method_entries,
    _mcp_package_info,
    _safe_get_attr,
    _to_dict_annotation_row,
    _to_dict_class_row,
    _to_dict_field_row,
    _to_dict_import_row,
    _to_dict_method_row,
)
from .base import (
    Class,
    CodeElement,
    Comprehension,
    Expression,
    Function,
    Import,
    Lambda,
    Package,
    Variable,
    dataclass_with_slots,
)
from .java_models import (
    JavaAnnotation,
    JavaClass,
    JavaField,
    JavaImport,
    JavaMethod,
    JavaPackage,
)
from .markup_models import (
    MarkupElement,
    StyleElement,
    YAMLElement,
)
from .result import AnalysisResult
from .sql_models import (
    SQLColumn,
    SQLConstraint,
    SQLElement,
    SQLElementType,
    SQLFunction,
    SQLIndex,
    SQLParameter,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
)

__all__ = [
    # base
    "dataclass_with_slots",
    "CodeElement",
    "Function",
    "Class",
    "Variable",
    "Import",
    "Package",
    "Lambda",
    "Comprehension",
    "Expression",
    # java
    "JavaAnnotation",
    "JavaMethod",
    "JavaClass",
    "JavaField",
    "JavaImport",
    "JavaPackage",
    # sql
    "SQLElementType",
    "SQLColumn",
    "SQLParameter",
    "SQLConstraint",
    "SQLElement",
    "SQLTable",
    "SQLView",
    "SQLProcedure",
    "SQLFunction",
    "SQLTrigger",
    "SQLIndex",
    # markup
    "MarkupElement",
    "StyleElement",
    "YAMLElement",
    # result
    "AnalysisResult",
    # private helpers (kept for any internal code that imported them directly)
    "_safe_get_attr",
    "_mcp_package_info",
    "_mcp_line_range",
    "_mcp_import_entries",
    "_mcp_class_entries",
    "_mcp_method_entries",
    "_mcp_field_entries",
    "_mcp_annotation_entries",
    "_mcp_metadata_block",
    "_group_elements_by_type",
    "_to_dict_import_row",
    "_to_dict_class_row",
    "_to_dict_method_row",
    "_to_dict_field_row",
    "_to_dict_annotation_row",
]
