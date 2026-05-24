#!/usr/bin/env python3
# r37as (dogfood): regression — security/anti-pattern false positives
# on docstring + comment lines.
#
# The Agent-Teams parallel scanner flagged
# tree_sitter_analyzer/mcp/tools/refactoring_suggestions_tool.py:272 as
# a CRITICAL security finding (eval_usage) and L204 as an
# AP001 mutable_default_argument. Both were actually documentation text
# - L272 is inside a triple-quoted docstring, L204 is a "# def f(x=[])"
# comment line.
#
# This guards the two-fix combo:
#
# 1. security_scanner._python_lines_inside_multiline_strings —
#    pre-computes the line set covered by multi-line STRING tokens and
#    skips _PYTHON_STRING_OR_COMMENT_SAFE_ISSUES on those lines.
# 2. anti_patterns._check_python_anti_patterns — adds
#    stripped.startswith("#") short-circuit so AP001 / AP002 stop
#    firing inside comments (AP003 already had this guard).
#
# Same pattern as task #8 (code_patterns docstring false-positive) but
# extended to security + structural anti-patterns.
"""Regression tests for r37as docstring + comment false-positive fixes."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.security_scanner import detect_security_issues
from tree_sitter_analyzer.mcp.tools.utils.anti_patterns import detect_anti_patterns


def _ids(findings: list[dict[str, object]]) -> list[str]:
    """Extract finding identifiers (``issue`` for security, ``id`` for AP)."""
    out: list[str] = []
    for f in findings:
        if "issue" in f:
            out.append(str(f["issue"]))
        elif "id" in f:
            out.append(str(f["id"]))
    return out


class TestSecurityScannerDocstringSuppression:
    """``eval_usage`` etc. must NOT fire inside multi-line docstrings."""

    def test_eval_inside_triple_quoted_docstring_is_ignored(self) -> None:
        source = '''
def documented():
    """Doc example showing the eval anti-pattern.

    Like::

        eval("1+1")
        exec("print('bad')")

    The above should NOT be flagged when scanning this file.
    """
    return 42
'''
        findings = detect_security_issues(source, "python", file_path=None)
        assert "eval_usage" not in _ids(findings), (
            f"r37as: eval() inside docstring must be ignored. Got: {_ids(findings)}"
        )

    def test_real_eval_call_still_detected(self) -> None:
        """Sanity — the suppression must not blind the scanner to real evals."""
        source = """
def hot_path(payload):
    result = eval(payload)
    return result
"""
        findings = detect_security_issues(source, "python", file_path=None)
        assert "eval_usage" in _ids(findings), (
            f"r37as: real eval() at module scope MUST still be flagged. "
            f"Got: {_ids(findings)}"
        )

    def test_bare_except_inside_docstring_is_ignored(self) -> None:
        """``bare_except`` is also in the safe-issues set."""
        source = '''
def documented():
    """Example showing the bare except smell::

        try: pass
        except: pass
    """
    return 0
'''
        findings = detect_security_issues(source, "python", file_path=None)
        assert "bare_except" not in _ids(findings), (
            f"r37as: bare `except:` inside docstring must be ignored. "
            f"Got: {_ids(findings)}"
        )


class TestAntiPatternCommentSuppression:
    """AP001 (mutable default) etc. must NOT fire on ``#``-comment lines."""

    def test_mutable_default_in_comment_is_ignored(self, tmp_path: Path) -> None:
        """A comment that mentions ``def f(x=[])`` is documentation, not code."""
        src = tmp_path / "doc_example.py"
        src.write_text(
            "def real_function():\n"
            "    # Example: ``def bad(x=[])`` is the mutable-default smell.\n"
            "    return 1\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" not in _ids(findings), (
            f"r37as: AP001 must skip `#` comments. Got: {_ids(findings)}"
        )

    def test_real_mutable_default_still_detected(self, tmp_path: Path) -> None:
        """Sanity — the comment skip must not blind the detector to real bugs."""
        src = tmp_path / "real_bug.py"
        src.write_text("def buggy(x=[]):\n    x.append(1)\n    return x\n")
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" in _ids(findings), (
            f"r37as: real mutable default MUST still be flagged. Got: {_ids(findings)}"
        )

    def test_bare_except_in_comment_is_ignored(self, tmp_path: Path) -> None:
        """AP002 ``bare_except`` must skip ``#``-comment lines too."""
        src = tmp_path / "doc.py"
        src.write_text(
            "def f():\n"
            "    # Don't write `except:` — it catches KeyboardInterrupt.\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP002" not in _ids(findings), (
            f"r37as: AP002 must skip `#` comments. Got: {_ids(findings)}"
        )


@pytest.mark.parametrize(
    "smell_id_in_target_file",
    [
        # All confirmed gone via manual ``--code-patterns`` run after the fix.
        "eval_usage",
        "AP001",
    ],
)
def test_refactoring_suggestions_tool_self_scan(smell_id_in_target_file: str) -> None:
    """End-to-end: scan refactoring_suggestions_tool.py — both false
    positives that prompted r37as must stay quiet.
    """
    import subprocess
    import sys

    project_root = Path(__file__).parent.parent.parent.parent.parent
    target = (
        project_root
        / "tree_sitter_analyzer"
        / "mcp"
        / "tools"
        / "refactoring_suggestions_tool.py"
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            "--code-patterns",
            str(target),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    assert proc.returncode == 0, proc.stderr
    import json

    payload = json.loads(proc.stdout)
    smells = payload.get("results", [])
    smell_ids = [s.get("id") for s in smells] + [s.get("issue") for s in smells]
    assert smell_id_in_target_file not in smell_ids, (
        f"r37as ratchet: refactoring_suggestions_tool.py must NOT report "
        f"{smell_id_in_target_file} (documentation-only artifact). "
        f"Findings: {smells}"
    )
