#!/usr/bin/env python3
"""
修复 A 验证：isinstance/issubclass 参数引用检测测试

覆盖规格：openspec/changes/fix-intelligence-graph/specs/false-positive-detection/spec.md
验收标准：AC-FP-003、AC-FP-004、AC-FP-005、AC-FP-006

关键场景：类在同一文件中通过 isinstance 引用（无 import 语句），
         应被识别为有引用，不出现在死代码列表。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.project_indexer import ProjectIndexer


class TestIsinstanceReferenceDetection:
    """isinstance/issubclass 参数中的类名应被计为引用。"""

    def test_isinstance_same_file_registers_reference(self, tmp_path):
        """AC-FP-003: 同文件中 isinstance(x, SomeClass) 应将 SomeClass 计为引用。

        场景：类和使用方在同一文件，无单独 import 语句。
        这是 MCPToolError/FileRestrictionError 误报的真实模式。
        """
        (tmp_path / "exc.py").write_text(
            "class AppError(Exception): pass\n"
            "\n"
            "def create_response(e):\n"
            "    if isinstance(e, AppError):\n"
            "        return 'error'\n"
        )

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        refs = indexer.symbol_index.lookup_references("AppError")
        assert len(refs) >= 1, (
            "同文件的 isinstance(e, AppError) 应将 AppError 注册为引用，"
            f"但引用列表为空（当前 refs={refs}）"
        )

    def test_issubclass_same_file_registers_reference(self, tmp_path):
        """AC-FP-004: 同文件中 issubclass(cls, SomeClass) 应将 SomeClass 计为引用。"""
        (tmp_path / "registry.py").write_text(
            "class BasePlugin: pass\n"
            "\n"
            "def validate(cls):\n"
            "    if issubclass(cls, BasePlugin):\n"
            "        return True\n"
        )

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        refs = indexer.symbol_index.lookup_references("BasePlugin")
        assert len(refs) >= 1, (
            "同文件的 issubclass(cls, BasePlugin) 应将 BasePlugin 注册为引用"
        )

    def test_isinstance_prevents_dead_code_false_positive(self, tmp_path):
        """AC-FP-005: 仅通过同文件 isinstance 引用的类不应出现在死代码列表中。

        模拟 exceptions.py 中 MCPToolError 的真实情形。
        """
        (tmp_path / "exceptions.py").write_text(
            "class SpecialError(Exception): pass\n"
            "\n"
            "def create_mcp_error_response(exception):\n"
            "    if isinstance(exception, SpecialError):\n"
            "        return {'error': 'special'}\n"
        )

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        m = ArchitectureMetrics(indexer.dep_graph, indexer.symbol_index)
        report = m.compute_report(".", checks=["dead_code"])

        assert "SpecialError" not in report.dead_symbols, (
            "仅通过同文件 isinstance 引用的类不应被判定为死代码，"
            f"但 SpecialError 出现在: {report.dead_symbols}"
        )

    def test_truly_unused_class_still_in_dead_symbols(self, tmp_path):
        """AC-FP-006: 真正未被引用的类仍应出现在死代码列表中。"""
        (tmp_path / "unused.py").write_text(
            "class TotallyUnused:\n"
            "    def method(self): pass\n"
        )

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        m = ArchitectureMetrics(indexer.dep_graph, indexer.symbol_index)
        report = m.compute_report(".", checks=["dead_code"])

        assert "TotallyUnused" in report.dead_symbols, (
            "未引用的类应出现在死代码列表中"
        )

    def test_isinstance_with_tuple_of_classes(self, tmp_path):
        """isinstance(x, (ClassA, ClassB)) 中两个类都应被计为引用。"""
        (tmp_path / "types_module.py").write_text(
            "class TypeA: pass\n"
            "class TypeB: pass\n"
            "\n"
            "def check(x):\n"
            "    return isinstance(x, (TypeA, TypeB))\n"
        )

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        refs_a = indexer.symbol_index.lookup_references("TypeA")
        refs_b = indexer.symbol_index.lookup_references("TypeB")
        assert len(refs_a) >= 1, "isinstance 元组中 TypeA 应被计为引用"
        assert len(refs_b) >= 1, "isinstance 元组中 TypeB 应被计为引用"
