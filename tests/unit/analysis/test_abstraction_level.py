"""Tests for AbstractionLevelAnalyzer — Python, JS/TS, Java, Go."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.abstraction_level import (
    ISSUE_LEAKY_ABSTRACTION,
    ISSUE_MIXED_ABSTRACTION,
    AbstractionLevelAnalyzer,
)


@pytest.fixture
def analyzer() -> AbstractionLevelAnalyzer:
    return AbstractionLevelAnalyzer()


def _write(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# -- Python Tests ---------------------------------------------------------


class TestPythonAbstraction:
    def test_mixed_abstraction_detected(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        def process(data):
            validate_input(data)
            result = transform(data)
            raw = data.split(",")
            val = raw[2].strip().lower()
            log_result(result)
            total = int(val) + 100
            notify_user(result)
            return result
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) >= 1
        issue = issues[0]
        assert issue.function_name == "process"
        assert issue.high_level_count >= 3
        assert issue.low_level_count >= 3

    def test_pure_high_level_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        def handle_request(request):
            validated = validate(request)
            processed = transform(validated)
            stored = persist(processed)
            response = format_response(stored)
            log_outcome(response)
            return response
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) == 0

    def test_pure_low_level_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        def calculate(a, b, c):
            x = a + b * c
            y = x / 2.0
            z = int(y) + 1
            w = z % 10
            return w
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) == 0

    def test_short_function_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        def quick(data):
            x = data + 1
            return process(x)
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_method_in_class(self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path) -> None:
        code = """\
        class Service:
            def execute(self, data):
                validated = self.validate(data)
                transformed = self.transform(validated)
                raw = data.split(",")
                val = raw[0].strip().encode("utf-8")
                self.persist(transformed)
                checksum = sum(val) % 256
                self.notify(transformed)
                return checksum
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) >= 1
        assert issues[0].function_name == "execute"

    def test_constructor_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        class Config:
            def __init__(self, raw):
                self.name = raw.split("=")[1].strip()
                self.value = int(self.name) + 10
                self.ready = len(self.name) > 0
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        assert len(result.issues) == 0

    def test_leaky_abstraction_detected(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        def orchestrate(order):
            validated = validate_order(order)
            payment = charge_customer(validated)
            shipping = arrange_delivery(payment)
            raw = order.split(",")
            total = int(raw[1]) + len(raw)
            return shipping
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.py", code))
        leaky = [i for i in result.issues if i.issue_type == ISSUE_LEAKY_ABSTRACTION]
        assert len(leaky) >= 1


# -- JavaScript / TypeScript Tests ---------------------------------------


class TestJavaScriptAbstraction:
    def test_mixed_abstraction_js(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        function process(data) {
            validateInput(data);
            const result = transform(data);
            const raw = data.split(",");
            const val = raw[2].trim().toLowerCase();
            logResult(result);
            const total = parseInt(val) + 100;
            notifyUser(result);
            return result;
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) >= 1
        assert issues[0].function_name == "process"

    def test_pure_high_level_js_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        function handleRequest(req) {
            const validated = validate(req);
            const processed = transform(validated);
            const stored = persist(processed);
            return formatResponse(stored);
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.js", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) == 0


# -- Java Tests -----------------------------------------------------------


class TestJavaAbstraction:
    def test_mixed_abstraction_java(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        public class Service {
            public String process(String data) {
                validateInput(data);
                String result = transform(data);
                String[] raw = data.split(",");
                String val = raw[2].trim().toLowerCase();
                logResult(result);
                int total = Integer.parseInt(val) + 100;
                notifyUser(result);
                return result;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "A.java", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) >= 1
        assert issues[0].function_name == "process"

    def test_pure_high_level_java_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        public class Handler {
            public Response handle(Request req) {
                Request validated = validate(req);
                Result processed = transform(validated);
                Response resp = formatResponse(processed);
                return resp;
            }
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "A.java", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) == 0


# -- Go Tests -------------------------------------------------------------


class TestGoAbstraction:
    def test_mixed_abstraction_go(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        package main

        func process(data string) string {
            validateInput(data)
            result := transform(data)
            raw := strings.Split(data, ",")
            val := strings.TrimSpace(raw[2])
            logResult(result)
            total := len(val) + 100
            notifyUser(result)
            return result
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.go", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) >= 1
        assert issues[0].function_name == "process"

    def test_pure_high_level_go_not_flagged(
        self, analyzer: AbstractionLevelAnalyzer, tmp_path: Path,
    ) -> None:
        code = """\
        package main

        func handle(req Request) Response {
            validated := validate(req)
            processed := transform(validated)
            resp := formatResponse(processed)
            return resp
        }
        """
        result = analyzer.analyze_file(_write(tmp_path, "a.go", code))
        issues = [i for i in result.issues if i.issue_type == ISSUE_MIXED_ABSTRACTION]
        assert len(issues) == 0
