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
