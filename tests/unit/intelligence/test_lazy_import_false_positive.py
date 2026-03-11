#!/usr/bin/env python3
"""
修复 A 验证：懒加载 import 误报修复测试

覆盖规格：openspec/changes/fix-intelligence-graph/specs/false-positive-detection/spec.md
验收标准：AC-FP-001、AC-FP-002、AC-FP-007

测试原则：单元测试，使用 tmp_path + 真实 tree-sitter 解析（unit/intelligence 现有惯例）
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.models import DependencyEdge
from tree_sitter_analyzer.intelligence.project_indexer import ProjectIndexer
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


# ---------------------------------------------------------------------------
# AC-FP-007：DependencyEdge.is_lazy_import 字段
# ---------------------------------------------------------------------------


class TestLazyImportEdgeModel:
    """DependencyEdge 应支持 is_lazy_import 标志。"""

    def test_default_edge_is_not_lazy(self):
        """AC-FP-007a: 默认 DependencyEdge.is_lazy_import 应为 False。"""
        edge = DependencyEdge("a.py", "b.py", "b")
        assert edge.is_lazy_import is False

    def test_lazy_import_edge_can_be_created(self):
        """AC-FP-007b: 可以创建 is_lazy_import=True 的 DependencyEdge。"""
        edge = DependencyEdge("a.py", "b.py", "b", is_lazy_import=True)
        assert edge.is_lazy_import is True

    def test_to_dict_includes_is_lazy_import(self):
        """AC-FP-007c: to_dict() 应包含 is_lazy_import 字段。"""
        edge = DependencyEdge("a.py", "b.py", "b", is_lazy_import=True)
        d = edge.to_dict()
        assert "is_lazy_import" in d
        assert d["is_lazy_import"] is True

    def test_to_dict_lazy_import_false(self):
        """to_dict() 中 is_lazy_import=False 也应出现（一致性）。"""
        edge = DependencyEdge("a.py", "b.py", "b")
        d = edge.to_dict()
        assert "is_lazy_import" in d
        assert d["is_lazy_import"] is False


# ---------------------------------------------------------------------------
# AC-FP-001、AC-FP-002：架构指标层过滤懒加载 import
# ---------------------------------------------------------------------------


class TestLazyImportCycleFiltering:
    """ArchitectureMetrics._detect_cycles 应忽略懒加载 import 边。"""

    def test_lazy_import_cycle_excluded(self):
        """AC-FP-001: 由懒加载 import 构成的循环依赖不应被报告。"""
        dg = DependencyGraphBuilder()
        si = SymbolIndex()
        # 正常 import: a -> b
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        # 懒加载（方法体内）import: b -> a
        dg.add_edge(DependencyEdge("b.py", "a.py", "a", is_lazy_import=True))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 0, (
            f"懒加载 import 不应触发循环依赖，但检测到: {report.cycles}"
        )

    def test_real_cycle_still_detected(self):
        """AC-FP-002: 真实顶层循环依赖仍应被正确报告。"""
        dg = DependencyGraphBuilder()
        si = SymbolIndex()
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        dg.add_edge(DependencyEdge("b.py", "a.py", "a"))  # 非懒加载

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 1, (
            f"真实循环依赖应被检测，实际报告: {report.cycles}"
        )

    def test_three_node_lazy_cycle_excluded(self):
        """三节点懒加载循环：只要有一条懒加载边断开循环，就不报告。"""
        dg = DependencyGraphBuilder()
        si = SymbolIndex()
        dg.add_edge(DependencyEdge("a.py", "b.py", "b"))
        dg.add_edge(DependencyEdge("b.py", "c.py", "c"))
        dg.add_edge(DependencyEdge("c.py", "a.py", "a", is_lazy_import=True))  # 懒加载

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 0

    def test_lazy_and_type_check_both_excluded(self):
        """懒加载 import 和 TYPE_CHECKING import 都应被排除。"""
        dg = DependencyGraphBuilder()
        si = SymbolIndex()
        # 场景：两个不同的"伪循环"
        dg.add_edge(DependencyEdge("x.py", "y.py", "y"))
        dg.add_edge(DependencyEdge("y.py", "x.py", "x", is_lazy_import=True))
        dg.add_edge(DependencyEdge("p.py", "q.py", "q"))
        dg.add_edge(DependencyEdge("q.py", "p.py", "p", is_type_check_only=True))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 0


# ---------------------------------------------------------------------------
# AC-FP-001（集成）：使用 ProjectIndexer 解析含懒加载 import 的真实文件
# ---------------------------------------------------------------------------


class TestLazyImportParsingIntegration:
    """ProjectIndexer 解析文件时，方法体内 import 应标记 is_lazy_import=True。"""

    def test_function_body_import_marked_as_lazy(self, tmp_path):
        """AC-FP-001 集成：方法内 import 生成的边应有 is_lazy_import=True。"""
        # 模拟 analysis_engine.py 的懒加载模式
        (tmp_path / "engine.py").write_text(
            "class Engine:\n"
            "    def init(self):\n"
            "        from detector import Detector\n"
            "        self.d = Detector()\n"
        )
        (tmp_path / "detector.py").write_text("class Detector: pass\n")

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        edges = indexer.dep_graph.get_edges()
        lazy_edges = [e for e in edges if e.is_lazy_import]
        assert len(lazy_edges) >= 1, (
            "方法体内的 import 应生成 is_lazy_import=True 的依赖边"
        )
        assert any(e.source_file == "engine.py" for e in lazy_edges)

    def test_top_level_import_not_marked_as_lazy(self, tmp_path):
        """顶层 import 不应被标记为懒加载。"""
        (tmp_path / "app.py").write_text("from utils import helper\n")
        (tmp_path / "utils.py").write_text("def helper(): pass\n")

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        edges = indexer.dep_graph.get_edges()
        for e in edges:
            if e.source_file == "app.py" and "utils" in (e.target_module or ""):
                assert not e.is_lazy_import, (
                    f"顶层 import 不应标记为懒加载，但发现: {e}"
                )

    def test_lazy_import_does_not_create_false_positive_cycle(self, tmp_path):
        """AC-FP-001 端到端：含懒加载循环的项目不应报告循环依赖。"""
        (tmp_path / "a.py").write_text(
            "from b import B\n"
            "class A: pass\n"
        )
        (tmp_path / "b.py").write_text(
            "class B:\n"
            "    def load(self):\n"
            "        from a import A\n"  # 懒加载 import
            "        return A()\n"
        )

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        from tree_sitter_analyzer.intelligence.architecture_metrics import (
            ArchitectureMetrics,
        )

        m = ArchitectureMetrics(indexer.dep_graph, indexer.symbol_index)
        report = m.compute_report(".", checks=["circular_dependencies"])
        assert len(report.cycles) == 0, (
            f"懒加载 import 循环不应被报告，但检测到: {[c.files for c in report.cycles]}"
        )
