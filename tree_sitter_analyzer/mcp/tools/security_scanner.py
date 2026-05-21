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

# SQL-injection patterns. The f-string variant must require an actual SQL
# clause inside the same f-string — without that anchor, benign English
# text like ``f"please update {n} call sites"`` matched and showed up as
# ``critical: sql_injection`` (G3 dogfood bug).
#
# Approach B (clause indicator): require a SQL keyword AND a clause keyword
# in the same f-string body, both before the closing quote. We split
# single/double quoted variants so the body-matcher can reject only the
# OUTER quote — that way ``f"... '{name}' ..."`` still scans cleanly.
_SQL_INJECTION = re.compile(
    r"(?ix)"
    r"(?:execute|exec|cursor\.execute|\.query)\s*\("
    r"[^)]*%[sd]"
    r"|"
    r"(?:execute|exec|cursor\.execute|\.query)\s*\("
    r"[^)]*\.format\("
    r"|"
    # Double-quoted f-string body cannot contain unescaped ".
    r'f"(?:[^"\\]|\\.)*?'
    r"(?:SELECT|INSERT|UPDATE|DELETE|DROP)"
    r'(?:[^"\\]|\\.)*?'
    r"(?:FROM\s+\w+|INTO\s+\w+|WHERE\s+[\w\.{}]+\s*[=<>!]"
    r"|TABLE\s+\S+|VALUES\s*\(|SET\s+\w+\s*=)"
    r"|"
    # Single-quoted f-string body cannot contain unescaped '.
    r"f'(?:[^'\\]|\\.)*?"
    r"(?:SELECT|INSERT|UPDATE|DELETE|DROP)"
    r"(?:[^'\\]|\\.)*?"
    r"(?:FROM\s+\w+|INTO\s+\w+|WHERE\s+[\w\.{}]+\s*[=<>!]"
    r"|TABLE\s+\S+|VALUES\s*\(|SET\s+\w+\s*=)"
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
    # r37as (dogfood): pre-compute the set of Python source lines that live
    # entirely inside a multi-line string token (docstrings, triple-quoted
    # literals). The pre-existing single-line ``tokenize`` check in
    # ``_should_ignore_match`` only sees one line at a time and can't tell
    # that ``        eval("1+1")`` is wrapped in a ``"""..."""`` block.
    # The scanner's own ``refactoring_suggestions_tool.py`` docstring tripped
    # this bug — it documents ``eval()`` as an *example* and the detector
    # flagged the documentation as a critical security finding. Same class
    # as task #8 (docstring false-positive) but for security scanner.
    docstring_lines: set[int] = (
        _python_lines_inside_multiline_strings(source)
        if language == "python"
        else set()
    )

    for name, pattern, severity, description in patterns:
        if is_test_path and name == "assert_in_prod":
            continue

        matches: list[int] = []
        for i, line in enumerate(lines, 1):
            if i in docstring_lines and name in _PYTHON_STRING_OR_COMMENT_SAFE_ISSUES:
                continue
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


def _python_lines_inside_multiline_strings(source: str) -> set[int]:
    """Return the 1-indexed line numbers covered by any multi-line STRING token.

    r37as (dogfood): the single-line ``tokenize.generate_tokens`` check in
    ``_is_python_string_or_comment_position`` doesn't span lines, so it
    misses code that sits *inside* a triple-quoted docstring. This helper
    walks the full source once and returns every line that falls inside
    a ``STRING`` token spanning more than one line. ``_PYTHON_STRING_OR_
    COMMENT_SAFE_ISSUES`` (``eval_usage`` / ``pickle_usage`` / ``bare_except``
    / ``tls_disabled`` / ``assert_in_prod`` / ``insecure_hash``) are then
    skipped on those lines, matching the single-line semantics.

    Returns empty set on tokenization failure — the caller falls back to
    the existing per-line check, never crashing.
    """
    covered: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.STRING:
                continue
            start_line, _start_col = token.start
            end_line, _end_col = token.end
            if end_line == start_line:
                # Single-line string — the existing single-line tokenize
                # check handles it correctly, no need to cover here.
                continue
            covered.update(range(start_line, end_line + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Malformed source — fall back to the per-line check.
        return set()
    return covered


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
