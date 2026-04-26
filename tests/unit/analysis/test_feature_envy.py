"""Tests for Feature Envy Analyzer."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.feature_envy import (
    ISSUE_FEATURE_ENVY,
    FeatureEnvyAnalyzer,
)

ANALYZER = FeatureEnvyAnalyzer()


class TestPythonFeatureEnvy:
    def test_feature_envy_detected(self, tmp_path: Path) -> None:
        code = (
            "class Order:\n"
            "    def __init__(self):\n"
            "        self.value = 0\n"
            "\n"
            "    def print_label(self, addr):\n"
            "        name = addr.name\n"
            "        street = addr.street\n"
            "        city = addr.city\n"
            "        zip_code = addr.zip\n"
            "        x = self.value\n"
        )
        f = tmp_path / "envy.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_FEATURE_ENVY for i in result.issues)

    def test_no_envy(self, tmp_path: Path) -> None:
        code = (
            "class Calculator:\n"
            "    def __init__(self):\n"
            "        self.value = 0\n"
            "\n"
            "    def add(self, x):\n"
            "        self.value = self.value + x\n"
            "        return self.value\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert not any(i.issue_type == ISSUE_FEATURE_ENVY for i in result.issues)


class TestJavaFeatureEnvy:
    def test_feature_envy_java(self, tmp_path: Path) -> None:
        code = (
            "public class Order {\n"
            "  private Customer customer;\n"
            "  public String printLabel() {\n"
            "    this.doSomething();\n"
            "    String n = customer.getName();\n"
            "    String c = customer.getCity();\n"
            "    String z = customer.getZip();\n"
            "    String s = customer.getStreet();\n"
            "    return n;\n"
            "  }\n"
            "  public void doSomething() {}\n"
            "}\n"
        )
        f = tmp_path / "Order.java"
        f.write_text(code)
        result = ANALYZER.analyze_file(f)
        assert any(i.issue_type == ISSUE_FEATURE_ENVY for i in result.issues)
