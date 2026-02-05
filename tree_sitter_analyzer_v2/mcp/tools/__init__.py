"""
MCP Tools for tree-sitter-analyzer v2.

This module provides MCP tool implementations:
- BaseTool: Base class for all tools
- ToolRegistry: Registry for managing tools
- AnalyzeTool: Analyze code structure
- FindFilesTool: Find files using fd
- SearchContentTool: Search content using ripgrep
- QueryTool: Query code elements
- CheckCodeScaleTool: Check code scale and complexity
- FindAndGrepTool: Combined file finding and content search
- ExtractCodeSectionTool: Extract code sections by line range
- AnalyzeCodeGraphTool: Analyze code structure and call relationships (NEW!)
- FindFunctionCallersTool: Find who calls a function (NEW!)
- QueryCallChainTool: Find call paths between functions (NEW!)
"""

from tree_sitter_analyzer_v2.mcp.tools.analyze import AnalyzeTool
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
from tree_sitter_analyzer_v2.mcp.tools.code_graph import (
    AnalyzeCodeGraphTool,
    FindFunctionCallersTool,
    QueryCallChainTool,
    VisualizeCodeGraphTool,
)
from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool
from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool
from tree_sitter_analyzer_v2.mcp.tools.query import QueryTool
from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry
from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool
from tree_sitter_analyzer_v2.mcp.tools.batch import BatchOperationsTool
from tree_sitter_analyzer_v2.mcp.tools.delete import DeleteFileTool
from tree_sitter_analyzer_v2.mcp.tools.dependencies import DependencyAnalyzerTool, DependencyGraphTool
from tree_sitter_analyzer_v2.mcp.tools.documentation import APIDocTool, DocGeneratorTool
from tree_sitter_analyzer_v2.mcp.tools.formatter import FormatterTool
from tree_sitter_analyzer_v2.mcp.tools.generator import ClassGeneratorTool, MockGeneratorTool, TestGeneratorTool
from tree_sitter_analyzer_v2.mcp.tools.git_tools import GitCommitTool, GitDiffTool, GitStatusTool
from tree_sitter_analyzer_v2.mcp.tools.incremental import (
    CacheManagerTool,
    ChangeDetectorTool,
    IncrementalAnalyzerTool,
)
from tree_sitter_analyzer_v2.mcp.tools.linter import LinterTool
from tree_sitter_analyzer_v2.mcp.tools.metrics import CodeMetricsTool
from tree_sitter_analyzer_v2.mcp.tools.performance import PerformanceMonitorTool, ProfileCodeTool
from tree_sitter_analyzer_v2.mcp.tools.project import ProjectAnalyzerTool, ProjectInitTool
from tree_sitter_analyzer_v2.mcp.tools.quality import CodeQualityTool
from tree_sitter_analyzer_v2.mcp.tools.refactor import RefactorRenameTool
from tree_sitter_analyzer_v2.mcp.tools.security import SecurityScannerTool
from tree_sitter_analyzer_v2.mcp.tools.test_runner import TestRunnerTool
from tree_sitter_analyzer_v2.mcp.tools.replace import ReplaceInFileTool
from tree_sitter_analyzer_v2.mcp.tools.search import FindFilesTool, SearchContentTool
from tree_sitter_analyzer_v2.mcp.tools.write import WriteFileTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "AnalyzeTool",
    "FindFilesTool",
    "SearchContentTool",
    "QueryTool",
    "CheckCodeScaleTool",
    "FindAndGrepTool",
    "ExtractCodeSectionTool",
    "AnalyzeCodeGraphTool",
    "FindFunctionCallersTool",
    "QueryCallChainTool",
    "VisualizeCodeGraphTool",
    "WriteFileTool",
    "ReplaceInFileTool",
    "DeleteFileTool",
    "BatchOperationsTool",
    "RefactorRenameTool",
    "CodeQualityTool",
    "LinterTool",
    "FormatterTool",
    "TestRunnerTool",
    "DependencyAnalyzerTool",
    "DependencyGraphTool",
    "DocGeneratorTool",
    "APIDocTool",
    "GitStatusTool",
    "GitDiffTool",
    "GitCommitTool",
    "ProjectInitTool",
    "ProjectAnalyzerTool",
    "SecurityScannerTool",
    "PerformanceMonitorTool",
    "ProfileCodeTool",
    "TestGeneratorTool",
    "MockGeneratorTool",
    "ClassGeneratorTool",
    "CodeMetricsTool",
    "ChangeDetectorTool",
    "CacheManagerTool",
    "IncrementalAnalyzerTool",
]
