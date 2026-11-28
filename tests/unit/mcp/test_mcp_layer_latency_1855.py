"""#1855: per-call MCP-layer work, done once (argument schema check, loader key, nav facade).

* ``tools/call`` argument validation: the server runs the SDK's own steps with
  the schema checked once per schema object; every answer (valid, invalid,
  broken schema, unlisted tool) is the one the SDK's ``jsonschema.validate``
  path gives.
* the resident loader's root key is computed once per root string.
* the ``nav`` facade is built on the event loop once the resident load ends.
"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import jsonschema
import pytest

pytest.importorskip("mcp")
from mcp import types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402

from tree_sitter_analyzer.mcp import server as server_module  # noqa: E402
from tree_sitter_analyzer.mcp._sdk_compat import MCP2ServerAdapter  # noqa: E402
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer  # noqa: E402
from tree_sitter_analyzer.mcp.server_utils import tool_registration  # noqa: E402
from tree_sitter_analyzer.mcp.server_utils.tool_registration import (  # noqa: E402  # noqa: E402
    _SET_PROJECT_PATH_TOOL,
    InputValidationError,
    ToolInputValidator,
    call_tool_registration,
)
from tree_sitter_analyzer.resident import loader  # noqa: E402

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["callers", "callees", "context"]},
        "function_name": {"type": "string", "minLength": 1},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
        "include_bodies": {"type": "boolean"},
        "paths": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "mode": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
    },
    "required": ["action"],
    "additionalProperties": False,
}

_ARGUMENTS: list[dict[str, Any]] = [
    {"action": "callers", "function_name": "f", "limit": 10},
    {"action": "callers", "include_bodies": False, "paths": ["a"], "mode": 3},
    {},
    {"action": "nope"},
    {"action": 1},
    {"action": "callers", "limit": 0},
    {"action": "callers", "limit": "10"},
    {"action": "callers", "function_name": ""},
    {"action": "callers", "unknown": True},
    {"action": "callers", "paths": ["a", "b", "c"]},
    {"action": "callers", "paths": [1]},
    {"action": "callers", "mode": 1.5},
    {"action": "callers", "mode": None, "limit": -1, "x": 1},
]


class _Tool:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.inputSchema = schema


def _sdk_message(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    """The SDK's own answer: ``None`` (valid) or its error result text."""
    try:
        jsonschema.validate(instance=arguments, schema=schema)
    except jsonschema.ValidationError as e:
        return f"Input validation error: {e.message}"
    return None


def _ours(
    validator: ToolInputValidator, name: str, arguments: dict[str, Any]
) -> str | None:
    try:
        validator.validate(name, arguments)
    except InputValidationError as e:
        return str(e)
    return None


@pytest.mark.parametrize("schema", [_SCHEMA, _SET_PROJECT_PATH_TOOL["inputSchema"]])
def test_validation_answers_like_the_sdk(schema: dict[str, Any]) -> None:
    validator = ToolInputValidator(lambda: {"t": _Tool(schema)})
    extra = [
        {"project_path": "/x"},
        {"project_path": 3},
        {"project_path": "/x", "y": 1},
    ]
    for arguments in [*_ARGUMENTS, *extra]:
        for _ in range(2):  # first (checks the schema) and cached
            assert _ours(validator, "t", arguments) == _sdk_message(arguments, schema)


def test_the_nav_facade_schema_answers_like_the_sdk(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp._tool_registry import build_facade

    schema = build_facade("nav", str(tmp_path), None).get_tool_definition()[
        "inputSchema"
    ]
    validator = ToolInputValidator(lambda: {"nav": _Tool(schema)})
    cases = [
        {"action": "callers", "function_name": "f", "file_path": "a.py"},
        {
            "action": "callers",
            "function_name": "f",
            "include_bodies": False,
            "limit": 5000,
        },
        {},
        {"action": "no_such_action"},
        {"action": "callers", "limit": "many"},
        {"action": 7, "function_name": ["f"]},
    ]
    for arguments in cases:
        assert _ours(validator, "nav", arguments) == _sdk_message(arguments, schema)


def test_the_schema_is_checked_once_per_schema_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks: list[int] = []
    cls = jsonschema.validators.validator_for(_SCHEMA)
    original = cls.check_schema

    def counting(schema: Any, *a: Any, **k: Any) -> None:
        checks.append(id(schema))
        original(schema, *a, **k)

    monkeypatch.setattr(cls, "check_schema", staticmethod(counting))
    tool = _Tool(copy.deepcopy(_SCHEMA))
    cache = {"t": tool}
    validator = ToolInputValidator(lambda: cache)
    for arguments in _ARGUMENTS:
        _ours(validator, "t", arguments)
    assert len(checks) == 1
    # A new tool definition (tools/list again) is a new schema object: checked again.
    cache["t"] = _Tool(copy.deepcopy(_SCHEMA))
    _ours(validator, "t", _ARGUMENTS[0])
    assert len(checks) == 2


def test_a_broken_schema_raises_the_sdk_error_every_time() -> None:
    schema = {"type": "object", "properties": {"a": {"type": 12}}}
    validator = ToolInputValidator(lambda: {"t": _Tool(schema)})
    with pytest.raises(jsonschema.SchemaError) as sdk:
        jsonschema.validate(instance={}, schema=schema)
    for _ in range(2):  # a failed check is never kept
        with pytest.raises(jsonschema.SchemaError) as ours:
            validator.validate("t", {})
        assert str(ours.value) == str(sdk.value)
    validator.prepare("t")  # best effort: never raises


def test_an_unlisted_tool_is_not_validated() -> None:
    validator = ToolInputValidator(lambda: {})
    validator.validate("missing", {"anything": object()})
    validator.prepare("missing")


def test_validator_bound_clears_instead_of_growing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_registration, "MAX_VALIDATORS", 2)
    cache: dict[str, Any] = {}
    validator = ToolInputValidator(lambda: cache)
    for index in range(5):
        cache[f"t{index}"] = _Tool(copy.deepcopy(_SCHEMA))
        validator.validate(f"t{index}", _ARGUMENTS[0])
        assert len(validator._validators) <= 2


def test_registration_falls_back_to_sdk_validation_when_unsupported() -> None:
    class NoKeyword:
        _tool_cache: dict[str, Any] = {}

        def call_tool(self) -> str:
            return "sdk-validates"

    class NoCache:
        def call_tool(self, **_kwargs: Any) -> str:
            return "sdk-validates"

    for server in (NoKeyword(), NoCache(), MCP2ServerAdapter(object())):
        if isinstance(server, MCP2ServerAdapter):
            # The 2.x adapter has no tool cache: its call_tool() is used as is.
            assert call_tool_registration(server)[1] is None
            continue
        decorator, validator = call_tool_registration(server)
        assert decorator == "sdk-validates"
        assert validator is None


def _call_request(name: str, arguments: dict[str, Any]) -> types.CallToolRequest:
    return types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )


async def _sdk_reference_result(
    tool: types.Tool, arguments: dict[str, Any]
) -> types.ServerResult:
    """The same request through a stock SDK server that validates itself."""
    reference = Server("reference")

    @reference.list_tools()  # type: ignore[untyped-decorator]
    async def _list() -> list[types.Tool]:
        return [tool]

    @reference.call_tool()  # type: ignore[untyped-decorator]
    async def _call(_name: str, _arguments: dict[str, Any]) -> list[Any]:
        raise AssertionError("invalid arguments must not reach the tool")

    return await reference.request_handlers[types.CallToolRequest](
        _call_request(tool.name, arguments)
    )


@pytest.mark.asyncio
async def test_real_server_rejects_invalid_arguments_with_the_sdk_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TreeSitterAnalyzerMCPServer, "tool_definitions", lambda _s: [])
    instance = TreeSitterAnalyzerMCPServer(str(tmp_path))
    server = instance.create_server()
    assert instance.input_validator is not None  # this SDK: the server validates
    tool = types.Tool(**_SET_PROJECT_PATH_TOOL)
    for arguments in ({}, {"project_path": 3}, {"project_path": "/x", "extra": 1}):
        ours = await server.request_handlers[types.CallToolRequest](
            _call_request("set_project_path", arguments)
        )
        expected = await _sdk_reference_result(tool, arguments)
        assert ours.model_dump() == expected.model_dump()
        assert ours.root.isError is True


@pytest.mark.asyncio
async def test_real_server_answers_valid_arguments_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TreeSitterAnalyzerMCPServer, "tool_definitions", lambda _s: [])
    instance = TreeSitterAnalyzerMCPServer(str(tmp_path))
    server = instance.create_server()
    result = await server.request_handlers[types.CallToolRequest](
        _call_request("set_project_path", {"project_path": str(tmp_path / "missing")})
    )
    # Valid per schema: the tool ran and answered with its own error envelope.
    assert result.root.isError is False
    assert "does not exist" in result.root.content[0].text


def test_loader_key_is_computed_once_per_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader.reset()
    calls: list[str] = []
    real = loader.os.path.realpath

    def counting(path: str) -> str:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(loader.os.path, "realpath", counting)
    root = str(tmp_path)
    first = loader._key(root)
    assert loader._key(root) == first
    assert calls == [root]
    loader.reset()  # forgets the keys with the rest of the state
    assert loader._key(root) == first
    assert calls == [root, root]
    loader.reset()


@pytest.mark.asyncio
async def test_nav_facade_is_built_after_the_load_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = TreeSitterAnalyzerMCPServer(str(tmp_path))
    built: list[str] = []
    finished = {"load": False}
    monkeypatch.setattr(loader, "wait", lambda _root, _timeout: finished["load"])
    monkeypatch.setattr(server_module, "_FACADE_WARM_POLL_SECONDS", 0.01)
    monkeypatch.setattr(instance, "facade", lambda name: built.append(name))

    instance._schedule_facade_warm(str(tmp_path))
    await asyncio.sleep(0.05)
    assert built == []  # the load is still running: nothing is built
    finished["load"] = True
    assert instance._facade_warm_task is not None
    await asyncio.wait_for(instance._facade_warm_task, 5)
    assert built == ["nav"]


@pytest.mark.asyncio
async def test_facade_warm_skips_a_changed_root_and_survives_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loader, "wait", lambda _root, _timeout: True)
    instance = TreeSitterAnalyzerMCPServer(str(tmp_path))
    built: list[str] = []
    monkeypatch.setattr(instance, "facade", lambda name: built.append(name))
    await instance._warm_facade_after_load(str(tmp_path / "other"))
    assert built == []

    def broken(_name: str) -> None:
        raise RuntimeError("cannot build")

    monkeypatch.setattr(instance, "facade", broken)
    await instance._warm_facade_after_load(str(tmp_path))  # logged, never raised


def test_facade_warm_needs_an_event_loop(tmp_path: Path) -> None:
    instance = TreeSitterAnalyzerMCPServer(str(tmp_path))
    instance._schedule_facade_warm(str(tmp_path))  # no running loop: nothing
    assert instance._facade_warm_task is None


def test_only_a_new_loader_thread_schedules_the_warm_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[str | None] = []
    instance = TreeSitterAnalyzerMCPServer(str(tmp_path))
    monkeypatch.setattr(instance, "_schedule_facade_warm", scheduled.append)
    monkeypatch.setattr(loader, "start", lambda _root: False)
    instance.start_resident()
    assert scheduled == []
    monkeypatch.setattr(loader, "start", lambda _root: True)
    instance.start_resident()
    assert scheduled == [str(tmp_path)]
