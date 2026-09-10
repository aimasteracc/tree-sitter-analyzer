"""#1376：test_safe_to_edit_tool_causal_envelope 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


@pytest.mark.slow_ok  # 真实索引、子进程和认证快照捕获。
@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0025 P1 read_existing authority is Linux-only",
)
def test_causal_envelope_dogfood_needs_one_analyzer_call(tmp_path: Path) -> None:
    import subprocess

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

    source = tmp_path / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project(max_files=20)
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.close()
    script = Path("scripts/check_causal_envelope.py").resolve()

    completed = subprocess.run(  # nosec B603 — fixed interpreter/script argv
        [
            sys.executable,
            str(script),
            "app.py",
            "--project-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["success"] is True
    assert report["analyzer_calls"] == 1
    assert report["separate_causality_queries"] == 0
    assert report["certified_snapshot"] is True
    assert report["missing_fields"] == []
    assert report["invalid_fields"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dependents", None),
        ("dependencies", "app.py"),
        ("exercising_tests", [1]),
        ("constraint_verdict", "safe"),
        ("verification_command", ""),
        ("stale_edges", [""]),
    ],
)
def test_causal_envelope_dogfood_rejects_invalid_field_value(
    field: str,
    value: object,
) -> None:
    import runpy

    check = runpy.run_path("scripts/check_causal_envelope.py")["_invalid_causal_fields"]
    envelope = {
        "dependents": [],
        "dependencies": [],
        "exercising_tests": [],
        "constraint_verdict": "unknown",
        "verification_command": "uv run pytest -q",
        "stale_edges": [],
    }
    envelope[field] = value

    assert check(envelope) == [field]


def test_causal_envelope_dogfood_requires_command_for_exercising_tests() -> None:
    import runpy

    check = runpy.run_path("scripts/check_causal_envelope.py")["_invalid_causal_fields"]
    envelope = {
        "dependents": [],
        "dependencies": [],
        "exercising_tests": ["tests/test_app.py"],
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": [],
    }

    assert check(envelope) == ["verification_command"]


def test_causal_envelope_dogfood_allows_unavailable_test_runner() -> None:
    import runpy

    check = runpy.run_path("scripts/check_causal_envelope.py")["_invalid_causal_fields"]
    envelope = {
        "dependents": [],
        "dependencies": [],
        "exercising_tests": ["src/test/java/com/acme/UtilTest.java"],
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": [],
    }

    assert check(envelope, "src/main/java/com/acme/Util.java") == []


def test_causal_envelope_dogfood_accepts_explicitly_unavailable_facts() -> None:
    import runpy

    check = runpy.run_path("scripts/check_causal_envelope.py")["_invalid_causal_fields"]

    assert (
        check(
            {
                "dependents": None,
                "dependencies": None,
                "exercising_tests": None,
                "constraint_verdict": "unknown",
                "verification_command": None,
                "stale_edges": None,
            }
        )
        == []
    )


def test_format_result_reads_constraints_from_snapshot_conn(
    tmp_path: Path,
) -> None:
    """快照模式格式化应忽略无法证明新鲜度的行。"""
    import sqlite3
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        SafeToEditContext,
        SafeToEditFacts,
        _format_safe_to_edit_result,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_constraint_violations ("
        "rule_id TEXT NOT NULL, caller_file TEXT NOT NULL, "
        "caller_name TEXT NOT NULL, caller_line INTEGER NOT NULL, "
        "callee_name TEXT NOT NULL, callee_file TEXT NOT NULL DEFAULT '', "
        "severity TEXT NOT NULL, detected_at INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT INTO ast_constraint_violations VALUES "
        "('R1', 'app.py', 'app', 1, 'secret', '', 'error', 1)"
    )
    health = SimpleNamespace(grade="A", total=95, dimensions={})
    facts = SafeToEditFacts(
        dependents=[],
        dependencies=[],
        health=health,
        test_files=[],
        has_tests=False,
        risk="safe",
        risk_factors=[],
        pre_edit_checklist=[],
    )
    context = SafeToEditContext(
        file_path="app.py",
        edit_type="refactor",
        resolved_path=str(tmp_path / "app.py"),
        project_root=str(tmp_path),
        graph=None,
        scorer=None,
        snapshot_conn=conn,
    )
    result = _format_safe_to_edit_result(context, facts)
    # C21: 预置的错误行未绑定快照代次，因此
    # 不能升级判定。
    assert result["verdict"] == "SAFE"
    assert not any(
        factor.get("factor") == "constraint_violation"
        for factor in result["risk_factors"]
    )


def test_format_result_marks_unsupported_import_facts_unavailable(
    tmp_path: Path,
) -> None:
    import sqlite3
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        SafeToEditContext,
        SafeToEditFacts,
        _format_safe_to_edit_result,
    )

    health = SimpleNamespace(grade="A", total=95, dimensions={})
    facts = SafeToEditFacts(
        dependents=[],
        dependencies=[],
        health=health,
        test_files=[],
        has_tests=False,
        risk="safe",
        risk_factors=[],
        pre_edit_checklist=[],
    )
    result = _format_safe_to_edit_result(
        SafeToEditContext(
            file_path="src/main.go",
            edit_type="refactor",
            resolved_path=str(tmp_path / "src/main.go"),
            project_root=str(tmp_path),
            graph=None,
            scorer=None,
            snapshot_conn=sqlite3.connect(":memory:"),
            certified_inventory=frozenset({"src/main.go"}),
        ),
        facts,
    )

    assert result["causal_envelope"] == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_format_result_exposes_certified_envelope_and_fixture_risk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完整的认证投影返回事实，并保留夹具风险升级规则。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.security.fixture_detector import FixtureFact

    monkeypatch.setattr(
        helpers, "_certified_import_facts_available", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        helpers,
        "is_fixture",
        lambda *_a, **_k: FixtureFact(
            is_fixture=True,
            confidence=0.9,
            source="test_scan",
            evidence=("tests/test_app.py",),
            note="fixture evidence",
        ),
    )
    facts = helpers.SafeToEditFacts(
        dependents=["consumer.py"],
        dependencies=["dependency.py"],
        health=SimpleNamespace(grade="A", total=95, dimensions={}),
        test_files=["tests/test_app.py"],
        has_tests=True,
        risk="safe",
        risk_factors=[],
        pre_edit_checklist=[],
        test_projection_complete=True,
    )
    context = helpers.SafeToEditContext(
        file_path="app.py",
        edit_type="refactor",
        resolved_path=str(tmp_path / "app.py"),
        project_root=str(tmp_path),
        graph=None,
        scorer=None,
        snapshot_conn=sqlite3.connect(":memory:"),
        certified_inventory=frozenset({"app.py", "consumer.py", "dependency.py"}),
        stale_edges=("old.py",),
    )

    result = helpers._format_safe_to_edit_result(context, facts)

    assert result["verdict"] == "UNSAFE"
    assert result["causal_envelope"] == {
        "dependents": ["consumer.py"],
        "dependencies": ["dependency.py"],
        "exercising_tests": ["tests/test_app.py"],
        "constraint_verdict": "unknown",
        "verification_command": "uv run pytest tests/test_app.py -q",
        "stale_edges": ["old.py"],
    }
    assert result["risk_factors"][-1]["reason_code"] == "TEST_FIXTURE"
