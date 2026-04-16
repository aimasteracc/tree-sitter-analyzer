"""Edge extractor registry — maps file extensions to language extractors.

To add a new language:
1. Create a new file (e.g., kotlin.py) with a class extending EdgeExtractor
2. Add its extensions to REGISTRY below
3. Done — no other files need to change
"""

from __future__ import annotations

from .base import EdgeExtractor
from .csharp import CSharpEdgeExtractor
from .go import GoEdgeExtractor
from .java import JavaEdgeExtractor
from .kotlin import KotlinEdgeExtractor
from .python import PythonEdgeExtractor
from .typescript import TypeScriptEdgeExtractor

REGISTRY: dict[str, EdgeExtractor] = {
    # Java
    ".java": JavaEdgeExtractor(),
    # Kotlin
    ".kt": KotlinEdgeExtractor(),
    # Python
    ".py": PythonEdgeExtractor(),
    # TypeScript / JavaScript
    ".ts": TypeScriptEdgeExtractor(),
    ".tsx": TypeScriptEdgeExtractor(),
    ".js": TypeScriptEdgeExtractor(),
    ".jsx": TypeScriptEdgeExtractor(),
    # C#
    ".cs": CSharpEdgeExtractor(),
    # Go
    ".go": GoEdgeExtractor(),
}


def get_extractor(suffix: str) -> EdgeExtractor | None:
    """Get the edge extractor for a file extension, or None."""
    return REGISTRY.get(suffix)


__all__ = ["EdgeExtractor", "get_extractor", "REGISTRY"]
