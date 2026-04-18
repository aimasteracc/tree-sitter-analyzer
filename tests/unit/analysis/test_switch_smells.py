"""Tests for Switch Smell Analyzer — Python + Multi-Language."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.switch_smells import (
    SwitchSmellAnalyzer,
    SwitchSmellResult,
    SwitchStatement,
    _rating,
)

ANALYZER = SwitchSmellAnalyzer


# ── Rating tests ────────────────────────────────────────────────────────


class TestRating:
    def test_good_2(self) -> None:
        assert _rating(2) == "good"

    def test_good_3(self) -> None:
        assert _rating(3) == "good"

    def test_warning_4(self) -> None:
        assert _rating(4) == "warning"

    def test_critical_5(self) -> None:
        assert _rating(5) == "critical"

    def test_critical_10(self) -> None:
        assert _rating(10) == "critical"


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_switch_statement_frozen(self) -> None:
        s = SwitchStatement(
            line_number=10, case_count=3, has_default=True,
            smell_type="too_many_cases", statement_type="switch",
        )
        assert s.line_number == 10
        with pytest.raises(AttributeError):
            s.line_number = 5  # type: ignore[misc]

    def test_result_properties(self) -> None:
        result = SwitchSmellResult(
            total_switches=3,
            smelly_switches=1,
            switches=(),
            file_path="test.py",
        )
        assert result.total_switches == 3
        assert result.smelly_switches == 1


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_switches == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("case x; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_switches == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_switches == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_switches == 0


# ── Python tests (match statement) ─────────────────────────────────────


class TestPythonMatch:
    def test_no_match(self, tmp_path: Path) -> None:
        f = tmp_path / "nomatch.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_switches == 0

    def test_small_match(self, tmp_path: Path) -> None:
        f = tmp_path / "small.py"
        f.write_text(
            "match x:\n"
            "    case 1:\n"
            "        pass\n"
            "    case 2:\n"
            "        pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1
        assert result.smelly_switches == 0

    def test_large_match(self, tmp_path: Path) -> None:
        f = tmp_path / "large.py"
        f.write_text(
            "match x:\n"
            "    case 1: pass\n"
            "    case 2: pass\n"
            "    case 3: pass\n"
            "    case 4: pass\n"
            "    case 5: pass\n"
            "    case 6: pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1
        assert result.smelly_switches >= 1
        assert result.switches[0].case_count >= 6

    def test_match_with_default(self, tmp_path: Path) -> None:
        f = tmp_path / "default.py"
        f.write_text(
            "match x:\n"
            "    case 1: pass\n"
            "    case 2: pass\n"
            "    case _:\n"
            "        pass\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1
        default_switches = [s for s in result.switches if s.has_default]
        assert len(default_switches) >= 1

    def test_match_without_default(self, tmp_path: Path) -> None:
        f = tmp_path / "nodefault.py"
        f.write_text(
            "match x:\n"
            "    case 1: pass\n"
            "    case 2: pass\n"
        )
        result = ANALYZER().analyze_file(f)
        no_default = [s for s in result.switches if not s.has_default]
        assert len(no_default) >= 1


# ── JavaScript / TypeScript tests ──────────────────────────────────────


class TestJavaScriptSwitch:
    def test_small_switch(self, tmp_path: Path) -> None:
        f = tmp_path / "test.js"
        f.write_text(
            "switch(x) {\n"
            "  case 1: break;\n"
            "  case 2: break;\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1
        assert result.smelly_switches == 0

    def test_large_switch(self, tmp_path: Path) -> None:
        f = tmp_path / "large.js"
        f.write_text(
            "switch(x) {\n"
            "  case 1: break;\n"
            "  case 2: break;\n"
            "  case 3: break;\n"
            "  case 4: break;\n"
            "  case 5: break;\n"
            "  case 6: break;\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1
        assert result.smelly_switches >= 1

    def test_switch_with_default(self, tmp_path: Path) -> None:
        f = tmp_path / "default.js"
        f.write_text(
            "switch(x) {\n"
            "  case 1: break;\n"
            "  default: break;\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        default_switches = [s for s in result.switches if s.has_default]
        assert len(default_switches) >= 1

    def test_switch_without_default(self, tmp_path: Path) -> None:
        f = tmp_path / "nodefault.js"
        f.write_text(
            "switch(x) {\n"
            "  case 1: break;\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        no_default = [s for s in result.switches if not s.has_default]
        assert len(no_default) >= 1


# ── Java tests ─────────────────────────────────────────────────────────


class TestJavaSwitch:
    def test_small_switch(self, tmp_path: Path) -> None:
        f = tmp_path / "Test.java"
        f.write_text(
            "public class Test {\n"
            "  void foo(int x) {\n"
            "    switch(x) {\n"
            "      case 1: break;\n"
            "      case 2: break;\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1

    def test_large_switch(self, tmp_path: Path) -> None:
        f = tmp_path / "Large.java"
        f.write_text(
            "public class Large {\n"
            "  void foo(int x) {\n"
            "    switch(x) {\n"
            "      case 1: break;\n"
            "      case 2: break;\n"
            "      case 3: break;\n"
            "      case 4: break;\n"
            "      case 5: break;\n"
            "      case 6: break;\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        assert result.smelly_switches >= 1

    def test_switch_with_default(self, tmp_path: Path) -> None:
        f = tmp_path / "Default.java"
        f.write_text(
            "public class Default {\n"
            "  void foo(int x) {\n"
            "    switch(x) {\n"
            "      case 1: break;\n"
            "      default: break;\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = ANALYZER().analyze_file(f)
        default_switches = [s for s in result.switches if s.has_default]
        assert len(default_switches) >= 1


# ── Go tests ───────────────────────────────────────────────────────────


class TestGoSwitch:
    def test_small_switch(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\n"
            "func foo(x int) {\n"
            "    switch x {\n"
            "    case 1: return\n"
            "    case 2: return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1

    def test_large_switch(self, tmp_path: Path) -> None:
        f = tmp_path / "large.go"
        f.write_text(
            "package main\n\n"
            "func foo(x int) {\n"
            "    switch x {\n"
            "    case 1: return\n"
            "    case 2: return\n"
            "    case 3: return\n"
            "    case 4: return\n"
            "    case 5: return\n"
            "    case 6: return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.smelly_switches >= 1

    def test_switch_with_default(self, tmp_path: Path) -> None:
        f = tmp_path / "default.go"
        f.write_text(
            "package main\n\n"
            "func foo(x int) {\n"
            "    switch x {\n"
            "    case 1: return\n"
            "    default: return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        default_switches = [s for s in result.switches if s.has_default]
        assert len(default_switches) >= 1

    def test_select_statement(self, tmp_path: Path) -> None:
        f = tmp_path / "select.go"
        f.write_text(
            "package main\n\n"
            'import "sync"\n\n'
            "func foo(ch chan int) {\n"
            "    select {\n"
            "    case <-ch: return\n"
            "    default: return\n"
            "    }\n"
            "}\n"
        )
        result = ANALYZER().analyze_file(f)
        assert result.total_switches >= 1
