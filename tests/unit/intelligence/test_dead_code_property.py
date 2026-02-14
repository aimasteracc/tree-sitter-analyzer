"""Tests for AH-011: Property-Aware Dead Code Detection."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.intelligence.architecture_metrics import ArchitectureMetrics
from tree_sitter_analyzer.intelligence.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.intelligence.models import SymbolDefinition
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


def _make_metrics_with_defs(definitions: list[SymbolDefinition]) -> ArchitectureMetrics:
    """Helper to build ArchitectureMetrics with pre-populated symbol index."""
    si = SymbolIndex()
    for d in definitions:
        si.add_definition(d)
    dg = DependencyGraphBuilder()
    return ArchitectureMetrics(dg, si)


class TestPropertyAwareDeadCode:
    """@property methods must not be reported as dead code."""

    def test_property_method_excluded_from_dead_code(self):
        """A @property method with no references should NOT be dead."""
        metrics = _make_metrics_with_defs([
            SymbolDefinition(
                name="instability",
                file_path="models.py",
                line=10,
                end_line=15,
                symbol_type="method",
                parent_class="ModuleMetrics",
                modifiers=["property"],
            ),
        ])
        dead = metrics._detect_dead_symbols()
        assert "instability" not in dead

    def test_staticmethod_excluded_from_dead_code(self):
        """A @staticmethod with no references should NOT be dead (accessed via class)."""
        metrics = _make_metrics_with_defs([
            SymbolDefinition(
                name="is_test_file",
                file_path="project_indexer.py",
                line=10,
                end_line=20,
                symbol_type="method",
                parent_class="ProjectIndexer",
                modifiers=["staticmethod"],
            ),
        ])
        dead = metrics._detect_dead_symbols()
        assert "is_test_file" not in dead

    def test_regular_method_still_detected_as_dead(self):
        """A regular method with no references IS dead."""
        metrics = _make_metrics_with_defs([
            SymbolDefinition(
                name="old_helper",
                file_path="utils.py",
                line=10,
                end_line=15,
                symbol_type="function",
                modifiers=[],
            ),
        ])
        dead = metrics._detect_dead_symbols()
        assert "old_helper" in dead

    def test_classmethod_excluded(self):
        """A @classmethod should not be reported as dead."""
        metrics = _make_metrics_with_defs([
            SymbolDefinition(
                name="from_config",
                file_path="factory.py",
                line=10,
                end_line=20,
                symbol_type="method",
                parent_class="Factory",
                modifiers=["classmethod"],
            ),
        ])
        dead = metrics._detect_dead_symbols()
        assert "from_config" not in dead

    def test_mixed_modifiers_with_property(self):
        """If modifiers contain 'property' among others, still excluded."""
        metrics = _make_metrics_with_defs([
            SymbolDefinition(
                name="distance_from_main_sequence",
                file_path="models.py",
                line=20,
                end_line=25,
                symbol_type="method",
                parent_class="ModuleMetrics",
                modifiers=["property"],
            ),
            SymbolDefinition(
                name="truly_dead",
                file_path="models.py",
                line=30,
                end_line=35,
                symbol_type="function",
                modifiers=[],
            ),
        ])
        dead = metrics._detect_dead_symbols()
        assert "distance_from_main_sequence" not in dead
        assert "truly_dead" in dead
