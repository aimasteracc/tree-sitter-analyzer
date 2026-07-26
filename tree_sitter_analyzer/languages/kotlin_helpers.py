"""Stable Kotlin helper facade backed by focused extraction modules."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error
from ._kotlin_class_helpers import (
    _KOTLIN_CLASS_KIND_MODIFIERS,
    _KOTLIN_PROPERTY_OTHER_MODIFIERS,
    _KOTLIN_PROPERTY_VISIBILITY_MODIFIERS,
    _extract_kotlin_delegation,
    _extract_kotlin_property_modifiers,
    _extract_kotlin_property_name,
    _refine_kotlin_class_kind,
    extract_kotlin_class_or_object,
    extract_kotlin_property,
)
from ._kotlin_core_helpers import (
    _KOTLIN_DECISION_TYPES,
    _KOTLIN_LOGIC_OP_TOKENS,
    _kotlin_expression_body_type,
    _kotlin_extension_receiver,
    _kotlin_owning_type,
    _kotlin_parameter_pair,
    _safe_children,
    calculate_kotlin_complexity,
    determine_visibility,
    extract_import,
    extract_kotlin_parameters,
)
from ._kotlin_function_helpers import (
    _kotlin_primary_ctor_class_name,
    extract_kotlin_function,
    extract_kotlin_primary_constructor,
)

# Keep direct imports of historical private helpers compatible without adding
# them to the module's former wildcard-visible surface.
_PRIVATE_COMPAT_EXPORTS = (
    _KOTLIN_CLASS_KIND_MODIFIERS,
    _KOTLIN_DECISION_TYPES,
    _KOTLIN_LOGIC_OP_TOKENS,
    _KOTLIN_PROPERTY_OTHER_MODIFIERS,
    _KOTLIN_PROPERTY_VISIBILITY_MODIFIERS,
    _extract_kotlin_delegation,
    _extract_kotlin_property_modifiers,
    _extract_kotlin_property_name,
    _kotlin_expression_body_type,
    _kotlin_extension_receiver,
    _kotlin_owning_type,
    _kotlin_parameter_pair,
    _kotlin_primary_ctor_class_name,
    _refine_kotlin_class_kind,
    _safe_children,
)

__all__ = [
    "Any",
    "Callable",
    "Class",
    "Function",
    "Import",
    "Variable",
    "calculate_kotlin_complexity",
    "determine_visibility",
    "extract_import",
    "extract_kotlin_class_or_object",
    "extract_kotlin_function",
    "extract_kotlin_parameters",
    "extract_kotlin_primary_constructor",
    "extract_kotlin_property",
    "log_error",
]
