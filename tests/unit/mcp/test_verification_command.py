"""Unit tests for project-aware verification command selection."""

import pytest

from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
    PYTEST_COMMAND,
    DefaultTestCommand,
    build_test_argv_batches,
    build_test_command,
    detect_default_test_command,
)


def test_detect_default_test_command_falls_back_to_pytest(tmp_path):
    """Unknown or Python-style projects should keep the repo's pytest contract."""
    assert detect_default_test_command(tmp_path) == DefaultTestCommand(
        "pytest",
        "uv run pytest -q",
    )


def test_detect_default_test_command_uses_package_json_test_script(tmp_path):
    """Node projects should expose their package test script to agents."""
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}',
        encoding="utf-8",
    )

    assert detect_default_test_command(tmp_path) == DefaultTestCommand(
        "npm",
        "npm test",
    )


def test_detect_default_test_command_prefers_node_lockfile_manager(tmp_path):
    """Node package manager lockfiles should make commands copy-pasteable."""
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'", encoding="utf-8")

    assert detect_default_test_command(tmp_path) == DefaultTestCommand(
        "pnpm",
        "pnpm test",
    )


def test_detect_default_test_command_uses_go_test(tmp_path):
    """Go projects should not be sent into pytest."""
    (tmp_path / "go.mod").write_text("module example.com/tool\n", encoding="utf-8")

    assert detect_default_test_command(tmp_path) == DefaultTestCommand(
        "go",
        "go test ./...",
    )


def test_detect_default_test_command_uses_cargo_test(tmp_path):
    """Rust projects should surface cargo test as the default command."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'tool'\n", encoding="utf-8")

    assert detect_default_test_command(tmp_path) == DefaultTestCommand(
        "cargo",
        "cargo test",
    )


def test_build_test_command_targets_supported_runners():
    """Supported runners should receive direct test path arguments."""
    assert (
        build_test_command(
            DefaultTestCommand("npm", "npm test --"),
            ["tests/unit/path with space.test.ts"],
        )
        == "npm test -- 'tests/unit/path with space.test.ts'"
    )


def test_build_test_command_falls_back_for_untargetable_runners():
    """Untargeted runners should keep the safe full-project default command."""
    assert (
        build_test_command(
            DefaultTestCommand("go", "go test ./..."),
            ["internal/tool/tool_test.go"],
        )
        == "go test ./..."
    )


def test_batches_preserve_a_thousand_targets_in_order():
    """#1407：大集合按实际进程参数分批，不能丢弃或重复目标。"""
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        build_test_commands,
    )

    targets = [f"tests/test_{index:04d}.py" for index in range(1000)]
    commands = build_test_commands(
        DefaultTestCommand("pytest", "uv run pytest -q"), targets
    )
    expected = [
        "uv run pytest " + " ".join(targets[start : start + 20]) + " -q"
        for start in range(0, 1000, 20)
    ]
    assert commands == expected


def test_batches_respect_encoded_command_length():
    """#1407：少量长 Unicode 路径也须分批，不能只限制路径个数。"""
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        build_test_commands,
    )

    prefix = ("路径" * 40 + "/") * 15
    targets = [prefix + f"test_{index}.py" for index in range(3)]
    expected = [
        build_test_command(DefaultTestCommand("pytest", "uv run pytest -q"), [target])
        for target in targets
    ]
    assert (
        build_test_commands(DefaultTestCommand("pytest", "uv run pytest -q"), targets)
        == expected
    )


def test_oversized_single_target_is_explicitly_rejected():
    """#1407：无法形成有界命令的单路径必须报错，不能产生不可执行的成功计划。"""
    import pytest

    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        build_test_commands,
    )

    with pytest.raises(ValueError, match="TEST_TARGET_EXCEEDS_COMMAND_BUDGET"):
        build_test_commands(
            DefaultTestCommand("pytest", "uv run pytest -q"), ["x" * 6000]
        )


def test_windows_verification_chain_quotes_arguments_and_checks_each_step(monkeypatch):
    # #1407：PowerShell 5.1 不支持 &&，单引号和美元符号必须保留原值。
    from tree_sitter_analyzer.mcp.tools.utils import verification_command as commands

    monkeypatch.setattr(commands.sys, "platform", "win32")
    assert commands.join_verification_steps(
        ["pytest 'tests/a b.py'", "pytest 'tests/a'\"'\"'b$HOME.py'"]
    ) == (
        "& { & 'pytest' 'tests/a b.py'; if (-not $?) { throw 'Verification failed' }; "
        "& 'pytest' 'tests/a''b$HOME.py'; if (-not $?) { throw 'Verification failed' } }"
    )


def test_posix_verification_chain_stops_after_failure(tmp_path):
    # #1407：多步命令不能在前一步失败后继续运行。
    import subprocess
    import sys

    import pytest

    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        join_verification_steps,
    )

    if sys.platform == "win32":
        pytest.skip("tracked: #1407 POSIX 原生 shell 验证")
    result = subprocess.run(
        join_verification_steps(["false", "touch should_not_exist"]),
        shell=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 1
    assert (tmp_path / "should_not_exist").exists() is False


def test_windows_native_verification_chain_stops_after_failure(tmp_path):
    # #1407：Windows CI 使用真实 PowerShell 5.1 验证失败传播。
    import subprocess
    import sys

    import pytest

    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        join_verification_steps,
    )

    if sys.platform != "win32":
        pytest.skip("tracked: #1407 PowerShell 5.1 原生验证由 Windows CI 执行")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            join_verification_steps(["cmd /c exit 7", "cmd /c mkdir should_not_exist"]),
        ],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert (tmp_path / "should_not_exist").exists() is False


@pytest.mark.parametrize("step_count", [1, 2])
def test_native_verification_chain_preserves_order_and_literal_arguments(
    tmp_path, step_count
):
    # #1407：真实 shell 按顺序执行，并保留路径中的引号、空格和美元符号。
    import shlex
    import subprocess
    import sys

    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        join_verification_steps,
    )

    literal = "a b'c$HOME"
    steps = [
        shlex.join(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path('receipt').write_text(sys.argv[1], encoding='utf-8')",
                literal,
            ]
        ),
        shlex.join(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; assert pathlib.Path('receipt').read_text(encoding='utf-8')==sys.argv[1]",
                literal,
            ]
        ),
    ]
    command = join_verification_steps(steps[:step_count])
    if sys.platform == "win32":
        args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        args = ["/bin/sh", "-c", command]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "receipt").read_text(encoding="utf-8") == literal


def test_argv_batches_preserve_exact_targets_and_windows_process_budget():
    # #1407：参数数组保留引用字符和重复项，Windows 启动转义后的长度也必须有界。
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        build_test_argv_batches,
    )

    target = "tests/test_case.py::test_value[" + ('\\\\\\\\"' * 350) + "]"
    targets = [target, target, "tests/空 格.py"]
    assert build_test_argv_batches(
        DefaultTestCommand("pytest", "uv run pytest -q"), targets
    ) == [
        ["uv", "run", "pytest", target, "-q"],
        ["uv", "run", "pytest", target, "tests/空 格.py", "-q"],
    ]


def test_argv_batches_preserve_default_runner_semantics():
    # #1407：不能把不可定向的项目默认门禁改成空执行或错误的路径参数。
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        build_test_argv_batches,
    )

    assert build_test_argv_batches(
        DefaultTestCommand("go", "go test ./..."), ["a_test.go"]
    ) == [["go", "test", "./..."]]
    assert build_test_argv_batches(
        DefaultTestCommand("pytest", "uv run pytest -q"), []
    ) == [["uv", "run", "pytest", "-q"]]


def test_shell_targets_use_independent_bash_processes_in_order():
    # 2026-09-09：TSA 把 .sh 交给 pytest，导致 shell 检查完全未执行。
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        PYTEST_COMMAND,
        build_test_argv_batches,
    )

    assert build_test_argv_batches(
        PYTEST_COMMAND,
        [
            "tests/test_a.py",
            "tests/test one.sh",
            "tests/test_two.sh",
            "tests/test_b.py",
        ],
    ) == [
        ["uv", "run", "pytest", "tests/test_a.py", "-q"],
        ["uv", "run", "bash", "--", "tests/test one.sh"],
        ["uv", "run", "bash", "--", "tests/test_two.sh"],
        ["uv", "run", "pytest", "tests/test_b.py", "-q"],
    ]


def test_shell_command_uses_quoted_literal_path():
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        PYTEST_COMMAND,
        join_verification_steps,
    )

    assert build_test_command(
        PYTEST_COMMAND, ["tests/test $HOME.sh"]
    ) == join_verification_steps(["uv run bash -- 'tests/test $HOME.sh'"])


def test_pytest_node_id_ending_in_sh_stays_with_pytest():
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        PYTEST_COMMAND,
        build_test_argv_batches,
    )

    target = "tests/test_files.py::test_script.sh"
    assert build_test_argv_batches(PYTEST_COMMAND, [target]) == [
        ["uv", "run", "pytest", target, "-q"]
    ]


def test_shell_only_plan_does_not_claim_pytest_is_required():
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_verification import (
        _build_verification_plan,
    )

    path = "tests/test_check.sh"
    plan = _build_verification_plan([path], [path])
    assert plan["verification_command"] == "uv run bash -- tests/test_check.sh"
    assert plan["test_required"] is True
    assert plan["pytest_required"] is False
    assert plan["pytest_command"] == ""


def test_shell_target_still_has_a_command_length_budget():
    import pytest

    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        PYTEST_COMMAND,
        build_test_argv_batches,
    )

    with pytest.raises(ValueError, match="TEST_TARGET_EXCEEDS_COMMAND_BUDGET"):
        build_test_argv_batches(PYTEST_COMMAND, ["tests/" + "路径" * 4000 + ".sh"])


@pytest.mark.parametrize("project_kind", ["python", "node"])
def test_shell_only_cli_plan_executes_the_actual_script(tmp_path, project_kind):
    # 2026-09-09：用真实 CLI 和新仓库确认不会再返回 pytest 的空收集命令。
    import json
    import shlex
    import subprocess
    import sys

    def run(argv):
        result = subprocess.run(
            argv, cwd=tmp_path, capture_output=True, text=True, check=False
        )
        if result.returncode:
            print("command:", argv)
            print("stdout:", result.stdout)
            print("stderr:", result.stderr)
        assert result.returncode == 0
        return result

    if project_kind == "node":
        (tmp_path / "package.json").write_text(
            '{"scripts":{"test":"vitest run"}}', encoding="utf-8"
        )
    run(["git", "init", "-q"])
    run(["git", "config", "user.email", "test@example.com"])
    run(["git", "config", "user.name", "test"])
    path = tmp_path / "tests/test_smoke's.sh"
    path.parent.mkdir()
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    run(["git", "add", "."])
    run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "baseline"])
    body = (
        'python -c \'print("shell-verified", end="")\' > receipt'
        if project_kind == "python"
        else "printf shell-verified > receipt"
    )
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    response = run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            "--change-impact",
            "--change-impact-full",
            "--format",
            "json",
        ]
    )
    plan = json.loads(response.stdout)
    assert plan["pytest_required"] is False
    assert plan["test_required"] is True
    command = plan["verification_command"]
    if sys.platform == "win32":
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command])
    else:
        run(shlex.split(command))
    assert (tmp_path / "receipt").read_text(encoding="utf-8") == "shell-verified"


@pytest.mark.parametrize("runner", ["npm", "pnpm", "yarn", "bun"])
def test_node_shell_targets_bypass_the_package_test_runner(runner):
    """Node 的 shell 检查也必须由 Bash 执行，不能传入 Jest/Vitest。"""
    default = DefaultTestCommand(runner, f"{runner} test")
    import shutil
    import sys

    executable = shutil.which("bash") if sys.platform == "win32" else "bash"
    assert build_test_argv_batches(default, ["tests/test_smoke.sh"]) == [
        [executable, "--", "tests/test_smoke.sh"]
    ]


def test_single_shell_target_uses_powershell_literal_quoting(monkeypatch):
    """单条 shell 命令中的撇号和美元符号也按 PowerShell 字面量传递。"""
    from tree_sitter_analyzer.mcp.tools.utils import verification_command as module

    monkeypatch.setattr(module.sys, "platform", "win32")
    assert module.build_test_command(PYTEST_COMMAND, ["tests/a'b$HOME.sh"]) == (
        "& { & 'uv' 'run' 'bash' '--' 'tests/a''b$HOME.sh'; "
        "if (-not $?) { throw 'Verification failed' } }"
    )


@pytest.mark.parametrize("bash_path", ["C:/Program Files/Git/bin/bash.exe", None])
def test_windows_node_shell_resolves_the_path_executable(monkeypatch, bash_path):
    """Windows 原生启动不得绕过 PATH 选择另一个同名 Bash。"""
    import shutil

    from tree_sitter_analyzer.mcp.tools.utils import verification_command as module

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(
        shutil, "which", lambda name: bash_path if name == "bash" else None
    )
    default = DefaultTestCommand("npm", "npm test")
    if bash_path is None:
        with pytest.raises(ValueError, match="BASH_EXECUTABLE_NOT_FOUND"):
            build_test_argv_batches(default, ["tests/test_smoke.sh"])
    else:
        assert build_test_argv_batches(default, ["tests/test_smoke.sh"]) == [
            [bash_path, "--", "tests/test_smoke.sh"]
        ]
