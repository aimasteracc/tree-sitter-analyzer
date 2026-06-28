"""Shared infrastructure for language plugins.

Exports thin, reusable helpers that language plugins can import instead of
duplicating boilerplate traversal / complexity / import-extraction code.
"""

from .traversal import (
    iter_children_of_type,
    find_first_child,
    collect_named_nodes,
    node_text,
    node_range,
)
from .scope_tracker import ScopeStack
from .name_resolver import QualifiedNameBuilder, resolve_self_reference, strip_type_params
from .import_extractor import (
    ImportRecord,
    extract_qualified_import,
    extract_from_import,
    extract_namespace_import,
)
from .complexity import CyclomaticCounter, LogicalBranchCounter, ComplexityResult

__all__ = [
    # traversal
    "iter_children_of_type",
    "find_first_child",
    "collect_named_nodes",
    "node_text",
    "node_range",
    # scope_tracker
    "ScopeStack",
    # name_resolver
    "QualifiedNameBuilder",
    "resolve_self_reference",
    "strip_type_params",
    # import_extractor
    "ImportRecord",
    "extract_qualified_import",
    "extract_from_import",
    "extract_namespace_import",
    # complexity
    "CyclomaticCounter",
    "LogicalBranchCounter",
    "ComplexityResult",
]
