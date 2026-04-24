"""Neural Perception Engine — holistic codebase awareness.

Biological metaphor:
  Sensory Neurons  = individual analyzers (fire on specific patterns)
  Interneurons     = FindingCorrelator (connect findings by proximity)
  Synapses         = locations where 2+ neurons fire together
  Perception Map   = holistic view of what all neurons collectively detect

The engine dynamically discovers all BaseAnalyzer subclasses, runs applicable
ones on target files, and correlates findings into compound hotspots.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.base import (
    _EXTENSION_TO_LANGUAGE,
    BaseAnalyzer,
)
from tree_sitter_analyzer.analysis.finding_correlation import (
    FindingCorrelator,
    Hotspot,
    UnifiedFinding,
    normalize_findings,
)
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

_PACKAGE = "tree_sitter_analyzer.analysis"
_ANALYZE_METHODS = ("analyze_file", "detect_file", "analyze", "detect")


class NeuronCategory(Enum):
    SMELL = "smell"
    COMPLEXITY = "complexity"
    SECURITY = "security"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    NAMING = "naming"
    ERROR_HANDLING = "error_handling"
    DEAD_CODE = "dead_code"
    PROJECT = "project"
    META = "meta"


_CATEGORY_KEYWORDS: dict[NeuronCategory, tuple[str, ...]] = {
    NeuronCategory.TESTING: (
        "test_smell", "test_coverage", "test_flakiness", "assertion",
    ),
    NeuronCategory.SECURITY: (
        "security", "hardcoded", "regex_safety", "null_safety",
        "injection", "concurrency_safety",
    ),
    NeuronCategory.COMPLEXITY: (
        "complexity", "nesting", "cognitive", "boolean", "depth",
        "function_size", "long_parameter", "method_chain",
    ),
    NeuronCategory.DEAD_CODE: (
        "dead_", "unused", "import_sanitiz", "dead_code", "dead_store",
        "commented_code",
    ),
    NeuronCategory.ARCHITECTURE: (
        "architect", "circular", "coupling", "dependency", "solid",
        "design_pattern", "contract", "inheritance", "boundary",
        "parameter_coupling",
    ),
    NeuronCategory.ERROR_HANDLING: (
        "error", "exception", "return_path", "guard_clause",
    ),
    NeuronCategory.NAMING: (
        "naming", "comment", "doc_", "type_annotation", "magic_value",
    ),
    NeuronCategory.PROJECT: (
        "health_score", "ci_report", "change_impact", "refactor",
        "semantic_impact", "correlation", "code_clone", "call_graph",
    ),
    NeuronCategory.META: (
        "context_optim", "env_tracker", "llm_benchmark",
    ),
    NeuronCategory.SMELL: (
        "smell", "god_class", "lazy_class", "middle_man", "feature_envy",
        "parameter_coupling", "primitive_obsession", "speculative", "refused_bequest",
        "shotgun_surgery", "side_effect", "flag_argument",
    ),
}


def _classify_neuron(name: str) -> NeuronCategory:
    lowered = name.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return category
    return NeuronCategory.QUALITY


@dataclass(frozen=True)
class Neuron:
    """A single analyzer wrapped as a sensory neuron."""
    name: str
    category: NeuronCategory
    module_name: str
    class_name: str
    supported_extensions: frozenset[str]


@dataclass(frozen=True)
class PerceptionMap:
    """Holistic perception result from all neurons firing on one file."""
    file_path: str
    total_neurons: int
    fired_neurons: int
    total_findings: int
    severity_distribution: dict[str, int]
    category_coverage: dict[str, int]
    hotspots: tuple[Hotspot, ...]
    critical_hotspots: tuple[Hotspot, ...]
    perception_score: float

    @property
    def health_score(self) -> float:
        return round((1.0 - self.perception_score) * 100, 1)


@dataclass
class NeuralPerceptionResult:
    """Aggregated neural perception across multiple files."""
    file_maps: list[PerceptionMap]
    total_files: int
    total_neurons_available: int
    total_findings: int
    total_critical_hotspots: int
    top_hotspots: list[Hotspot]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_neurons": self.total_neurons_available,
            "total_findings": self.total_findings,
            "total_critical_hotspots": self.total_critical_hotspots,
            "top_hotspots": [
                {
                    "file": h.file_path,
                    "line": h.line,
                    "analyzer_count": h.analyzer_count,
                    "analyzer_names": h.analyzer_names,
                    "max_severity": h.max_severity.value,
                    "finding_types": h.finding_types,
                }
                for h in self.top_hotspots[:20]
            ],
            "file_summaries": [
                {
                    "file": m.file_path,
                    "active_neurons": m.total_neurons,
                    "fired_neurons": m.fired_neurons,
                    "total_findings": m.total_findings,
                    "health_score": m.health_score,
                    "critical_hotspots": len(m.critical_hotspots),
                }
                for m in self.file_maps
            ],
        }


class NeuralNetwork:
    """Discovers and manages all analyzer neurons."""

    def __init__(self) -> None:
        self._neurons: list[Neuron] = []
        self._discover()

    def _discover(self) -> None:
        import tree_sitter_analyzer.analysis as pkg
        for _importer, mod_name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            if is_pkg or mod_name.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"{_PACKAGE}.{mod_name}")
                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (isinstance(obj, type)
                            and issubclass(obj, BaseAnalyzer)
                            and obj is not BaseAnalyzer):
                        exts = frozenset(
                            getattr(
                                obj,
                                "SUPPORTED_EXTENSIONS",
                                _EXTENSION_TO_LANGUAGE.keys(),
                            )
                        )
                        self._neurons.append(Neuron(
                            name=mod_name,
                            category=_classify_neuron(mod_name),
                            module_name=mod_name,
                            class_name=attr_name,
                            supported_extensions=exts,
                        ))
            except Exception as e:
                logger.debug("Skip %s: %s", mod_name, e)

    @property
    def neurons(self) -> list[Neuron]:
        return list(self._neurons)

    @property
    def neuron_count(self) -> int:
        return len(self._neurons)

    @property
    def categories(self) -> dict[NeuronCategory, list[Neuron]]:
        result: dict[NeuronCategory, list[Neuron]] = defaultdict(list)
        for n in self._neurons:
            result[n.category].append(n)
        return dict(result)

    def neurons_for_file(self, file_path: str) -> list[Neuron]:
        ext = Path(file_path).suffix.lower()
        return [n for n in self._neurons if ext in n.supported_extensions]


class NeuralPerception:
    """The brain — runs all neurons and produces holistic perception."""

    def __init__(self) -> None:
        self._network = NeuralNetwork()

    @property
    def network(self) -> NeuralNetwork:
        return self._network

    def perceive_file(self, file_path: str) -> PerceptionMap:
        neurons = self._network.neurons_for_file(file_path)
        correlator = FindingCorrelator()
        fired = 0
        severity_dist: dict[str, int] = defaultdict(int)
        category_cov: dict[str, int] = defaultdict(int)

        for neuron in neurons:
            findings = self._fire_neuron(neuron, file_path)
            if findings:
                correlator.add_unified(findings)
                fired += 1
                category_cov[neuron.category.value] += 1
                for f in findings:
                    severity_dist[f.severity.value] += 1

        correlation = correlator.correlate()
        critical = correlation.critical_hotspots
        warning = correlation.warning_hotspots

        # perception_score: 0.0 (clean) to 1.0 (deeply flawed)
        score = min(
            1.0,
            (len(critical) * 0.15 + len(warning) * 0.05)
            / max(len(neurons), 1),
        )

        return PerceptionMap(
            file_path=file_path,
            total_neurons=len(neurons),
            fired_neurons=fired,
            total_findings=correlation.total_findings,
            severity_distribution=dict(severity_dist),
            category_coverage=dict(category_cov),
            hotspots=tuple(correlation.hotspots),
            critical_hotspots=tuple(critical),
            perception_score=score,
        )

    def perceive_files(self, file_paths: list[str]) -> NeuralPerceptionResult:
        maps: list[PerceptionMap] = []
        all_hotspots: list[Hotspot] = []

        for fp in file_paths:
            pmap = self.perceive_file(fp)
            maps.append(pmap)
            all_hotspots.extend(pmap.hotspots)

        all_hotspots.sort(
            key=lambda h: (h.analyzer_count, h.max_severity.value),
            reverse=True,
        )

        return NeuralPerceptionResult(
            file_maps=maps,
            total_files=len(file_paths),
            total_neurons_available=self._network.neuron_count,
            total_findings=sum(m.total_findings for m in maps),
            total_critical_hotspots=sum(
                len(m.critical_hotspots) for m in maps
            ),
            top_hotspots=all_hotspots[:20],
        )

    def perceive_self(self) -> NeuralPerceptionResult:
        """Perceive the project's own source code."""
        import tree_sitter_analyzer as pkg
        base = Path(pkg.__file__).parent
        py_files = sorted(
            str(p) for p in base.rglob("*.py")
            if not p.name.startswith("__pycache__")
        )
        return self.perceive_files(py_files)

    def _fire_neuron(
        self, neuron: Neuron, file_path: str
    ) -> list[UnifiedFinding] | None:
        try:
            module = importlib.import_module(
                f"{_PACKAGE}.{neuron.module_name}"
            )
            cls = getattr(module, neuron.class_name)
            instance = cls()

            result = None
            for method_name in _ANALYZE_METHODS:
                method = getattr(instance, method_name, None)
                if method is not None:
                    result = method(file_path)
                    break

            if result is None:
                return None

            return normalize_findings(neuron.name, result, file_path)
        except Exception as e:
            logger.debug(
                "Neuron %s failed on %s: %s", neuron.name, file_path, e
            )
            return None
