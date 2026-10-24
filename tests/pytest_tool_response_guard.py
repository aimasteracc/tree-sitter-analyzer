"""Validate every MCP tool response the suite produces.

Each production ``BaseMCPTool.execute()`` call made while a test runs (setup,
call or teardown) is checked with
:func:`tree_sitter_analyzer.mcp.tools.tool_response.envelope_violations`:
``validate_tool_response`` plus the agent-envelope rules (verdict /
``agent_summary`` consistency, a machine code on failure, completeness reason
codes from the known set, truncation fields that agree with their counts).

A violation fails the test that produced it, at teardown, naming the tool,
the rule and the message. Only the outermost production call is checked: a
facade's answer is what a client sees, and its inner tool's answer is part of
it. Responses built from a test double (a ``BaseMCPTool`` subclass defined
outside ``tree_sitter_analyzer``) are not production output and are skipped,
together with every production response that wraps them.

Known producer gaps live in :data:`tests.tool_response_allowlist.ALLOWLIST`,
each with an issue reference; the list may only shrink
(``tests/governance/test_tool_response_allowlist.py``).

``TSA_TOOL_RESPONSE_GUARD`` selects the mode: ``enforce`` (default) fails the
test, ``report`` writes every violation (allowlisted or not) as JSON lines to
``TSA_TOOL_RESPONSE_GUARD_REPORT`` without failing, ``off`` disables the guard.
"""

from __future__ import annotations

import contextvars
import fnmatch
import functools
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.tool_response_allowlist import ALLOWLIST

MODE_ENV = "TSA_TOOL_RESPONSE_GUARD"
REPORT_ENV = "TSA_TOOL_RESPONSE_GUARD_REPORT"
_PLUGIN_NAME = "tsa-tool-response-guard"
_GUARD_ATTR = "_tsa_tool_response_guarded"
_PRODUCTION_PREFIX = "tree_sitter_analyzer."


@dataclass
class _Frame:
    """One ``execute`` call on the current call path."""

    production: bool
    from_double: bool = False


@dataclass(frozen=True)
class Violation:
    tool: str
    rule: str
    message: str


_STACK: contextvars.ContextVar[tuple[_Frame, ...]] = contextvars.ContextVar(
    "tsa_tool_response_stack", default=()
)


@dataclass
class _State:
    mode: str
    current: str | None = None
    found: dict[str, list[Violation]] = field(default_factory=dict)
    allowlist_hits: set[int] = field(default_factory=set)
    checked: int = 0


_STATE = _State(mode="off")


def allowlisted(violation: Violation) -> int | None:
    """Index of the allowlist entry covering ``violation``, if any."""
    for index, entry in enumerate(ALLOWLIST):
        if entry["rule"] == violation.rule and fnmatch.fnmatchcase(
            violation.tool, entry["tool"]
        ):
            return index
    return None


def tool_label(tool: Any, arguments: Any) -> str:
    """``nav action=callers`` for a facade, else the tool's definition name."""
    facade = getattr(tool, "facade_name", None)
    if isinstance(facade, str):
        action = arguments.get("action") if isinstance(arguments, dict) else None
        return f"{facade} action={action}" if action else facade
    cls = type(tool)
    if cls not in _NAMES:
        try:
            name = tool.get_tool_definition().get("name")
        except Exception:  # noqa: BLE001 - the label is best effort
            name = None
        _NAMES[cls] = name if isinstance(name, str) and name else cls.__name__
    return _NAMES[cls]


_NAMES: dict[type, str] = {}


def _record(tool: Any, arguments: Any, result: Any) -> None:
    from tree_sitter_analyzer.mcp.tools.tool_response import envelope_violations

    _STATE.checked += 1
    label = tool_label(tool, arguments)
    problems = envelope_violations(result, label)
    if not problems or _STATE.current is None:
        return
    bucket = _STATE.found.setdefault(_STATE.current, [])
    for rule, message in problems:
        bucket.append(Violation(label, rule, message))


def guard_execute(execute: Any) -> Any:
    """Wrap an ``execute`` coroutine function so its response is validated."""
    if getattr(execute, _GUARD_ATTR, False):
        return execute

    @functools.wraps(execute)
    async def guarded(self: Any, arguments: Any) -> Any:
        stack = _STACK.get()
        production = type(self).__module__.startswith(_PRODUCTION_PREFIX)
        if not production:
            for frame in stack:
                frame.from_double = True
        frame = _Frame(production)
        token = _STACK.set((*stack, frame))
        try:
            result = await execute(self, arguments)
        finally:
            _STACK.reset(token)
        outermost = not any(f.production for f in stack)
        if production and outermost and not frame.from_double:
            _record(self, arguments, result)
        return result

    setattr(guarded, _GUARD_ATTR, True)
    return guarded


def _subclasses(cls: type) -> list[type]:
    seen: list[type] = []
    pending = list(cls.__subclasses__())
    while pending:
        sub = pending.pop()
        if sub not in seen:
            seen.append(sub)
            pending.extend(sub.__subclasses__())
    return seen


def _patch_tools() -> None:
    from tree_sitter_analyzer.mcp.tools import base_tool

    original = base_tool.wrap_execute_with_strict_params
    if not getattr(original, _GUARD_ATTR, False):

        def wrap(cls_execute: Any) -> Any:
            wrapped = original(cls_execute)
            return wrapped if wrapped is cls_execute else guard_execute(wrapped)

        setattr(wrap, _GUARD_ATTR, True)
        base_tool.wrap_execute_with_strict_params = wrap  # type: ignore[assignment]
    for cls in _subclasses(base_tool.BaseMCPTool):
        execute = cls.__dict__.get("execute")
        if getattr(execute, base_tool._F5_WRAPPED_ATTR, False):
            cls.execute = guard_execute(execute)  # type: ignore[attr-defined]


class ToolResponseGuard:
    """pytest hooks registered by :func:`install`."""

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: Any):
        _STATE.current = item.nodeid
        try:
            return (yield)
        finally:
            _STATE.current = None
            _STATE.found.pop(item.nodeid, None)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: Any):
        report = yield
        if call.when != "teardown":
            return report
        violations = _STATE.found.get(item.nodeid, [])
        failing = self._triage(item.nodeid, violations)
        if failing and _STATE.mode == "enforce" and report.outcome != "failed":
            report.outcome = "failed"
            report.longrepr = _describe(item.nodeid, failing)
        return report

    def _triage(self, nodeid: str, violations: list[Violation]) -> list[Violation]:
        failing: list[Violation] = []
        seen: set[Violation] = set()
        for violation in violations:
            if violation in seen:
                continue
            seen.add(violation)
            index = allowlisted(violation)
            if index is not None:
                _STATE.allowlist_hits.add(index)
            else:
                failing.append(violation)
            if _STATE.mode == "report":
                _write_report(nodeid, violation, index)
        return failing

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        if _STATE.mode == "off" or hasattr(terminalreporter.config, "workerinput"):
            return
        if _STATE.checked:  # in-process run; xdist workers keep their own count
            terminalreporter.write_line(
                f"tool-response guard: {_STATE.checked} responses checked"
            )
        if _STATE.mode == "report":
            terminalreporter.write_line(
                f"tool-response guard (report mode): violations -> "
                f"{os.environ.get(REPORT_ENV, '<unset>')}"
            )


def _describe(nodeid: str, violations: list[Violation]) -> str:
    lines = [
        f"[{_PLUGIN_NAME}] {nodeid} produced MCP tool responses that break the "
        "envelope contract (tree_sitter_analyzer/mcp/tools/tool_response.py):"
    ]
    lines += [f"  - {v.tool}: [{v.rule}] {v.message}" for v in violations]
    lines.append(
        "Fix the producer. If the fix is out of scope, add an entry with an issue "
        "reference to tests/tool_response_allowlist.py."
    )
    return "\n".join(lines)


def _write_report(nodeid: str, violation: Violation, index: int | None) -> None:
    target = os.environ.get(REPORT_ENV)
    if not target:
        return
    directory = Path(target)
    directory.mkdir(parents=True, exist_ok=True)
    line = {
        "nodeid": nodeid,
        "tool": violation.tool,
        "rule": violation.rule,
        "message": violation.message,
        "allowlisted": index is not None,
    }
    with (directory / f"violations-{os.getpid()}.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def install(config: pytest.Config) -> ToolResponseGuard | None:
    """Register the guard for this process (controller and xdist workers)."""
    mode = os.environ.get(MODE_ENV, "enforce").strip().lower() or "enforce"
    if mode not in {"enforce", "report", "off"}:
        raise pytest.UsageError(f"{MODE_ENV} must be enforce, report or off: {mode!r}")
    _STATE.mode = mode
    if mode == "off":
        return None
    existing = config.pluginmanager.get_plugin(_PLUGIN_NAME)
    if isinstance(existing, ToolResponseGuard):
        return existing
    _patch_tools()
    guard = ToolResponseGuard()
    config.pluginmanager.register(guard, _PLUGIN_NAME)
    return guard
