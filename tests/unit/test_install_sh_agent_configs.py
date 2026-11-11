"""验证安装器按客户端实际读取的位置配置 MCP。"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.qualify_fresh_install import _restricted_tools, _write_executable

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: install.sh supports macOS/Linux shell installs only",
)

REPO = Path(__file__).resolve().parents[2]
ARGS = ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"]


@pytest.fixture
def installer(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    tools = _restricted_tools(tmp_path)
    _write_executable(tools / "uv", '#!/bin/sh\nprintf "uv 0.13.7\\n"\n')
    _write_executable(tools / "uvx", "#!/bin/sh\nexit 99\n")
    (tools / "uname").unlink()
    _write_executable(tools / "uname", "#!/bin/sh\necho Linux\n")

    def run():
        return subprocess.run(
            ["/bin/bash", str(REPO / "install.sh")],
            cwd=project,
            env={
                "HOME": str(home),
                "PATH": str(tools),
                "TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP": "1",
            },
            capture_output=True,
            text=True,
            timeout=20,
        )

    return home, project, tools, run


@pytest.mark.parametrize(
    "client,path,key",
    [
        ("claude", ".mcp.json", "mcpServers"),
        ("cursor", ".cursor/mcp.json", "mcpServers"),
        ("code", ".vscode/mcp.json", "servers"),
    ],
)
@pytest.mark.parametrize("existing", [False, True])
def test_client_config_created_or_merged(installer, client, path, key, existing):
    home, project, tools, run = installer
    _write_executable(tools / client, "#!/bin/sh\nexit 0\n")
    config = project / path
    original = {"other": 1, key: {"other-server": {"command": "other"}}}
    if existing:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(original))
        config.chmod(0o640)
    result = run()
    assert result.returncode == 0, result.stderr
    entry = {
        "command": "uvx",
        "args": ARGS,
        "env": {"TREE_SITTER_PROJECT_ROOT": str(project)},
    }
    if key == "servers":
        entry["type"] = "stdio"
        entry["env"]["TREE_SITTER_PROJECT_ROOT"] = "${workspaceFolder}"
    expected = json.loads(json.dumps(original)) if existing else {key: {}}
    expected[key]["tree-sitter-analyzer"] = entry
    assert json.loads(config.read_text()) == expected
    assert config.read_bytes().endswith(b"\n")
    assert config.stat().st_mode & 0o777 == (0o640 if existing else 0o644)
    backups = list(config.parent.glob(config.name + ".bak.*"))
    assert len(backups) == int(existing)
    if existing:
        assert json.loads(backups[0].read_text()) == original
    assert not (home / ".cursor/mcp.json").exists()


def test_global_cursor_untouched(installer):
    home, project, tools, run = installer
    config = home / ".cursor/mcp.json"
    config.parent.mkdir()
    body = '{"mcpServers":{"tree-sitter-analyzer":{"command":"old"}}}\n'
    config.write_text(body)
    result = run()
    assert result.returncode == 0
    assert config.read_text() == body
    assert list(config.parent.glob("*.bak.*")) == []
    assert (project / ".cursor/mcp.json").is_file()
    assert "pins every project to one root" in result.stdout


@pytest.mark.parametrize("spelling", ["Claude", "claude"])
def test_desktop_existing_global_config(installer, spelling):
    home, project, tools, run = installer
    config = home / f".config/{spelling}/claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}\n")
    result = run()
    assert result.returncode == 0
    assert json.loads(config.read_text()) == {
        "mcpServers": {
            "tree-sitter-analyzer": {
                "command": "uvx",
                "args": ARGS,
                "env": {"TREE_SITTER_PROJECT_ROOT": str(project)},
            }
        }
    }
    assert "global entry pins one project root" in result.stdout


def test_codex_prints_block_without_editing_toml(installer):
    home, project, tools, run = installer
    (home / ".codex").mkdir()
    config = home / ".codex/config.toml"
    config.write_text("# existing\n")
    result = run()
    assert result.returncode == 0
    assert config.read_text() == "# existing\n"
    assert (
        '[mcp_servers.tree-sitter-analyzer]\ncommand = "uvx"\n'
        'args = ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"]\n'
        f'env = {{ TREE_SITTER_PROJECT_ROOT = "{project}" }}'
    ) in result.stdout


def test_next_steps_and_undetected_clients(installer):
    home, project, tools, run = installer
    result = run()
    assert result.returncode == 0
    assert list(project.iterdir()) == []
    assert "Skipped agents" in result.stdout
    assert (
        f'uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer --project-root "{project}" --full-index'
        in result.stdout
    )
    assert (
        f'TREE_SITTER_PROJECT_ROOT="{project}" uvx --from tree-sitter-analyzer tree-sitter-analyzer --doctor'
        in result.stdout
    )
    assert (
        "If something looks wrong: tree-sitter-analyzer --doctor" not in result.stdout
    )


def test_existing_symlink_preserved(installer):
    home, project, tools, run = installer
    target = home / "managed.json"
    target.write_text("{}\n")
    config = project / ".mcp.json"
    config.symlink_to(target)
    result = run()
    assert result.returncode == 0
    assert config.is_symlink()
    assert (
        json.loads(target.read_text())["mcpServers"]["tree-sitter-analyzer"]["command"]
        == "uvx"
    )
    assert [p.read_text() for p in project.glob(".mcp.json.bak.*")] == ["{}\n"]


@pytest.mark.parametrize(
    "key,path", [("servers", ".vscode/mcp.json"), ("mcpServers", ".mcp.json")]
)
def test_invalid_server_map_fails_without_writing(installer, key, path):
    home, project, tools, run = installer
    config = project / path
    config.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({key: []})
    config.write_text(body)
    result = run()
    assert result.returncode == 1
    assert config.read_text() == body
    assert list(config.parent.glob(config.name + ".bak.*")) == []
    assert "Failed agents" in result.stdout


@pytest.mark.parametrize(
    "directory,path",
    [
        (".claude", ".mcp.json"),
        (".cursor", ".cursor/mcp.json"),
        (".config/Code/User", ".vscode/mcp.json"),
    ],
)
def test_client_detected_by_directory(installer, directory, path):
    home, project, tools, run = installer
    (home / directory).mkdir(parents=True)
    result = run()
    assert result.returncode == 0
    assert (project / path).is_file()


def test_existing_entry_is_replaced_and_configured(installer):
    home, project, tools, run = installer
    config = project / ".mcp.json"
    config.write_text('{"mcpServers":{"tree-sitter-analyzer":{"command":"old"}}}')
    result = run()
    assert result.returncode == 0
    assert json.loads(config.read_text())["mcpServers"]["tree-sitter-analyzer"] == {
        "command": "uvx",
        "args": ARGS,
        "env": {"TREE_SITTER_PROJECT_ROOT": str(project)},
    }
    assert "✅ Configured agents:\n   • Claude Code (project)" in result.stdout


def test_desktop_prefers_uppercase_path(installer):
    home, project, tools, run = installer
    for spelling in ("Claude", "claude"):
        config = home / f".config/{spelling}/claude_desktop_config.json"
        config.parent.mkdir(parents=True)
        config.write_text("{}\n")
    result = run()
    assert result.returncode == 0
    assert (home / ".config/claude/claude_desktop_config.json").read_text() == "{}\n"
    assert (
        json.loads((home / ".config/Claude/claude_desktop_config.json").read_text())[
            "mcpServers"
        ]["tree-sitter-analyzer"]["command"]
        == "uvx"
    )


def test_macos_desktop_and_vscode_detection(installer):
    home, project, tools, run = installer
    _write_executable(tools / "uname", "#!/bin/sh\necho Darwin\n")
    desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("{}\n")
    (home / "Library/Application Support/Code/User").mkdir(parents=True)
    result = run()
    assert result.returncode == 0
    assert json.loads(desktop.read_text())["mcpServers"]["tree-sitter-analyzer"][
        "env"
    ] == {"TREE_SITTER_PROJECT_ROOT": str(project)}
    assert json.loads((project / ".vscode/mcp.json").read_text())["servers"][
        "tree-sitter-analyzer"
    ]["env"] == {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
