#!/usr/bin/env python3
"""
Unit tests for Security Scanner.
"""
from __future__ import annotations

import pytest
from tree_sitter_analyzer.analysis.security_scan import (
    SecurityPattern,
    SecurityScanner,
    SecurityFinding,
    SecurityScanResult,
    SecuritySeverity,
    VulnerabilityType,
)


class TestSecurityPattern:
    """Test SecurityPattern dataclass."""

    def test_create_pattern(self) -> None:
        """Test creating a security pattern."""
        pattern = SecurityPattern(
            rule_id="test-rule",
            name="Test Rule",
            vulnerability_type=VulnerabilityType.SQL_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="Test description",
            remediation="Test remediation",
            cwe_id="CWE-89",
            keywords=("SELECT", "execute"),
            language="python",
        )
        assert pattern.rule_id == "test-rule"
        assert pattern.name == "Test Rule"
        assert pattern.vulnerability_type == VulnerabilityType.SQL_INJECTION
        assert pattern.severity == SecuritySeverity.HIGH
        assert pattern.cwe_id == "CWE-89"
        assert pattern.keywords == ("SELECT", "execute")
        assert pattern.language == "python"


class TestSecurityScanner:
    """Test SecurityScanner class."""

    def test_scanner_initialization(self) -> None:
        """Test scanner initializes with default patterns."""
        scanner = SecurityScanner()
        assert len(scanner.PATTERNS) > 0
        # Check Python patterns are registered
        assert "py-hardcoded-api-key" in scanner.PATTERNS
        assert "py-sql-injection-concat" in scanner.PATTERNS
        assert "py-command-injection-os-system" in scanner.PATTERNS
        assert "py-unsafe-pickle" in scanner.PATTERNS
        assert "py-weak-md5" in scanner.PATTERNS

    def test_get_all_patterns(self) -> None:
        """Test getting all patterns."""
        scanner = SecurityScanner()
        patterns = scanner.get_patterns()
        assert len(patterns) > 0
        assert any(p.language == "python" for p in patterns)
        assert any(p.language == "javascript" for p in patterns)

    def test_get_python_patterns(self) -> None:
        """Test filtering patterns by language."""
        scanner = SecurityScanner()
        py_patterns = scanner.get_patterns("python")
        assert all(p.language == "python" for p in py_patterns)
        assert len(py_patterns) > 0

    def test_register_custom_pattern(self) -> None:
        """Test registering a custom pattern."""
        scanner = SecurityScanner()
        custom_pattern = SecurityPattern(
            rule_id="custom-test-rule",
            name="Custom Test Rule",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.MEDIUM,
            description="Custom test pattern",
            remediation="Custom remediation",
            keywords=("custom_keyword",),
            language="python",
        )
        scanner.register_pattern(custom_pattern)
        assert "custom-test-rule" in scanner.PATTERNS

    def test_detect_language(self) -> None:
        """Test language detection from file extension."""
        scanner = SecurityScanner()
        from pathlib import Path

        assert scanner._detect_language(Path("test.py")) == "python"
        assert scanner._detect_language(Path("test.js")) == "javascript"
        assert scanner._detect_language(Path("test.ts")) == "javascript"
        assert scanner._detect_language(Path("test.java")) == "java"
        assert scanner._detect_language(Path("test.go")) == "go"
        assert scanner._detect_language(Path("test.unknown")) == ""


class TestPythonSecurityPatterns:
    """Test Python-specific security pattern detection."""

    def test_hardcoded_api_key_detection(self) -> None:
        """Test detection of hardcoded API keys."""
        scanner = SecurityScanner()
        code = """
API_KEY = "sk-1234567890abcdef"
api_key = "secret-key-here"
"""
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        api_key_findings = [
            f for f in result.findings
            if f.vulnerability_type == "hardcoded_secret"
        ]
        assert len(api_key_findings) > 0

    def test_hardcoded_password_detection(self) -> None:
        """Test detection of hardcoded passwords."""
        scanner = SecurityScanner()
        code = '''
password = "mypassword"
db_password = "secretpass"
PASSWORD = "admin123"
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        findings = [f for f in result.findings if "password" in f.rule_id]
        assert len(findings) > 0

    def test_hardcoded_token_detection(self) -> None:
        """Test detection of hardcoded tokens."""
        scanner = SecurityScanner()
        code = '''
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
access_token = "secret-token-value"
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        token_findings = [f for f in result.findings if "token" in f.rule_id]
        assert len(token_findings) > 0

    def test_sql_injection_detection(self) -> None:
        """Test detection of SQL injection patterns."""
        scanner = SecurityScanner()
        code = '''
query = "SELECT * FROM users WHERE id = " + user_id
cursor.execute("INSERT INTO users (name) VALUES ('" + name + "')")
cursor.executemany("UPDATE users SET name = '" + name + "'")
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        sql_findings = [
            f for f in result.findings
            if f.vulnerability_type == "sql_injection"
        ]
        assert len(sql_findings) > 0

    def test_command_injection_os_system(self) -> None:
        """Test detection of os.system command injection."""
        scanner = SecurityScanner()
        code = '''
os.system("cat " + user_input)
os.system("rm -rf " + directory)
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        cmd_findings = [
            f for f in result.findings
            if f.vulnerability_type == "command_injection" and "os-system" in f.rule_id
        ]
        assert len(cmd_findings) > 0

    def test_command_injection_subprocess(self) -> None:
        """Test detection of subprocess command injection."""
        scanner = SecurityScanner()
        code = '''
subprocess.call("ls " + directory, shell=True)
subprocess.run("cat " + filename, shell=True)
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        cmd_findings = [
            f for f in result.findings
            if f.vulnerability_type == "command_injection" and "subprocess" in f.rule_id
        ]
        assert len(cmd_findings) > 0

    def test_unsafe_pickle_detection(self) -> None:
        """Test detection of unsafe pickle deserialization."""
        scanner = SecurityScanner()
        code = '''
data = pickle.loads(user_data)
obj = pickle.load(untrusted_file)
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        pickle_findings = [f for f in result.findings if "pickle" in f.rule_id]
        assert len(pickle_findings) > 0

    def test_unsafe_yaml_detection(self) -> None:
        """Test detection of unsafe YAML deserialization."""
        scanner = SecurityScanner()
        code = '''
config = yaml.load(user_data)
data = yaml.load(open("config.yaml"))
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        yaml_findings = [f for f in result.findings if "yaml" in f.rule_id]
        assert len(yaml_findings) > 0

    def test_weak_md5_detection(self) -> None:
        """Test detection of MD5 usage."""
        scanner = SecurityScanner()
        code = '''
hash = hashlib.md5(data).hexdigest()
m = md5(data)
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        md5_findings = [f for f in result.findings if "md5" in f.rule_id]
        assert len(md5_findings) > 0

    def test_weak_sha1_detection(self) -> None:
        """Test detection of SHA1 usage."""
        scanner = SecurityScanner()
        code = '''
hash = hashlib.sha1(data).hexdigest()
s = sha1(data)
'''
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings >= 1
        sha1_findings = [f for f in result.findings if "sha1" in f.rule_id]
        assert len(sha1_findings) > 0


class TestJavaScriptSecurityPatterns:
    """Test JavaScript/TypeScript security pattern detection."""

    def test_xss_innerhtml_detection(self) -> None:
        """Test detection of XSS via innerHTML."""
        scanner = SecurityScanner()
        code = '''
element.innerHTML = userInput;
div.innerHTML += userContent;
'''
        result = scanner.scan_file("test.js", content=code)
        assert result.total_findings >= 1
        xss_findings = [
            f for f in result.findings
            if f.vulnerability_type == "xss" and "innerhtml" in f.rule_id
        ]
        assert len(xss_findings) > 0

    def test_xss_eval_detection(self) -> None:
        """Test detection of XSS via eval."""
        scanner = SecurityScanner()
        code = '''
eval(userInput);
const fn = new Function(userCode);
'''
        result = scanner.scan_file("test.js", content=code)
        assert result.total_findings >= 1
        eval_findings = [
            f for f in result.findings
            if f.vulnerability_type == "xss" and "eval" in f.rule_id
        ]
        assert len(eval_findings) > 0

    def test_js_hardcoded_api_key(self) -> None:
        """Test detection of hardcoded API keys in JavaScript."""
        scanner = SecurityScanner()
        code = '''
const apiKey = "AIza1234567890abcdef";
const API_KEY = "sk-1234567890abcdef";
'''
        result = scanner.scan_file("test.js", content=code)
        assert result.total_findings >= 1


class TestJavaSecurityPatterns:
    """Test Java security pattern detection."""

    def test_sql_injection_string(self) -> None:
        """Test detection of SQL injection in Java."""
        scanner = SecurityScanner()
        code = '''
String query = "SELECT * FROM users WHERE id = " + userId;
stmt.executeQuery(query);
'''
        result = scanner.scan_file("Test.java", content=code)
        assert result.total_findings >= 1
        sql_findings = [
            f for f in result.findings
            if f.vulnerability_type == "sql_injection"
        ]
        assert len(sql_findings) > 0

    def test_command_injection_runtime_exec(self) -> None:
        """Test detection of command injection via Runtime.exec."""
        scanner = SecurityScanner()
        code = '''
Runtime.getRuntime().exec("cmd " + userInput);
'''
        result = scanner.scan_file("Test.java", content=code)
        assert result.total_findings >= 1
        cmd_findings = [
            f for f in result.findings
            if f.vulnerability_type == "command_injection"
        ]
        assert len(cmd_findings) > 0

    def test_unsafe_deserialization(self) -> None:
        """Test detection of unsafe deserialization in Java."""
        scanner = SecurityScanner()
        code = '''
ObjectInputStream ois = new ObjectInputStream(inputStream);
Object obj = ois.readObject();
'''
        result = scanner.scan_file("Test.java", content=code)
        assert result.total_findings >= 1
        deser_findings = [
            f for f in result.findings
            if f.vulnerability_type == "unsafe_deserialization"
        ]
        assert len(deser_findings) > 0


class TestGoSecurityPatterns:
    """Test Go security pattern detection."""

    def test_sql_injection_fmt_sprintf(self) -> None:
        """Test detection of SQL injection via fmt.Sprintf in Go."""
        scanner = SecurityScanner()
        code = '''
query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userId)
'''
        result = scanner.scan_file("main.go", content=code)
        assert result.total_findings >= 1
        sql_findings = [
            f for f in result.findings
            if f.vulnerability_type == "sql_injection"
        ]
        assert len(sql_findings) > 0

    def test_command_injection_exec_command(self) -> None:
        """Test detection of command injection in Go."""
        scanner = SecurityScanner()
        code = '''
cmd := exec.Command("sh", "-c", userCommand)
'''
        result = scanner.scan_file("main.go", content=code)
        assert result.total_findings >= 1


class TestSecurityScanResult:
    """Test SecurityScanResult aggregation."""

    def test_add_finding(self) -> None:
        """Test adding findings to result."""
        result = SecurityScanResult(file_path="test.py", language="python")
        assert result.total_findings == 0

        finding1 = SecurityFinding(
            rule_id="test-1",
            vulnerability_type="sql_injection",
            severity="high",
            file_path="test.py",
            line=10,
            column=5,
            message="Test",
            remediation="Fix it",
        )
        result.add_finding(finding1)
        assert result.total_findings == 1
        assert result.by_severity["high"] == 1
        assert result.by_type["sql_injection"] == 1

        finding2 = SecurityFinding(
            rule_id="test-2",
            vulnerability_type="hardcoded_secret",
            severity="critical",
            file_path="test.py",
            line=20,
            column=0,
            message="Test 2",
            remediation="Fix it 2",
        )
        result.add_finding(finding2)
        assert result.total_findings == 2
        assert result.by_severity["critical"] == 1

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = SecurityScanResult(file_path="test.py", language="python")
        finding = SecurityFinding(
            rule_id="test-1",
            vulnerability_type="sql_injection",
            severity="high",
            file_path="test.py",
            line=10,
            column=5,
            message="Test",
            remediation="Fix it",
            cwe_id="CWE-89",
            code_snippet="line of code",
        )
        result.add_finding(finding)

        d = result.to_dict()
        assert d["file_path"] == "test.py"
        assert d["language"] == "python"
        assert d["total_findings"] == 1
        assert len(d["findings"]) == 1
        assert d["findings"][0]["rule_id"] == "test-1"


class TestScannerSummary:
    """Test summary generation."""

    def test_get_summary(self) -> None:
        """Test generating aggregate summary."""
        scanner = SecurityScanner()

        # Create mock results
        result1 = SecurityScanResult(file_path="file1.py", language="python")
        result1.add_finding(SecurityFinding(
            rule_id="test-1",
            vulnerability_type="sql_injection",
            severity="high",
            file_path="file1.py",
            line=10,
            column=0,
            message="Test",
            remediation="Fix",
        ))

        result2 = SecurityScanResult(file_path="file2.py", language="python")
        result2.add_finding(SecurityFinding(
            rule_id="test-2",
            vulnerability_type="hardcoded_secret",
            severity="critical",
            file_path="file2.py",
            line=20,
            column=0,
            message="Test 2",
            remediation="Fix 2",
        ))

        results = {"file1.py": result1, "file2.py": result2}
        summary = scanner.get_summary(results)

        assert summary["total_files_scanned"] == 2
        assert summary["total_findings"] == 2
        assert summary["by_severity"]["high"] == 1
        assert summary["by_severity"]["critical"] == 1
        assert summary["by_type"]["sql_injection"] == 1
        assert summary["by_type"]["hardcoded_secret"] == 1


class TestFalsePositiveHandling:
    """Test false positive filtering."""

    def test_skip_comment_lines(self) -> None:
        """Test that comment lines are not flagged."""
        scanner = SecurityScanner()
        code = '''
# API_KEY = "sk-1234567890abcdef"
// password = "test123"
/* token = "secret" */
'''
        result = scanner.scan_file("test.py", content=code)
        # Comments should be skipped
        assert result.total_findings == 0

    def test_import_statement_handling(self) -> None:
        """Test handling of import statements for weak crypto."""
        scanner = SecurityScanner()
        code = '''
import hashlib
import md5
# Actual usage below
hash = hashlib.md5(data)
'''
        result = scanner.scan_file("test.py", content=code)
        # Should flag the usage, not the import
        findings = [f for f in result.findings if "md5" in f.rule_id]
        assert len(findings) == 1


class TestSeverityLevels:
    """Test severity classification."""

    def test_critical_severity_patterns(self) -> None:
        """Test patterns marked as critical severity."""
        scanner = SecurityScanner()
        critical_patterns = [
            p for p in scanner.get_patterns()
            if p.severity == SecuritySeverity.CRITICAL
        ]
        assert len(critical_patterns) > 0
        # Check that critical patterns include api-key, password, injections
        pattern_names = {p.name for p in critical_patterns}
        assert any("api key" in name.lower() or "password" in name.lower() or "command injection" in name.lower() for name in pattern_names)

    def test_high_severity_patterns(self) -> None:
        """Test patterns marked as high severity."""
        scanner = SecurityScanner()
        high_patterns = [
            p for p in scanner.get_patterns()
            if p.severity == SecuritySeverity.HIGH
        ]
        assert len(high_patterns) > 0


class TestCWEMapping:
    """Test CWE ID mapping."""

    def test_cwe_ids_present(self) -> None:
        """Test that patterns have CWE IDs."""
        scanner = SecurityScanner()
        patterns_with_cwe = [
            p for p in scanner.get_patterns() if p.cwe_id
        ]
        assert len(patterns_with_cwe) > 0
        # Check common CWEs
        cwe_ids = {p.cwe_id for p in patterns_with_cwe}
        assert "CWE-89" in cwe_ids  # SQL Injection
        assert "CWE-78" in cwe_ids  # OS Command Injection
        assert "CWE-798" in cwe_ids  # Hardcoded Credentials
        assert "CWE-79" in cwe_ids  # XSS
        assert "CWE-502" in cwe_ids  # Unsafe Deserialization


class TestMultiFileScan:
    """Test scanning multiple files."""

    def test_scan_project_filters_by_extension(self) -> None:
        """Test that project scan filters by file extension."""
        scanner = SecurityScanner()
        # Create a temporary directory with test files
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "test.py").write_text('API_KEY = "secret"')
            (tmppath / "test.txt").write_text('API_KEY = "secret"')
            (tmppath / "test.js").write_text('const apiKey = "secret";')

            results = scanner.scan_project(tmppath)
            # Should find .py and .js files, but not .txt
            assert any("test.py" in r for r in results)
            assert any("test.js" in r for r in results)
            assert not any("test.txt" in r for r in results)


class TestRemediationAdvice:
    """Test remediation guidance."""

    def test_remediation_present(self) -> None:
        """Test that findings include remediation advice."""
        scanner = SecurityScanner()
        code = 'API_KEY = "sk-1234567890abcdef"'
        result = scanner.scan_file("test.py", content=code)
        assert result.total_findings > 0
        finding = result.findings[0]
        assert finding.remediation
        assert len(finding.remediation) > 0
