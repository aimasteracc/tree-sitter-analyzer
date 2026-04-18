"""Tests for Cognitive Complexity Analyzer (SonarSource spec)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.cognitive_complexity import (
    CognitiveComplexityAnalyzer,
    CognitiveComplexityResult,
    FunctionComplexity,
    _rating,
    RATING_SIMPLE,
    RATING_MODERATE,
    RATING_COMPLEX,
    RATING_VERY_COMPLEX,
    RATING_EXTREME,
)


@pytest.fixture
def analyzer() -> CognitiveComplexityAnalyzer:
    return CognitiveComplexityAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Rating function tests ──────────────────────────────────────────────


class TestRating:
    def test_simple(self) -> None:
        assert _rating(0) == RATING_SIMPLE
        assert _rating(1) == RATING_SIMPLE
        assert _rating(5) == RATING_SIMPLE

    def test_moderate(self) -> None:
        assert _rating(6) == RATING_MODERATE
        assert _rating(10) == RATING_MODERATE

    def test_complex(self) -> None:
        assert _rating(11) == RATING_COMPLEX
        assert _rating(20) == RATING_COMPLEX

    def test_very_complex(self) -> None:
        assert _rating(21) == RATING_VERY_COMPLEX
        assert _rating(50) == RATING_VERY_COMPLEX

    def test_extreme(self) -> None:
        assert _rating(51) == RATING_EXTREME
        assert _rating(100) == RATING_EXTREME


# ── Empty / edge case tests ────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/path.py")
        assert result.total_functions == 0
        assert result.total_complexity == 0

    def test_unsupported_extension(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp("int x = 1;", suffix=".c")
        result = analyzer.analyze_file(path)
        assert result.total_functions == 0
        path.unlink()

    def test_empty_file(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp("")
        result = analyzer.analyze_file(path)
        assert result.total_functions == 0
        assert result.total_complexity == 0
        path.unlink()

    def test_no_functions(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp("x = 42\ny = x + 1\n")
        result = analyzer.analyze_file(path)
        assert result.total_functions == 0
        path.unlink()


# ── Simple function tests ──────────────────────────────────────────────


class TestSimpleFunctions:
    def test_no_control_flow(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def hello():\n"
            "    return 'hello'\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.functions[0].total_complexity == 0
        assert result.functions[0].name == "hello"
        assert result.functions[0].element_type == "function"
        path.unlink()

    def test_single_if(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def check(x):\n"
            "    if x > 0:\n"
            "        return True\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.total_complexity == 1
        assert len(fc.increments) == 1
        assert fc.increments[0].increment_type == "nesting"
        path.unlink()

    def test_if_else(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def check(x):\n"
            "    if x > 0:\n"
            "        return True\n"
            "    else:\n"
            "        return False\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, else: +1 = total 2
        assert fc.total_complexity == 2
        assert len(fc.increments) == 2
        path.unlink()

    def test_if_elif_else(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def classify(x):\n"
            "    if x > 0:\n"
            "        return 'pos'\n"
            "    elif x < 0:\n"
            "        return 'neg'\n"
            "    else:\n"
            "        return 'zero'\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, elif: +1, else: +1 = total 3
        assert fc.total_complexity == 3
        path.unlink()

    def test_nested_if(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def nested(x, y):\n"
            "    if x > 0:\n"
            "        if y > 0:\n"
            "            return x + y\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # outer if: +1 (nesting=0), inner if: +2 (nesting=1) = total 3
        assert fc.total_complexity == 3
        assert fc.increments[0].value == 1
        assert fc.increments[1].value == 2
        path.unlink()


class TestLoops:
    def test_for_loop(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def sum_list(items):\n"
            "    total = 0\n"
            "    for item in items:\n"
            "        total += item\n"
            "    return total\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_while_loop(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def countdown(n):\n"
            "    while n > 0:\n"
            "        n -= 1\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        assert fc.total_complexity == 1
        path.unlink()

    def test_nested_loop(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def matrix_sum(grid):\n"
            "    total = 0\n"
            "    for row in grid:\n"
            "        for val in row:\n"
            "            total += val\n"
            "    return total\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # outer for: +1, inner for: +2 = total 3
        assert fc.total_complexity == 3
        path.unlink()


class TestTryExcept:
    def test_try_except(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def safe_div(a, b):\n"
            "    try:\n"
            "        return a / b\n"
            "    except ZeroDivisionError:\n"
            "        return 0\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # try: +1, except: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_try_multiple_except(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def safe_op(x):\n"
            "    try:\n"
            "        return risky(x)\n"
            "    except ValueError:\n"
            "        return -1\n"
            "    except TypeError:\n"
            "        return -2\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # try: +1, except1: +1, except2: +1 = total 3
        assert fc.total_complexity == 3
        path.unlink()


class TestLogicalOperators:
    def test_and(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def check(a, b):\n"
            "    if a and b:\n"
            "        return True\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, and: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_or(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def check(a, b):\n"
            "    if a or b:\n"
            "        return True\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, or: +1 = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_same_operator_sequence(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def check(a, b, c):\n"
            "    if a and b and c:\n"
            "        return True\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, and sequence: +1 (same op counted once) = total 2
        assert fc.total_complexity == 2
        path.unlink()

    def test_mixed_operators(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def check(a, b, c):\n"
            "    if a and b or c:\n"
            "        return True\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, and: +1, or: +1 (operator change) = total 3
        assert fc.total_complexity == 3
        path.unlink()


class TestTernary:
    def test_conditional_expression(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def label(x):\n"
            "    return 'yes' if x else 'no'\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # ternary: +1 (nesting=0) = total 1
        assert fc.total_complexity == 1
        path.unlink()

    def test_nested_ternary(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def label(x, y):\n"
            "    if x:\n"
            "        return 'a' if y else 'b'\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if: +1, ternary inside if: +2 (nesting=1) = total 3
        assert fc.total_complexity == 3
        path.unlink()


class TestComprehensions:
    def test_list_comprehension(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def squares(n):\n"
            "    return [x*x for x in range(n)]\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # list_comprehension: +1 (nesting=0) = total 1
        assert fc.total_complexity == 1
        path.unlink()

    def test_nested_comprehension_with_if(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def filtered_squares(n):\n"
            "    return [x*x for x in range(n) if x % 2 == 0]\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # list_comprehension: +1, if_clause inside comp: +2 (nesting=1) = total 3
        assert fc.total_complexity == 3
        path.unlink()


class TestMethods:
    def test_method_in_class(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Service:\n"
            "    def process(self, data):\n"
            "        if data:\n"
            "            return True\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "process"
        assert fc.element_type == "method"
        assert fc.total_complexity == 1
        path.unlink()

    def test_decorated_method(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Api:\n"
            "    @staticmethod\n"
            "    def handle(req):\n"
            "        if req.valid:\n"
            "            return req.data\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "handle"
        assert fc.element_type == "method"
        path.unlink()

    def test_static_and_instance(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "class Calc:\n"
            "    @staticmethod\n"
            "    def add(a, b):\n"
            "        return a + b\n"
            "\n"
            "    def compute(self, x):\n"
            "        if x > 0:\n"
            "            return x * 2\n"
            "        return 0\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 2
        names = [f.name for f in result.functions]
        assert "add" in names
        assert "compute" in names
        path.unlink()


class TestLambda:
    def test_simple_lambda(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "fn = lambda x: x * 2\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        fc = result.functions[0]
        assert fc.name == "<lambda>"
        assert fc.element_type == "lambda"
        assert fc.total_complexity == 0
        path.unlink()

    def test_lambda_with_if(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "fn = lambda x: x if x > 0 else -x\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # ternary in lambda: +1
        assert fc.total_complexity == 1
        path.unlink()


class TestMultipleFunctions:
    def test_two_functions(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def simple():\n"
            "    return 1\n"
            "\n"
            "def complex_fn(x):\n"
            "    if x > 0:\n"
            "        for i in range(x):\n"
            "            if i % 2 == 0:\n"
            "                pass\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 2
        assert result.max_complexity == 6  # if(+1) + for(+2) + if(+3) = 6
        path.unlink()

    def test_aggregate_stats(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def simple():\n"
            "    return 1\n"
            "\n"
            "def medium(x):\n"
            "    if x:\n"
            "        return x\n"
        )
        result = analyzer.analyze_file(path)
        assert result.total_functions == 2
        assert result.total_complexity == 1  # only medium has +1
        assert result.avg_complexity == 0.5
        assert result.max_complexity == 1
        path.unlink()


class TestGetComplexFunctions:
    def test_filter_by_threshold(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def simple():\n"
            "    return 1\n"
            "\n"
            "def bad(x):\n"
            "    if x > 0:\n"
            "        if x > 10:\n"
            "            if x > 100:\n"
            "                if x > 1000:\n"
            "                    return x\n"
            "    return 0\n"
        )
        result = analyzer.analyze_file(path)
        # bad: if(+1) + if(+2) + if(+3) + if(+4) = 10
        complex_fns = result.get_complex_functions(threshold=5)
        assert len(complex_fns) == 1
        assert complex_fns[0].name == "bad"
        path.unlink()


class TestDeepNesting:
    def test_triple_nested(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def deep(a, b, c):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                return True\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # if(+1) + if(+2) + if(+3) = 6
        assert fc.total_complexity == 6
        assert fc.rating == RATING_MODERATE
        path.unlink()

    def test_with_statement(self, analyzer: CognitiveComplexityAnalyzer) -> None:
        path = _write_tmp(
            "def read_config():\n"
            "    with open('config.yaml') as f:\n"
            "        if f:\n"
            "            return f.read()\n"
        )
        result = analyzer.analyze_file(path)
        fc = result.functions[0]
        # with: +1, if inside with: +2 = 3
        assert fc.total_complexity == 3
        path.unlink()
