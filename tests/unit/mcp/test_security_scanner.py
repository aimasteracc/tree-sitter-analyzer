"""Tests for language-specific security scanning."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
from tree_sitter_analyzer.mcp.tools.security_scanner import detect_security_issues


def _run(coro):
    return asyncio.run(coro)


def test_python_asserts_are_reported_in_source_files() -> None:
    issues = detect_security_issues(
        "def check(value):\n    assert value\n",
        "python",
        file_path="tree_sitter_analyzer/example.py",
    )

    assert {issue["issue"] for issue in issues} == {"assert_in_prod"}


def test_python_asserts_are_not_reported_in_test_files() -> None:
    issues = detect_security_issues(
        "def test_check():\n    assert True\n",
        "python",
        file_path="tests/unit/test_example.py",
    )

    assert issues == []


def test_test_files_still_report_other_security_issues() -> None:
    issues = detect_security_issues(
        "def test_eval():\n    eval(user_input)\n",
        "python",
        file_path="tests/unit/test_example.py",
    )

    assert {issue["issue"] for issue in issues} == {"eval_usage"}


def test_python_eval_inside_string_or_comment_is_not_reported() -> None:
    issues = detect_security_issues(
        "message = 'avoid eval() in suggestions'\n"
        "# eval(user_input)\n"
        "result = eval(user_input)\n",
        "python",
        file_path="tree_sitter_analyzer/example.py",
    )

    assert issues == [
        {
            "issue": "eval_usage",
            "severity": "critical",
            "description": "eval() usage — arbitrary code execution risk",
            "lines": [3],
            "count": 1,
        }
    ]


def test_python_hardcoded_secret_detection_still_scans_assignments() -> None:
    issues = detect_security_issues(
        "pass" + "word = 'example-secret-value'\n",
        "python",
        file_path="tree_sitter_analyzer/example.py",
    )

    assert {issue["issue"] for issue in issues} == {"hardcoded_secret"}


def test_scanner_rule_samples_do_not_report_as_security_issues() -> None:
    scanner_path = Path("tree_sitter_analyzer/mcp/tools/security_scanner.py")

    issues = detect_security_issues(
        scanner_path.read_text(),
        "python",
        file_path=str(scanner_path),
    )

    assert {
        issue["issue"]
        for issue in issues
        if issue["issue"]
        in {"pickle_usage", "bare_except", "tls_disabled", "assert_in_prod"}
    } == set()


def test_python_runtime_security_constructs_are_still_reported() -> None:
    issues = detect_security_issues(
        "import pickle\n"
        "import ssl\n"
        "data = pickle.loads(payload)\n"
        "try:\n"
        "    call()\n"
        "except:\n"
        "    pass\n"
        "context.verify_mode = ssl.CERT_NONE\n"
        "assert user.is_admin\n",
        "python",
        file_path="tree_sitter_analyzer/example.py",
    )

    assert {
        "pickle_usage",
        "bare_except",
        "tls_disabled",
        "assert_in_prod",
    } <= {issue["issue"] for issue in issues}


def test_file_health_does_not_report_test_asserts_as_prod_security_smell(
    tmp_path,
) -> None:
    test_file = tmp_path / "tests" / "unit" / "test_example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_check():\n    assert True\n")

    tool = FileHealthTool(project_root=str(tmp_path))
    result = _run(
        tool.execute(
            {
                "file_path": "tests/unit/test_example.py",
                "language": "python",
                "output_format": "json",
            }
        )
    )

    smells = {smell["smell"] for smell in result["code_smells"]}
    assert "security:assert_in_prod" not in smells
