"""Tests for Unnecessary Lambda Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.unnecessary_lambda import (
    ISSUE_IDENTITY_LAMBDA,
    ISSUE_TRIVIAL_LAMBDA,
    UnnecessaryLambdaAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Trivial lambda ────────────────────────────────────────────


class TestTrivialLambda:
    def test_trivial_single_arg(self, tmp_path: Path) -> None:
        code = "f = lambda x: g(x)\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_TRIVIAL_LAMBDA

    def test_trivial_two_args(self, tmp_path: Path) -> None:
        code = "f = lambda x, y: g(x, y)\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_TRIVIAL_LAMBDA

    def test_not_trivial_extra_arg(self, tmp_path: Path) -> None:
        code = "f = lambda x: g(x, 1)\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_not_trivial_different_name(self, tmp_path: Path) -> None:
        code = "f = lambda x: g(y)\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_not_trivial_complex_body(self, tmp_path: Path) -> None:
        code = "f = lambda x: x + 1\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_not_trivial_method_call(self, tmp_path: Path) -> None:
        code = "f = lambda x: obj.method(x)\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Identity lambda ───────────────────────────────────────────


class TestIdentityLambda:
    def test_identity(self, tmp_path: Path) -> None:
        code = "f = lambda x: x\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IDENTITY_LAMBDA

    def test_not_identity_two_params(self, tmp_path: Path) -> None:
        code = "f = lambda x, y: x\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_not_identity_returns_different(self, tmp_path: Path) -> None:
        code = "f = lambda x: y\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Normal lambdas (no issues) ────────────────────────────────


class TestNormalLambda:
    def test_meaningful_lambda(self, tmp_path: Path) -> None:
        code = "f = lambda x: x * 2\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_lambda_with_expression(self, tmp_path: Path) -> None:
        code = "f = lambda x: x.strip().lower()\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_no_lambdas(self, tmp_path: Path) -> None:
        code = "def f(x):\n    return x * 2\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0
        assert r.total_lambdas == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = UnnecessaryLambdaAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "const f = (x) => x;\n")
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        code = "f = lambda x: g(x)\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert d["issue_count"] == 1
        assert d["total_lambdas"] == 1

    def test_multiple_lambdas(self, tmp_path: Path) -> None:
        code = "f = lambda x: g(x)\nh = lambda y: y * 2\n"
        p = _write(tmp_path, "a.py", code)
        r = UnnecessaryLambdaAnalyzer().analyze_file(p)
        assert r.total_lambdas == 2
        assert len(r.issues) == 1
