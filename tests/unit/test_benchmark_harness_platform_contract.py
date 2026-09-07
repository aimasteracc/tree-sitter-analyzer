"""Issue #1376：platform_contract 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import os as os
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_git_repo,
    _qualification_plans,
    _qualification_verifier_config,
    _validate_qualification_receipt,
    _write_valid_qualification_receipt,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_strict_receipt_json_rejects_flat_node_budget_overflow():
    # PR #1247 review 3742970270: byte/depth checks alone missed flat JSON trees.
    from benchmarks.codegraph_compare.setup_qualification import strict_json_loads

    payload = b"[" + b",".join([b"0"] * 100_000) + b"]"

    with pytest.raises(ValueError, match="depth or node limits"):
        strict_json_loads(payload)


def test_source_inventory_rejects_ignored_checkout_path(tmp_path: Path):
    # PR #1247 review 3742970272: fresh evidence requires a completely clean checkout.
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    (repo / ".git/info/exclude").write_text("rogue.ts\n", encoding="utf-8")
    (repo / "rogue.ts").write_text("export const decoy = true;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tracked or untracked changes"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_cell_plan_rejects_authenticated_tool_argv_decoy(tmp_path: Path):
    # PR #1247 review 3742970282: signed artifacts must be the executed artifacts.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    build = plan.executions[1]
    decoy = replace(build, argv=("/tmp/decoy", *build.argv[1:]))

    with pytest.raises(ValueError, match="exactly bind authenticated tool/config"):
        replace(plan, executions=(plan.executions[0], decoy, *plan.executions[2:]))


def test_raw_blob_same_size_rewrite_is_rejected(tmp_path: Path):
    # PR #1247 review 3742970275: a first-pass digest is not quiescence evidence.
    import benchmarks.codegraph_compare.setup_qualification_validation as module

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    target = cell_root / receipt["raw_executions"][0]["stdout_bytes"]["path"]
    original_hash = module._hash_regular_descriptor
    calls = 0

    def rewrite_after_first_hash(*args, **kwargs):
        nonlocal calls
        result = original_hash(*args, **kwargs)
        calls += 1
        if calls == 1:
            target.write_bytes(b"[]")
        return result

    with patch.object(
        module, "_hash_regular_descriptor", side_effect=rewrite_after_first_hash
    ):
        failures = _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )

    assert failures == ("RAW_EXECUTION_EVIDENCE_MISSING",)


def test_qualification_architecture_codemap_lists_security_modules():
    # PR #1247 review 3742970277: codemap-first discovery includes the trust boundary.
    codemap = Path("docs/CODEMAPS/architecture.md").read_text(encoding="utf-8")

    assert (
        "`setup_qualification_paths.py` — canonical openat filesystem isolation"
        in codemap
    )
    assert "`setup_qualification_trust.py` — externally supplied Ed25519" in codemap


def test_posix_qualification_marker_invocation_is_final_top_level_statement():
    # PR #1247 review final11: appended tests must remain inside the marked section.
    import ast

    syntax = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    statement = syntax.body[-1]

    assert (
        type(statement).__name__,
        type(statement.value).__name__,
        type(statement.value.func).__name__,
        statement.value.func.id,
    ) == ("Expr", "Call", "Name", "_mark_posix_qualification_section_tests")


def test_posix_qualification_section_functions_have_collection_marker():
    # PR #1247 review final11: every collected section test must share the Windows skip.
    reason = "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"
    section_tests = tuple(
        (name, candidate)
        for name, candidate in globals().items()
        if name.startswith("test_")
        and getattr(getattr(candidate, "__code__", None), "co_firstlineno", 0)
        > _POSIX_QUALIFICATION_SECTION_START
    )
    missing = tuple(
        name
        for name, candidate in section_tests
        if not any(
            mark.name == "skipif" and mark.kwargs.get("reason") == reason
            for mark in getattr(candidate, "pytestmark", ())
        )
    )

    assert missing == ()


def test_latest_qualification_tests_skip_in_simulated_windows(request, monkeypatch):
    # PR #1247 review final11: the five tests appended in 0d4d53f0 stay skipped on Windows.
    from _pytest.skipping import evaluate_condition

    latest_names = (
        "test_strict_receipt_json_rejects_flat_node_budget_overflow",
        "test_source_inventory_rejects_ignored_checkout_path",
        "test_cell_plan_rejects_authenticated_tool_argv_decoy",
        "test_raw_blob_same_size_rewrite_is_rejected",
        "test_qualification_architecture_codemap_lists_security_modules",
    )
    marks = tuple(
        next(mark for mark in globals()[name].pytestmark if mark.name == "skipif")
        for name in latest_names
    )
    with monkeypatch.context() as context:
        context.setattr(sys.modules[__name__], "os", SimpleNamespace(name="nt"))
        evaluations = tuple(
            evaluate_condition(request.node, mark, mark.args[0]) for mark in marks
        )

    assert evaluations == (
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
        (True, "tracked: NO1-008A qualification requires openat/O_NOFOLLOW"),
    )


_mark_posix_qualification_section_tests()
