"""Tests for Middle Man Detector."""
from __future__ import annotations

import os
import tempfile

from tree_sitter_analyzer.analysis.middle_man import (
    ISSUE_MIDDLE_MAN,
    MiddleManAnalyzer,
    MiddleManResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Python Tests ──


class TestPythonMiddleMan:
    def test_basic_middle_man(self) -> None:
        code = """\
class Manager:
    def __init__(self):
        self.worker = Worker()

    def process(self, data):
        return self.worker.process(data)

    def validate(self, data):
        return self.worker.validate(data)

    def transform(self, data):
        return self.worker.transform(data)
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.7)
            result = analyzer.analyze_file(path)
            assert isinstance(result, MiddleManResult)
            assert result.classes_analyzed == 1
            assert result.total_issues >= 1
            issue = result.issues[0]
            assert issue.issue_type == ISSUE_MIDDLE_MAN
            assert issue.class_name == "Manager"
        finally:
            os.unlink(path)

    def test_not_middle_man(self) -> None:
        code = """\
class Service:
    def __init__(self):
        self.repo = Repo()
        self.logger = Logger()

    def process(self, data):
        result = self.repo.find(data)
        self.logger.log(result)
        return result * 2

    def validate(self, data):
        return len(data) > 0
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_no_classes(self) -> None:
        code = """\
def foo():
    return 42
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 0
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_empty_class(self) -> None:
        code = """\
class Empty:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 1
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_threshold_customization(self) -> None:
        code = """\
class Partial:
    def __init__(self):
        self.service = Service()

    def method_a(self):
        return self.service.do_a()

    def method_b(self):
        return self.service.do_b()

    def method_c(self):
        return 42
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer_strict = MiddleManAnalyzer(delegation_threshold=0.5)
            result = analyzer_strict.analyze_file(path)
            assert result.total_issues >= 1

            analyzer_loose = MiddleManAnalyzer(delegation_threshold=0.9)
            result2 = analyzer_loose.analyze_file(path)
            assert result2.total_issues == 0
        finally:
            os.unlink(path)

    def test_single_method_class(self) -> None:
        code = """\
class Single:
    def __init__(self):
        self.delegate = Delegate()

    def run(self):
        return self.delegate.run()
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_multiple_classes(self) -> None:
        code = """\
class MiddleMan1:
    def __init__(self):
        self.worker = Worker()

    def do_a(self):
        return self.worker.do_a()

    def do_b(self):
        return self.worker.do_b()

class RealClass:
    def __init__(self):
        self.data = []

    def add(self, item):
        self.data.append(item)

    def process(self):
        return [x * 2 for x in self.data]
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.7)
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 2
            middle_man_names = {i.class_name for i in result.issues}
            assert "MiddleMan1" in middle_man_names
            assert "RealClass" not in middle_man_names
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        analyzer = MiddleManAnalyzer()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0
        assert result.classes_analyzed == 0

    def test_to_dict(self) -> None:
        code = """\
class Manager:
    def __init__(self):
        self.delegate = Delegate()

    def run(self):
        return self.delegate.run()

    def execute(self):
        return self.delegate.execute()
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.5)
            result = analyzer.analyze_file(path)
            if result.issues:
                d = result.issues[0].to_dict()
                assert "issue_type" in d
                assert "class_name" in d
                assert "line" in d
        finally:
            os.unlink(path)

    def test_result_to_dict(self) -> None:
        code = """\
class Foo:
    pass
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "classes_analyzed" in d
        finally:
            os.unlink(path)


# ── JavaScript Tests ──


class TestJavaScriptMiddleMan:
    def test_basic_middle_man(self) -> None:
        code = """\
class Manager {
    constructor() {
        this.worker = new Worker();
    }

    process(data) {
        return this.worker.process(data);
    }

    validate(data) {
        return this.worker.validate(data);
    }

    transform(data) {
        return this.worker.transform(data);
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.7)
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 1
            assert result.total_issues >= 1
            assert result.issues[0].class_name == "Manager"
        finally:
            os.unlink(path)

    def test_not_middle_man(self) -> None:
        code = """\
class Service {
    constructor() {
        this.cache = {};
    }

    process(data) {
        this.cache[data.id] = data;
        return data.value * 2;
    }

    validate(data) {
        return data !== null;
    }
}
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_no_classes(self) -> None:
        code = """\
function foo() { return 42; }
"""
        path = _write_tmp(code, ".js")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 0
        finally:
            os.unlink(path)


# ── TypeScript Tests ──


class TestTypeScriptMiddleMan:
    def test_basic_middle_man(self) -> None:
        code = """\
class Manager {
    private worker: Worker;

    constructor() {
        this.worker = new Worker();
    }

    process(data: any): any {
        return this.worker.process(data);
    }

    validate(data: any): boolean {
        return this.worker.validate(data);
    }

    transform(data: any): any {
        return this.worker.transform(data);
    }
}
"""
        path = _write_tmp(code, ".ts")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.7)
            result = analyzer.analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_not_middle_man(self) -> None:
        code = """\
class Real {
    process(x: number): number {
        return x * 2;
    }

    validate(x: number): boolean {
        return x > 0;
    }
}
"""
        path = _write_tmp(code, ".ts")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── Java Tests ──


class TestJavaMiddleMan:
    def test_basic_middle_man(self) -> None:
        code = """\
public class Manager {
    private Worker worker;

    public Manager(Worker worker) {
        this.worker = worker;
    }

    public String process(String data) {
        return this.worker.process(data);
    }

    public boolean validate(String data) {
        return this.worker.validate(data);
    }

    public String transform(String data) {
        return this.worker.transform(data);
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.7)
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 1
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_not_middle_man(self) -> None:
        code = """\
public class Service {
    private Map<String, Object> cache;

    public Object process(String key) {
        cache.put(key, new Object());
        return cache.get(key);
    }

    public boolean validate(String key) {
        return cache.containsKey(key);
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_no_methods(self) -> None:
        code = """\
public class Empty {
}
"""
        path = _write_tmp(code, ".java")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 1
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── Go Tests ──


class TestGoMiddleMan:
    def test_basic_detection(self) -> None:
        code = """\
package main

type Service struct {
    repo *Repository
}

func (s *Service) Find(id int) (string, error) {
    return s.repo.Find(id)
}

func (s *Service) Store(data string) error {
    return s.repo.Store(data)
}
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.5)
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 1
        finally:
            os.unlink(path)

    def test_no_struct(self) -> None:
        code = """\
package main

func foo() int { return 42 }
"""
        path = _write_tmp(code, ".go")
        try:
            analyzer = MiddleManAnalyzer()
            result = analyzer.analyze_file(path)
            assert result.classes_analyzed == 0
        finally:
            os.unlink(path)


# ── Edge Cases ──


class TestEdgeCases:
    def test_get_issues_by_severity(self) -> None:
        code = """\
class Middle:
    def __init__(self):
        self.delegate = D()

    def a(self):
        return self.delegate.a()

    def b(self):
        return self.delegate.b()
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.5)
            result = analyzer.analyze_file(path)
            medium = result.get_issues_by_severity("medium")
            assert len(medium) >= 1
        finally:
            os.unlink(path)

    def test_mixed_delegates(self) -> None:
        code = """\
class Mixed:
    def __init__(self):
        self.service_a = A()
        self.service_b = B()

    def method_a(self):
        return self.service_a.run()

    def method_b(self):
        return self.service_b.run()

    def method_c(self):
        return self.service_a.run()

    def method_d(self):
        return 42
"""
        path = _write_tmp(code, ".py")
        try:
            analyzer = MiddleManAnalyzer(delegation_threshold=0.7)
            result = analyzer.analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)
