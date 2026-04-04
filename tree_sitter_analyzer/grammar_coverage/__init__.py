#!/usr/bin/env python3
"""
Grammar Coverage Validation Module

此模块用于验证 tree-sitter 语言插件对语法节点的覆盖度。
通过比较插件提取的元素与语法中所有可能的节点类型，确保 MECE 覆盖（互斥且完全穷尽）。

主要功能：
- validate_plugin_coverage: 验证单个语言的覆盖度
- generate_coverage_report: 生成人类可读的覆盖度报告
- check_coverage_threshold: CI 集成，检查覆盖度是否达标
- get_all_node_types: 获取语言的所有节点类型（语法自省）
- auto_detect_extractable_types: 自动检测可提取节点类型
- get_structural_types: 识别结构性节点类型
"""

from .auto_discovery import (
    AutoDiscoveryEngine,
    CoverageGapReport,
    NodeStats,
    WrapperCandidate,
)
from .corpus_generator import (
    generate_and_save_corpus,
    generate_corpus_by_category,
    generate_minimal_code_for_node_type,
    save_corpus_files,
    validate_generated_code,
)
from .grammar_snapshot import (
    LanguageSnapshot,
    SnapshotDiff,
    check_snapshot,
    diff_snapshot,
    load_snapshot,
    take_snapshot,
)
from .introspector import (
    auto_detect_extractable_types,
    get_all_node_types,
    get_language_summary,
    get_structural_types,
)
from .validator import (
    CoverageReport,
    check_coverage_threshold,
    generate_coverage_report,
    validate_plugin_coverage,
    validate_plugin_coverage_sync,
)

__all__ = [
    # Auto-Discovery Engine (Phase 3)
    "AutoDiscoveryEngine",
    "CoverageGapReport",
    "NodeStats",
    "WrapperCandidate",
    # Grammar Snapshot & CI Guard
    "LanguageSnapshot",
    "SnapshotDiff",
    "take_snapshot",
    "load_snapshot",
    "diff_snapshot",
    "check_snapshot",
    # Validator
    "CoverageReport",
    "validate_plugin_coverage",
    "validate_plugin_coverage_sync",
    "generate_coverage_report",
    "check_coverage_threshold",
    # Introspector
    "get_all_node_types",
    "auto_detect_extractable_types",
    "get_structural_types",
    "get_language_summary",
    # Corpus Generator
    "generate_minimal_code_for_node_type",
    "generate_corpus_by_category",
    "validate_generated_code",
    "save_corpus_files",
    "generate_and_save_corpus",
]
