"""Compatibility facade for Go extraction helpers."""

from ._go_common_helpers import (
    extract_docstring,
    extract_method_receiver,
    extract_parameters,
    extract_return_type,
)
from ._go_function_helpers import (
    extract_go_function,
    extract_go_interface_methods,
    extract_go_method,
)
from ._go_import_helpers import (
    _extract_import_declaration,
    extract_import_spec,
    extract_imports_from_tree,
)
from ._go_package_helpers import extract_go_package
from ._go_type_helpers import (
    extract_embedded_types,
    extract_go_type_spec,
    extract_type_declaration,
)
from ._go_variable_helpers import extract_var_or_const, extract_var_spec

__all__ = [
    "_extract_import_declaration",
    "extract_docstring",
    "extract_embedded_types",
    "extract_go_function",
    "extract_go_interface_methods",
    "extract_go_method",
    "extract_go_package",
    "extract_go_type_spec",
    "extract_import_spec",
    "extract_imports_from_tree",
    "extract_method_receiver",
    "extract_parameters",
    "extract_return_type",
    "extract_type_declaration",
    "extract_var_or_const",
    "extract_var_spec",
]
