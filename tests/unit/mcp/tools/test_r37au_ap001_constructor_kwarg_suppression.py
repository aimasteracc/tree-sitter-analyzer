#!/usr/bin/env python3
# r37au (dogfood): AP001 was firing on constructor / function CALLs that
# passed an empty list/dict as a keyword argument
# (``SQLTable(columns=[], constraints=[], dependencies=[])``).
# 11 such false positives showed up in
# tree_sitter_analyzer/formatters/_sql_formatter_wrapper_helpers.py.
#
# The old heuristic was "line text contains =[] AND any nearby line has
# 'def '". Constructor calls inside a function body trivially satisfy
# that — every dataclass-builder file is full of them.
#
# Fix: AST-based detection. Walk ast.FunctionDef / AsyncFunctionDef /
# Lambda nodes and inspect args.defaults + args.kw_defaults directly.
# A mutable-default is a literal [] / {} / {a,b} or a zero-arg
# list()/dict()/set() call. Constructor/function-call kwargs are
# unaffected.
"""Regression tests for r37au AST-based AP001 detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.utils.anti_patterns import detect_anti_patterns


def _ids(findings: list[dict[str, object]]) -> list[str]:
    return [str(f["id"]) for f in findings if "id" in f]


class TestAP001ConstructorCallsClean:
    """The 11 false positives in _sql_formatter_wrapper_helpers.py all
    look like ``return SQLTable(name=..., columns=[], constraints=[])`` —
    keyword args in a CALL, not defaults in a DEF."""

    def test_constructor_kwarg_empty_list_is_not_ap001(self, tmp_path: Path) -> None:
        src = tmp_path / "factory.py"
        src.write_text(
            "from dataclasses import dataclass, field\n"
            "\n"
            "@dataclass\n"
            "class Box:\n"
            "    name: str\n"
            "    items: list = field(default_factory=list)\n"
            "\n"
            "def make_box(name):\n"
            "    return Box(name=name, items=[])\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" not in _ids(findings), (
            f"r37au: empty-list kwarg to constructor is not a mutable default. "
            f"Got: {_ids(findings)}"
        )

    def test_function_call_kwarg_empty_dict_is_not_ap001(self, tmp_path: Path) -> None:
        src = tmp_path / "call.py"
        src.write_text(
            "def configure(**kwargs):\n"
            "    return kwargs\n"
            "\n"
            "def main():\n"
            "    return configure(options={}, overrides={})\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" not in _ids(findings), (
            f"r37au: empty-dict kwarg to call is not a mutable default. "
            f"Got: {_ids(findings)}"
        )

    def test_local_variable_assignment_is_not_ap001(self, tmp_path: Path) -> None:
        src = tmp_path / "locals.py"
        # Old heuristic matched ``x=[]`` even as local assignment if a
        # ``def `` was nearby.
        src.write_text(
            "def gather():\n    items=[]\n    items.append(1)\n    return items\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" not in _ids(findings), (
            f"r37au: local assignment is not a mutable default. Got: {_ids(findings)}"
        )


class TestAP001RealDefaultsStillDetected:
    """The AST-based detector must still catch real bugs."""

    @pytest.mark.parametrize(
        "default_literal",
        ["[]", "{}", "set()", "list()", "dict()"],
    )
    def test_real_mutable_default_at_def(
        self, tmp_path: Path, default_literal: str
    ) -> None:
        src = (
            tmp_path
            / f"bug_{default_literal.replace('(', '').replace(')', '').replace('{', 'D').replace('}', 'D').replace('[', 'L').replace(']', 'L')}.py"
        )
        src.write_text(
            f"def buggy(items={default_literal}):\n"
            "    items.append(1)\n"
            "    return items\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" in _ids(findings), (
            f"r37au: real def f(x={default_literal}) MUST be flagged. "
            f"Got: {_ids(findings)}"
        )

    def test_keyword_only_mutable_default_detected(self, tmp_path: Path) -> None:
        """Keyword-only ``def f(*, x=[])`` defaults live in kw_defaults."""
        src = tmp_path / "kw.py"
        src.write_text("def cfg(*, items=[]):\n    items.append(1)\n    return items\n")
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" in _ids(findings), (
            f"r37au: keyword-only mutable default MUST be flagged. "
            f"Got: {_ids(findings)}"
        )

    def test_async_function_default_detected(self, tmp_path: Path) -> None:
        src = tmp_path / "async_bug.py"
        src.write_text(
            "async def boom(items=[]):\n    items.append(1)\n    return items\n"
        )
        findings = detect_anti_patterns(str(src), "python")
        assert "AP001" in _ids(findings), (
            f"r37au: async def mutable default MUST be flagged. Got: {_ids(findings)}"
        )


def test_sql_formatter_helper_self_scan() -> None:
    """End-to-end: scan the file that prompted r37au — 11 false positives
    must stay quiet. This is the ratchet that prevents regression."""
    import json
    import subprocess
    import sys

    project_root = Path(__file__).parent.parent.parent.parent.parent
    target = (
        project_root
        / "tree_sitter_analyzer"
        / "formatters"
        / "_sql_formatter_wrapper_helpers.py"
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
    payload = json.loads(proc.stdout)
    smells = payload.get("results", [])
    ap001_lines = [s.get("line") for s in smells if s.get("id") == "AP001"]
    assert not ap001_lines, (
        f"r37au ratchet: _sql_formatter_wrapper_helpers.py must NOT report "
        f"any AP001 (all 11 false positives were constructor kwargs, not "
        f"function defaults). Got AP001 on lines: {ap001_lines}"
    )


# ---------------------------------------------------------------------------
# Encoding guard (tracked: #1130)
# ---------------------------------------------------------------------------
# anti_patterns.py:28 called read_text(errors="replace") without encoding,
# causing UnicodeDecodeError on Windows non-UTF-8 locales. The fix pins
# encoding="utf-8". Tests below lock that requirement.


@pytest.mark.regression
def test_detect_anti_patterns_reads_with_explicit_utf8(tmp_path: Path, monkeypatch) -> None:
    """REQ-TEST-003 / ARCH-003: detect_anti_patterns must call
    read_text(encoding='utf-8', ...) so non-ASCII files succeed on
    non-UTF-8-locale hosts (tracked: #1130)."""
    source = tmp_path / "locale_sensitive.py"
    source.write_text(
        "# 日本語コメント\ndef greet():\n    print('こんにちは')\n",
        encoding="utf-8",
    )

    seen_encodings: list[str | None] = []
    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        encoding = kwargs.get("encoding")
        seen_encodings.append(encoding)
        if encoding is None:
            raise UnicodeDecodeError("cp1252", b"\x00", 0, 1, "simulated")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    result = detect_anti_patterns(str(source), "python")

    assert isinstance(result, list), (
        "detect_anti_patterns must return a list; got None or raised"
    )
    assert "utf-8" in seen_encodings, (
        f"detect_anti_patterns must call read_text with encoding='utf-8'; "
        f"observed encodings: {seen_encodings}"
    )
    assert any(f.get("id") == "AP003" for f in result), (
        f"Expected AP003 (print_in_production) finding; got: {result}"
    )


@pytest.mark.regression
def test_non_ascii_python_file_with_mutable_default_detects_ap001(tmp_path: Path) -> None:
    """REQ-TEST-003: non-ASCII UTF-8 file must not raise and must return
    the expected AP001 finding (tracked: #1130)."""
    source = tmp_path / "non_ascii.py"
    source.write_text(
        "# 日本語コメント\ndef process(data=[]):\n    pass\n",
        encoding="utf-8",
    )

    result = detect_anti_patterns(str(source), "python")

    assert isinstance(result, list), (
        f"detect_anti_patterns must return a list, got {type(result)!r}"
    )
    assert any(f.get("id") == "AP001" for f in result), (
        f"Expected AP001 (mutable_default_argument) finding; got: {result}"
    )
