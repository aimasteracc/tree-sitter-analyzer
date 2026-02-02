"""
Language-specific parsers for extracting structured information.

This module provides high-level parsers for each supported language,
extracting classes, functions, imports, and other language constructs.
"""

from tree_sitter_analyzer_v2.languages.java_parser import JavaParser
from tree_sitter_analyzer_v2.languages.python_parser import PythonParser
from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

__all__ = ["JavaParser", "PythonParser", "TypeScriptParser"]
