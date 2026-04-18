"""Unit tests for ResourceLifecycleAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.resource_lifecycle import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    ResourceIssue,
    ResourceLifecycleAnalyzer,
    ResourceLifecycleResult,
    ResourceSafetyStats,
    _analyze_csharp,
    _analyze_java,
    _analyze_python,
    _analyze_typescript,
    _count_safe_acquisitions,
)


@pytest.fixture
def analyzer() -> ResourceLifecycleAnalyzer:
    return ResourceLifecycleAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestResourceIssue:
    def test_to_dict(self) -> None:
        issue = ResourceIssue(
            file_path="test.py",
            line=10,
            resource_type="file_open",
            risk=RISK_HIGH,
            description="open() without context manager",
        )
        d = issue.to_dict()
        assert d["file_path"] == "test.py"
        assert d["line"] == 10
        assert d["risk"] == RISK_HIGH

    def test_frozen(self) -> None:
        issue = ResourceIssue(
            file_path="a.py", line=1, resource_type="x",
            risk=RISK_HIGH, description="d",
        )
        with pytest.raises(AttributeError):
            issue.line = 5  # type: ignore[misc]


class TestResourceSafetyStats:
    def test_to_dict(self) -> None:
        stats = ResourceSafetyStats(
            total_acquisitions=10,
            safe_acquisitions=8,
            risky_acquisitions=2,
            safety_percentage=80.0,
        )
        d = stats.to_dict()
        assert d["total_acquisitions"] == 10
        assert d["safety_percentage"] == 80.0

    def test_frozen(self) -> None:
        stats = ResourceSafetyStats(0, 0, 0, 100.0)
        with pytest.raises(AttributeError):
            stats.total_acquisitions = 99  # type: ignore[misc]


class TestResourceLifecycleResult:
    def test_to_dict(self) -> None:
        issue = ResourceIssue(
            file_path="a.py", line=1, resource_type="x",
            risk=RISK_HIGH, description="d",
        )
        stats = ResourceSafetyStats(1, 0, 1, 0.0)
        result = ResourceLifecycleResult(
            file_path="a.py", issues=(issue,), stats=stats,
        )
        d = result.to_dict()
        assert d["issue_count"] == 1
        assert len(d["issues"]) == 1


class TestAnalyzePython:
    def test_open_without_with(self) -> None:
        code = "f = open('data.txt')\ncontent = f.read()\nf.close()\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 1
        assert issues[0].risk == RISK_HIGH
        assert "open()" in issues[0].description

    def test_open_with_with(self) -> None:
        code = "with open('data.txt') as f:\n    content = f.read()\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 0

    def test_open_with_try_finally(self) -> None:
        code = "f = open('data.txt')\ntry:\n    content = f.read()\nfinally:\n    f.close()\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 1
        assert issues[0].risk == RISK_LOW

    def test_open_with_try_no_finally(self) -> None:
        code = "f = open('data.txt')\ntry:\n    content = f.read()\nexcept:\n    pass\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 1
        assert issues[0].risk == RISK_MEDIUM

    def test_multiple_opens(self) -> None:
        code = "f1 = open('a.txt')\nf2 = open('b.txt')\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 2

    def test_no_opens(self) -> None:
        code = "x = 1\ny = 2\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 0

    def test_with_open_and_bare_open(self) -> None:
        code = "with open('a.txt') as f:\n    pass\nf2 = open('b.txt')\n"
        issues = _analyze_python(code, "test.py")
        assert len(issues) == 1
        assert issues[0].risk == RISK_HIGH


class TestAnalyzeJava:
    def test_new_stream_without_try_with(self) -> None:
        code = (
            "FileInputStream fis = new FileInputStream(\"data.txt\");\n"
            "int data = fis.read();\n"
        )
        issues = _analyze_java(code, "Test.java")
        assert len(issues) == 1
        assert issues[0].risk == RISK_HIGH

    def test_new_stream_with_try_with(self) -> None:
        code = (
            "try (FileInputStream fis = new FileInputStream(\"data.txt\")) {\n"
            "    int data = fis.read();\n"
            "}\n"
        )
        issues = _analyze_java(code, "Test.java")
        assert len(issues) == 1
        assert issues[0].risk == RISK_LOW

    def test_buffered_reader(self) -> None:
        code = "BufferedReader br = new BufferedReader(new FileReader(\"f.txt\"));\n"
        issues = _analyze_java(code, "Test.java")
        assert len(issues) >= 1
        assert any(i.risk == RISK_HIGH for i in issues)

    def test_connection_without_cleanup(self) -> None:
        code = "Connection conn = new Connection(url);\n"
        issues = _analyze_java(code, "Test.java")
        assert len(issues) == 1
        assert issues[0].risk == RISK_HIGH

    def test_no_streams(self) -> None:
        code = "int x = 5;\nString s = \"hello\";\n"
        issues = _analyze_java(code, "Test.java")
        assert len(issues) == 0


class TestAnalyzeTypeScript:
    def test_fs_open(self) -> None:
        code = "const stream = fs.open('/tmp/data');\n"
        issues = _analyze_typescript(code, "test.ts")
        assert len(issues) == 1
        assert issues[0].risk == RISK_MEDIUM

    def test_create_read_stream(self) -> None:
        code = "const rs = fs.createReadStream('./data.txt');\n"
        issues = _analyze_typescript(code, "test.ts")
        assert len(issues) == 1

    def test_no_fs_operations(self) -> None:
        code = "const x = 5;\nconsole.log(x);\n"
        issues = _analyze_typescript(code, "test.ts")
        assert len(issues) == 0


class TestAnalyzeCSharp:
    def test_filestream_without_using(self) -> None:
        code = "var fs = new FileStream(\"data.txt\", FileMode.Open);\n"
        issues = _analyze_csharp(code, "Test.cs")
        assert len(issues) == 1
        assert issues[0].risk == RISK_HIGH

    def test_filestream_with_using(self) -> None:
        code = "using (var fs = new FileStream(\"data.txt\", FileMode.Open)) {\n    fs.Read(buf);\n}\n"
        issues = _analyze_csharp(code, "Test.cs")
        assert len(issues) == 1
        assert issues[0].risk == RISK_LOW

    def test_http_client_without_using(self) -> None:
        code = "var client = new HttpClient();\n"
        issues = _analyze_csharp(code, "Test.cs")
        assert len(issues) == 1
        assert issues[0].risk == RISK_HIGH

    def test_no_resources(self) -> None:
        code = "int x = 5;\nConsole.WriteLine(x);\n"
        issues = _analyze_csharp(code, "Test.cs")
        assert len(issues) == 0


class TestCountSafeAcquisitions:
    def test_python_with_open(self) -> None:
        code = "with open('a.txt') as f:\n    pass\nwith open('b.txt') as g:\n    pass\n"
        assert _count_safe_acquisitions(code, ".py") == 2

    def test_java_try_with(self) -> None:
        code = "try (FileInputStream fis = new FileInputStream(\"a.txt\")) {}\n"
        assert _count_safe_acquisitions(code, ".java") == 1

    def test_csharp_using(self) -> None:
        code = "using (var fs = new FileStream(\"a.txt\", FileMode.Open)) {}\n"
        assert _count_safe_acquisitions(code, ".cs") == 1

    def test_unknown_ext(self) -> None:
        assert _count_safe_acquisitions("code", ".rs") == 0


class TestAnalyzerFile:
    def test_python_file(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        path = _write_tmp("f = open('data.txt')\nf.read()\n")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.issues) == 1
            assert result.stats.risky_acquisitions == 1
        finally:
            Path(path).unlink()

    def test_java_file(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        code = (
            "import java.io.*;\n"
            "FileInputStream fis = new FileInputStream(\"data.txt\");\n"
        )
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.issues) >= 1
        finally:
            Path(path).unlink()

    def test_clean_python_file(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        path = _write_tmp("with open('data.txt') as f:\n    f.read()\n")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.issues) == 0
            assert result.stats.safety_percentage == 100.0
        finally:
            Path(path).unlink()

    def test_nonexistent_file(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert len(result.issues) == 0
        assert result.stats.safety_percentage == 100.0

    def test_unsupported_extension(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        path = _write_tmp("open('data.txt')", suffix=".rs")
        try:
            result = analyzer.analyze_file(path)
            assert len(result.issues) == 0
        finally:
            Path(path).unlink()


class TestAnalyzerProject:
    def test_project_analysis(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("f = open('data.txt')\n")
            (Path(tmp) / "b.py").write_text("with open('safe.txt') as f:\n    pass\n")

            results = analyzer.analyze_project(tmp)
            assert len(results) == 1
            assert results[0].stats.risky_acquisitions >= 1

    def test_empty_project(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = analyzer.analyze_project(tmp)
            assert len(results) == 0

    def test_nonexistent_project(self, analyzer: ResourceLifecycleAnalyzer) -> None:
        results = analyzer.analyze_project("/nonexistent/path")
        assert len(results) == 0
