"""Multi-language tests for Call Graph Analyzer — JS/TS, Java, Go."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.call_graph import CallGraphAnalyzer, _detect_language


def _write_tmp(content: bytes, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        return Path(f.name)


# --- JavaScript ---


@pytest.fixture
def js_analyzer() -> CallGraphAnalyzer:
    return CallGraphAnalyzer("javascript")


def test_js_extract_functions(js_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
function foo() {
    bar();
}

function bar() {
    return 1;
}
''', ".js")
    result = js_analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "foo" in names
    assert "bar" in names


def test_js_extract_calls(js_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
function main() {
    helper();
    process();
}

function helper() {}
function process() {}
''', ".js")
    result = js_analyzer.analyze_file(str(path))
    main_calls = {e.callee for e in result.call_edges if e.caller == "main"}
    assert "helper" in main_calls
    assert "process" in main_calls


def test_js_method_calls(js_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
class Service {
    run() {
        helper();
    }
    helper() {}
}
''', ".js")
    result = js_analyzer.analyze_file(str(path))
    callees = {e.callee for e in result.call_edges}
    assert "helper" in callees


def test_js_island_detection(js_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
function used() {}
function unused() {}

used();
''', ".js")
    result = js_analyzer.analyze_file(str(path))
    assert "unused" in result.island_functions
    assert "used" not in result.island_functions


# --- TypeScript ---


@pytest.fixture
def ts_analyzer() -> CallGraphAnalyzer:
    return CallGraphAnalyzer("typescript")


def test_ts_extract_functions(ts_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
function greet(name: string): string {
    return format(name);
}

function format(s: string): string {
    return s.trim();
}
''', ".ts")
    result = ts_analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "greet" in names
    assert "format" in names


def test_ts_method_calls(ts_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
class Calculator {
    compute() {
        validate();
    }
    validate() {}
}
''', ".ts")
    result = ts_analyzer.analyze_file(str(path))
    callees = {e.callee for e in result.call_edges}
    assert "validate" in callees


def test_ts_island_detection(ts_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
function entry() {
    process();
}
function process() {}
function dead() {}

entry();
''', ".ts")
    result = ts_analyzer.analyze_file(str(path))
    assert "dead" in result.island_functions
    assert "entry" not in result.island_functions
    assert "process" not in result.island_functions


# --- Java ---


@pytest.fixture
def java_analyzer() -> CallGraphAnalyzer:
    return CallGraphAnalyzer("java")


def test_java_extract_methods(java_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
public class Service {
    public void process() {
        validate();
        transform();
    }

    private void validate() {}

    private void transform() {}
}
''', ".java")
    result = java_analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "process" in names
    assert "validate" in names
    assert "transform" in names


def test_java_method_calls(java_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
public class App {
    public void run() {
        init();
        execute();
    }

    private void init() {}
    private void execute() {}
}
''', ".java")
    result = java_analyzer.analyze_file(str(path))
    run_calls = {e.callee for e in result.call_edges if e.caller == "run"}
    assert "init" in run_calls
    assert "execute" in run_calls


def test_java_island_detection(java_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
public class Main {
    public static void main(String[] args) {
        new Main().entry();
    }

    public void entry() {
        helper();
    }

    private void helper() {}

    private void orphan() {}
}
''', ".java")
    result = java_analyzer.analyze_file(str(path))
    assert "orphan" in result.island_functions
    assert "helper" not in result.island_functions


def test_java_constructor(java_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''
public class Config {
    public Config() {
        init();
    }

    private void init() {}
}
''', ".java")
    result = java_analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "<constructor>" in names


# --- Go ---


@pytest.fixture
def go_analyzer() -> CallGraphAnalyzer:
    return CallGraphAnalyzer("go")


def test_go_extract_functions(go_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''package main

func foo() {
    bar()
}

func bar() {}
''', ".go")
    result = go_analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "foo" in names
    assert "bar" in names


def test_go_method_extraction(go_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''package main

type Server struct{}

func (s *Server) Start() {
    s.listen()
}

func (s *Server) listen() {}
''', ".go")
    result = go_analyzer.analyze_file(str(path))
    names = {f.name for f in result.functions}
    assert "Start" in names
    assert "listen" in names


def test_go_call_graph(go_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''package main

import "fmt"

func main() {
    process()
}

func process() {
    validate()
    transform()
}

func validate() {}
func transform() {}
''', ".go")
    result = go_analyzer.analyze_file(str(path))
    main_calls = {e.callee for e in result.call_edges if e.caller == "main"}
    assert "process" in main_calls

    proc_calls = {e.callee for e in result.call_edges if e.caller == "process"}
    assert "validate" in proc_calls
    assert "transform" in proc_calls


def test_go_island_detection(go_analyzer: CallGraphAnalyzer) -> None:
    path = _write_tmp(b'''package main

func used() {}
func unused() {}

func main() {
    used()
}
''', ".go")
    result = go_analyzer.analyze_file(str(path))
    assert "unused" in result.island_functions
    assert "used" not in result.island_functions
    # main is an entry point (called by runtime, not code)
    # It's correct for it to appear in islands since no code calls it


# --- Language detection ---


def test_detect_language_tsx() -> None:
    assert _detect_language("app.tsx") == "tsx"


def test_detect_language_jsx() -> None:
    assert _detect_language("app.jsx") == "javascript"
