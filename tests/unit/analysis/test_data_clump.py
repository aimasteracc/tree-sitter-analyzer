"""Tests for Data Clump Detector."""
from __future__ import annotations

import tempfile

from tree_sitter_analyzer.analysis.data_clump import (
    ISSUE_DATA_CLUMP,
    DataClumpAnalyzer,
    DataClumpResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Python Tests ──


class TestPythonDataClump:
    def test_basic_clump(self) -> None:
        code = """\
def create_user(name, email, age, role):
    pass

def update_user(name, email, age, role):
    pass

def delete_user(name, email, age):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert isinstance(result, DataClumpResult)
            assert result.functions_analyzed == 3
            assert result.total_issues >= 1
            clump_issues = result.get_issues_by_severity("medium")
            assert len(clump_issues) >= 1
            names = {p for i in clump_issues for p in i.params}
            assert "name" in names
            assert "email" in names
            assert "age" in names
        finally:
            import os
            os.unlink(path)

    def test_no_clump(self) -> None:
        code = """\
def foo(a, b):
    pass

def bar(c, d):
    pass

def baz(e, f):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
            assert result.functions_analyzed == 3
        finally:
            import os
            os.unlink(path)

    def test_self_filtered(self) -> None:
        code = """\
class Service:
    def method_one(self, x, y, z):
        pass

    def method_two(self, x, y, z):
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 2
            clump_issues = [i for i in result.issues
                            if i.issue_type == ISSUE_DATA_CLUMP]
            if clump_issues:
                for issue in clump_issues:
                    assert "self" not in issue.params
        finally:
            import os
            os.unlink(path)

    def test_four_param_clump(self) -> None:
        code = """\
def send_email(to, subject, body, cc):
    pass

def forward_email(to, subject, body, cc):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
            issue = result.issues[0]
            assert "to" in issue.params
            assert "subject" in issue.params
            assert "body" in issue.params
            assert "cc" in issue.params
        finally:
            import os
            os.unlink(path)

    def test_threshold_min_occurrences(self) -> None:
        code = """\
def func_a(x, y, z):
    pass

def func_b(x, y, z):
    pass

def func_c(x, y, z):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=3)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].occurrences >= 3
        finally:
            import os
            os.unlink(path)

    def test_single_function_no_clump(self) -> None:
        code = """\
def only_one(a, b, c, d):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_no_functions(self) -> None:
        code = """\
x = 42
y = "hello"
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 0
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_default_parameters(self) -> None:
        code = """\
def create(name, email, age=18):
    pass

def update(name, email, age=18):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_too_few_params(self) -> None:
        code = """\
def func_a(x, y):
    pass

def func_b(x, y):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3)
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_decorated_function(self) -> None:
        code = """\
import functools

@functools.lru_cache
def compute(x, y, z):
    pass

@functools.lru_cache
def recompute(x, y, z):
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_file_not_found(self) -> None:
        analyzer = DataClumpAnalyzer()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0
        assert result.functions_analyzed == 0


# ── JavaScript Tests ──


class TestJavaScriptDataClump:
    def test_basic_clump(self) -> None:
        code = """\
function createUser(name, email, age) {
    return { name, email, age };
}

function updateUser(name, email, age) {
    Object.assign(user, { name, email, age });
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 2
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_arrow_function(self) -> None:
        code = """\
const send = (to, subject, body) => to;
const forward = (to, subject, body) => to;
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_no_clump(self) -> None:
        code = """\
function foo(a) { return a; }
function bar(b) { return b; }
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_method_definition(self) -> None:
        code = """\
class Service {
    methodOne(x, y, z) { return x; }
    methodTwo(x, y, z) { return y; }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)


# ── TypeScript Tests ──


class TestTypeScriptDataClump:
    def test_basic_clump(self) -> None:
        code = """\
function create(name: string, email: string, age: number): void {}
function update(name: string, email: string, age: number): void {}
"""
        path = _write_tmp(code, ".ts")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_no_clump_ts(self) -> None:
        code = """\
function foo(a: number): void {}
function bar(b: string): void {}
"""
        path = _write_tmp(code, ".ts")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_tsx_file(self) -> None:
        code = """\
function Component(a: string, b: string, c: string) { return null; }
function AnotherComponent(a: string, b: string, c: string) { return null; }
"""
        path = _write_tmp(code, ".tsx")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)


# ── Java Tests ──


class TestJavaDataClump:
    def test_basic_clump(self) -> None:
        code = """\
public class Service {
    public void create(String name, String email, int age) {}
    public void update(String name, String email, int age) {}
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 2
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_constructor_clump(self) -> None:
        code = """\
public class User {
    public User(String name, String email, int age) {}
}

public class Admin {
    public Admin(String name, String email, int age) {}
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_no_clump(self) -> None:
        code = """\
public class Service {
    public void foo(int x) {}
    public void bar(String y) {}
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)


# ── Go Tests ──


class TestGoDataClump:
    def test_basic_clump(self) -> None:
        code = """\
package main

func Create(name string, email string, age int) error {
    return nil
}

func Update(name string, email string, age int) error {
    return nil
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed >= 2
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_method_clump(self) -> None:
        code = """\
package main

type Service struct{}

func (s *Service) Create(name string, email string, age int) error {
    return nil
}

func (s *Service) Update(name string, email string, age int) error {
    return nil
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)

    def test_no_clump(self) -> None:
        code = """\
package main

func foo(x int) int { return x }
func bar(y int) int { return y }
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)


# ── Result Object Tests ──


class TestResultObjects:
    def test_to_dict(self) -> None:
        code = """\
def func_a(x, y, z): pass
def func_b(x, y, z): pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "functions_analyzed" in d
            assert "total_issues" in d
            assert "issues" in d
        finally:
            import os
            os.unlink(path)

    def test_issue_to_dict(self) -> None:
        code = """\
def func_a(x, y, z): pass
def func_b(x, y, z): pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            if result.issues:
                d = result.issues[0].to_dict()
                assert "issue_type" in d
                assert "line" in d
                assert "params" in d
                assert "occurrences" in d
                assert "locations" in d
        finally:
            import os
            os.unlink(path)

    def test_get_issues_by_severity(self) -> None:
        code = """\
def func_a(x, y, z): pass
def func_b(x, y, z): pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            medium = result.get_issues_by_severity("medium")
            assert len(medium) >= 1
        finally:
            import os
            os.unlink(path)


# ── Edge Cases ──


class TestEdgeCases:
    def test_unsupported_extension(self) -> None:
        code = "def foo(a, b, c): pass"
        path = _write_tmp(code, ".txt")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_empty_file(self) -> None:
        path = _write_tmp("", ".py")
        try:
            analyzer = DataClumpAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 0
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_cls_filtered(self) -> None:
        code = """\
class Meta:
    @classmethod
    def create(cls, x, y, z):
        pass

    @classmethod
    def update(cls, x, y, z):
        pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            if result.issues:
                for issue in result.issues:
                    assert "cls" not in issue.params
        finally:
            import os
            os.unlink(path)

    def test_many_functions(self) -> None:
        lines = []
        for i in range(10):
            lines.append(f"def func_{i}(a, b, c): pass")
        code = "\n".join(lines)
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 10
            assert result.total_issues >= 1
            assert result.issues[0].occurrences >= 10
        finally:
            import os
            os.unlink(path)

    def test_different_param_names_no_clump(self) -> None:
        code = """\
def func_a(a1, b1, c1): pass
def func_b(a2, b2, c2): pass
def func_c(a3, b3, c3): pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            import os
            os.unlink(path)

    def test_partial_overlap(self) -> None:
        code = """\
def func_a(x, y, z, w): pass
def func_b(x, y, z): pass
def func_c(x, y, z): pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = DataClumpAnalyzer(min_params=3, min_occurrences=2)
            result = analyzer.analyze_file(path)
            assert result.functions_analyzed == 3
            assert result.total_issues >= 1
        finally:
            import os
            os.unlink(path)
