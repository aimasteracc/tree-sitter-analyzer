"""
Centralized configuration for tree-sitter-analyzer v2.

All magic numbers and default values are collected here to avoid
scattered hardcoded constants across the codebase.

Usage:
    from tree_sitter_analyzer_v2.core.config import AnalyzerConfig

    config = AnalyzerConfig()
    # Access values:
    config.max_tokens        # 4000
    config.batch.max_files   # 20
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BatchLimits:
    """Safety limits for batch operations (extract, scale, etc.)."""

    max_files: int = 20
    max_sections_per_file: int = 50
    max_sections_total: int = 200
    max_total_bytes: int = 1024 * 1024  # 1 MiB
    max_total_lines: int = 5000
    max_file_size_bytes: int = 5 * 1024 * 1024  # 5 MiB

    def to_dict(self) -> dict[str, int]:
        """Export as dict (for backward compatibility with BATCH_LIMITS)."""
        return {
            "max_files": self.max_files,
            "max_sections_per_file": self.max_sections_per_file,
            "max_sections_total": self.max_sections_total,
            "max_total_bytes": self.max_total_bytes,
            "max_total_lines": self.max_total_lines,
            "max_file_size_bytes": self.max_file_size_bytes,
        }


@dataclass(frozen=True)
class SecurityLimits:
    """Security-related limits."""

    max_file_size: int = 50 * 1024 * 1024  # 50 MB


@dataclass(frozen=True)
class CodeMapDefaults:
    """Defaults for code map / intelligence tool."""

    max_tokens: int = 4000
    max_symbols: int = 20
    default_extensions: tuple[str, ...] = (".py", ".java", ".ts", ".js")
    max_depth: int = 1
    max_items: int = 50


@dataclass(frozen=True)
class GraphDefaults:
    """Defaults for code graph tools."""

    max_tokens: int = 4000
    max_nodes: int = 50
    max_depth: int = 5
    max_call_chain_depth: int = 10


@dataclass(frozen=True)
class AnalyzerConfig:
    """Root configuration object aggregating all subsystem defaults.

    Immutable (frozen) to prevent accidental mutation.
    Create a new instance with `dataclasses.replace()` to override values.
    """

    batch: BatchLimits = field(default_factory=BatchLimits)
    security: SecurityLimits = field(default_factory=SecurityLimits)
    code_map: CodeMapDefaults = field(default_factory=CodeMapDefaults)
    graph: GraphDefaults = field(default_factory=GraphDefaults)

    # General defaults
    default_output_format: str = "toon"
    default_language: str = "python"


# Module-level singleton (use this to avoid creating new instances everywhere)
DEFAULT_CONFIG = AnalyzerConfig()
