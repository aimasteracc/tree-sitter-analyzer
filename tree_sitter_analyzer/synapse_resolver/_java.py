"""Stable facade for Java import parsing and call-target resolution.

Implementation lives in focused import, context, and resolution modules. The
facade preserves the resolver API used by Synapse and downstream callers.
"""

from __future__ import annotations

from ._java_context import JavaResolverContext, build_java_context
from ._java_imports import _PACKAGE_MARKER, parse_java_imports
from ._java_resolution import (
    _lookup_in_file,
    _project_owns,
    _split_receiver,
    resolve_java_callee,
)

__all__ = [
    "_PACKAGE_MARKER",
    "_lookup_in_file",
    "_project_owns",
    "_split_receiver",
    "JavaResolverContext",
    "build_java_context",
    "parse_java_imports",
    "resolve_java_callee",
]
