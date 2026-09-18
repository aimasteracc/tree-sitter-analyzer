#!/usr/bin/env python3
"""Every tool that guards a parameter must run the guard before reading it.

``BaseMCPTool`` subclasses declare ``validate_arguments`` and are responsible
for calling it: ``wrap_execute_with_strict_params`` checks the declared schema,
not this method. A tool that subscript-reads ``arguments["x"]`` for a key its
own ``validate_arguments`` refuses to run without therefore rejects a missing
value with ``KeyError: 'x'`` instead of the message it wrote for that case.

That is how ``nav action=lineage`` answered ``KeyError: 'symbol'`` — for a
missing symbol *and* for the documented ``function_name`` alias — while every
sibling action replied with a verdict envelope. ``execute`` reading
``arguments[...]`` directly is not wrong on its own; skipping the guard that
already describes the precondition is.

The check is structural rather than a list of names, so a tool added later is
covered without editing this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"

_GUARD_READERS = frozenset({"get", "require"})


def _methods(cls: ast.ClassDef) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _guarded_keys(validate: ast.AST) -> set[str]:
    """Parameter names ``validate_arguments`` reads before deciding to allow."""
    keys: set[str] = set()
    for node in ast.walk(validate):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _GUARD_READERS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def _required_reads(execute: ast.AST) -> dict[str, int]:
    """``arguments["name"]`` subscripts in ``execute``, by name."""
    reads: dict[str, int] = {}
    for node in ast.walk(execute):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "arguments"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            reads.setdefault(node.slice.value, node.lineno)
    return reads


def _calls_validate(execute: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "validate_arguments"
        for node in ast.walk(execute)
    )


def _survey() -> tuple[list[str], int]:
    """Return (unguarded tools, tools that declare the contract at all)."""
    unguarded: list[str] = []
    declaring = 0
    for path in sorted(TOOLS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            methods = _methods(cls)
            if "validate_arguments" not in methods or "execute" not in methods:
                continue
            declaring += 1
            if _calls_validate(methods["execute"]):
                continue
            guarded = _guarded_keys(methods["validate_arguments"])
            for name, line in sorted(_required_reads(methods["execute"]).items()):
                if name in guarded:
                    unguarded.append(
                        f"{path.name}:{line} {cls.name} reads arguments[{name!r}]"
                    )
    return unguarded, declaring


def test_the_survey_found_the_tools_it_constrains() -> None:
    """精确固定声明两个方法的工具数，防止扫描器空跑后仍然通过。"""
    _unguarded, declaring = _survey()
    assert declaring == 83, (
        f"expected 82 tool classes declaring validate_arguments and execute, "
        f"found {declaring}; update this constant if the tool set legitimately "
        "changed, otherwise the AST walk no longer matches how tools are written"
    )


def test_no_tool_reads_a_guarded_parameter_without_validating() -> None:
    unguarded, _declaring = _survey()
    assert unguarded == [], (
        "these tools read a parameter their own validate_arguments guards, "
        "without calling it — a missing value raises KeyError instead of the "
        "message the tool wrote for that case, so the caller gets no verdict "
        "envelope and no hint:\n  " + "\n  ".join(unguarded)
    )


def test_the_check_can_fail() -> None:
    """The analysis must reject the shape it exists to catch.

    The two tools this gate was written for both matched it while broken; this
    pins that a reintroduced copy still does.
    """
    source = (
        "import ast\n"
        "class Probe:\n"
        "    def validate_arguments(self, arguments):\n"
        "        if not arguments.get('symbol'):\n"
        "            raise ValueError('symbol is required')\n"
        "        return True\n"
        "    async def execute(self, arguments):\n"
        "        return arguments['symbol'].strip()\n"
    )
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    methods = _methods(cls)
    assert _guarded_keys(methods["validate_arguments"]) == {"symbol"}
    assert _calls_validate(methods["execute"]) is False
    assert sorted(_required_reads(methods["execute"])) == ["symbol"]

    guarded_source = source.replace(
        "        return arguments['symbol'].strip()",
        "        self.validate_arguments(arguments)\n"
        "        return arguments['symbol'].strip()",
    )
    guarded_cls = next(
        n for n in ast.parse(guarded_source).body if isinstance(n, ast.ClassDef)
    )
    assert _calls_validate(_methods(guarded_cls)["execute"]) is True
