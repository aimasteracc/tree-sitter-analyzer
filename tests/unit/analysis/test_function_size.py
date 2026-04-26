"""Unit tests for FunctionSizeAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.function_size import (
    LOC_CRITICAL,
    LOC_GOOD,
    PARAM_CRITICAL,
    PARAM_GOOD,
    RATING_CRITICAL,
    RATING_GOOD,
    RATING_WARNING,
    FunctionSize,
    FunctionSizeAnalyzer,
    FunctionSizeResult,
    _size_rating,
)


@pytest.fixture
def analyzer() -> FunctionSizeAnalyzer:
    return FunctionSizeAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestSizeRating:
    def test_good(self) -> None:
        assert _size_rating(10, 2) == RATING_GOOD
        assert _size_rating(LOC_GOOD, PARAM_GOOD) == RATING_GOOD

    def test_warning_loc(self) -> None:
        assert _size_rating(LOC_GOOD + 1, 2) == RATING_WARNING
        assert _size_rating(LOC_CRITICAL, 2) == RATING_WARNING

    def test_critical_loc(self) -> None:
        assert _size_rating(LOC_CRITICAL + 1, 2) == RATING_CRITICAL

    def test_warning_params(self) -> None:
        assert _size_rating(10, PARAM_GOOD + 1) == RATING_WARNING
        assert _size_rating(10, PARAM_CRITICAL) == RATING_WARNING

    def test_critical_params(self) -> None:
        assert _size_rating(10, PARAM_CRITICAL + 1) == RATING_CRITICAL

    def test_loc_takes_priority(self) -> None:
        assert _size_rating(LOC_CRITICAL + 1, 1) == RATING_CRITICAL
        assert _size_rating(5, PARAM_CRITICAL + 1) == RATING_CRITICAL


class TestFunctionSizeDataclass:
    def test_to_dict(self) -> None:
        fs = FunctionSize(
            name="foo",
            start_line=1,
            end_line=10,
            loc=10,
            param_count=2,
            rating=RATING_GOOD,
            element_type="function",
        )
        d = fs.to_dict()
        assert d["name"] == "foo"
        assert d["loc"] == 10
        assert d["rating"] == RATING_GOOD

    def test_frozen(self) -> None:
        fs = FunctionSize(
            name="foo", start_line=1, end_line=5, loc=5,
            param_count=0, rating=RATING_GOOD, element_type="function",
        )
        with pytest.raises(AttributeError):
            fs.name = "bar"  # type: ignore[misc]


class TestFunctionSizeResultDataclass:
    def test_to_dict(self) -> None:
        r = FunctionSizeResult(
            functions=(),
            total_functions=0,
            oversized_functions=0,
            avg_loc=0.0,
            max_loc=0,
            max_params=0,
            file_path="test.py",
        )
        d = r.to_dict()
        assert d["total_functions"] == 0
        assert d["file_path"] == "test.py"

    def test_get_oversized(self) -> None:
        f1 = FunctionSize("a", 1, 5, 5, 1, RATING_GOOD, "function")
        f2 = FunctionSize("b", 1, 60, 60, 1, RATING_CRITICAL, "function")
        r = FunctionSizeResult(
            functions=(f1, f2), total_functions=2,
            oversized_functions=1, avg_loc=32.5, max_loc=60,
            max_params=1, file_path="test.py",
        )
        oversized = r.get_oversized()
        assert len(oversized) == 1
        assert oversized[0].name == "b"

    def test_get_high_param(self) -> None:
        f1 = FunctionSize("a", 1, 5, 5, 2, RATING_GOOD, "function")
        f2 = FunctionSize("b", 1, 5, 5, 7, RATING_CRITICAL, "function")
        r = FunctionSizeResult(
            functions=(f1, f2), total_functions=2,
            oversized_functions=1, avg_loc=5.0, max_loc=5,
            max_params=7, file_path="test.py",
        )
        high = r.get_high_param()
        assert len(high) == 1
        assert high[0].name == "b"


class TestPythonAnalysis:
    def test_simple_function(self, analyzer: FunctionSizeAnalyzer) -> None:
        path = _write_tmp("def hello():\n    print('hello')\n")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            fn = result.functions[0]
            assert fn.name == "hello"
            assert fn.loc == 2
            assert fn.param_count == 0
            assert fn.rating == RATING_GOOD
            assert fn.element_type == "function"
        finally:
            Path(path).unlink()

    def test_function_with_params(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = "def greet(name, greeting='hi'):\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].param_count == 2
        finally:
            Path(path).unlink()

    def test_method_in_class(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].element_type == "method"
            assert result.functions[0].name == "bar"
        finally:
            Path(path).unlink()

    def test_oversized_function(self, analyzer: FunctionSizeAnalyzer) -> None:
        lines = ["def big():"] + [f"    x = {i}" for i in range(60)]
        code = "\n".join(lines) + "\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            fn = result.functions[0]
            assert fn.loc > LOC_CRITICAL
            assert fn.rating == RATING_CRITICAL
            assert result.oversized_functions == 1
        finally:
            Path(path).unlink()

    def test_many_params(self, analyzer: FunctionSizeAnalyzer) -> None:
        params = ", ".join(f"p{i}" for i in range(8))
        code = f"def f({params}):\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].param_count == 8
            assert result.functions[0].rating == RATING_CRITICAL
        finally:
            Path(path).unlink()

    def test_multiple_functions(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "def small():\n"
            "    pass\n"
            "\n"
            "def medium(a, b, c):\n"
            "    x = 1\n"
            "    return x\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 2
            assert result.functions[0].name == "small"
            assert result.functions[1].name == "medium"
            assert result.max_params == 3
        finally:
            Path(path).unlink()

    def test_nested_functions(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "def outer():\n"
            "    def inner():\n"
            "        pass\n"
            "    return inner\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 2
            names = [f.name for f in result.functions]
            assert "outer" in names
            assert "inner" in names
        finally:
            Path(path).unlink()

    def test_decorator(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "@staticmethod\n"
            "def my_method():\n"
            "    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].name == "my_method"
        finally:
            Path(path).unlink()

    def test_warning_sized_function(self, analyzer: FunctionSizeAnalyzer) -> None:
        lines = ["def medium():"] + [f"    x = {i}" for i in range(25)]
        code = "\n".join(lines) + "\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].rating == RATING_WARNING
        finally:
            Path(path).unlink()

    def test_star_params(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = "def f(a, *args, **kwargs):\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].param_count == 3
        finally:
            Path(path).unlink()

    def test_class_with_init(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "class Foo:\n"
            "    def __init__(self, x):\n"
            "        self.x = x\n"
            "    def get(self):\n"
            "        return self.x\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 2
            for fn in result.functions:
                assert fn.element_type == "method"
        finally:
            Path(path).unlink()

    def test_avg_loc(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "def small():\n"
            "    pass\n"
            "\n"
            "def big():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 2
            assert result.avg_loc == 3.0
        finally:
            Path(path).unlink()


class TestJavaScriptAnalysis:
    def test_function_declaration(
        self, analyzer: FunctionSizeAnalyzer
    ) -> None:
        code = "function hello() {\n  console.log('hi');\n}\n"
        path = _write_tmp(code, ".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].name == "hello"
            assert result.functions[0].element_type == "function"
        finally:
            Path(path).unlink()

    def test_arrow_function(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = "const add = (a, b) => a + b;\n"
        path = _write_tmp(code, ".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions >= 1
            found = any(
                f.element_type == "arrow_function" for f in result.functions
            )
            assert found
        finally:
            Path(path).unlink()

    def test_method_definition(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "class Foo {\n"
            "  bar(x, y) {\n"
            "    return x + y;\n"
            "  }\n"
            "}\n"
        )
        path = _write_tmp(code, ".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].element_type == "method"
            assert result.functions[0].param_count == 2
        finally:
            Path(path).unlink()

    def test_oversized_js_function(
        self, analyzer: FunctionSizeAnalyzer
    ) -> None:
        lines = ["function big() {"]
        lines += [f"  var x{i} = {i};" for i in range(60)]
        lines.append("}")
        code = "\n".join(lines) + "\n"
        path = _write_tmp(code, ".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].rating == RATING_CRITICAL
        finally:
            Path(path).unlink()

    def test_typescript_file(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "function greet(name: string): string {\n"
            "  return 'Hello ' + name;\n"
            "}\n"
        )
        path = _write_tmp(code, ".ts")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].name == "greet"
        finally:
            Path(path).unlink()


class TestJavaAnalysis:
    def test_method(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() {\n"
            "    System.out.println(\"hello\");\n"
            "  }\n"
            "}\n"
        )
        path = _write_tmp(code, ".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].name == "bar"
            assert result.functions[0].element_type == "method"
        finally:
            Path(path).unlink()

    def test_constructor(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "public class Foo {\n"
            "  public Foo(int x) {\n"
            "    this.x = x;\n"
            "  }\n"
            "}\n"
        )
        path = _write_tmp(code, ".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].name == "<init>"
        finally:
            Path(path).unlink()

    def test_method_with_params(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "public class Foo {\n"
            "  public int add(int a, int b, int c) {\n"
            "    return a + b + c;\n"
            "  }\n"
            "}\n"
        )
        path = _write_tmp(code, ".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].param_count == 3
        finally:
            Path(path).unlink()

    def test_multiple_methods(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            "public class Service {\n"
            "  public void init() {}\n"
            "  public void process(String input) {\n"
            "    // 25+ lines\n"
            "  }\n"
            "}\n"
        )
        path = _write_tmp(code, ".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 2
        finally:
            Path(path).unlink()


class TestGoAnalysis:
    def test_function(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            'package main\n\n'
            'import "fmt"\n\n'
            'func hello() {\n'
            '\tfmt.Println("hello")\n'
            '}\n'
        )
        path = _write_tmp(code, ".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].name == "hello"
            assert result.functions[0].element_type == "function"
        finally:
            Path(path).unlink()

    def test_method(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            'package main\n\n'
            'type Server struct {}\n\n'
            'func (s *Server) Start() {\n'
            '\t// start\n'
            '}\n'
        )
        path = _write_tmp(code, ".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.total_functions == 1
            assert result.functions[0].element_type == "method"
            assert result.functions[0].name == "Start"
        finally:
            Path(path).unlink()

    def test_function_with_params(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            'package main\n\n'
            'func add(a int, b int) int {\n'
            '\treturn a + b\n'
            '}\n'
        )
        path = _write_tmp(code, ".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].param_count == 2
        finally:
            Path(path).unlink()

    def test_oversized_go_function(
        self, analyzer: FunctionSizeAnalyzer
    ) -> None:
        lines = ['package main\n', 'func big() {\n']
        lines += [f'\tx := {i}\n' for i in range(60)]
        lines.append('}\n')
        code = "".join(lines)
        path = _write_tmp(code, ".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].rating == RATING_CRITICAL
        finally:
            Path(path).unlink()

    def test_variadic_param(self, analyzer: FunctionSizeAnalyzer) -> None:
        code = (
            'package main\n\n'
            'func sum(nums ...int) int {\n'
            '\treturn 0\n'
            '}\n'
        )
        path = _write_tmp(code, ".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.functions[0].param_count == 1
        finally:
            Path(path).unlink()
