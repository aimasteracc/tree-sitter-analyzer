"""
Tests for features/security_scanner.py module.

TDD: Testing security vulnerability scanning.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.security_scanner import (
    Severity,
    Vulnerability,
    SecurityRule,
    SQLInjectionRule,
    XSSRule,
    HardcodedSecretRule,
    SecurityScanner,
    scan_security,
)


class TestSeverity:
    """Test Severity enum."""

    def test_severity_values(self) -> None:
        """Should have correct severity values."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"


class TestVulnerability:
    """Test Vulnerability dataclass."""

    def test_creation(self) -> None:
        """Should create Vulnerability."""
        vuln = Vulnerability(
            file="test.py",
            line=10,
            severity=Severity.HIGH,
            rule_id="SEC001",
            rule_name="SQL Injection",
            description="Potential SQL injection",
            recommendation="Use parameterized queries"
        )
        
        assert vuln.file == "test.py"
        assert vuln.severity == Severity.HIGH


class TestSQLInjectionRule:
    """Test SQLInjectionRule."""

    def test_detect_string_formatting(self) -> None:
        """Should detect SQL with string formatting."""
        rule = SQLInjectionRule()
        
        code = 'cursor.execute("SELECT * FROM users WHERE id=%s" % user_id)\n'
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = Path(f.name)
        
        try:
            vulns = rule.check(path, code)
            assert len(vulns) >= 1
            assert vulns[0].rule_id == "SEC001"
        finally:
            path.unlink()

    def test_detect_string_concatenation(self) -> None:
        """Should detect SQL with string concatenation."""
        rule = SQLInjectionRule()
        
        code = 'cursor.execute("SELECT * FROM users WHERE id=" + user_id)\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) >= 1

    def test_detect_fstring(self) -> None:
        """Should detect SQL with f-strings."""
        rule = SQLInjectionRule()
        
        code = 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) >= 1

    def test_safe_code(self) -> None:
        """Should not flag parameterized queries."""
        rule = SQLInjectionRule()
        
        code = 'cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) == 0


class TestXSSRule:
    """Test XSSRule."""

    def test_detect_innerhtml(self) -> None:
        """Should detect innerHTML assignments."""
        rule = XSSRule()
        
        code = 'element.innerHTML = user_input\n'
        
        vulns = rule.check(Path("test.js"), code)
        assert len(vulns) >= 1
        assert vulns[0].rule_id == "SEC002"

    def test_detect_document_write(self) -> None:
        """Should detect document.write."""
        rule = XSSRule()
        
        code = 'document.write(user_input)\n'
        
        vulns = rule.check(Path("test.js"), code)
        assert len(vulns) >= 1

    def test_safe_code(self) -> None:
        """Should not flag safe code."""
        rule = XSSRule()
        
        code = 'element.textContent = user_input\n'
        
        vulns = rule.check(Path("test.js"), code)
        assert len(vulns) == 0


class TestHardcodedSecretRule:
    """Test HardcodedSecretRule."""

    def test_detect_password(self) -> None:
        """Should detect hardcoded passwords."""
        rule = HardcodedSecretRule()
        
        code = 'password = "super_secret_password123"\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) >= 1
        assert vulns[0].severity == Severity.CRITICAL

    def test_detect_api_key(self) -> None:
        """Should detect hardcoded API keys."""
        rule = HardcodedSecretRule()
        
        code = 'api_key = "abcdefghijklmnop"\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) >= 1

    def test_detect_aws_key(self) -> None:
        """Should detect AWS keys."""
        rule = HardcodedSecretRule()
        
        code = 'aws_access_key = "AKIAIOSFODNN7EXAMPLE"\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) >= 1

    def test_skip_comments(self) -> None:
        """Should skip commented code."""
        rule = HardcodedSecretRule()
        
        code = '# password = "commented_out"\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) == 0

    def test_skip_short_values(self) -> None:
        """Should skip short values (< 8 chars)."""
        rule = HardcodedSecretRule()
        
        code = 'password = "short"\n'
        
        vulns = rule.check(Path("test.py"), code)
        assert len(vulns) == 0


class TestSecurityScanner:
    """Test SecurityScanner class."""

    def test_scan_file(self) -> None:
        """Should scan single file."""
        scanner = SecurityScanner()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('password = "hardcoded_secret_here"\n')
            f.flush()
            path = Path(f.name)
        
        try:
            vulns = scanner.scan_file(path)
            assert len(vulns) >= 1
        finally:
            path.unlink()

    def test_scan_nonexistent_file(self) -> None:
        """Should handle non-existent file."""
        scanner = SecurityScanner()
        
        vulns = scanner.scan_file(Path("/nonexistent/file.py"))
        assert vulns == []

    def test_scan_directory(self) -> None:
        """Should scan directory."""
        scanner = SecurityScanner()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text('password = "secret123456"\n')
            (Path(tmpdir) / "b.py").write_text('api_key = "key_value_12345"\n')
            
            vulns = scanner.scan_directory(Path(tmpdir))
            
            assert len(vulns) >= 2

    def test_get_summary(self) -> None:
        """Should generate summary."""
        scanner = SecurityScanner()
        
        vulns = [
            Vulnerability("a.py", 1, Severity.CRITICAL, "SEC003", "Secret", "", ""),
            Vulnerability("b.py", 1, Severity.HIGH, "SEC001", "SQLi", "", ""),
            Vulnerability("c.py", 1, Severity.HIGH, "SEC002", "XSS", "", ""),
        ]
        
        summary = scanner.get_summary(vulns)
        
        assert summary["total"] == 3
        assert summary["critical"] == 1
        assert summary["high"] == 2


class TestScanSecurity:
    """Test scan_security convenience function."""

    def test_scan_security(self) -> None:
        """Should scan project for security issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text('token = "my_secret_token_value"\n')
            
            result = scan_security(Path(tmpdir))
            
            assert "summary" in result
            assert "vulnerabilities" in result
            assert result["summary"]["total"] >= 1
