"""Issue #1376：test_benchmark_harness_platform_contract 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import ast
import importlib
import os as os
import sys
from functools import partial
from pathlib import Path
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

import pytest

from tests.unit._benchmark_harness_platform import (
    POSIX_QUALIFICATION_TEST,
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_git_repo,
    _qualification_plans,
    _qualification_verifier_config,
)
from tests.unit._benchmark_harness_receipt_helpers import (
    _validate_qualification_receipt,
    _write_valid_qualification_receipt,
)


def _posix_module_paths():
    """PR #1393：从真实顶层赋值发现全部区段模块，不维护手工模块数量。"""
    result = []
    for path in sorted(Path(__file__).parent.glob("test_benchmark_harness*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "_POSIX_QUALIFICATION_SECTION_START"
                for target in node.targets
            )
            for node in tree.body
        ):
            result.append(path)
    return tuple(result)


@pytest.fixture(params=_posix_module_paths(), ids=lambda path: path.stem)
def posix_module(request):
    """每个参数对应一个实际导入模块，返回源码与独立命名空间副本。"""
    path = request.param
    module = importlib.import_module(f"tests.unit.{path.stem}")
    return path.read_text(encoding="utf-8"), dict(vars(module))


def _assert_final_registration(source):
    """注册必须是最后一个顶层语句，追加函数或其他语句都会失败。"""
    last = ast.parse(source).body[-1]
    expected = ast.parse("_mark_posix_qualification_section_tests()").body[0]
    assert ast.dump(last, include_attributes=False) == ast.dump(
        expected, include_attributes=False
    )


def _assert_marked_section(source, namespace):
    """独立对照源码与运行时函数，并精确检查原平台条件和原因。"""
    tree = ast.parse(source)
    boundaries = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_POSIX_QUALIFICATION_SECTION_START"
            for target in node.targets
        )
    ]
    assert len(boundaries) == 1
    boundary = boundaries[0].lineno
    assert namespace["_POSIX_QUALIFICATION_SECTION_START"] == boundary
    expected_names = sorted(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        and node.lineno > boundary
    )
    actual_names = sorted(
        name
        for name, candidate in namespace.items()
        if name.startswith("test_")
        and getattr(candidate, "__module__", None) == namespace["__name__"]
        and getattr(getattr(candidate, "__code__", None), "co_firstlineno", 0)
        > boundary
    )
    assert actual_names == expected_names
    for name in expected_names:
        marks = tuple(
            mark
            for mark in getattr(namespace[name], "pytestmark", ())
            if mark.name == "skipif"
            and mark.kwargs.get("reason")
            == POSIX_QUALIFICATION_TEST.mark.kwargs["reason"]
        )
        assert len(marks) == 1, name
        assert marks[0].args == POSIX_QUALIFICATION_TEST.mark.args, name
        assert marks[0].kwargs == POSIX_QUALIFICATION_TEST.mark.kwargs, name


def test_each_posix_module_registers_last(posix_module):
    """PR #1393：每个实际区段模块都必须以注册调用结尾。"""
    source, _ = posix_module
    _assert_final_registration(source)


def test_each_posix_module_marks_section(posix_module):
    """PR #1393：每个实际区段测试都必须带有精确的平台标记。"""
    _assert_marked_section(*posix_module)


def test_posix_contract_rejects_appended_test(posix_module):
    """PR #1393：注册后追加测试必须同时触发末尾和漏标检测。"""
    source, namespace = posix_module
    addition = "\ndef test_unmarked_append():\n    pass\n"
    mutated = source + addition
    with pytest.raises(AssertionError):
        _assert_final_registration(mutated)
    exec(
        compile("\n" * len(source.splitlines()) + addition, "<append-probe>", "exec"),
        namespace,
    )
    with pytest.raises(AssertionError):
        _assert_marked_section(mutated, namespace)


def test_posix_contract_rejects_missing_mark(posix_module):
    """PR #1393：仅复制一个函数并移除标记，不能污染真实模块。"""
    source, namespace = posix_module
    original = next(
        candidate
        for name, candidate in namespace.items()
        if name.startswith("test_")
        and getattr(getattr(candidate, "__code__", None), "co_firstlineno", 0)
        > namespace["_POSIX_QUALIFICATION_SECTION_START"]
    )
    clone = FunctionType(
        original.__code__,
        original.__globals__,
        original.__name__,
        original.__defaults__,
        original.__closure__,
    )
    clone.pytestmark = [
        mark for mark in original.pytestmark if mark != POSIX_QUALIFICATION_TEST.mark
    ]
    namespace[original.__name__] = clone
    with pytest.raises(AssertionError):
        _assert_marked_section(source, namespace)


# 治理用例位于平台边界前，在 Windows 上也执行；原用例的边界保持不变。
_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_strict_receipt_json_rejects_flat_node_budget_overflow():
    # PR #1247 review 3742970270: 仅检查字节数和深度会漏掉扁平 JSON 树。
    from benchmarks.codegraph_compare.setup_qualification import strict_json_loads

    payload = b"[" + b",".join([b"0"] * 100_000) + b"]"

    with pytest.raises(ValueError, match="depth or node limits"):
        strict_json_loads(payload)


def test_source_inventory_rejects_ignored_checkout_path(tmp_path: Path):
    # PR #1247 review 3742970272: 新鲜证据要求工作副本完全干净。
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
    # PR #1247 review 3742970282: 签名产物必须正是实际执行的产物。
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    build = plan.executions[1]
    decoy = replace(build, argv=("/tmp/decoy", *build.argv[1:]))

    with pytest.raises(ValueError, match="exactly bind authenticated tool/config"):
        replace(plan, executions=(plan.executions[0], decoy, *plan.executions[2:]))


def test_raw_blob_same_size_rewrite_is_rejected(tmp_path: Path):
    # PR #1247 review 3742970275: 首遍摘要不能证明静止状态。
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
    # PR #1247 review 3742970277: 优先从 codemap 发现代码时，也必须包含信任边界。
    codemap = Path("docs/CODEMAPS/architecture.md").read_text(encoding="utf-8")

    assert (
        "`setup_qualification_paths.py` — canonical openat filesystem isolation"
        in codemap
    )
    assert "`setup_qualification_trust.py` — externally supplied Ed25519" in codemap


def test_posix_qualification_marker_invocation_is_final_top_level_statement():
    # PR #1247 review final11: 追加测试必须仍位于已标记区段内。
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
    # PR #1247 review final11: 区段中每个收集到的测试都必须具有相同的 Windows 跳过标记。
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
    # PR #1247 review final11: 提交 0d4d53f0 追加的五个测试在 Windows 上仍须跳过。
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
