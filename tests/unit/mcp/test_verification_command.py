"""Unit tests for project-aware verification command selection."""

from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
    DefaultTestCommand,
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
