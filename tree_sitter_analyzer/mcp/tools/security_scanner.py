#!/usr/bin/env python3
"""
Language-specific security pattern detection.

Detects hardcoded secrets, SQL injection, XSS, eval/shell injection,
and other common vulnerabilities using regex patterns (fast, no AST needed).
"""

from __future__ import annotations

import io
import re
import tokenize
from typing import Any

_SECRET_PATTERNS = re.compile(
    r"(?i)"
    r"(?:password|passwd|pwd|secret|api_key|apikey|access_token|auth_token"
    r"|private_key|aws_secret|credentials)\s*[:=]\s*['\"][^'\"]{6,}['\"]"
)

_SQL_INJECTION = re.compile(
    r"(?i)"
    r"(?:execute|exec|cursor\.execute|\.query)\s*\("
    r"[^)]*%[sd]"
    r"|"
    r"(?:execute|exec|cursor\.execute|\.query)\s*\("
    r"[^)]*\.format\("
    r"|"
    r"f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s"
)

_EVAL_USAGE = re.compile(r"\beval\s*\(")

_SHELL_INJECTION = re.compile(
    r"(?:os\.system|subprocess\.(?:call|run|Popen)|exec\s*\()"
    r"\s*\([^)]*(?:%[sd]|\.format\(|f['\"])"
)

_XSS_PATTERNS = re.compile(
    r"(?:innerHTML|\.html\(|dangerouslySetInnerHTML|document\.write)\s*[\(=]"
)

_PICKLE_USAGE = re.compile(r"\bpickle\.loads?\s*\(")

_ASSERT_IN_PROD = re.compile(r"\bassert\s+")

_EXCEPT_BARE = re.compile(r"except\s*:")

_INSECURE_HASH = re.compile(
    r"\b(?:hashlib\.(?:md5|sha1)|hashlib\.new\s*\(\s*['\"](?:md5|sha1)['\"])\s*\("
)

_TLS_DISABLE = re.compile(
    r"(?:verify\s*=\s*False|CERT_NONE|check_hostname\s*=\s*False)"
)

_PYTHON_STRING_OR_COMMENT_SAFE_ISSUES = {
    "eval_usage",
    "pickle_usage",
    "bare_except",
    "tls_disabled",
    "assert_in_prod",
    "insecure_hash",
}

_PATTERNS_BY_LANG: dict[str, list[tuple[str, re.Pattern[str], str, str]]] = {
    "python": [
        (
            "hardcoded_secret",
            _SECRET_PATTERNS,
            "critical",
            "Hardcoded secret/credential in source",
        ),
        (
            "sql_injection",
            _SQL_INJECTION,
            "critical",
            "SQL injection: string formatting in SQL query",
        ),
        (
            "eval_usage",
            _EVAL_USAGE,
            "critical",
            "eval() usage — arbitrary code execution risk",
        ),
        (
            "shell_injection",
            _SHELL_INJECTION,
            "critical",
            "Shell injection: unsanitized input to subprocess",
        ),
        (
            "pickle_usage",
            _PICKLE_USAGE,
            "warning",
            "pickle.loads() — arbitrary code execution risk",
        ),
        (
            "bare_except",
            _EXCEPT_BARE,
            "warning",
            "Bare 'except:' swallows all exceptions",
        ),
        (
            "insecure_hash",
            _INSECURE_HASH,
            "warning",
            "Insecure hash (MD5/SHA1) — use SHA256+",
        ),
        ("tls_disabled", _TLS_DISABLE, "critical", "TLS verification disabled"),
        (
            "assert_in_prod",
            _ASSERT_IN_PROD,
            "info",
            "assert stripped in optimized mode (-O)",
        ),
    ],
    "javascript": [
        (
            "hardcoded_secret",
            _SECRET_PATTERNS,
            "critical",
            "Hardcoded secret/credential in source",
        ),
        (
            "eval_usage",
            _EVAL_USAGE,
            "critical",
            "eval() usage — arbitrary code execution risk",
        ),
        ("xss_risk", _XSS_PATTERNS, "critical", "XSS risk: direct HTML injection"),
        (
            "sql_injection",
            _SQL_INJECTION,
            "critical",
            "SQL injection: string formatting in SQL query",
        ),
    ],
    "typescript": [
        (
            "hardcoded_secret",
            _SECRET_PATTERNS,
            "critical",
            "Hardcoded secret/credential in source",
        ),
        (
            "eval_usage",
            _EVAL_USAGE,
            "critical",
            "eval() usage — arbitrary code execution risk",
        ),
        ("xss_risk", _XSS_PATTERNS, "critical", "XSS risk: direct HTML injection"),
        (
            "sql_injection",
            _SQL_INJECTION,
            "critical",
            "SQL injection: string formatting in SQL query",
        ),
    ],
    "java": [
        (
            "hardcoded_secret",
            _SECRET_PATTERNS,
            "critical",
            "Hardcoded secret/credential in source",
        ),
        (
            "sql_injection",
            re.compile(r"(?i)(?:Statement|createStatement)\s*\([^)]*\+\s"),
            "critical",
            "SQL injection: string concatenation in Statement",
        ),
        (
            "eval_usage",
            re.compile(r"(?:ScriptEngine|eval\s*\()"),
            "critical",
            "Script engine eval — arbitrary code execution risk",
        ),
    ],
    "go": [
        (
            "hardcoded_secret",
            _SECRET_PATTERNS,
            "critical",
            "Hardcoded secret/credential in source",
        ),
        (
            "sql_injection",
            re.compile(
                r"fmt\.Sprintf\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)", re.IGNORECASE
            ),
            "critical",
            "SQL injection: fmt.Sprintf in SQL query",
        ),
    ],
    "rust": [
        (
            "hardcoded_secret",
            _SECRET_PATTERNS,
            "critical",
            "Hardcoded secret/credential in source",
        ),
    ],
}


def _is_test_path(file_path: str | None) -> bool:
    """Return True for conventional test file paths."""
    if not file_path:
        return False
    normalized = file_path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    return (
        "/tests/" in normalized
        or normalized.startswith("tests/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def detect_security_issues(
    source: str,
    language: str,
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    patterns = _PATTERNS_BY_LANG.get(language, [])
    if not patterns:
        patterns = [
            (
                "hardcoded_secret",
                _SECRET_PATTERNS,
                "critical",
                "Hardcoded secret/credential",
            )
        ]

    issues: list[dict[str, Any]] = []
    lines = source.splitlines()
    is_test_path = _is_test_path(file_path)

    for name, pattern, severity, description in patterns:
        if is_test_path and name == "assert_in_prod":
            continue

        matches: list[int] = []
        for i, line in enumerate(lines, 1):
            if _line_has_security_match(line, pattern, name, language):
                matches.append(i)
                if len(matches) >= 10:
                    break

        if matches:
            issues.append(
                {
                    "issue": name,
                    "severity": severity,
                    "description": description,
                    "lines": matches[:5],
                    "count": len(matches),
                }
            )

    return issues


def _line_has_security_match(
    line: str,
    pattern: re.Pattern[str],
    issue_name: str,
    language: str,
) -> bool:
    """Return True when a security pattern matches executable source text."""
    for match in pattern.finditer(line):
        if _should_ignore_match(line, match.start(), issue_name, language):
            continue
        return True
    return False


def _should_ignore_match(
    line: str,
    column: int,
    issue_name: str,
    language: str,
) -> bool:
    """Suppress Python false positives inside strings and comments."""
    if language != "python" or issue_name not in _PYTHON_STRING_OR_COMMENT_SAFE_ISSUES:
        return False
    return _is_python_string_or_comment_position(line, column)


def _is_python_string_or_comment_position(line: str, column: int) -> bool:
    """Return True when a column falls inside a Python string/comment token."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(line).readline)
        for token in tokens:
            if token.type not in {tokenize.STRING, tokenize.COMMENT}:
                continue
            start = token.start[1]
            end = token.end[1]
            if start <= column < end:
                return True
    except tokenize.TokenError:
        return False
    return False
