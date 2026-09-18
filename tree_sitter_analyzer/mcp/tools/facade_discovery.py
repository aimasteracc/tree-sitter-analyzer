"""为 facade 提供按需动作 schema 与 Agent 核心工作流发现。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_CORE_PROFILE: dict[str, Any] = {
    "version": "agent-core/v1",
    "steps": [
        {"position": 1, "facade": "search", "action": "symbol"},
        {"position": 2, "facade": "structure", "action": "outline"},
        {"position": 3, "facade": "nav", "action": "pulse"},
        {"position": 4, "facade": "edit", "action": "impact"},
        {"position": 5, "facade": "edit", "action": "verify"},
    ],
}

_JSON_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "string",
    "enum": ["json"],
    "default": "json",
    "description": "Output format: JSON.",
}


def _inner_input_schema(inner: Any) -> dict[str, Any] | None:
    """读取 inner 的权威输入 schema；形状异常时诚实返回不可用。"""
    try:
        definition = inner.get_tool_definition()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(definition, dict):
        return None
    schema = definition.get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return None
    if not isinstance(schema.get("properties"), dict):
        return None
    return deepcopy(schema)


def _alias_target(name: str, properties: dict[str, Any]) -> str | None:
    """返回 facade 投影实际支持的必填参数别名。"""
    if name == "symbol" and "symbol" in properties:
        return "function_name"
    if name in {"function_name", "class_name"} and name in properties:
        return "symbol"
    return None


def _add_alias_property(properties: dict[str, Any], *, target: str, alias: str) -> None:
    """把 facade 接受的别名补入可执行 schema，保持运行时与声明一致。"""
    if target not in properties or alias in properties:
        return
    alias_schema = deepcopy(properties[target])
    description = alias_schema.get("description")
    suffix = f"Facade alias for {target}."
    alias_schema["description"] = (
        f"{description} {suffix}" if isinstance(description, str) else suffix
    )
    properties[alias] = alias_schema


def build_action_schema(action: str, inner: Any) -> dict[str, Any] | None:
    """把 inner schema 转换为可直接调用 facade 的精确 schema。"""
    schema = _inner_input_schema(inner)
    if schema is None:
        return None

    properties = schema["properties"]
    properties["action"] = {
        "type": "string",
        "const": action,
        "description": "Facade action selector.",
    }
    properties["output_format"] = deepcopy(_JSON_OUTPUT_SCHEMA)
    _add_alias_property(properties, target="symbol", alias="function_name")
    _add_alias_property(properties, target="function_name", alias="symbol")
    _add_alias_property(properties, target="class_name", alias="symbol")

    original_required = schema.get("required")
    required = list(original_required) if isinstance(original_required, list) else []
    alias_constraints: list[dict[str, Any]] = []
    seen_alias_sets: set[tuple[str, str]] = set()
    for name in list(required):
        alias = _alias_target(name, properties)
        if alias is None:
            continue
        required.remove(name)
        alias_set = tuple(sorted((name, alias)))
        if alias_set in seen_alias_sets:
            continue
        seen_alias_sets.add(alias_set)
        alias_constraints.append(
            {"anyOf": [{"required": [name]}, {"required": [alias]}]}
        )

    schema["required"] = ["action", *required]
    if alias_constraints:
        existing_all_of = schema.get("allOf")
        all_of = list(existing_all_of) if isinstance(existing_all_of, list) else []
        schema["allOf"] = [*all_of, *alias_constraints]
    schema["additionalProperties"] = False
    return schema


def _error_response(
    facade_name: str,
    target_action: Any,
    *,
    code: str,
    message: str,
    available_actions: list[str],
) -> dict[str, Any]:
    """构造稳定、可恢复的发现错误 envelope。"""
    next_step = (
        "Set target_action to one of: " + ", ".join(available_actions) + "."
        if available_actions
        else "No business actions are registered on this facade."
    )
    summary_line = f"{facade_name}.help: {message}"
    return {
        "success": False,
        "verdict": "ERROR",
        "error_type": "validation",
        "error_code": code,
        "error": message,
        "facade": facade_name,
        "action": "help",
        "target_action": target_action,
        "available_actions": available_actions,
        "summary_line": summary_line,
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": next_step,
        },
    }


def build_help_response(
    *,
    facade_name: str,
    available_actions: list[str],
    full_description: str,
    action_map: dict[str, Any],
    bespoke_actions: set[str],
    arguments: dict[str, Any],
    target_action: Any = None,
) -> dict[str, Any]:
    """返回帮助摘要，或指定 direct action 的机器可读调用 schema。"""
    allowed_help_arguments = ["action", "output_format", "target_action"]
    invalid_arguments = sorted(set(arguments) - set(allowed_help_arguments))
    if invalid_arguments:
        response = _error_response(
            facade_name,
            target_action,
            code="INVALID_ARGUMENT",
            message="unsupported help arguments: " + ", ".join(invalid_arguments),
            available_actions=available_actions,
        )
        response["invalid_arguments"] = invalid_arguments
        response["allowed_arguments"] = allowed_help_arguments
        return response
    if arguments.get("output_format", "json") != "json":
        response = _error_response(
            facade_name,
            target_action,
            code="INVALID_ARGUMENT",
            message=f"invalid output_format: {arguments.get('output_format')!r}",
            available_actions=available_actions,
        )
        response["invalid_arguments"] = ["output_format"]
        response["invalid_values"] = {"output_format": arguments.get("output_format")}
        response["allowed_values"] = {"output_format": ["json"]}
        return response
    if target_action is not None and not isinstance(target_action, str):
        return _error_response(
            facade_name,
            target_action,
            code="INVALID_ARGUMENT",
            message="target_action must be a string",
            available_actions=available_actions,
        )
    if isinstance(target_action, str) and target_action not in available_actions:
        return _error_response(
            facade_name,
            target_action,
            code="UNKNOWN_ACTION",
            message=f"unknown target_action {target_action!r}",
            available_actions=available_actions,
        )
    if isinstance(target_action, str) and target_action in bespoke_actions:
        response = _error_response(
            facade_name,
            target_action,
            code="ACTION_SCHEMA_UNAVAILABLE",
            message=(
                f"action {target_action!r} uses a bespoke route without a "
                "machine-readable schema"
            ),
            available_actions=available_actions,
        )
        response["schema_status"] = "unavailable"
        return response

    action_schema = None
    if isinstance(target_action, str):
        action_schema = build_action_schema(target_action, action_map[target_action])
        if action_schema is None:
            response = _error_response(
                facade_name,
                target_action,
                code="ACTION_SCHEMA_UNAVAILABLE",
                message=f"action {target_action!r} has no valid object input schema",
                available_actions=available_actions,
            )
            response["schema_status"] = "unavailable"
            return response

    schema_status = "available" if action_schema is not None else "not_requested"
    summary_line = (
        f"{facade_name}.{target_action}: action schema available"
        if isinstance(target_action, str)
        else f"{facade_name}: {len(available_actions)} actions available"
    )
    next_step = (
        f"Call {facade_name} with arguments matching action_schema."
        if isinstance(target_action, str)
        else "Set target_action to one of actions to fetch its exact input schema."
    )
    success_response: dict[str, Any] = {
        "success": True,
        "verdict": "INFO",
        "facade": facade_name,
        "action": "help",
        "target_action": target_action,
        "actions": available_actions,
        "schema_status": schema_status,
        "schema_request": {"action": "help", "target_action": "<action>"},
        "core_profile": deepcopy(_CORE_PROFILE),
        "summary_line": summary_line,
        "agent_summary": {
            "verdict": "INFO",
            "summary_line": summary_line,
            "next_step": next_step,
        },
        "hint": next_step,
    }
    if target_action is None:
        success_response["description"] = full_description
    if action_schema is not None:
        success_response["action_schema"] = action_schema
    return success_response
