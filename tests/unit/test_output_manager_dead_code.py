#!/usr/bin/env python3
"""
修复 B 验证：output_manager.py 死代码清理测试

覆盖规格：openspec/changes/fix-intelligence-graph/specs/output-manager-dead-code/spec.md
验收标准：AC-OM-001 ~ AC-OM-005
"""

from __future__ import annotations

import importlib
import pytest


class TestOutputManagerDeadCodeRemoval:
    """output_success、output_languages、output_queries 应从模块中删除。"""

    def test_output_success_does_not_exist(self):
        """AC-OM-001: output_success 不应存在于 output_manager 模块。"""
        import tree_sitter_analyzer.output_manager as om

        assert not hasattr(om, "output_success"), (
            "output_success 是死代码，应已删除，但仍存在于 output_manager 模块"
        )

    def test_output_languages_does_not_exist(self):
        """AC-OM-002: output_languages 不应存在于 output_manager 模块。"""
        import tree_sitter_analyzer.output_manager as om

        assert not hasattr(om, "output_languages"), (
            "output_languages 是死代码，应已删除，但仍存在于 output_manager 模块"
        )

    def test_output_queries_does_not_exist(self):
        """AC-OM-003: output_queries 不应存在于 output_manager 模块。"""
        import tree_sitter_analyzer.output_manager as om

        assert not hasattr(om, "output_queries"), (
            "output_queries 是死代码，应已删除，但仍存在于 output_manager 模块"
        )

    def test_output_manager_module_still_importable(self):
        """AC-OM-004: output_manager 模块删除死代码后仍可正常 import。"""
        import tree_sitter_analyzer.output_manager as om  # noqa: F401

        assert om is not None

    def test_output_manager_has_live_functions(self):
        """保留的活跃函数（output_info 等）仍存在。"""
        import tree_sitter_analyzer.output_manager as om

        # 这些函数有实际使用，应保留
        assert hasattr(om, "output_info"), "output_info 应保留"
        assert hasattr(om, "output_warning"), "output_warning 应保留"
        assert hasattr(om, "output_error"), "output_error 应保留"
