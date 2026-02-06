"""
Language-specific parsers for tree-sitter-analyzer v2.

Each parser wraps the core TreeSitterParser and provides
structured extraction of language elements (functions, classes, imports).
"""

from tree_sitter_analyzer_v2.languages.python_parser import PythonParser
from tree_sitter_analyzer_v2.languages.java_parser import JavaParser
from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

__all__ = ["PythonParser", "JavaParser", "TypeScriptParser"]
