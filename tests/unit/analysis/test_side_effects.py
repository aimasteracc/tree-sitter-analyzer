"""Unit tests for SideEffectAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.side_effects import (
    ISSUE_GLOBAL_MUTATION,
    ISSUE_PARAMETER_MUTATION,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SideEffectAnalyzer,
)


@pytest.fixture
def analyzer() -> SideEffectAnalyzer:
    return SideEffectAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.flush()
    f.close()
    return Path(f.name)


# -- Python tests ----------------------------------------------------------


class TestPythonGlobalMutation:
    def test_global_assignment_detected(self, analyzer: SideEffectAnalyzer) -> None:
        code = """counter = 0

def increment():
    global counter
    counter = counter + 1
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1
        assert globals_found[0].variable == "counter"
        assert globals_found[0].function_name == "increment"

    def test_augmented_assign_global(self, analyzer: SideEffectAnalyzer) -> None:
        code = """total = 0

def add(n):
    global total
    total += n
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1
        assert globals_found[0].variable == "total"

    def test_module_var_mutation_without_global(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """config = {"key": "value"}

def update_config():
    config["key"] = "new_value"
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1

    def test_no_global_mutation(self, analyzer: SideEffectAnalyzer) -> None:
        code = """x = 10

def pure_func(y):
    return y + 1
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) == 0

    def test_severity_high_for_global(self, analyzer: SideEffectAnalyzer) -> None:
        code = """state = []

def add_item(item):
    global state
    state.append(item)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        if globals_found:
            assert globals_found[0].severity == SEVERITY_HIGH


class TestPythonParameterMutation:
    def test_attr_assignment_detected(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """class User:
    pass

def rename(user, name):
    user.name = name
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1
        assert param_found[0].variable == "user"

    def test_index_assignment_detected(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """def set_first(lst, val):
    lst[0] = val
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1
        assert param_found[0].variable == "lst"

    def test_append_detected(self, analyzer: SideEffectAnalyzer) -> None:
        code = """def add_item(items, item):
    items.append(item)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_update_detected(self, analyzer: SideEffectAnalyzer) -> None:
        code = """def merge(config, overrides):
    config.update(overrides)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_no_mutation_pure(self, analyzer: SideEffectAnalyzer) -> None:
        code = """def safe_add(items, item):
    return items + [item]
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) == 0

    def test_severity_medium_for_param(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """def mutate(data):
    data.append(1)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        if param_found:
            assert param_found[0].severity == SEVERITY_MEDIUM


class TestPythonMultipleFunctions:
    def test_two_functions_both_mutate(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """cache = {}

def set_cache(key, val):
    global cache
    cache[key] = val

def clear_cache(d):
    d.clear()
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_issues >= 2

    def test_mixed_issues(self, analyzer: SideEffectAnalyzer) -> None:
        code = """counter = 0

def increment_and_append(lst):
    global counter
    counter += 1
    lst.append(counter)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        types = {i.issue_type for i in result.issues}
        assert ISSUE_GLOBAL_MUTATION in types
        assert ISSUE_PARAMETER_MUTATION in types


class TestPythonEdgeCases:
    def test_empty_file(self, analyzer: SideEffectAnalyzer) -> None:
        path = _write_tmp("")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_nonexistent_file(self, analyzer: SideEffectAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0
        assert result.language == "unknown"

    def test_unsupported_extension(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        path = _write_tmp("x = 1", suffix=".txt")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_nested_function(self, analyzer: SideEffectAnalyzer) -> None:
        code = """def outer():
    def inner(x):
        x.data = 42
    return inner
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_self_is_not_flagged(self, analyzer: SideEffectAnalyzer) -> None:
        code = """class Service:
    def __init__(self):
        self.value = 0

    def set_value(self, val):
        self.value = val
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
            and i.variable == "self"
        ]
        assert len(param_found) == 0


# -- JavaScript/TypeScript tests -------------------------------------------


class TestJavaScript:
    def test_module_var_mutation(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """let count = 0;

function increment() {
    count = count + 1;
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1
        assert globals_found[0].variable == "count"

    def test_param_mutation(self, analyzer: SideEffectAnalyzer) -> None:
        code = """function addItem(arr, item) {
    arr.push(item);
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_pure_function(self, analyzer: SideEffectAnalyzer) -> None:
        code = """const add = (a, b) => a + b;
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_const_no_mutation(self, analyzer: SideEffectAnalyzer) -> None:
        code = """const CONFIG = {key: "val"};

function readConfig() {
    return CONFIG.key;
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) == 0

    def test_js_attr_assignment(self, analyzer: SideEffectAnalyzer) -> None:
        code = """function setName(obj, name) {
    obj.name = name;
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_no_class_no_issues(self, analyzer: SideEffectAnalyzer) -> None:
        code = """console.log("hello");
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0


# -- Java tests ------------------------------------------------------------


class TestJava:
    def test_static_field_mutation(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """public class Counter {
    static int count = 0;

    public static void increment() {
        count = count + 1;
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1

    def test_setter_on_parameter(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """public class Service {
    public void rename(User user, String name) {
        user.setName(name);
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_pure_method(self, analyzer: SideEffectAnalyzer) -> None:
        code = """public class Math {
    public static int add(int a, int b) {
        return a + b;
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_java_extends(self, analyzer: SideEffectAnalyzer) -> None:
        code = """public class Child extends Parent {
    static String name = "child";

    public void update(String n) {
        name = n;
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1


# -- Go tests --------------------------------------------------------------


class TestGo:
    def test_package_var_mutation(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """package main

var count int = 0

func increment() {
    count = count + 1
}
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        globals_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_GLOBAL_MUTATION
        ]
        assert len(globals_found) >= 1
        assert globals_found[0].variable == "count"

    def test_append_on_parameter(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """package main

func addItem(items []int, item int) {
    items = append(items, item)
}
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        param_found = [
            i for i in result.issues
            if i.issue_type == ISSUE_PARAMETER_MUTATION
        ]
        assert len(param_found) >= 1

    def test_pure_function(self, analyzer: SideEffectAnalyzer) -> None:
        code = """package main

func add(a int, b int) int {
    return a + b
}
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_no_functions(self, analyzer: SideEffectAnalyzer) -> None:
        code = """package main

var x = 1
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0


# -- Result filtering tests -------------------------------------------------


class TestResultFiltering:
    def test_get_issues_by_severity(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """counter = 0

def mixed(lst):
    global counter
    counter += 1
    lst.append(counter)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        high = result.get_issues_by_severity(SEVERITY_HIGH)
        medium = result.get_issues_by_severity(SEVERITY_MEDIUM)
        assert len(high) >= 1
        assert len(medium) >= 1

    def test_get_issues_by_type(
        self, analyzer: SideEffectAnalyzer,
    ) -> None:
        code = """x = []

def add(lst):
    global x
    x = [1, 2]
    lst.append(2)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        globals_found = result.get_issues_by_type(ISSUE_GLOBAL_MUTATION)
        params = result.get_issues_by_type(ISSUE_PARAMETER_MUTATION)
        assert len(globals_found) >= 1
        assert len(params) >= 1

    def test_to_dict(self, analyzer: SideEffectAnalyzer) -> None:
        code = """state = 0

def modify():
    global state
    state = 1
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "issues" in d
        assert "total_issues" in d
        assert isinstance(d["issues"], list)

    def test_language_detection(self, analyzer: SideEffectAnalyzer) -> None:
        code = """let x = 1;
function f() { x = 2; }
"""
        path = _write_tmp(code, suffix=".ts")
        result = analyzer.analyze_file(path)
        assert result.language == "typescript"
