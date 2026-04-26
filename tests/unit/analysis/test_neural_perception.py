"""Tests for neural perception engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.neural_perception import (
    NeuralNetwork,
    NeuralPerception,
    Neuron,
    NeuronCategory,
    PerceptionMap,
    _classify_neuron,
)


class TestNeuronClassification:
    def test_smell_category(self):
        assert _classify_neuron("god_class") == NeuronCategory.SMELL
        assert _classify_neuron("side_effect") == NeuronCategory.SMELL

    def test_complexity_category(self):
        assert _classify_neuron("cognitive_complexity") == NeuronCategory.COMPLEXITY
        assert _classify_neuron("nesting_depth") == NeuronCategory.COMPLEXITY

    def test_security_category(self):
        assert _classify_neuron("security_scan") == NeuronCategory.SECURITY

    def test_testing_category(self):
        assert _classify_neuron("test_smells") == NeuronCategory.TESTING

    def test_quality_fallback(self):
        assert _classify_neuron("some_random_analyzer") == NeuronCategory.QUALITY


class TestNeuralNetwork:
    def test_discovers_analyzers(self):
        network = NeuralNetwork()
        assert network.neuron_count > 0

    def test_categories_populated(self):
        network = NeuralNetwork()
        cats = network.categories
        assert len(cats) > 0

    def test_neurons_for_python_file(self):
        network = NeuralNetwork()
        neurons = network.neurons_for_file("example.py")
        assert len(neurons) > 0
        for n in neurons:
            assert ".py" in n.supported_extensions or any(
                e in n.supported_extensions for e in (".py",)
            )

    def test_neurons_for_unsupported_file(self):
        network = NeuralNetwork()
        neurons = network.neurons_for_file("example.xyz")
        assert len(neurons) == 0

    def test_neurons_are_immutable(self):
        network = NeuralNetwork()
        neurons = network.neurons
        assert isinstance(neurons, list)
        assert all(isinstance(n, Neuron) for n in neurons)


class TestNeuralPerception:
    @pytest.fixture
    def sample_py(self, tmp_path: Path) -> str:
        code = '''
def deeply_nested(x):
    if x > 0:
        if x > 10:
            if x > 100:
                if x > 1000:
                    for i in range(x):
                        if i % 2 == 0:
                            pass
    return x

class GodClass:
    def method_a(self): pass
    def method_b(self): pass
    def method_c(self): pass
    def method_d(self): pass
    def method_e(self): pass
    def method_f(self): pass
    def method_g(self): pass
    def method_h(self): pass
    def method_i(self): pass
    def method_j(self): pass
'''
        p = tmp_path / "sample.py"
        p.write_text(code)
        return str(p)

    def test_perceive_file(self, sample_py: str):
        perception = NeuralPerception()
        pmap = perception.perceive_file(sample_py)
        assert isinstance(pmap, PerceptionMap)
        assert pmap.file_path == sample_py
        assert pmap.total_neurons > 0
        assert pmap.fired_neurons >= 0
        assert 0.0 <= pmap.perception_score <= 1.0
        assert 0.0 <= pmap.health_score <= 100.0

    def test_perceive_files(self, sample_py: str):
        perception = NeuralPerception()
        result = perception.perceive_files([sample_py])
        assert result.total_files == 1
        assert result.total_neurons_available > 0
        assert result.total_findings >= 0
        assert isinstance(result.top_hotspots, list)

    def test_perceive_result_to_dict(self, sample_py: str):
        perception = NeuralPerception()
        result = perception.perceive_files([sample_py])
        d = result.to_dict()
        assert "total_files" in d
        assert "total_neurons" in d
        assert "top_hotspots" in d
        assert "file_summaries" in d

    def test_perception_map_immutable(self, sample_py: str):
        perception = NeuralPerception()
        pmap = perception.perceive_file(sample_py)
        assert isinstance(pmap.hotspots, tuple)
        assert isinstance(pmap.critical_hotspots, tuple)

    @pytest.mark.slow
    def test_self_perception(self):
        perception = NeuralPerception()
        result = perception.perceive_self()
        assert result.total_files > 0
        assert result.total_neurons_available > 0


class TestPerceptionMapProperties:
    def test_health_score_inverses_perception(self):
        pmap = PerceptionMap(
            file_path="test.py",
            total_neurons=10,
            fired_neurons=5,
            total_findings=20,
            severity_distribution={},
            category_coverage={},
            hotspots=(),
            critical_hotspots=(),
            perception_score=0.3,
        )
        assert pmap.health_score == 70.0

    def test_perfect_health(self):
        pmap = PerceptionMap(
            file_path="test.py",
            total_neurons=10,
            fired_neurons=0,
            total_findings=0,
            severity_distribution={},
            category_coverage={},
            hotspots=(),
            critical_hotspots=(),
            perception_score=0.0,
        )
        assert pmap.health_score == 100.0
