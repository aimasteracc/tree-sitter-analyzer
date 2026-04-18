"""Unit tests for Call Graph Analyzer — Python core engine."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.call_graph import (
    CallEdge,
    CallGraphAnalyzer,
    CallGraphResult,
    FunctionDef,
    _detect_language,
)


@pytest.fixture
def analyzer() -> CallGraphAnalyzer:
    return CallGraphAnalyzer("python")


def _write_tmp(content: bytes, suffix: str = ".py") -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        return Path(f.name)


# --- Dataclass tests ---


def test_call_edge_to_dict() -> None:
    edge = CallEdge(caller="foo", callee="bar", file_path="a.py", line=5, column=0)
    d = edge.to_dict()
    assert d["caller"] == "foo"
    assert d["callee"] == "bar"
    assert d["line"] == 5


def test_function_def_to_dict() -> None:
    fd = FunctionDef(name="my_func", file_path="b.py", start_line=1, end_line=10, language="python")
    d = fd.to_dict()
    assert d["name"] == "my_func"
    assert d["end_line"] == 10


def test_call_graph_result_properties() -> None:
    result = CallGraphResult(
        file_path="test.py",
        functions=(
            FunctionDef("a", "test.py", 1, 5, "python"),
            FunctionDef("b", "test.py", 7, 10, "python"),
        ),
        call_edges=(
            CallEdge("a", "b", "test.py", 3, 4),
        ),
    )
    assert result.function_count == 2
    assert result.edge_count == 1


def test_call_graph_result_to_dict() -> None:
    result = CallGraphResult(
        file_path="test.py",
        island_functions=("unused",),
        god_functions=(("big_func", 25),),
    )
    d = result.to_dict()
    assert d["island_count"] == 1
    assert d["god_count"] == 1
    assert d["island_functions"] == ["unused"]
    assert d["god_functions"][0]["callee_count"] == 25


# --- Language detection ---


def test_detect_language_python() -> None:
    assert _detect_language("foo.py") == "python"


def test_detect_language_javascript() -> None:
    assert _detect_language("foo.js") == "javascript"


def test_detect_language_typescript() -> None:
    assert _detect_language("foo.ts") == "typescript"


def test_detect_language_java() -> None:
    assert _detect_language("foo.java") == "java"


def test_detect_language_go() -> None:
    assert _detect_language("foo.go") == "go"


def test_detect_language_unknown() -> None:
    assert _detect_language("foo.rs") is None


# --- Function extraction ---


def test_extract_simple_functions(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def foo():
    pass

def bar():
    foo()
''')
    result = analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "foo" in names
    assert "bar" in names


def test_extract_no_functions(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'x = 42\n')
    result = analyzer.analyze_file(str(path))
    assert result.function_count == 0


def test_extract_nested_functions(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def outer():
    def inner():
        pass
    inner()
''')
    result = analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "outer" in names
    assert "inner" in names


# --- Call extraction ---


def test_extract_direct_call(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def foo():
    pass

def bar():
    foo()
''')
    result = analyzer.analyze_file(str(path))
    callers = {e.caller for e in result.call_edges}
    callees = {e.callee for e in result.call_edges}
    assert "bar" in callers
    assert "foo" in callees


def test_extract_multiple_calls(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def foo():
    pass

def bar():
    pass

def baz():
    foo()
    bar()
''')
    result = analyzer.analyze_file(str(path))
    baz_edges = [e for e in result.call_edges if e.caller == "baz"]
    callees = {e.callee for e in baz_edges}
    assert "foo" in callees
    assert "bar" in callees


def test_extract_method_call(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
class MyClass:
    def process(self):
        self.helper()

    def helper(self):
        pass
''')
    result = analyzer.analyze_file(str(path))
    callees = {e.callee for e in result.call_edges}
    assert "helper" in callees


def test_module_level_call(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def foo():
    pass

foo()
''')
    result = analyzer.analyze_file(str(path))
    module_calls = [e for e in result.call_edges if e.caller == "<module>"]
    assert len(module_calls) >= 1
    assert module_calls[0].callee == "foo"


# --- Island detection ---


def test_detect_island_function(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def used():
    pass

def unused():
    pass

def caller():
    used()
''')
    result = analyzer.analyze_file(str(path))
    assert "unused" in result.island_functions
    assert "used" not in result.island_functions


def test_no_islands_when_all_called(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def foo():
    pass

def bar():
    foo()

bar()
''')
    result = analyzer.analyze_file(str(path))
    # bar is called from module level, foo is called from bar
    assert "foo" not in result.island_functions


def test_all_islands(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def lonely():
    pass

def solo():
    pass
''')
    result = analyzer.analyze_file(str(path))
    assert "lonely" in result.island_functions
    assert "solo" in result.island_functions


# --- God function detection ---


def test_detect_god_function(analyzer: CallGraphAnalyzer) -> None:
    # Create a function that calls 5 helpers, threshold 5
    helpers = "\n".join(f"    helper_{i}()" for i in range(5))
    path = _write_tmp(f'''
def god():
{helpers}

def helper_0(): pass
def helper_1(): pass
def helper_2(): pass
def helper_3(): pass
def helper_4(): pass
'''.encode())
    result = analyzer.analyze_file(str(path), god_threshold=5)
    god_names = {name for name, _ in result.god_functions}
    assert "god" in god_names


def test_no_god_functions_below_threshold(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def simple():
    helper()

def helper():
    pass
''')
    result = analyzer.analyze_file(str(path), god_threshold=20)
    assert len(result.god_functions) == 0


# --- Edge cases ---


def test_empty_file(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b"")
    result = analyzer.analyze_file(str(path))
    assert result.function_count == 0
    assert result.edge_count == 0
    assert len(result.island_functions) == 0


def test_nonexistent_file(analyzer: CallGraphAnalyzer) -> None:
    result = analyzer.analyze_file("/nonexistent/file.py")
    assert result.function_count == 0


def test_recursive_function(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
''')
    result = analyzer.analyze_file(str(path))
    callees = {e.callee for e in result.call_edges}
    assert "factorial" in callees


def test_mutual_recursion(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def is_even(n):
    if n == 0:
        return True
    return is_odd(n - 1)

def is_odd(n):
    if n == 0:
        return False
    return is_even(n - 1)
''')
    result = analyzer.analyze_file(str(path))
    even_edges = [e for e in result.call_edges if e.caller == "is_even"]
    odd_edges = [e for e in result.call_edges if e.caller == "is_odd"]
    assert any(e.callee == "is_odd" for e in even_edges)
    assert any(e.callee == "is_even" for e in odd_edges)


def test_builtin_calls_ignored(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def foo():
    print("hello")
    len([1, 2, 3])
''')
    result = analyzer.analyze_file(str(path))
    callees = {e.callee for e in result.call_edges}
    assert "print" in callees
    assert "len" in callees
    assert len(result.island_functions) == 1  # foo is island


def test_chained_calls(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
def a():
    b()

def b():
    c()

def c():
    pass

a()
''')
    result = analyzer.analyze_file(str(path))
    assert "a" not in result.island_functions
    assert "b" not in result.island_functions
    assert "c" not in result.island_functions


def test_line_numbers_accurate(analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''# line 1
# line 2
def foo():  # line 3
    bar()    # line 4
# line 5
def bar():  # line 6
    pass     # line 7
''')
    result = analyzer.analyze_file(str(path))
    foo = [f for f in result.functions if f.name == "foo"][0]
    assert foo.start_line == 3
    bar_edge = [e for e in result.call_edges if e.caller == "foo"][0]
    assert bar_edge.line == 4
