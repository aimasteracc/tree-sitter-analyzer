#!/usr/bin/env python3
"""生成 v3.1.2 门面（facade）固定数据——全部为真实运行输出，禁止手写期望值。

产出两个 JSON（相对本脚本位于 ``../facade/``）：

1. ``facade_registry.json`` —— 门面注册表快照：
   - ``facade_map`` 的常量（FACADE_NAMES / SET_PROJECT_PATH_TOOL_NAME /
     REMOVED_TOOL_NAMES / LEGACY_TOOL_MAP / NEW_ACTION_PARITY / MCP_ONLY_ACTIONS）；
   - ``create_tool_registry(project_root='.')`` 产出的每个门面的
     name / takes_lifecycle_manager / action_map 键 / bespoke_map 键 /
     get_tool_definition() 摘要；
   - ``server_utils.tool_registration`` 中的 set_project_path 工具定义。
2. ``facade_dispatch.json`` —— 用 ``anyio.run`` 驱动
   ``create_tool_registry(project_root='/workspace/tree-sitter-analyzer')``
   产出的真实门面：structure 门面的错误路径与成功路径、
   ``legacy_shim.dispatch_legacy`` 的 β 旧名转发（含 scope=graph 注入与
   deprecation 信封），以及 ``legacy_to_facade`` 的两个对照路由。

归一化（唯一允许的改动，保证固定数据跨运行可复现）：
- 逐次运行必变的计时/世代字段：``analysis_time`` / ``analysis_time_ms`` /
  ``duration_ms`` / ``elapsed_ms`` / ``cache_age_s``，以及
  ``provenance.generation`` / ``provenance.producer_version`` → ``"<normalized>"``；
- 字符串中的绝对路径前缀 ``/workspace/tree-sitter-analyzer/`` 剥掉。

用法（在仓库根目录）::

    /tmp/tsa-v312-venv/bin/python rust/fixtures/tools/gen_facade.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import anyio

from tree_sitter_analyzer import __version__ as TSA_VERSION
from tree_sitter_analyzer.mcp import _tool_registry, facade_map, legacy_shim
from tree_sitter_analyzer.mcp.server_utils import tool_registration

# 仓库根（分发用门面以它为 project_root；也是路径剥离前缀）。
REPO_ROOT = "/workspace/tree-sitter-analyzer"
# 分发用例的目标文件（仓库相对路径）。
CORPUS = "tests/golden/corpus_python.py"
# 固定数据输出目录：本脚本位于 rust/fixtures/tools/，输出到 rust/fixtures/facade/。
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "facade"
# 本脚本在仓库内的规范路径（写入 JSON 作为溯源信息）。
SCRIPT_PATH = "rust/fixtures/tools/gen_facade.py"

# 归一化占位符与逐次运行必变的字段集合（见模块 docstring）。
_PLACEHOLDER = "<normalized>"
_VOLATILE_TOP_KEYS = frozenset(
    {"analysis_time", "analysis_time_ms", "duration_ms", "elapsed_ms", "cache_age_s"}
)
_VOLATILE_PROVENANCE_KEYS = frozenset({"generation", "producer_version"})


def _normalize(value: Any) -> Any:
    """递归归一化固定数据：抹平计时/世代字段，剥掉仓库绝对路径前缀。"""
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _VOLATILE_TOP_KEYS:
                normalized[key] = _PLACEHOLDER
            elif key == "provenance" and isinstance(item, dict):
                normalized[key] = {
                    sub_key: (
                        _PLACEHOLDER
                        if sub_key in _VOLATILE_PROVENANCE_KEYS
                        else _normalize(sub_value)
                    )
                    for sub_key, sub_value in item.items()
                }
            else:
                normalized[key] = _normalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return value.replace(REPO_ROOT + "/", "")
    return value


def _write_json(path: Path, document: dict[str, Any]) -> None:
    """写出确定性 JSON：排序键、UTF-8、两空格缩进、结尾换行。"""
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path} ({path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# 1. facade_registry.json —— 注册表快照
# ---------------------------------------------------------------------------


def build_registry_document() -> dict[str, Any]:
    """真实构建一次注册表（project_root='.'）并拍下静态快照。"""
    # _FACADE_REGISTRATIONS 是 takes_lifecycle_manager 的权威来源。
    takes_lifecycle_manager = dict(_tool_registry._FACADE_REGISTRATIONS)
    tool_instances, _lookup = _tool_registry.create_tool_registry(project_root=".")

    facades: list[dict[str, Any]] = []
    for name, facade in tool_instances:
        definition = facade.get_tool_definition()
        schema = definition.get("inputSchema", {})
        facades.append(
            {
                "name": name,
                "takes_lifecycle_manager": takes_lifecycle_manager[name],
                "actions": sorted(facade.action_map),
                "bespoke_actions": sorted(facade.bespoke_map),
                "tool_definition": {
                    "name": definition.get("name"),
                    "annotations": copy.deepcopy(definition.get("annotations")),
                    "required": copy.deepcopy(schema.get("required")),
                    "action_enum": copy.deepcopy(
                        schema.get("properties", {}).get("action", {}).get("enum")
                    ),
                    "additionalProperties": schema.get("additionalProperties"),
                },
            }
        )

    return {
        "generator": SCRIPT_PATH,
        "package_version": TSA_VERSION,
        "facade_map": {
            "SET_PROJECT_PATH_TOOL_NAME": facade_map.SET_PROJECT_PATH_TOOL_NAME,
            "FACADE_NAMES": list(facade_map.FACADE_NAMES),
            "REMOVED_TOOL_NAMES": sorted(facade_map.REMOVED_TOOL_NAMES),
            "LEGACY_TOOL_MAP": {
                legacy_name: [facade, action]
                for legacy_name, (facade, action) in sorted(
                    facade_map.LEGACY_TOOL_MAP.items()
                )
            },
            "NEW_ACTION_PARITY": {
                capability: [facade, action, cli_flag]
                for capability, (
                    facade,
                    action,
                    cli_flag,
                ) in sorted(facade_map.NEW_ACTION_PARITY.items())
            },
            "MCP_ONLY_ACTIONS": {
                capability: [facade, action]
                for capability, (facade, action) in sorted(
                    facade_map.MCP_ONLY_ACTIONS.items()
                )
            },
        },
        "facades": facades,
        # set_project_path：独立基础设施项，不在 8 门面之内的第 9 个工具。
        "set_project_path_tool_definition": copy.deepcopy(
            tool_registration._SET_PROJECT_PATH_TOOL
        ),
    }


# ---------------------------------------------------------------------------
# 2. facade_dispatch.json —— 真实分发输出
# ---------------------------------------------------------------------------


class _RegistryServer:
    """``dispatch_legacy`` 只依赖 ``server.tools.get(facade_name)`` 的最小服务端。"""

    def __init__(self, tools: dict[str, Any]) -> None:
        self.tools = tools


class _SpyFacade:
    """记录转发参数并委托真实门面执行，用于验证旧名 shim 的参数注入。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.forwarded: list[dict[str, Any]] = []

    async def execute(self, arguments: dict[str, Any]) -> Any:
        self.forwarded.append(dict(arguments))
        return await self._inner.execute(arguments)


async def _run_facade_case(facade: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """执行一次真实门面调用；抛出的异常如实记录类型与消息。"""
    try:
        result = await facade.execute(arguments)
    except Exception as exc:  # noqa: BLE001 —— 固定数据需保留真实异常形态
        return {"exception_type": type(exc).__name__, "exception_message": str(exc)}
    return {"result": _normalize(result)}


async def build_dispatch_document() -> dict[str, Any]:
    """在 anyio 事件循环内执行全部真实分发用例。"""
    tool_instances, lookup = _tool_registry.create_tool_registry(project_root=REPO_ROOT)
    structure = lookup["structure"]

    cases: list[dict[str, Any]] = []

    def record(case: str, arguments: dict[str, Any], outcome: dict[str, Any]) -> None:
        cases.append({"case": case, "input": arguments, **outcome})

    # —— structure 门面：错误路径（错误信封均为真实返回值） ——
    record(
        "structure_missing_action",
        {},
        await _run_facade_case(structure, {}),
    )
    record(
        "structure_unknown_action_with_suggestion",
        {"action": "outlin"},
        await _run_facade_case(structure, {"action": "outlin"}),
    )
    record(
        "structure_unknown_action_without_suggestion",
        {"action": "zzzzzz"},
        await _run_facade_case(structure, {"action": "zzzzzz"}),
    )
    record(
        "structure_help_no_target",
        {"action": "help"},
        await _run_facade_case(structure, {"action": "help"}),
    )
    record(
        "structure_help_target_outline",
        {"action": "help", "target_action": "outline"},
        await _run_facade_case(structure, {"action": "help", "target_action": "outline"}),
    )
    record(
        "structure_invalid_output_format",
        {"action": "outline", "output_format": "yaml"},
        await _run_facade_case(
            structure, {"action": "outline", "output_format": "yaml"}
        ),
    )
    record(
        "structure_invalid_argument",
        {"action": "outline", "bogus_param": 123},
        await _run_facade_case(structure, {"action": "outline", "bogus_param": 123}),
    )
    record(
        "structure_read_fractional_line_bound",
        {"action": "read", "file_path": CORPUS, "start_line": 1.5},
        await _run_facade_case(
            structure, {"action": "read", "file_path": CORPUS, "start_line": 1.5}
        ),
    )

    # —— structure 门面：成功路径（结果经归一化） ——
    record(
        "structure_analyze",
        {"action": "analyze", "file_path": CORPUS},
        await _run_facade_case(structure, {"action": "analyze", "file_path": CORPUS}),
    )
    record(
        "structure_outline",
        {"action": "outline", "file_path": CORPUS},
        await _run_facade_case(structure, {"action": "outline", "file_path": CORPUS}),
    )
    record(
        "structure_read_lines_1_to_15",
        {"action": "read", "file_path": CORPUS, "start_line": 1, "end_line": 15},
        await _run_facade_case(
            structure,
            {"action": "read", "file_path": CORPUS, "start_line": 1, "end_line": 15},
        ),
    )

    # —— β 旧名 shim：dispatch_legacy 转发到真实门面 ——
    # nav 用 spy 包一层，拍下 shim 注入 action/scope 后的实际转发参数。
    nav_spy = _SpyFacade(lookup["nav"])
    server = _RegistryServer({**lookup, "nav": nav_spy})

    get_code_outline_args = {"file_path": CORPUS}
    get_code_outline_result = await legacy_shim.dispatch_legacy(
        server, "get_code_outline", get_code_outline_args
    )
    record(
        "legacy_get_code_outline",
        get_code_outline_args,
        {"result": _normalize(get_code_outline_result)},
    )

    call_graph_args = {"file_path": CORPUS, "function_name": "regular_function"}
    call_graph_result = await legacy_shim.dispatch_legacy(
        server, "codegraph_call_graph", call_graph_args
    )
    record(
        "legacy_codegraph_call_graph",
        call_graph_args,
        {
            # shim 应注入 action='callers' 与 scope='graph'（R4）。
            "forwarded_to_nav": _normalize(nav_spy.forwarded[0]),
            "result": _normalize(call_graph_result),
            # 双通道可见性之二：响应内的 deprecation 信封。
            "deprecation": _normalize(
                call_graph_result.get("deprecation")
                if isinstance(call_graph_result, dict)
                else None
            ),
        },
    )

    # —— F3 对照：query_code（.scm DSL）与 codegraph_symbol_search（BM25）路由不同 ——
    record(
        "legacy_to_facade_query_code",
        {"legacy_name": "query_code"},
        {"result": list(facade_map.legacy_to_facade("query_code"))},
    )
    record(
        "legacy_to_facade_codegraph_symbol_search",
        {"legacy_name": "codegraph_symbol_search"},
        {"result": list(facade_map.legacy_to_facade("codegraph_symbol_search"))},
    )

    return {
        "generator": SCRIPT_PATH,
        "package_version": TSA_VERSION,
        "project_root": REPO_ROOT,
        "corpus": CORPUS,
        "runner": "anyio.run",
        "registry_order": [name for name, _facade in tool_instances],
        "cases": cases,
    }


def main() -> None:
    """生成两个固定数据文件并校验它们能被 json 解析。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    registry_document = build_registry_document()
    dispatch_document = anyio.run(build_dispatch_document)

    registry_path = FIXTURE_DIR / "facade_registry.json"
    dispatch_path = FIXTURE_DIR / "facade_dispatch.json"
    _write_json(registry_path, registry_document)
    _write_json(dispatch_path, dispatch_document)

    # 自校验：刚写出的文件必须能被标准 json 干净解析。
    for path in (registry_path, dispatch_path):
        with path.open("r", encoding="utf-8") as handle:
            json.load(handle)
        print(f"verified {path} parses cleanly")


if __name__ == "__main__":
    main()
