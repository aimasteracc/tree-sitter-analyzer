#!/usr/bin/env python3
"""Tests for abstractness calculation in ArchitectureMetrics (C3)."""
import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.models import (
    DependencyEdge,
    SymbolDefinition,
)
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


@pytest.fixture
def components():
    dg = DependencyGraphBuilder()
    si = SymbolIndex()
    return dg, si


class TestAbstractness:
    """Abstractness should be computed from ABC/Protocol/abstractmethod ratio."""

    def test_module_with_abc_has_nonzero_abstractness(self, components):
        """A module containing ABC subclasses should have abstractness > 0."""
        dg, si = components
        # Abstract class in src/base.py
        si.add_definition(SymbolDefinition(
            "BaseHandler", "src/base.py", 1, 20, "class",
            modifiers=["ABC"],
        ))
        # Concrete class in src/impl.py
        si.add_definition(SymbolDefinition(
            "ConcreteHandler", "src/impl.py", 1, 30, "class",
        ))
        # Need edges so files appear in dep graph
        dg.add_edge(DependencyEdge("src/impl.py", "src/base.py", "base", ["BaseHandler"]))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["coupling_metrics"])
        src_metrics = report.module_metrics.get("src")
        assert src_metrics is not None, f"Expected 'src' module metrics, got {list(report.module_metrics.keys())}"
        assert src_metrics.abstractness > 0, f"Expected abstractness > 0, got {src_metrics.abstractness}"

    def test_pure_concrete_module_zero_abstractness(self, components):
        """A module with only concrete classes should have abstractness = 0."""
        dg, si = components
        si.add_definition(SymbolDefinition("Foo", "lib/foo.py", 1, 20, "class"))
        si.add_definition(SymbolDefinition("Bar", "lib/bar.py", 1, 20, "class"))
        dg.add_edge(DependencyEdge("lib/foo.py", "lib/bar.py", "bar"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("lib/", checks=["coupling_metrics"])
        lib_metrics = report.module_metrics.get("lib")
        assert lib_metrics is not None
        assert lib_metrics.abstractness == 0.0

    def test_stable_abstract_module_low_distance(self, components):
        """A stable (low I) and abstract (high A) module should have low D."""
        dg, si = components
        # All classes in this module are abstract
        si.add_definition(SymbolDefinition(
            "AbstractBase", "core/base.py", 1, 20, "class", modifiers=["ABC"],
        ))
        si.add_definition(SymbolDefinition(
            "AbstractProto", "core/proto.py", 1, 20, "class", modifiers=["Protocol"],
        ))
        # Many modules depend on core/ (high Ca), no outgoing (Ce=0)
        dg.add_edge(DependencyEdge("app/main.py", "core/base.py", "core.base", ["AbstractBase"]))
        dg.add_edge(DependencyEdge("app/service.py", "core/proto.py", "core.proto", ["AbstractProto"]))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["coupling_metrics"])
        core_metrics = report.module_metrics.get("core")
        assert core_metrics is not None
        # I = 0 (stable), A = 1.0 (all abstract) => D = |0 + 1 - 1| = 0
        assert core_metrics.abstractness == 1.0
        assert core_metrics.distance_from_main_sequence < 0.3

    def test_protocol_counted_as_abstract(self, components):
        """Classes with 'Protocol' modifier should count as abstract."""
        dg, si = components
        si.add_definition(SymbolDefinition(
            "MyProtocol", "src/proto.py", 1, 10, "class", modifiers=["Protocol"],
        ))
        si.add_definition(SymbolDefinition(
            "Concrete", "src/impl.py", 1, 10, "class",
        ))
        dg.add_edge(DependencyEdge("src/impl.py", "src/proto.py", "proto"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report("src/", checks=["coupling_metrics"])
        src_metrics = report.module_metrics.get("src")
        assert src_metrics is not None
        assert src_metrics.abstractness == 0.5  # 1 abstract / 2 total

    def test_no_classes_zero_abstractness(self, components):
        """Modules with no classes should have abstractness = 0."""
        dg, si = components
        si.add_definition(SymbolDefinition("func1", "utils/helper.py", 1, 5, "function"))
        dg.add_edge(DependencyEdge("main.py", "utils/helper.py", "utils.helper"))

        m = ArchitectureMetrics(dg, si)
        report = m.compute_report(".", checks=["coupling_metrics"])
        utils_metrics = report.module_metrics.get("utils")
        assert utils_metrics is not None
        assert utils_metrics.abstractness == 0.0
