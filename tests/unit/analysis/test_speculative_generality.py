"""Tests for Speculative Generality Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.speculative_generality import (
    ISSUE_SPECULATIVE_ABSTRACT,
    SpeculativeGeneralityAnalyzer,
)

ANALYZER = SpeculativeGeneralityAnalyzer()


class TestPythonSpeculativeGenerality:
    def test_speculative_abstract_class(self, tmp_path: Path) -> None:
        code = (
            "from abc import ABC, abstractmethod\n"
            "\n"
            "class BaseProcessor(ABC):\n"
            "    @abstractmethod\n"
            "    def process(self, data):\n"
            "        pass\n"
        )
        f = tmp_path / "abstract.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SPECULATIVE_ABSTRACT for i in result.issues
        )

    def test_concrete_class_not_flagged(self, tmp_path: Path) -> None:
        code = (
            "class Dog:\n"
            "    def speak(self):\n"
            "        return 'woof'\n"
        )
        f = tmp_path / "concrete.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert not any(
            i.issue_type == ISSUE_SPECULATIVE_ABSTRACT for i in result.issues
        )

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER.analyze_file(f)
        assert result.total_issues == 0


class TestJavaSpeculativeGenerality:
    def test_speculative_interface(self, tmp_path: Path) -> None:
        code = (
            "public interface Processor {\n"
            "  void process(String data);\n"
            "}\n"
        )
        f = tmp_path / "Processor.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SPECULATIVE_ABSTRACT for i in result.issues
        )


class TestGoSpeculativeGenerality:
    def test_speculative_interface_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'type Processor interface {\n'
            '    Process(data string)\n'
            '}\n'
        )
        f = tmp_path / "processor.go"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(
            i.issue_type == ISSUE_SPECULATIVE_ABSTRACT for i in result.issues
        )
