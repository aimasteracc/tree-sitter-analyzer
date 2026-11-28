"""Guard for #1891: subprocess calls must not inherit the MCP stdio stdin.

On Windows a child process (for example ``git``) that inherits the MCP
server's stdin pipe can hang forever.  Every subprocess spawn in the package
must therefore set ``stdin`` explicitly (normally ``subprocess.DEVNULL``), or
pass ``input=`` (which makes ``subprocess.run`` create its own stdin pipe).
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "tree_sitter_analyzer"

_SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}
_ASYNCIO_FUNCS = {"create_subprocess_exec", "create_subprocess_shell"}


def _spawn_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "subprocess" and func.attr in _SUBPROCESS_FUNCS:
            return f"subprocess.{func.attr}"
        if func.value.id == "asyncio" and func.attr in _ASYNCIO_FUNCS:
            return f"asyncio.{func.attr}"
    if isinstance(func, ast.Name) and func.id in _SUBPROCESS_FUNCS - {"run", "call"}:
        # ``from subprocess import Popen`` style (run/call are too generic).
        return func.id
    return None


def _has_stdin(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg in {"stdin", "input"}:
            return True
        if kw.arg is None:  # **kwargs may carry stdin; cannot judge, allow
            return True
    return False


def find_violations(source: str, filename: str = "<src>") -> list[tuple[int, str]]:
    tree = ast.parse(source, filename=filename)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _spawn_name(node)
            if name and not _has_stdin(node):
                found.append((node.lineno, name))
    return sorted(found)


def test_all_subprocess_calls_set_stdin() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "subprocess" not in source and "Popen" not in source:
            continue  # cheap prefilter: keeps the scan inside the unit budget
        for lineno, name in find_violations(source, str(path)):
            offenders.append(f"{path.relative_to(PACKAGE_ROOT.parent)}:{lineno} {name}")
    assert not offenders, (
        "subprocess calls without stdin= (add stdin=subprocess.DEVNULL, #1891):\n"
        + "\n".join(offenders)
    )


def test_scanner_flags_missing_stdin() -> None:
    src = "import subprocess\nsubprocess.run(['git'])\n"
    assert find_violations(src) == [(2, "subprocess.run")]


def test_scanner_accepts_stdin_or_input() -> None:
    src = (
        "import subprocess, asyncio\n"
        "subprocess.run(['git'], stdin=subprocess.DEVNULL)\n"
        "subprocess.run(['cat'], input=b'x')\n"
        "asyncio.create_subprocess_exec('x', stdin=asyncio.subprocess.PIPE)\n"
    )
    assert find_violations(src) == []


def test_scanner_flags_asyncio_and_bare_popen() -> None:
    src = (
        "import asyncio\nfrom subprocess import Popen\n"
        "asyncio.create_subprocess_exec('x')\nPopen(['x'])\n"
    )
    assert find_violations(src) == [(3, "asyncio.create_subprocess_exec"), (4, "Popen")]
