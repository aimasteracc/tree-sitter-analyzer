"""Tests for Cognitive Complexity Analyzer multi-language support."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.cognitive_complexity import (
    CognitiveComplexityAnalyzer,
)


@pytest.fixture
def analyzer() -> CognitiveComplexityAnalyzer:
    return CognitiveComplexityAnalyzer()


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── JavaScript / TypeScript ─────────────────────────────────────────────


class TestJSBasic:
    def test_empty_function(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function hello() {\n  return 'hello';\n}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.functions[0].total_complexity == 0
        assert result.functions[0].name == "hello"
        assert result.functions[0].element_type == "function"
        path.unlink()

    def test_if_else(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function check(x) {\n"
            "  if (x > 0) {\n"
            "    return true;\n"
            "  } else {\n"
            "    return false;\n"
            "  }\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, else: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_nested_if(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function nested(x, y) {\n"
            "  if (x > 0) {\n"
            "    if (y > 0) {\n"
            "      return x + y;\n"
            "    }\n"
            "  }\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # outer if: +1, inner if: +2 = total 3
        assert fc.total_complexity == 3
        path.unlink()

    def test_for_loop(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function sum(arr) {\n"
            "  let total = 0;\n"
            "  for (let i = 0; i < arr.length; i++) {\n"
            "    total += arr[i];\n"
            "  }\n"
            "  return total;\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_switch(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function classify(x) {\n"
            "  switch (x) {\n"
            "    case 1: return 'a';\n"
            "    case 2: return 'b';\n"
            "  }\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_try_catch(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function safeDiv(a, b) {\n"
            "  try {\n"
            "    return a / b;\n"
            "  } catch (e) {\n"
            "    return 0;\n"
            "  }\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # try: +1, catch: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_logical_and_or(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function check(a, b, c) {\n"
            "  if (a && b || c) {\n"
            "    return true;\n"
            "  }\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, && : +1, ||: +1 = total 3
        assert fc.total_complexity == 3
        path.unlink()

    def test_ternary(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function label(x) {\n"
            "  return x ? 'yes' : 'no';\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()


class TestJSClass:
    def test_method(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service {\n"
            "  process(data) {\n"
            "    if (data) {\n"
            "      return true;\n"
            "    }\n"
            "  }\n"
            "}\n", ".js"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "process"
        assert fc.element_type == "method"
        assert fc.total_complexity == 1
        path.unlink()

    def test_arrow_function(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "const fn = (x) => x > 0 ? x : -x;\n", ".js"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "<arrow>"
        assert fc.element_type == "arrow_function"
        assert fc.total_complexity == 1
        path.unlink()


class TestTypeScript:
    def test_typescript_function(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "function check(x: number): boolean {\n"
            "  if (x > 0) {\n"
            "    return true;\n"
            "  } else {\n"
            "    return false;\n"
            "  }\n"
            "}\n", ".ts"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 2
        path.unlink()


# ── Java ─────────────────────────────────────────────────────────────────


class TestJavaBasic:
    def test_empty_method(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service {\n"
            "  public void process() {\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.functions[0].total_complexity == 0
        assert result.functions[0].name == "process"
        assert result.functions[0].element_type == "method"
        path.unlink()

    def test_if_else(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service {\n"
            "  public boolean check(int x) {\n"
            "    if (x > 0) {\n"
            "      return true;\n"
            "    } else {\n"
            "      return false;\n"
            "    }\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, else: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_for_loop(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Calc {\n"
            "  public int sum(int[] arr) {\n"
            "    int total = 0;\n"
            "    for (int i = 0; i < arr.length; i++) {\n"
            "      total += arr[i];\n"
            "    }\n"
            "    return total;\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_nested_if_in_for(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Calc {\n"
            "  public int sumEven(int[] arr) {\n"
            "    int total = 0;\n"
            "    for (int i = 0; i < arr.length; i++) {\n"
            "      if (arr[i] % 2 == 0) {\n"
            "        total += arr[i];\n"
            "      }\n"
            "    }\n"
            "    return total;\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # for: +1, if inside for: +2 = total 3
        assert fc.total_complexity == 3
        path.unlink()

    def test_try_catch(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service {\n"
            "  public int safeDiv(int a, int b) {\n"
            "    try {\n"
            "      return a / b;\n"
            "    } catch (Exception e) {\n"
            "      return 0;\n"
            "    }\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # try: +1, catch: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_logical_ops(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service {\n"
            "  public boolean check(boolean a, boolean b) {\n"
            "    if (a && b) {\n"
            "      return true;\n"
            "    }\n"
            "    return false;\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, && : +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_ternary(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service {\n"
            "  public String label(int x) {\n"
            "    return x > 0 ? \"pos\" : \"neg\";\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_constructor(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Config {\n"
            "  public Config(String val) {\n"
            "    if (val != null) {\n"
            "      this.value = val;\n"
            "    }\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "<init>"
        assert fc.total_complexity == 1
        path.unlink()

    def test_multiple_methods(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Calc {\n"
            "  public int add(int a, int b) {\n"
            "    return a + b;\n"
            "  }\n"
            "  public int compute(int x) {\n"
            "    if (x > 0) {\n"
            "      return x * 2;\n"
            "    }\n"
            "    return 0;\n"
            "  }\n"
            "}\n", ".java"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 2
        path.unlink()


# ── Go ───────────────────────────────────────────────────────────────────


class TestGoBasic:
    def test_empty_function(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\nfunc hello() string {\n  return \"hello\"\n}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.functions[0].total_complexity == 0
        assert result.functions[0].name == "hello"
        assert result.functions[0].element_type == "function"
        path.unlink()

    def test_if_else(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\nfunc check(x int) bool {\n"
            "  if x > 0 {\n"
            "    return true\n"
            "  } else {\n"
            "    return false\n"
            "  }\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, else: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_for_loop(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\nfunc sum(arr []int) int {\n"
            "  total := 0\n"
            "  for _, v := range arr {\n"
            "    total += v\n"
            "  }\n"
            "  return total\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_nested_if_in_for(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\nfunc sumEven(arr []int) int {\n"
            "  total := 0\n"
            "  for _, v := range arr {\n"
            "    if v % 2 == 0 {\n"
            "      total += v\n"
            "    }\n"
            "  }\n"
            "  return total\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # for: +1, if inside for: +2 = total 3
        assert fc.total_complexity == 3
        path.unlink()

    def test_switch(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\nfunc classify(x int) string {\n"
            "  switch x {\n"
            "  case 1: return \"a\"\n"
            "  case 2: return \"b\"\n"
            "  }\n"
            "  return \"unknown\"\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_method(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\ntype Service struct{}\n\n"
            "func (s *Service) Process(x int) bool {\n"
            "  if x > 0 {\n"
            "    return true\n"
            "  }\n"
            "  return false\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "Process"
        assert fc.element_type == "method"
        assert fc.total_complexity == 1
        path.unlink()

    def test_logical_ops(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\nfunc check(a, b bool) bool {\n"
            "  if a && b {\n"
            "    return true\n"
            "  }\n"
            "  return false\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, && : +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_multiple_functions(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "package main\n\n"
            "func simple() int {\n  return 1\n}\n\n"
            "func complex_(x int) int {\n"
            "  if x > 0 {\n"
            "    for i := 0; i < x; i++ {\n"
            "      if i % 2 == 0 {\n"
            "        return i\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "  return 0\n"
            "}\n", ".go"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 2
        assert result.max_complexity == 6
        path.unlink()
