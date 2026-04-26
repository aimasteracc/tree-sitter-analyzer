"""Tests for Method Chain Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.method_chain import (
    ChainHotspot,
    MethodChainAnalyzer,
    MethodChainResult,
    _severity,
)

ANALYZER = MethodChainAnalyzer


# ── Severity tests ──────────────────────────────────────────────────────


class TestSeverity:
    def test_ok_2(self) -> None:
        assert _severity(2) == "ok"

    def test_ok_3(self) -> None:
        assert _severity(3) == "ok"

    def test_long_chain_4(self) -> None:
        assert _severity(4) == "long_chain"

    def test_long_chain_5(self) -> None:
        assert _severity(5) == "long_chain"

    def test_train_wreck_6(self) -> None:
        assert _severity(6) == "train_wreck"

    def test_train_wreck_10(self) -> None:
        assert _severity(10) == "train_wreck"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_hotspot_frozen(self) -> None:
        h = ChainHotspot(
            line_number=10,
            chain_length=5,
            severity="long_chain",
            expression="a.b.c.d.e",
        )
        assert h.line_number == 10
        with pytest.raises(AttributeError):
            h.line_number = 5  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = MethodChainResult(
            max_chain_length=6,
            total_chains=3,
            hotspots=(),
            file_path="test.py",
        )
        assert result.max_chain_length == 6
        assert result.total_chains == 3

    def test_result_to_dict(self) -> None:
        result = MethodChainResult(
            max_chain_length=5,
            total_chains=2,
            hotspots=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["max_chain_length"] == 5
        assert d["total_chains"] == 2
        assert d["hotspot_count"] == 0


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_chains == 0


# ── Python tests ───────────────────────────────────────────────────────


class TestPythonChain:
    def test_no_chains(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.py"
        f.write_text("x = 1\ny = 2\nprint(x + y)\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_chains == 0
        assert result.max_chain_length == 0

    def test_simple_attribute(self, tmp_path: Path) -> None:
        f = tmp_path / "attr.py"
        f.write_text("x = obj.name\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_chains >= 1

    def test_three_level_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "three.py"
        f.write_text("x = obj.a.b.c\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 3

    def test_four_level_chain_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "four.py"
        f.write_text("x = obj.a.b.c.d\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4
        assert len(result.hotspots) >= 1
        assert result.hotspots[0].severity == "long_chain"

    def test_six_level_chain_train_wreck(self, tmp_path: Path) -> None:
        f = tmp_path / "train.py"
        f.write_text("x = obj.a.b.c.d.e.f\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 6
        assert any(h.severity == "train_wreck" for h in result.hotspots)

    def test_method_call_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "method.py"
        f.write_text("x = obj.get_a().get_b().get_c().get_d()\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_mixed_attr_method_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.py"
        f.write_text("x = obj.service.client.request.headers.content_type\n")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_multiple_independent_chains(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.py"
        f.write_text(
            "x = obj.a.b\n"
            "y = obj.c.d\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_chains >= 2

    def test_nested_in_function(self, tmp_path: Path) -> None:
        f = tmp_path / "func.py"
        f.write_text(
            "def process(data):\n"
            "    return data.get('key').items.first.value\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_chain_in_if(self, tmp_path: Path) -> None:
        f = tmp_path / "if_chain.py"
        f.write_text(
            "if obj.service.config.debug.verbose:\n"
            "    pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_two_level_not_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "two.py"
        f.write_text("x = obj.name\n")
        result = ANALYZER().analyze_file(f)
        assert len(result.hotspots) == 0


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptChain:
    def test_simple_member(self, tmp_path: Path) -> None:
        f = tmp_path / "test.js"
        f.write_text("const x = obj.name;")
        result = ANALYZER().analyze_file(f)
        assert result.total_chains >= 1

    def test_four_level_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "chain.js"
        f.write_text("const x = obj.a.b.c.d;")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4
        assert len(result.hotspots) >= 1

    def test_method_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "method.js"
        f.write_text("const x = obj.getA().getB().getC().getD();")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_train_wreck(self, tmp_path: Path) -> None:
        f = tmp_path / "wreck.js"
        f.write_text("const x = obj.a.b.c.d.e.f;")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 6

    def test_typescript_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ts"
        f.write_text("const x = obj.service.client.request.url;")
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_tsx_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "test.tsx"
        f.write_text(
            "const x = props.data.items.filter.map.length;"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaChain:
    def test_simple_field(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  String foo(Obj o) {\n"
            "    return o.name;\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_chains >= 1

    def test_four_level_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "Chain.java"
        f.write_text(
            "public class Chain {\n"
            "  String foo(Obj o) {\n"
            "    return o.getA().getB().getC().getD();\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_train_wreck(self, tmp_path: Path) -> None:
        f = tmp_path / "Wreck.java"
        f.write_text(
            "public class Wreck {\n"
            "  String foo(Obj o) {\n"
            "    return o.a.b.c.d.e.f;\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 6

    def test_mixed_field_method(self, tmp_path: Path) -> None:
        f = tmp_path / "Mixed.java"
        f.write_text(
            "public class Mixed {\n"
            "  String foo(Obj o) {\n"
            "    return o.getService().getClient().getRequest().getUrl();\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoChain:
    def test_simple_selector(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            "func foo(o Obj) string {\n"
            "    return o.Name\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_chains >= 1

    def test_four_level_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "chain.go"
        f.write_text(
            "package main\n\n"
            "func foo(o Obj) string {\n"
            "    return o.A.B.C.D\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_method_chain(self, tmp_path: Path) -> None:
        f = tmp_path / "method.go"
        f.write_text(
            "package main\n\n"
            "func foo(o Obj) string {\n"
            "    return o.GetA().GetB().GetC().GetD()\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 4

    def test_train_wreck(self, tmp_path: Path) -> None:
        f = tmp_path / "wreck.go"
        f.write_text(
            "package main\n\n"
            "func foo(o Obj) string {\n"
            "    return o.A.B.C.D.E.F\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.max_chain_length >= 6
