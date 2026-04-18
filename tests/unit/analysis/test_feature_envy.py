"""Unit tests for FeatureEnvyAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.feature_envy import (
    ISSUE_FEATURE_ENVY,
    ISSUE_METHOD_CHAIN,
    SEVERITY_HIGH,
    FeatureEnvyAnalyzer,
)


@pytest.fixture
def analyzer() -> FeatureEnvyAnalyzer:
    return FeatureEnvyAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.flush()
    f.close()
    return Path(f.name)


# -- Python tests ----------------------------------------------------------


class TestPythonFeatureEnvy:
    def test_feature_envy_detected(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class OrderService:
    def print_label(self, customer):
        name = customer.name
        street = customer.street
        city = customer.city
        zip_code = customer.zip_code
        country = customer.country
        self.format_label(name, street, city)

    def format_label(self, name, street, city):
        return f"{name}, {street}, {city}"
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1
        assert envy_issues[0].foreign_object == "customer"
        assert envy_issues[0].class_name == "OrderService"

    def test_no_envy_when_balanced(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Calculator:
    def compute(self, x, y):
        self.result = x + y
        self.history.append(self.result)
        return self.result
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0

    def test_method_with_only_foreign_accesses_no_envy(
        self, analyzer: FeatureEnvyAnalyzer,
    ) -> None:
        code = """\
class Printer:
    def print_name(self, person):
        return person.name
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0

    def test_multiple_foreign_objects(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Report:
    def generate(self, user, config):
        name = user.name
        email = user.email
        role = user.role
        self.set_title("Report")
        self.content = "data"
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1
        assert envy_issues[0].foreign_object == "user"

    def test_empty_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        path = _write_tmp("")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_nonexistent_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0
        assert result.language == "unknown"

    def test_method_severity_high(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Service:
    def process(self, data):
        x = data.x
        y = data.y
        z = data.z
        self.result = x + y + z
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        if envy_issues:
            assert envy_issues[0].severity == SEVERITY_HIGH

    def test_get_issues_by_type(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Service:
    def process(self, data):
        x = data.x
        y = data.y
        z = data.z
        self.result = x + y + z
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_only = result.get_issues_by_type(ISSUE_FEATURE_ENVY)
        for issue in envy_only:
            assert issue.issue_type == ISSUE_FEATURE_ENVY

    def test_get_issues_by_severity(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Service:
    def process(self, data):
        x = data.x
        y = data.y
        z = data.z
        self.result = x + y + z
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        high_only = result.get_issues_by_severity(SEVERITY_HIGH)
        for issue in high_only:
            assert issue.severity == SEVERITY_HIGH

    def test_to_dict(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Service:
    def process(self, data):
        x = data.x
        y = data.y
        z = data.z
        self.result = x + y + z
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "language" in d
        assert "issues" in d
        assert isinstance(d["issues"], list)


# -- Python: method chain tests ---


class TestPythonMethodChain:
    def test_chain_detected(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Processor:
    def transform(self, data):
        result = data.get_source().parse().transform().validate()
        self.output = result
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        chain_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_METHOD_CHAIN
        ]
        assert len(chain_issues) >= 1

    def test_no_chain_for_short_calls(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Service:
    def do_work(self, repo):
        item = repo.find_item()
        self.process(item)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        chain_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_METHOD_CHAIN
        ]
        assert len(chain_issues) == 0


# -- JavaScript tests ------------------------------------------------------


class TestJavaScriptFeatureEnvy:
    def test_js_feature_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class OrderService {
    printLabel(customer) {
        const name = customer.name;
        const street = customer.street;
        const city = customer.city;
        const zip = customer.zipCode;
        const country = customer.country;
        this.formatLabel(name, street);
    }
    formatLabel(name, street) {
        return name + ", " + street;
    }
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1
        assert envy_issues[0].foreign_object == "customer"

    def test_js_no_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Counter {
    increment() {
        this.count++;
        this.history.push(this.count);
        return this.count;
    }
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0

    def test_js_empty_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        path = _write_tmp("", suffix=".js")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_js_nonexistent_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.js")
        assert result.total_issues == 0

    def test_js_method_chain(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Transformer {
    transform(data) {
        return data.getSource().parse().transform().validate().output();
    }
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        chain_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_METHOD_CHAIN
        ]
        assert len(chain_issues) >= 1

    def test_js_arrow_method(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Handler {
    process = (event) => {
        const target = event.target;
        const type = event.type;
        const x = event.x;
        const y = event.y;
        this.handleClick(x, y);
    }
    handleClick(x, y) {}
}
"""
        path = _write_tmp(code, suffix=".js")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1


# -- TypeScript tests ------------------------------------------------------


class TestTypeScriptFeatureEnvy:
    def test_ts_feature_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class ReportService {
    generate(user: User, config: Config): string {
        const name = user.name;
        const email = user.email;
        const role = user.role;
        this.setTitle("Report");
        return name + email;
    }
    setTitle(title: string) {}
}
"""
        path = _write_tmp(code, suffix=".ts")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1
        assert envy_issues[0].foreign_object == "user"

    def test_ts_no_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Calculator {
    compute(a: number, b: number): number {
        this.result = a + b;
        this.history.push(this.result);
        return this.result;
    }
}
"""
        path = _write_tmp(code, suffix=".ts")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0

    def test_ts_language_detected(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Service {
    process(data: Data) {
        const x = data.x;
        this.result = x;
    }
}
"""
        path = _write_tmp(code, suffix=".ts")
        result = analyzer.analyze_file(path)
        assert result.language == "typescript"


# -- Java tests ------------------------------------------------------------


class TestJavaFeatureEnvy:
    def test_java_feature_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
public class ReportGenerator {
    public String generate(User user, Config config) {
        String name = user.getName();
        String email = user.getEmail();
        String role = user.getRole();
        String dept = user.getDepartment();
        this.setTitle("Report");
        return name + email;
    }
    public void setTitle(String title) {}
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1
        assert envy_issues[0].class_name == "ReportGenerator"

    def test_java_no_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
public class Calculator {
    private int result;
    public int compute(int a, int b) {
        this.result = a + b;
        this.log("computed");
        return this.result;
    }
    public void log(String msg) {}
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0

    def test_java_empty_class(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
public class Empty {
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_java_nonexistent_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/File.java")
        assert result.total_issues == 0

    def test_java_constructor(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
public class Builder {
    public Builder(Config config) {
        this.name = config.getName();
        this.value = config.getValue();
    }
}
"""
        path = _write_tmp(code, suffix=".java")
        result = analyzer.analyze_file(path)
        assert result.language == "java"


# -- Go tests --------------------------------------------------------------


class TestGoFeatureEnvy:
    def test_go_feature_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
package main

type Service struct {
    result int
}

func (s *Service) Process(data *Data) int {
    x := data.X
    y := data.Y
    z := data.Z
    w := data.W
    s.result = x + y + z + w
    return s.result
}
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) >= 1
        assert envy_issues[0].class_name == "Service"

    def test_go_no_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
package main

type Counter struct {
    count int
}

func (c *Counter) Increment() int {
    c.count++
    return c.count
}
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0

    def test_go_empty_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        path = _write_tmp("package main\n", suffix=".go")
        result = analyzer.analyze_file(path)
        assert result.total_issues == 0

    def test_go_nonexistent_file(self, analyzer: FeatureEnvyAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.go")
        assert result.total_issues == 0

    def test_go_language_detected(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
package main

type Handler struct{}

func (h *Handler) Serve() {
    h.process()
}

func (h *Handler) process() {}
"""
        path = _write_tmp(code, suffix=".go")
        result = analyzer.analyze_file(path)
        assert result.language == "go"


# -- Edge cases -------------------------------------------------------------


class TestEdgeCases:
    def test_unsupported_extension(self, analyzer: FeatureEnvyAnalyzer) -> None:
        path = _write_tmp("class X {}", suffix=".rb")
        result = analyzer.analyze_file(path)
        assert result.language == "unknown"
        assert result.total_issues == 0

    def test_decorator_class(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
import dataclasses

@dataclasses.dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other):
        dx = other.x
        dy = other.y
        self.x = dx
        self.y = dy
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.language == "python"

    def test_nested_class(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Outer:
    class Inner:
        def process(self, data):
            x = data.x
            y = data.y
            z = data.z
            self.result = x
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.language == "python"

    def test_static_method_no_envy(self, analyzer: FeatureEnvyAnalyzer) -> None:
        code = """\
class Utils:
    @staticmethod
    def calculate(x, y):
        return x + y
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        envy_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_FEATURE_ENVY
        ]
        assert len(envy_issues) == 0
