"""Tests for Hardcoded IP Address Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.hardcoded_ip import (
    ISSUE_HARDCODED_IP,
    ISSUE_HARDCODED_PORT,
    HardcodedIPAnalyzer,
)


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Python tests ──────────────────────────────────────────────────


class TestPythonHardcodedIP:
    def setup_method(self) -> None:
        self.analyzer = HardcodedIPAnalyzer()

    def test_no_ips(self) -> None:
        path = _write_tmp("x = 1\ny = 'hello'\n", ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips == 0
        assert len(result.issues) == 0

    def test_hardcoded_ipv4(self) -> None:
        path = _write_tmp('host = "192.168.1.100"\n', ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips >= 1
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1
        assert "192.168.1.100" in ip_issues[0].value

    def test_skip_loopback(self) -> None:
        path = _write_tmp('host = "127.0.0.1"\n', ".py")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) == 0

    def test_skip_zero_address(self) -> None:
        path = _write_tmp('host = "0.0.0.0"\n', ".py")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) == 0

    def test_private_ip_detected(self) -> None:
        path = _write_tmp('host = "10.0.0.1"\n', ".py")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_hardcoded_port(self) -> None:
        path = _write_tmp("port = 5432\n", ".py")
        result = self.analyzer.analyze_file(path)
        port_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_PORT]
        assert len(port_issues) >= 1
        assert port_issues[0].value == "5432"

    def test_port_not_flagged_for_non_port_var(self) -> None:
        path = _write_tmp("count = 5432\n", ".py")
        result = self.analyzer.analyze_file(path)
        port_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_PORT]
        assert len(port_issues) == 0

    def test_multiple_ips(self) -> None:
        code = '''\
db_host = "192.168.1.10"
cache_host = "10.0.0.50"
api_host = "172.16.0.1"
'''
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips >= 3

    def test_ip_in_comment_skipped(self) -> None:
        path = _write_tmp('# host = "192.168.1.100"\n', ".py")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips == 0

    def test_result_to_dict(self) -> None:
        path = _write_tmp('host = "192.168.1.1"\n', ".py")
        result = self.analyzer.analyze_file(path)
        d = result.to_dict()
        assert "total_ips" in d
        assert "total_ports" in d
        assert "issue_count" in d
        assert "issues" in d

    def test_issue_to_dict(self) -> None:
        path = _write_tmp('host = "10.0.0.1"\n', ".py")
        result = self.analyzer.analyze_file(path)
        if result.issues:
            d = result.issues[0].to_dict()
            assert "line_number" in d
            assert "issue_type" in d
            assert "value" in d
            assert "severity" in d
            assert "suggestion" in d

    def test_nonexistent_file(self) -> None:
        result = self.analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_ips == 0
        assert result.total_ports == 0

    def test_unsupported_extension(self) -> None:
        path = _write_tmp('host = "192.168.1.1"\n', ".txt")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips == 0


# ── JavaScript tests ──────────────────────────────────────────────


class TestJSHardcodedIP:
    def setup_method(self) -> None:
        self.analyzer = HardcodedIPAnalyzer()

    def test_js_hardcoded_ip(self) -> None:
        code = 'const host = "192.168.1.50";\n'
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_js_hardcoded_port(self) -> None:
        code = "const port = 3000;\n"
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        port_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_PORT]
        assert len(port_issues) >= 1

    def test_js_template_string_ip(self) -> None:
        code = "const url = `http://10.0.0.1/api`;\n"
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_js_no_ip(self) -> None:
        code = 'const name = "hello";\n'
        path = _write_tmp(code, ".js")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips == 0


# ── TypeScript tests ──────────────────────────────────────────────


class TestTSHardcodedIP:
    def setup_method(self) -> None:
        self.analyzer = HardcodedIPAnalyzer()

    def test_ts_hardcoded_ip(self) -> None:
        code = 'const dbHost: string = "172.16.0.1";\n'
        path = _write_tmp(code, ".ts")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_ts_hardcoded_port(self) -> None:
        code = "const PORT: number = 8080;\n"
        path = _write_tmp(code, ".ts")
        result = self.analyzer.analyze_file(path)
        port_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_PORT]
        assert len(port_issues) >= 1


# ── Java tests ────────────────────────────────────────────────────


class TestJavaHardcodedIP:
    def setup_method(self) -> None:
        self.analyzer = HardcodedIPAnalyzer()

    def test_java_hardcoded_ip(self) -> None:
        code = '''\
public class Config {
    String host = "192.168.1.100";
}
'''
        path = _write_tmp(code, ".java")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_java_no_ip(self) -> None:
        code = '''\
public class Main {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
'''
        path = _write_tmp(code, ".java")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips == 0


# ── Go tests ──────────────────────────────────────────────────────


class TestGoHardcodedIP:
    def setup_method(self) -> None:
        self.analyzer = HardcodedIPAnalyzer()

    def test_go_hardcoded_ip(self) -> None:
        code = '''\
package main

const host = "192.168.1.100"
'''
        path = _write_tmp(code, ".go")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_go_raw_string_ip(self) -> None:
        code = 'const host = `10.0.0.1`\n'
        path = _write_tmp(code, ".go")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_go_no_ip(self) -> None:
        code = '''\
package main

func main() {
    fmt.Println("hello")
}
'''
        path = _write_tmp(code, ".go")
        result = self.analyzer.analyze_file(path)
        assert result.total_ips == 0


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    def setup_method(self) -> None:
        self.analyzer = HardcodedIPAnalyzer()

    def test_empty_file(self) -> None:
        path = _write_tmp("", ".py")
        result = self.analyzer.analyzer_file(path) if hasattr(self.analyzer, 'analyzer_file') else self.analyzer.analyze_file(path)
        assert result.total_ips == 0

    def test_ip_in_url(self) -> None:
        code = 'url = "http://192.168.1.50:8080/api"\n'
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        ip_issues = [i for i in result.issues if i.issue_type == ISSUE_HARDCODED_IP]
        assert len(ip_issues) >= 1

    def test_severity_levels(self) -> None:
        code = 'host = "10.0.0.1"\nport = 3000\n'
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        for issue in result.issues:
            if issue.issue_type == ISSUE_HARDCODED_IP:
                assert issue.severity == "medium"
            elif issue.issue_type == ISSUE_HARDCODED_PORT:
                assert issue.severity == "low"

    def test_suggestion_not_empty(self) -> None:
        code = 'host = "192.168.1.1"\n'
        path = _write_tmp(code, ".py")
        result = self.analyzer.analyze_file(path)
        if result.issues:
            assert result.issues[0].suggestion != ""
