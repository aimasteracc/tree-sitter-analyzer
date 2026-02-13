#!/usr/bin/env python3
"""Tests for CycleDetector."""
import pytest
from tree_sitter_analyzer.intelligence.cycle_detector import CycleDetector


@pytest.fixture
def detector():
    return CycleDetector()


class TestCycleDetector:
    def test_no_cycles(self, detector):
        graph = {"a": ["b"], "b": ["c"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 0

    def test_simple_cycle(self, detector):
        graph = {"a": ["b"], "b": ["a"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 1
        assert cycles[0].length == 2

    def test_three_node_cycle(self, detector):
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 1
        assert cycles[0].length == 3

    def test_self_loop(self, detector):
        graph = {"a": ["a"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 1

    def test_multiple_cycles(self, detector):
        graph = {"a": ["b"], "b": ["a"], "c": ["d"], "d": ["c"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 2

    def test_empty_graph(self, detector):
        cycles = detector.detect_cycles({})
        assert cycles == []

    def test_no_edges(self, detector):
        graph = {"a": [], "b": []}
        cycles = detector.detect_cycles(graph)
        assert cycles == []

    def test_severity_large_cycle(self, detector):
        graph = {"a": ["b"], "b": ["c"], "c": ["d"], "d": ["a"]}
        cycles = detector.detect_cycles(graph)
        assert len(cycles) == 1
        assert cycles[0].severity == "error"  # > 3 nodes
