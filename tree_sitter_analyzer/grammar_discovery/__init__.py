"""
Grammar Auto-Discovery Module

This module provides automatic discovery of grammar elements (node types, fields,
wrappers) using tree-sitter's Language API and structural analysis.

Classes:
    GrammarIntrospector: Runtime introspection of tree-sitter grammars
    StructuralAnalyzer: Multi-feature scoring for wrapper detection
    PathEnumerator: Syntactic path discovery from code samples
"""
