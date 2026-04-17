"""Code analysis modules.

This package contains various code analysis engines:
- dependency_graph: Dependency analysis
- health_score: Code health metrics
- design_patterns: Design pattern detection
- git_analyzer: Git churn and ownership analysis
- risk_scoring: Risk scoring engine
"""

from tree_sitter_analyzer.analyzer.git_analyzer import (
    FileChurn,
    FileOwnership,
    GitAnalyzer,
)

__all__ = [
    "FileChurn",
    "FileOwnership",
    "GitAnalyzer",
]
