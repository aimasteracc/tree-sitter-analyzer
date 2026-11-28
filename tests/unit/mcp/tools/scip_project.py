"""Test helper: the TS fixture project (``tests/fixtures/scip_ts``) as a git repo.

``index.scip`` in the fixture was written by ``npx @sourcegraph/scip-typescript@0.6.1
index`` in that directory. To regenerate after editing ``src/``::

    cd tests/fixtures/scip_ts
    npx -y @sourcegraph/scip-typescript@0.6.1 index --output index.scip
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "scip_ts"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def git(root: Path, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(root), *args], check=True, capture_output=True)


def make_project(root: Path) -> Path:
    """Copy the fixture sources into ``root`` and commit them."""
    shutil.copytree(FIXTURE / "src", root / "src")
    for name in ("tsconfig.json", "package.json"):
        shutil.copy(FIXTURE / name, root / name)
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")
    return root


def install_index(root: Path, *, manifest: bool = True) -> Path:
    """Put the fixture ``index.scip`` at the default location (+ a fresh manifest)."""
    from tree_sitter_analyzer.mcp.tools.callers_scip_manifest import write_manifest

    target = root / ".ast-cache" / "scip" / "index.scip"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / "index.scip", target)
    if manifest:
        write_manifest(root, target, {"name": "scip-typescript", "version": "0.6.1"})
    return target


async def tsa_index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


async def callers(root: Path, name: str, file_path: str, **extra: object) -> dict:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    return await CodeGraphCallersTool(str(root)).execute(
        {
            "function_name": name,
            "file_path": file_path,
            "include_bodies": False,
            **extra,
        }
    )
