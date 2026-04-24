"""Tests for Parameter Coupling Analyzer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.parameter_coupling import (
    CouplingResult,
    DataClump,
    FunctionSignature,
    ParameterCouplingAnalyzer,
    ParameterInfo,
    _jaccard_similarity,
)

# --- Helpers ---


def _write_temp(content: str, suffix: str = ".py") -> Path:
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / f"test_file{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


# --- ParameterInfo Tests ---


class TestParameterInfo:
    def test_basic_param(self) -> None:
        p = ParameterInfo(name="x", position=0)
        assert p.name == "x"
        assert p.position == 0
        assert p.type_annotation is None
        assert not p.is_variadic
        assert not p.is_optional

    def test_typed_param(self) -> None:
        p = ParameterInfo(name="items", type_annotation="list[str]", position=1)
        assert p.type_annotation == "list[str]"

    def test_variadic_param(self) -> None:
        p = ParameterInfo(name="args", position=2, is_variadic=True)
        assert p.is_variadic

    def test_optional_param(self) -> None:
        p = ParameterInfo(name="debug", position=3, is_optional=True, default_value="False")
        assert p.is_optional
        assert p.default_value == "False"

    def test_frozen(self) -> None:
        p = ParameterInfo(name="x", position=0)
        with pytest.raises(AttributeError):
            p.name = "y"  # type: ignore[misc]


# --- FunctionSignature Tests ---


class TestFunctionSignature:
    def test_param_count(self) -> None:
        sig = FunctionSignature(
            name="foo",
            file_path="test.py",
            line_number=1,
            parameters=(
                ParameterInfo(name="a", position=0),
                ParameterInfo(name="b", position=1),
                ParameterInfo(name="c", position=2),
            ),
        )
        assert sig.param_count == 3

    def test_param_names(self) -> None:
        sig = FunctionSignature(
            name="foo",
            file_path="test.py",
            line_number=1,
            parameters=(
                ParameterInfo(name="a", position=0),
                ParameterInfo(name="b", position=1),
            ),
        )
        assert sig.param_names == frozenset({"a", "b"})

    def test_has_many_params_true(self) -> None:
        params = tuple(ParameterInfo(name=f"p{i}", position=i) for i in range(7))
        sig = FunctionSignature(name="big", file_path="test.py", line_number=1, parameters=params)
        assert sig.has_many_params

    def test_has_many_params_false(self) -> None:
        params = tuple(ParameterInfo(name=f"p{i}", position=i) for i in range(3))
        sig = FunctionSignature(name="small", file_path="test.py", line_number=1, parameters=params)
        assert not sig.has_many_params

    def test_empty_params(self) -> None:
        sig = FunctionSignature(name="no_args", file_path="test.py", line_number=1, parameters=())
        assert sig.param_count == 0
        assert sig.param_names == frozenset()


# --- Jaccard Similarity Tests ---


class TestJaccardSimilarity:
    def test_identical_sets(self) -> None:
        assert _jaccard_similarity(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0

    def test_disjoint_sets(self) -> None:
        assert _jaccard_similarity(frozenset({"a"}), frozenset({"b"})) == 0.0

    def test_partial_overlap(self) -> None:
        sim = _jaccard_similarity(frozenset({"a", "b", "c"}), frozenset({"b", "c", "d"}))
        assert 0.0 < sim < 1.0
        assert abs(sim - 0.5) < 0.01

    def test_empty_sets(self) -> None:
        assert _jaccard_similarity(frozenset(), frozenset()) == 1.0

    def test_one_empty(self) -> None:
        assert _jaccard_similarity(frozenset({"a"}), frozenset()) == 0.0


# --- CouplingResult Tests ---


class TestCouplingResult:
    def test_empty_result(self) -> None:
        result = CouplingResult(
            functions=(),
            high_param_functions=(),
            data_clumps=(),
            total_functions=0,
            total_parameters=0,
            avg_params_per_function=0.0,
        )
        assert result.total_functions == 0
        assert result.get_warnings() == []

    def test_warnings_high_params(self) -> None:
        func = FunctionSignature(
            name="big_func",
            file_path="test.py",
            line_number=10,
            parameters=tuple(ParameterInfo(name=f"p{i}", position=i) for i in range(8)),
        )
        result = CouplingResult(
            functions=(func,),
            high_param_functions=(func,),
            data_clumps=(),
            total_functions=1,
            total_parameters=8,
            avg_params_per_function=8.0,
        )
        warnings = result.get_warnings()
        assert len(warnings) == 1
        assert "big_func" in warnings[0]
        assert "8 parameters" in warnings[0]

    def test_warnings_data_clump(self) -> None:
        func1 = FunctionSignature(
            name="func_a", file_path="a.py", line_number=1,
            parameters=tuple(ParameterInfo(name=n, position=i) for i, n in enumerate(["user", "config", "logger", "db"])),
        )
        func2 = FunctionSignature(
            name="func_b", file_path="b.py", line_number=5,
            parameters=tuple(ParameterInfo(name=n, position=i) for i, n in enumerate(["user", "config", "logger", "cache"])),
        )
        clump = DataClump(
            param_names=frozenset({"user", "config", "logger"}),
            functions=(func1, func2),
            similarity=0.75,
        )
        result = CouplingResult(
            functions=(func1, func2),
            high_param_functions=(),
            data_clumps=(clump,),
            total_functions=2,
            total_parameters=8,
            avg_params_per_function=4.0,
        )
        warnings = result.get_warnings()
        assert any("Data Clump" in w for w in warnings)


# --- Python Analysis Tests ---


class TestPythonAnalysis:
    def test_simple_function(self) -> None:
        path = _write_temp("def hello(name, greeting):\n    pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 2

    def test_no_params(self) -> None:
        path = _write_temp("def nothing():\n    pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 0
        assert result.avg_params_per_function == 0.0

    def test_many_params_triggers_warning(self) -> None:
        params = ", ".join(f"p{i}" for i in range(8))
        path = _write_temp(f"def big({params}):\n    pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert len(result.high_param_functions) == 1
        assert result.high_param_functions[0].param_count == 8

    def test_typed_parameters(self) -> None:
        path = _write_temp("def typed(x: int, y: str, z: list[int]):\n    pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 3
        params = result.functions[0].parameters
        assert params[0].type_annotation == "int"
        assert params[1].type_annotation == "str"

    def test_default_parameters(self) -> None:
        path = _write_temp("def defaults(x, y=10, z='hello'):\n    pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_parameters == 3
        params = result.functions[0].parameters
        assert params[1].default_value is not None
        assert params[2].default_value is not None

    def test_class_methods(self) -> None:
        code = (
            "class Foo:\n"
            "    def __init__(self, x, y):\n"
            "        pass\n"
            "    def method(self, z):\n"
            "        pass\n"
        )
        path = _write_temp(code)
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 2
        element_types = {f.element_type for f in result.functions}
        assert "constructor" in element_types
        assert "method" in element_types

    def test_variadic_args(self) -> None:
        path = _write_temp("def variadic(x, *args, **kwargs):\n    pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        params = result.functions[0].parameters
        variadic_params = [p for p in params if p.is_variadic]
        assert len(variadic_params) == 2

    def test_data_clump_detection(self) -> None:
        code = (
            "def process(user, config, logger, data):\n"
            "    pass\n"
            "def validate(user, config, logger, schema):\n"
            "    pass\n"
            "def export(user, config, logger, fmt):\n"
            "    pass\n"
        )
        path = _write_temp(code)
        analyzer = ParameterCouplingAnalyzer(min_clump_size=3, clump_threshold=0.5)
        result = analyzer.analyze_file(path)
        assert len(result.data_clumps) >= 1
        clump = result.data_clumps[0]
        assert "user" in clump.param_names
        assert "config" in clump.param_names
        assert "logger" in clump.param_names

    def test_no_clump_below_threshold(self) -> None:
        code = (
            "def func_a(x, y, z):\n    pass\n"
            "def func_b(a, b, c):\n    pass\n"
        )
        path = _write_temp(code)
        analyzer = ParameterCouplingAnalyzer(min_clump_size=3, clump_threshold=0.5)
        result = analyzer.analyze_file(path)
        assert len(result.data_clumps) == 0

    def test_multiple_functions(self) -> None:
        code = (
            "def foo(a, b):\n    pass\n"
            "def bar(x, y, z):\n    pass\n"
            "def baz(p):\n    pass\n"
        )
        path = _write_temp(code)
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 3
        assert result.total_parameters == 6
        assert abs(result.avg_params_per_function - 2.0) < 0.01

    def test_nonexistent_file(self) -> None:
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_functions == 0

    def test_unsupported_extension(self) -> None:
        path = _write_temp("def foo(): pass\n", suffix=".rs")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 0


# --- JS/TS Analysis Tests ---


class TestJsTsAnalysis:
    def test_js_function(self) -> None:
        code = "function greet(name, greeting) {\n  return greeting + name;\n}\n"
        path = _write_temp(code, suffix=".js")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 2

    def test_js_arrow_function(self) -> None:
        code = "const add = (a, b) => a + b;\n"
        path = _write_temp(code, suffix=".js")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions >= 1
        assert any(f.name == "<arrow>" for f in result.functions)

    def test_js_method(self) -> None:
        code = (
            "class Foo {\n"
            "  bar(x, y, z) {\n"
            "    return x + y + z;\n"
            "  }\n"
            "}\n"
        )
        path = _write_temp(code, suffix=".js")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions >= 1
        methods = [f for f in result.functions if f.element_type == "method"]
        assert len(methods) >= 1

    def test_ts_typed_params(self) -> None:
        code = "function typed(x: number, y: string): void {}\n"
        path = _write_temp(code, suffix=".ts")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 2

    def test_ts_optional_params(self) -> None:
        code = "function opts(x: number, y?: string): void {}\n"
        path = _write_temp(code, suffix=".ts")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_parameters == 2
        optional_params = [p for p in result.functions[0].parameters if p.is_optional]
        assert len(optional_params) >= 1

    def test_js_rest_params(self) -> None:
        code = "function rest(first, ...others) {}\n"
        path = _write_temp(code, suffix=".js")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        variadic = [p for p in result.functions[0].parameters if p.is_variadic]
        assert len(variadic) >= 1

    def test_js_high_param_count(self) -> None:
        params = ", ".join(f"p{i}" for i in range(7))
        code = f"function big({params}) {{}}\n"
        path = _write_temp(code, suffix=".js")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert len(result.high_param_functions) == 1


# --- Java Analysis Tests ---


class TestJavaAnalysis:
    def test_java_method(self) -> None:
        code = (
            "public class Foo {\n"
            "    public void bar(String name, int age) {\n"
            "    }\n"
            "}\n"
        )
        path = _write_temp(code, suffix=".java")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions >= 1
        assert result.total_parameters >= 2

    def test_java_constructor(self) -> None:
        code = (
            "public class Foo {\n"
            "    public Foo(String name, int value) {\n"
            "    }\n"
            "}\n"
        )
        path = _write_temp(code, suffix=".java")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        ctors = [f for f in result.functions if f.element_type == "constructor"]
        assert len(ctors) >= 1

    def test_java_typed_params(self) -> None:
        code = (
            "public class Svc {\n"
            "    public void process(String user, java.util.List<String> items) {\n"
            "    }\n"
            "}\n"
        )
        path = _write_temp(code, suffix=".java")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions >= 1
        params = result.functions[0].parameters
        assert any(p.type_annotation is not None for p in params)

    def test_java_high_param_count(self) -> None:
        params = ", ".join(f"int p{i}" for i in range(7))
        code = (
            "public class Big {\n"
            f"    public void bigMethod({params}) {{}}\n"
            "}\n"
        )
        path = _write_temp(code, suffix=".java")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert len(result.high_param_functions) >= 1


# --- Go Analysis Tests ---


class TestGoAnalysis:
    def test_go_function(self) -> None:
        code = "package main\n\nfunc add(a int, b int) int {\n\treturn a + b\n}\n"
        path = _write_temp(code, suffix=".go")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 2

    def test_go_method(self) -> None:
        code = (
            "package main\n\n"
            "type Server struct {}\n\n"
            "func (s *Server) Handle(name string, port int) error {\n"
            "\treturn nil\n"
            "}\n"
        )
        path = _write_temp(code, suffix=".go")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions >= 1
        methods = [f for f in result.functions if f.element_type == "method"]
        assert len(methods) >= 1

    def test_go_variadic(self) -> None:
        code = "package main\n\nfunc sum(nums ...int) int {\n\treturn 0\n}\n"
        path = _write_temp(code, suffix=".go")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions >= 1
        variadic = [p for p in result.functions[0].parameters if p.is_variadic]
        assert len(variadic) >= 1

    def test_go_no_params(self) -> None:
        code = "package main\n\nfunc noop() {}\n"
        path = _write_temp(code, suffix=".go")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert result.total_functions == 1
        assert result.total_parameters == 0


# --- Directory Analysis Tests ---


class TestDirectoryAnalysis:
    def test_analyze_directory(self) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "a.py").write_text("def foo(x, y, z, a, b, c, d): pass\n", encoding="utf-8")
        (tmpdir / "b.py").write_text("def bar(x, y, z, a, b, e): pass\n", encoding="utf-8")
        analyzer = ParameterCouplingAnalyzer(min_clump_size=3, clump_threshold=0.5)
        result = analyzer.analyze_directory(tmpdir)
        assert result.total_functions == 2
        assert result.total_parameters == 13

    def test_analyze_empty_directory(self) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_directory(tmpdir)
        assert result.total_functions == 0

    def test_skips_git_and_node_modules(self) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        git_dir = tmpdir / ".git"
        git_dir.mkdir()
        (git_dir / "hook.py").write_text("def hook(): pass\n", encoding="utf-8")
        nm_dir = tmpdir / "node_modules"
        nm_dir.mkdir()
        (nm_dir / "mod.js").write_text("function mod() {}\n", encoding="utf-8")
        (tmpdir / "real.py").write_text("def real(): pass\n", encoding="utf-8")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_directory(tmpdir)
        assert result.total_functions == 1


# --- Configurable Threshold Tests ---


class TestConfigurableThresholds:
    def test_custom_max_params(self) -> None:
        params = ", ".join(f"p{i}" for i in range(4))
        path = _write_temp(f"def medium({params}): pass\n")
        analyzer = ParameterCouplingAnalyzer(max_params=3)
        result = analyzer.analyze_file(path)
        assert len(result.high_param_functions) == 1

    def test_default_max_params(self) -> None:
        params = ", ".join(f"p{i}" for i in range(5))
        path = _write_temp(f"def exact({params}): pass\n")
        analyzer = ParameterCouplingAnalyzer()
        result = analyzer.analyze_file(path)
        assert len(result.high_param_functions) == 0

    def test_custom_clump_threshold(self) -> None:
        code = (
            "def a(x, y, z, w): pass\n"
            "def b(x, y, z, v): pass\n"
        )
        path = _write_temp(code)
        strict = ParameterCouplingAnalyzer(min_clump_size=3, clump_threshold=0.9)
        result_strict = strict.analyze_file(path)
        loose = ParameterCouplingAnalyzer(min_clump_size=3, clump_threshold=0.5)
        result_loose = loose.analyze_file(path)
        assert len(result_loose.data_clumps) >= len(result_strict.data_clumps)
