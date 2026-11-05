"""The gate must start its child interpreters on Python 3.10 (``requires-python >= 3.10``).

``python -P`` is a 3.11+ flag; 3.10 exits with "Unknown option: -P". The gate
uses ``PYTHONSAFEPATH=1`` instead, which 3.11+ honours like ``-P``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from benchmarks.callers_gate.mcp_client import SAFE_PATH_ENV, server_env

GATE_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "callers_gate"


def _string_constants(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_gate_module_passes_the_3_11_only_dash_p_flag() -> None:
    offenders = [
        f"{path.name}:{line}"
        for path in sorted(GATE_DIR.glob("*.py"))
        for line, value in _string_constants(path)
        if value == "-P"
    ]
    assert offenders == []


def test_server_env_keeps_the_safe_path_setting(tmp_path: Path) -> None:
    env = server_env(tmp_path / "pkg", tmp_path / "private")
    assert env["PYTHONSAFEPATH"] == "1"
    assert SAFE_PATH_ENV == {"PYTHONSAFEPATH": "1"}
