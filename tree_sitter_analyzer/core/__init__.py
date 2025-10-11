#!/usr/bin/env python3
"""
Core module for tree_sitter_analyzer.

This module contains the core components of the new architecture:
- AnalysisEngine: Main analysis orchestrator
- Parser: Tree-sitter parsing wrapper
- QueryExecutor: Query execution engine
"""

from .analysis_engine import UnifiedAnalysisEngine
from .engine import AnalysisEngine
from .parser import Parser, ParseResult
from .query import QueryExecutor

__all__ = ["UnifiedAnalysisEngine", "AnalysisEngine", "Parser", "ParseResult", "QueryExecutor"]
