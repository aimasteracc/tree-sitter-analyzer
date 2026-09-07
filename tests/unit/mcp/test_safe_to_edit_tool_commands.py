"""#1376：test_safe_to_edit_tool_commands 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

from pathlib import Path

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_certified_commands_use_extension_runner(tmp_path: Path) -> None:
    """Codex P2 第七轮（C32）：认证 runner 根据目标扩展名推断，不能强制使用 pytest。"""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        AgentWorkflowContext,
        build_agent_workflow,
    )

    go_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="handler.go",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["handler_test.go"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "go test" in str(go_workflow.get("after_edit_commands", []))

    java_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="Calc.java",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["CalcTest.java"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    # C35: 生态系统不明确时省略命令，不作猜测。
    assert "mvn test" not in str(java_workflow.get("after_edit_commands", []))
    assert "go test" not in str(java_workflow.get("after_edit_commands", []))
    # C41: queue-boundary 列表必须为空，不能是包含空字符串的列表。
    assert java_workflow.get("queue_boundary_commands") == []
    # C49: 缺少 runner 时，health/impact 命令不能升级为 TEST
    # 验证命令；停止条件应说明尚未确定验证方法。
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_agent_summary,
    )

    java_summary = build_agent_summary(
        AgentWorkflowContext(
            file_path="Calc.java",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["CalcTest.java"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        ),
        java_workflow,
        verdict_override=None,
    )
    assert java_summary.get("verification_command") == ""
    assert "unidentified" in java_summary.get("stop_condition", "")
    # 不含 guardrails 的工作流覆盖空 guardrails 分支。
    bare_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="Calc.java",
            risk="safe",
            edit_type="add",
            has_tests=True,
            test_files=["CalcTest.java"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert bare_workflow.get("guardrails") == []
    bare_summary = build_agent_summary(
        AgentWorkflowContext(
            file_path="Calc.java",
            risk="safe",
            edit_type="add",
            has_tests=True,
            test_files=["CalcTest.java"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        ),
        bare_workflow,
        verdict_override=None,
    )
    assert "guardrails" not in bare_summary
    # C41: queue-boundary 列表必须为空，不能是包含空字符串的列表。
    assert java_workflow.get("queue_boundary_commands") == []

    rust_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="lib.rs",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/lib_test.rs"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "cargo test" in str(rust_workflow.get("after_edit_commands", []))

    js_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.js",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["__tests__/app.test.js"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    # C39: 仅凭快照不能区分 JS/TS 使用 npm、pnpm 还是 Yarn。
    assert "npm test" not in str(js_workflow.get("after_edit_commands", []))

    py_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.py",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "uv run pytest" in str(py_workflow.get("after_edit_commands", []))


def test_certified_commands_ignore_live_config_files(tmp_path: Path) -> None:
    """Codex P2 第六轮（C28）：认证清单和工作流使用 analyzer 的 pytest 默认值，不能读取未纳入清单的实时配置文件。"""
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        AgentWorkflowContext,
        build_agent_workflow,
    )
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_risk import (
        build_checklist,
    )

    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node test"}}', encoding="utf-8"
    )
    live_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.py",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=str(tmp_path),
        )
    )
    assert "npm test" in str(live_workflow.get("after_edit_commands", []))

    certified_workflow = build_agent_workflow(
        AgentWorkflowContext(
            file_path="app.py",
            risk="safe",
            edit_type="refactor",
            has_tests=True,
            test_files=["tests/test_app.py"],
            health_grade="A",
            project_root=str(tmp_path),
            certified=True,
        )
    )
    assert "npm test" not in str(certified_workflow.get("after_edit_commands", []))
    assert "uv run pytest" in str(certified_workflow.get("after_edit_commands", []))

    certified_checklist = build_checklist(
        "safe",
        0,
        False,
        [],
        "refactor",
        project_root=str(tmp_path),
        certified=True,
    )
    assert all("npm test" not in item for item in certified_checklist)

    # C35: 生态系统不明确且无测试时，清单完全省略
    # 所有命令条目，不应宣称存在不可验证的 runner。
    no_command = build_checklist(
        "safe",
        0,
        False,
        [],
        "refactor",
        file_path="Calc.java",
        project_root=str(tmp_path),
        certified=True,
    )
    assert all("command" not in item.lower() for item in no_command)

    # C35: 生态系统不明确但存在测试时，仍显示测试条目，
    # 但不提供未经认证的运行命令。
    java_tests = build_checklist(
        "safe",
        0,
        True,
        ["CalcTest.java"],
        "refactor",
        file_path="Calc.java",
        project_root=str(tmp_path),
        certified=True,
    )
    assert any("Run existing tests FIRST" in item for item in java_tests)
    assert all(
        "java" not in item.lower() and "mvn" not in item.lower() for item in java_tests
    )

    # 已认证的 Python 且存在测试时，必须包含 pytest 命令条目。
    py_tests = build_checklist(
        "safe",
        0,
        True,
        ["tests/test_app.py"],
        "refactor",
        file_path="app.py",
        project_root=str(tmp_path),
        certified=True,
    )
    assert any("uv run pytest" in item for item in py_tests)


@pytest.mark.parametrize("path", ["src/util.cxx", "include/util.hxx"])
def test_target_language_recognizes_indexed_cpp_extensions(path: str) -> None:
    # PR #1308 review: 认证读取使用统一的索引扩展名映射。
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _target_language,
    )

    assert _target_language(path) == "cpp"


@pytest.mark.parametrize(
    "path", ["tests/test_util.cc", "test/test_util.cxx", "spec/test_util.hxx"]
)
def test_certified_test_path_recognizes_cpp_extensions(path: str) -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _looks_like_test_path,
    )

    assert _looks_like_test_path(path, "cpp")


def test_certified_test_path_recognizes_root_pytest_module() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _looks_like_test_path,
    )

    assert _looks_like_test_path("test_app.py", "python") is True
    assert _looks_like_test_path("src/test_adapter.py", "python") is False


@pytest.mark.parametrize(
    ("name", "language", "expected"),
    [
        ("test_parser.c", "c", True),
        ("parser.c", "c", False),
        ("test_parser.cpp", "cpp", True),
        ("parser.cpp", "cpp", False),
    ],
)
def test_c_family_test_name_conventions(
    name: str, language: str, expected: bool
) -> None:
    assert helpers._looks_like_test_name(name, language) is expected


def test_pytest_projection_skips_seen_and_outside_dependents() -> None:
    assert helpers._pytest_exercising_projection_complete(
        "util.py",
        ["util.py", "missing.py", "tests/test_util.py"],
        frozenset({"util.py", "tests/test_util.py"}),
        reverse_dependencies={},
    )


def test_exercising_projection_accepts_python_support_module() -> None:
    dependent = "pkg/__init__.py"
    assert helpers._pytest_exercising_projection_complete(
        "util.py",
        [dependent],
        frozenset({"util.py", dependent}),
        reverse_dependencies={},
    )


def test_exercising_projection_ignores_non_certified_language_dependent() -> None:
    assert helpers._pytest_exercising_projection_complete(
        "util.py",
        ["docs/guide.md"],
        frozenset({"util.py", "docs/guide.md"}),
        reverse_dependencies={},
    )


@pytest.mark.parametrize(
    "test_path",
    ["checks/check_api.c", "checks/check_api.cpp", "checks/ApiCheck.java"],
)
def test_exercising_projection_rejects_custom_native_test_names(
    test_path: str,
) -> None:
    assert not helpers._pytest_exercising_projection_complete(
        "src/util.h",
        [test_path],
        frozenset({"src/util.h", test_path}),
        reverse_dependencies={},
    )
