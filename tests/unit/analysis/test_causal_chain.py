"""Tests for CausalChain — root cause analysis and impact prediction."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.analysis.causal_chain import (
    CausalChain,
    CausalResult,
    ImpactNode,
    ImpactResult,
    LeveragePoint,
)

_PREFIX = "/test/tree_sitter_analyzer/"


@pytest.fixture
def chain() -> CausalChain:
    return CausalChain(project_root="/test")


class TestCausalChainAnalyze:
    def test_empty_inputs(self, chain: CausalChain) -> None:
        result = chain.analyze({}, [])
        assert isinstance(result, CausalResult)
        assert result.leverage_points == []
        assert result.the_one_thread is None

    def test_pattern_leverage_point(self, chain: CausalChain) -> None:
        hotspots = [
            {"file": f"{_PREFIX}a.py", "analyzer_names": ["empty_block"]},
            {"file": f"{_PREFIX}b.py", "analyzer_names": ["empty_block"]},
            {"file": f"{_PREFIX}c.py", "analyzer_names": ["empty_block"]},
        ]
        result = chain.analyze({}, hotspots)
        assert len(result.leverage_points) >= 1
        pattern_lp = [
            lp for lp in result.leverage_points if lp.kind == "pattern"
        ]
        assert len(pattern_lp) >= 1
        assert pattern_lp[0].hotspot_count == 3

    def test_the_one_thread(self, chain: CausalChain) -> None:
        hotspots = [
            {"file": f"{_PREFIX}a.py", "analyzer_names": ["x"]},
            {"file": f"{_PREFIX}b.py", "analyzer_names": ["x"]},
            {"file": f"{_PREFIX}c.py", "analyzer_names": ["x"]},
            {"file": f"{_PREFIX}d.py", "analyzer_names": ["y"]},
        ]
        result = chain.analyze({}, hotspots)
        assert result.the_one_thread is not None
        assert result.the_one_thread.hotspot_count == 3


class TestPredictImpact:
    def _setup_imports(
        self, chain: CausalChain, imports: dict[str, set[str]]
    ) -> None:
        chain._import_graph = {}
        chain._reverse_imports = {}
        for src, targets in imports.items():
            chain._import_graph[src] = targets
            for t in targets:
                chain._reverse_imports.setdefault(t, set()).add(src)

    def test_no_dependents(self, chain: CausalChain) -> None:
        result = chain.predict_impact(f"{_PREFIX}isolated.py")
        assert isinstance(result, ImpactResult)
        assert result.total_affected_files == 0
        assert result.risk == "low"

    def test_direct_dependents(self, chain: CausalChain) -> None:
        self._setup_imports(chain, {
            "server.py": {"engine.py"},
            "api.py": {"engine.py"},
        })
        result = chain.predict_impact(f"{_PREFIX}engine.py")
        assert result.total_affected_files == 2
        assert any(n.kind == "direct_import" for n in result.code_impact)

    def test_transitive_dependents(self, chain: CausalChain) -> None:
        self._setup_imports(chain, {
            "server.py": {"engine.py"},
            "api.py": {"server.py"},
        })
        result = chain.predict_impact(f"{_PREFIX}engine.py")
        assert result.total_affected_files >= 2
        kinds = {n.kind for n in result.code_impact}
        assert "direct_import" in kinds
        assert "transitive" in kinds

    def test_risk_critical(self, chain: CausalChain) -> None:
        chain._reverse_imports["core.py"] = {f"dep_{i}.py" for i in range(20)}
        result = chain.predict_impact(f"{_PREFIX}core.py")
        assert result.risk == "critical"

    def test_risk_high(self, chain: CausalChain) -> None:
        chain._reverse_imports["core.py"] = {f"dep_{i}.py" for i in range(10)}
        result = chain.predict_impact(f"{_PREFIX}core.py")
        assert result.risk == "high"

    def test_risk_medium(self, chain: CausalChain) -> None:
        chain._reverse_imports["core.py"] = {f"dep_{i}.py" for i in range(5)}
        result = chain.predict_impact(f"{_PREFIX}core.py")
        assert result.risk == "medium"

    def test_to_dict_roundtrip(self, chain: CausalChain) -> None:
        chain._reverse_imports["core.py"] = {"a.py", "b.py"}
        result = chain.predict_impact(f"{_PREFIX}core.py")
        d = result.to_dict()
        assert "changed_file" in d
        assert "risk" in d
        assert "code_impact" in d
        assert "test_impact" in d
        assert "interface_impact" in d

    def test_mcp_interface_impact(self, chain: CausalChain) -> None:
        chain._reverse_imports["analysis/engine.py"] = {
            "mcp/tools/scan_tool.py",
            "mcp/server.py",
        }
        result = chain.predict_impact(f"{_PREFIX}analysis/engine.py")
        assert len(result.interface_impact) >= 1


class TestImpactNode:
    def test_creation(self) -> None:
        node = ImpactNode(
            file="test.py",
            kind="direct_import",
            distance=1,
            health=95.0,
            findings=2,
            imported_symbols=(),
        )
        assert node.file == "test.py"
        assert node.distance == 1


class TestLeveragePoint:
    def test_creation(self) -> None:
        lp = LeveragePoint(
            action="Fix all empty_block issues",
            kind="pattern",
            hotspot_count=5,
            file_count=3,
            affected_files=("a.py", "b.py", "c.py"),
            cascade="Fix empty_block in 3 files -> 5 hotspots disappear",
        )
        assert lp.kind == "pattern"
        assert lp.hotspot_count == 5
