#!/usr/bin/env python3
"""
Security Vulnerability Scanner.

Detects common security vulnerabilities using AST pattern matching.
Supports multi-language scanning with configurable severity levels.

Detects:
- Hardcoded secrets: API keys, passwords, tokens
- SQL injection: String concatenation in queries
- Command injection: Subprocess calls with untrusted input
- Unsafe deserialization: pickle/yaml loads with user data
- Weak crypto: MD5, SHA1 usage
- XSS: Unsafe innerHTML, eval() in JavaScript
- Path traversal: File operations with user input
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

# Check if sarif_om library is available for SARIF output
try:
    import sarif_om  # type: ignore[import-not-found]  # noqa: F401

    SARIF_OM_SUPPORTED = True
except ImportError:
    SARIF_OM_SUPPORTED = False
    logger.debug("sarif_om not available, SARIF output will use JSON fallback")

# Node types that represent comments across languages.
_COMMENT_NODE_TYPES: frozenset[str] = frozenset({
    "comment",           # Python, JS/TS, Go
    "line_comment",      # Java, C, C++
    "block_comment",     # Java, C, C++
})

class SecuritySeverity(Enum):
    """Severity level for security findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class VulnerabilityType(Enum):
    """OWASP-style vulnerability categorization."""

    HARD_CODED_SECRET = "hardcoded_secret"
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    XSS = "xss"
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"
    WEAK_CRYPTO = "weak_crypto"
    PATH_TRAVERSAL = "path_traversal"
    INSECURE_CONFIG = "insecure_config"

@dataclass(frozen=True)
class SecurityPattern:
    """A security vulnerability detection pattern."""

    rule_id: str
    name: str
    vulnerability_type: VulnerabilityType
    severity: SecuritySeverity
    description: str
    remediation: str
    cwe_id: str = ""
    query: str = ""
    keywords: tuple[str, ...] = ()
    language: str = ""  # Empty means applies to all languages

@dataclass(frozen=True)
class SecurityFinding:
    """A single detected security vulnerability."""

    rule_id: str
    vulnerability_type: str
    severity: str
    file_path: str
    line: int
    column: int
    message: str
    remediation: str
    cwe_id: str = ""
    code_snippet: str = ""
    matched_pattern: str = ""

@dataclass
class SecurityScanResult:
    """Aggregated result of security scan on a file."""

    file_path: str
    language: str
    total_findings: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    findings: list[SecurityFinding] = field(default_factory=list)

    def add_finding(self, finding: SecurityFinding) -> None:
        """Add a finding and update aggregates."""
        self.findings.append(finding)
        self.total_findings += 1
        self.by_severity[finding.severity] = self.by_severity.get(finding.severity, 0) + 1
        self.by_type[finding.vulnerability_type] = (
            self.by_type.get(finding.vulnerability_type, 0) + 1
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_findings": self.total_findings,
            "by_severity": self.by_severity,
            "by_type": self.by_type,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "vulnerability_type": f.vulnerability_type,
                    "severity": f.severity,
                    "line": f.line,
                    "column": f.column,
                    "message": f.message,
                    "remediation": f.remediation,
                    "cwe_id": f.cwe_id,
                    "code_snippet": f.code_snippet,
                }
                for f in self.findings
            ],
        }

class SecurityScanner(BaseAnalyzer):
    """Security vulnerability scanner using AST-aware pattern matching."""

    # Predefined security patterns
    PATTERNS: dict[str, SecurityPattern] = {}

    def __init__(self) -> None:
        """Initialize the security scanner with default patterns."""
        self._register_default_patterns()
        super().__init__()

    def _register_default_patterns(self) -> None:
        """Register default security patterns for supported languages."""
        # Python patterns
        self._register_python_patterns()
        # JavaScript patterns
        self._register_javascript_patterns()
        # Java patterns
        self._register_java_patterns()
        # Go patterns
        self._register_go_patterns()

    def _register_python_patterns(self) -> None:
        """Register Python-specific security patterns."""

        # Hardcoded secrets - common variable names with string literals
        self.PATTERNS["py-hardcoded-api-key"] = SecurityPattern(
            rule_id="py-hardcoded-api-key",
            name="Hardcoded API Key",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.CRITICAL,
            description="API key hardcoded in source code",
            remediation="Move API key to environment variables or secure secret manager",
            cwe_id="CWE-798",
            keywords=("api_key", "apikey", "API_KEY", "APIKEY"),
            language="python",
        )

        self.PATTERNS["py-hardcoded-password"] = SecurityPattern(
            rule_id="py-hardcoded-password",
            name="Hardcoded Password",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.CRITICAL,
            description="Password hardcoded in source code",
            remediation="Use environment variables or secret management",
            cwe_id="CWE-798",
            keywords=("password", "passwd", "PASSWORD", "PASSWD"),
            language="python",
        )

        self.PATTERNS["py-hardcoded-token"] = SecurityPattern(
            rule_id="py-hardcoded-token",
            name="Hardcoded Token",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.HIGH,
            description="Authentication token hardcoded in source code",
            remediation="Store tokens in secure configuration",
            cwe_id="CWE-798",
            keywords=("token", "access_token", "auth_token", "bearer"),
            language="python",
        )

        # SQL injection - string concatenation in SQL queries
        self.PATTERNS["py-sql-injection-concat"] = SecurityPattern(
            rule_id="py-sql-injection-concat",
            name="SQL Injection via String Concatenation",
            vulnerability_type=VulnerabilityType.SQL_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="SQL query built with string concatenation",
            remediation="Use parameterized queries or ORM",
            cwe_id="CWE-89",
            keywords=("SELECT", "INSERT", "UPDATE", "DELETE", "execute", "executemany"),
            language="python",
        )

        # Command injection - subprocess with user input
        self.PATTERNS["py-command-injection-os-system"] = SecurityPattern(
            rule_id="py-command-injection-os-system",
            name="Command Injection via os.system",
            vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
            severity=SecuritySeverity.CRITICAL,
            description="os.system() with potentially untrusted input",
            remediation="Use subprocess.run() with list arguments or shell=False",
            cwe_id="CWE-78",
            keywords=("os.system", "os.popen", "commands.getoutput"),
            language="python",
        )

        self.PATTERNS["py-command-injection-subprocess"] = SecurityPattern(
            rule_id="py-command-injection-subprocess",
            name="Command Injection via subprocess",
            vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="subprocess call with shell=True",
            remediation="Use shell=False or pass command as list",
            cwe_id="CWE-78",
            keywords=("subprocess.call", "subprocess.run", "subprocess.Popen"),
            language="python",
        )

        # Unsafe deserialization
        self.PATTERNS["py-unsafe-pickle"] = SecurityPattern(
            rule_id="py-unsafe-pickle",
            name="Unsafe Pickle Deserialization",
            vulnerability_type=VulnerabilityType.UNSAFE_DESERIALIZATION,
            severity=SecuritySeverity.CRITICAL,
            description="pickle.loads() can execute arbitrary code",
            remediation="Use JSON or safe serialization formats",
            cwe_id="CWE-502",
            keywords=("pickle.load", "pickle.loads"),
            language="python",
        )

        self.PATTERNS["py-unsafe-yaml"] = SecurityPattern(
            rule_id="py-unsafe-yaml",
            name="Unsafe YAML Deserialization",
            vulnerability_type=VulnerabilityType.UNSAFE_DESERIALIZATION,
            severity=SecuritySeverity.HIGH,
            description="yaml.load() without Loader=SafeLoader",
            remediation="Use yaml.safe_load() instead",
            cwe_id="CWE-502",
            keywords=("yaml.load",),
            language="python",
        )

        # Weak cryptography
        self.PATTERNS["py-weak-md5"] = SecurityPattern(
            rule_id="py-weak-md5",
            name="Weak Hash Algorithm (MD5)",
            vulnerability_type=VulnerabilityType.WEAK_CRYPTO,
            severity=SecuritySeverity.MEDIUM,
            description="MD5 is cryptographically broken",
            remediation="Use SHA-256 or stronger hash algorithms",
            cwe_id="CWE-327",
            keywords=("hashlib.md5", "md5("),
            language="python",
        )

        self.PATTERNS["py-weak-sha1"] = SecurityPattern(
            rule_id="py-weak-sha1",
            name="Weak Hash Algorithm (SHA1)",
            vulnerability_type=VulnerabilityType.WEAK_CRYPTO,
            severity=SecuritySeverity.MEDIUM,
            description="SHA1 is deprecated for cryptographic use",
            remediation="Use SHA-256 or stronger hash algorithms",
            cwe_id="CWE-327",
            keywords=("hashlib.sha1", "sha1("),
            language="python",
        )

    def _register_javascript_patterns(self) -> None:
        """Register JavaScript/TypeScript-specific security patterns."""

        # XSS patterns
        self.PATTERNS["js-xss-innerhtml"] = SecurityPattern(
            rule_id="js-xss-innerhtml",
            name="XSS via innerHTML",
            vulnerability_type=VulnerabilityType.XSS,
            severity=SecuritySeverity.HIGH,
            description="innerHTML assignment with user input",
            remediation="Use textContent or sanitize input",
            cwe_id="CWE-79",
            keywords=("innerHTML",),
            language="javascript",
        )

        self.PATTERNS["js-xss-eval"] = SecurityPattern(
            rule_id="js-xss-eval",
            name="XSS via eval()",
            vulnerability_type=VulnerabilityType.XSS,
            severity=SecuritySeverity.CRITICAL,
            description="eval() with user input can lead to XSS",
            remediation="Avoid eval(), use JSON.parse() or alternatives",
            cwe_id="CWE-79",
            keywords=("eval(", "Function(",),
            language="javascript",
        )

        # Hardcoded secrets
        self.PATTERNS["js-hardcoded-api-key"] = SecurityPattern(
            rule_id="js-hardcoded-api-key",
            name="Hardcoded API Key",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.CRITICAL,
            description="API key hardcoded in source code",
            remediation="Move API key to environment variables",
            cwe_id="CWE-798",
            keywords=("apiKey", "API_KEY", "apikey"),
            language="javascript",
        )

        self.PATTERNS["js-hardcoded-password"] = SecurityPattern(
            rule_id="js-hardcoded-password",
            name="Hardcoded Password",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.CRITICAL,
            description="Password hardcoded in source code",
            remediation="Use environment variables or secret management",
            cwe_id="CWE-798",
            keywords=("password", "PASSWORD", "passwd"),
            language="javascript",
        )

        # SQL injection
        self.PATTERNS["js-sql-injection-template"] = SecurityPattern(
            rule_id="js-sql-injection-template",
            name="SQL Injection via Template Literals",
            vulnerability_type=VulnerabilityType.SQL_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="SQL query built with template literals",
            remediation="Use parameterized queries or query builders",
            cwe_id="CWE-89",
            keywords=("SELECT", "INSERT", "UPDATE", "DELETE", "query"),
            language="javascript",
        )

        # Command injection
        self.PATTERNS["js-command-injection"] = SecurityPattern(
            rule_id="js-command-injection",
            name="Command Injection via child_process",
            vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="child_process.exec() with user input",
            remediation="Use execFile with argument array or spawn",
            cwe_id="CWE-78",
            keywords=("child_process.exec", "execSync", "spawn"),
            language="javascript",
        )

        # Path traversal
        self.PATTERNS["js-path-traversal"] = SecurityPattern(
            rule_id="js-path-traversal",
            name="Path Traversal via fs operations",
            vulnerability_type=VulnerabilityType.PATH_TRAVERSAL,
            severity=SecuritySeverity.HIGH,
            description="File system operations with user input",
            remediation="Validate and sanitize file paths",
            cwe_id="CWE-22",
            keywords=("fs.readFile", "fs.readFileSync", "fs.writeFile", "path.join"),
            language="javascript",
        )

    def _register_java_patterns(self) -> None:
        """Register Java-specific security patterns."""

        # SQL injection
        self.PATTERNS["java-sql-injection-string"] = SecurityPattern(
            rule_id="java-sql-injection-string",
            name="SQL Injection via String Concatenation",
            vulnerability_type=VulnerabilityType.SQL_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="SQL query built with string concatenation",
            remediation="Use PreparedStatement with parameterized queries",
            cwe_id="CWE-89",
            keywords=("executeQuery", "executeUpdate", "Statement"),
            language="java",
        )

        # Command injection
        self.PATTERNS["java-command-injection"] = SecurityPattern(
            rule_id="java-command-injection",
            name="Command Injection via Runtime.exec",
            vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="Runtime.exec() with user input",
            remediation="Use ProcessBuilder with proper argument array",
            cwe_id="CWE-78",
            keywords=("Runtime.exec", "Runtime.getRuntime().exec", "ProcessBuilder"),
            language="java",
        )

        # Unsafe deserialization
        self.PATTERNS["java-unsafe-deserialization"] = SecurityPattern(
            rule_id="java-unsafe-deserialization",
            name="Unsafe Java Deserialization",
            vulnerability_type=VulnerabilityType.UNSAFE_DESERIALIZATION,
            severity=SecuritySeverity.CRITICAL,
            description="ObjectInputStream can execute arbitrary code",
            remediation="Use safe deserialization practices or validate input",
            cwe_id="CWE-502",
            keywords=("ObjectInputStream", "XMLDecoder"),
            language="java",
        )

        # Hardcoded secrets
        self.PATTERNS["java-hardcoded-password"] = SecurityPattern(
            rule_id="java-hardcoded-password",
            name="Hardcoded Password",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.CRITICAL,
            description="Password hardcoded in source code",
            remediation="Use environment variables or secret management",
            cwe_id="CWE-798",
            keywords=("password", "PASSWORD", "passwd"),
            language="java",
        )

        # Path traversal
        self.PATTERNS["java-path-traversal"] = SecurityPattern(
            rule_id="java-path-traversal",
            name="Path Traversal via File operations",
            vulnerability_type=VulnerabilityType.PATH_TRAVERSAL,
            severity=SecuritySeverity.HIGH,
            description="File operations with user input",
            remediation="Validate and sanitize file paths",
            cwe_id="CWE-22",
            keywords=("new File(", "Files.read", "Path.of"),
            language="java",
        )

    def _register_go_patterns(self) -> None:
        """Register Go-specific security patterns."""

        # SQL injection
        self.PATTERNS["go-sql-injection-fmt"] = SecurityPattern(
            rule_id="go-sql-injection-fmt",
            name="SQL Injection via fmt.Sprintf",
            vulnerability_type=VulnerabilityType.SQL_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="SQL query built with string formatting",
            remediation="Use prepared statements with parameter binding",
            cwe_id="CWE-89",
            keywords=("fmt.Sprintf", "fmt.Sprintf"),
            language="go",
        )

        # Command injection
        self.PATTERNS["go-command-injection"] = SecurityPattern(
            rule_id="go-command-injection",
            name="Command Injection via exec.Command",
            vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
            severity=SecuritySeverity.HIGH,
            description="exec.Command with user input in arguments",
            remediation="Validate and sanitize input before use",
            cwe_id="CWE-78",
            keywords=("exec.Command", "os/exec"),
            language="go",
        )

        # Hardcoded secrets
        self.PATTERNS["go-hardcoded-password"] = SecurityPattern(
            rule_id="go-hardcoded-password",
            name="Hardcoded Password",
            vulnerability_type=VulnerabilityType.HARD_CODED_SECRET,
            severity=SecuritySeverity.CRITICAL,
            description="Password hardcoded in source code",
            remediation="Use environment variables or secret management",
            cwe_id="CWE-798",
            keywords=("password", "Password", "PASSWORD"),
            language="go",
        )

        # Path traversal
        self.PATTERNS["go-path-traversal"] = SecurityPattern(
            rule_id="go-path-traversal",
            name="Path Traversal via os operations",
            vulnerability_type=VulnerabilityType.PATH_TRAVERSAL,
            severity=SecuritySeverity.HIGH,
            description="File operations with user input",
            remediation="Validate and sanitize file paths with filepath.Clean",
            cwe_id="CWE-22",
            keywords=("os.Open", "ioutil.ReadFile", "os.ReadFile"),
            language="go",
        )

    def get_patterns(self, language: str = "") -> list[SecurityPattern]:
        """Get all registered patterns, optionally filtered by language."""
        if language:
            return [
                p for p in self.PATTERNS.values()
                if p.language == language.lower() or not p.language
            ]
        return list(self.PATTERNS.values())

    def register_pattern(self, pattern: SecurityPattern) -> None:
        """Register a custom security pattern."""
        self.PATTERNS[pattern.rule_id] = pattern

    def _get_code_line_numbers(self, tree: Any, total_lines: int) -> set[int] | None:
        """Walk the AST and return 1-based line numbers that are actual code.

        Returns ``None`` when tree-sitter parsing is unavailable so the caller
        can fall back to the legacy keyword-only scan.
        """
        if tree is None or not hasattr(tree, "root_node"):
            return None
        root = tree.root_node
        if root is None or not hasattr(root, "children"):
            return None

        # Collect all 1-based line numbers covered by comment nodes.
        comment_lines: set[int] = set()

        def _walk(node: Any) -> None:
            if node.type in _COMMENT_NODE_TYPES:
                # start_point is (row, col) zero-based; end_point exclusive.
                start_row = node.start_point[0]
                end_row = node.end_point[0]
                for row in range(start_row, end_row + 1):
                    comment_lines.add(row + 1)  # convert to 1-based
            for child in node.children:
                _walk(child)

        _walk(root)

        # Build set of code lines (1-based, 1..total_lines).
        if not comment_lines:
            return None  # No comments found -- skip filtering overhead.
        return {ln for ln in range(1, total_lines + 1) if ln not in comment_lines}

    def scan_file(
        self,
        file_path: str | Path,
        content: str | None = None,
    ) -> SecurityScanResult:
        """
        Scan a single file for security vulnerabilities.

        Uses tree-sitter AST parsing to identify comment regions and skip them,
        falling back to pure keyword matching when AST parsing is unavailable.

        Args:
            file_path: Path to the file to scan
            content: Optional file content (will read from disk if not provided)

        Returns:
            SecurityScanResult with all findings
        """
        file_path = Path(file_path)
        language = self._detect_language(file_path)

        if not language:
            return SecurityScanResult(file_path=str(file_path), language="unknown")

        if content is None:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")
                return SecurityScanResult(file_path=str(file_path), language=language)

        result = SecurityScanResult(file_path=str(file_path), language=language)
        lines = content.splitlines()

        # Attempt AST-aware comment filtering via tree-sitter.
        code_lines: set[int] | None = None
        ext = file_path.suffix.lower()
        _, parser = self._get_parser(ext)
        if parser is not None:
            try:
                tree = parser.parse(content.encode("utf-8"))
                code_lines = self._get_code_line_numbers(tree, len(lines))
            except Exception:
                logger.debug("tree-sitter parse failed for %s; using fallback", file_path)

        # Get patterns for this language
        patterns = self.get_patterns(language)

        for pattern in patterns:
            for line_num, line in enumerate(lines, start=1):
                # Skip lines that tree-sitter identified as comments.
                if code_lines is not None and line_num not in code_lines:
                    continue
                if self._matches_pattern(line, pattern):
                    finding = SecurityFinding(
                        rule_id=pattern.rule_id,
                        vulnerability_type=pattern.vulnerability_type.value,
                        severity=pattern.severity.value,
                        file_path=str(file_path),
                        line=line_num,
                        column=self._find_keyword_column(line, pattern.keywords),
                        message=pattern.description,
                        remediation=pattern.remediation,
                        cwe_id=pattern.cwe_id,
                        code_snippet=line.strip(),
                        matched_pattern=pattern.name,
                    )
                    result.add_finding(finding)

        return result

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "javascript",
            ".tsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".cs": "csharp",
            ".rb": "ruby",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".scala": "scala",
            ".lua": "lua",
            ".sh": "shell",
            ".bash": "shell",
        }
        return ext_map.get(file_path.suffix.lower(), "")

    def _matches_pattern(self, line: str, pattern: SecurityPattern) -> bool:
        """Check if a line matches the security pattern."""
        line_lower = line.lower()

        # Check for keywords
        for keyword in pattern.keywords:
            if keyword.lower() in line_lower:
                # Additional context checks to reduce false positives
                if self._is_valid_match(line, pattern):
                    return True
        return False

    def _is_valid_match(self, line: str, pattern: SecurityPattern) -> bool:
        """Additional validation to reduce false positives."""
        # Skip comment lines
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
            return False

        # Skip import statements for some patterns
        if pattern.vulnerability_type in (
            VulnerabilityType.WEAK_CRYPTO,
            VulnerabilityType.UNSAFE_DESERIALIZATION,
        ):
            if "import" in line.lower():
                # Allow imports for library documentation
                # but flag actual usage
                return "=" in line or "(" in line

        return True

    def _find_keyword_column(self, line: str, keywords: tuple[str, ...]) -> int:
        """Find the column of the first matching keyword."""
        line_lower = line.lower()
        min_col = len(line)
        for keyword in keywords:
            idx = line_lower.find(keyword.lower())
            if idx != -1 and idx < min_col:
                min_col = idx
        return max(0, min_col)

    def scan_project(
        self,
        project_path: str | Path,
        extensions: set[str] | None = None,
    ) -> dict[str, SecurityScanResult]:
        """
        Scan an entire project for security vulnerabilities.

        Args:
            project_path: Path to the project root
            extensions: File extensions to scan (default: SUPPORTED_EXTENSIONS)

        Returns:
            Dictionary mapping file paths to scan results
        """
        project_path = Path(project_path)
        if extensions is None:
            extensions = self.SUPPORTED_EXTENSIONS

        results = {}
        for file_path in project_path.rglob("*"):
            if file_path.suffix.lower() in extensions and file_path.is_file():
                try:
                    result = self.scan_file(file_path)
                    if result.total_findings > 0:
                        results[str(file_path)] = result
                except Exception as e:
                    logger.warning(f"Failed to scan {file_path}: {e}")

        return results

    def get_summary(
        self,
        results: dict[str, SecurityScanResult],
    ) -> dict[str, Any]:
        """
        Get aggregate summary of scan results.

        Returns:
            Summary dictionary with totals and breakdowns
        """
        total_files = len(results)
        total_findings = sum(r.total_findings for r in results.values())

        by_severity: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for result in results.values():
            for sev, count in result.by_severity.items():
                by_severity[sev] = by_severity.get(sev, 0) + count
            for vtype, count in result.by_type.items():
                by_type[vtype] = by_type.get(vtype, 0) + count

        return {
            "total_files_scanned": total_files,
            "total_findings": total_findings,
            "by_severity": by_severity,
            "by_type": by_type,
            "most_vulnerable_files": sorted(
                results.items(),
                key=lambda x: x[1].total_findings,
                reverse=True,
            )[:5],
        }
