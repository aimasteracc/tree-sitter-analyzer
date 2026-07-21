"""Scala language plugin package."""

from ._scaladoc import _parse_scaladoc_text
from .extractor import ScalaElementExtractor
from .plugin import (
    ScalaPlugin,
    _flatten_scala_elements,
    _make_scala_parser,
    _scala_empty_result,
    _scala_error_result,
)

__all__ = [
    "ScalaElementExtractor",
    "ScalaPlugin",
    "_flatten_scala_elements",
    "_make_scala_parser",
    "_parse_scaladoc_text",
    "_scala_empty_result",
    "_scala_error_result",
]
