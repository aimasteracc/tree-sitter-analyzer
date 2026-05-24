"""Sanitization helpers for exception contexts and MCP parameters."""

from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "key",
        "secret",
        "auth",
        "credential",
        "api_key",
        "access_token",
        "private_key",
        "session_id",
    }
)


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Sanitize sensitive information from parameters."""
    result: dict[str, Any] = {}
    for key, value in params.items():
        result[key] = _sanitize_param_value(key, value)
    return result


def _sanitize_parameter_value(parameter_value: Any) -> Any:
    if isinstance(parameter_value, str) and len(parameter_value) > 200:
        return parameter_value[:200] + "...[TRUNCATED]"
    return parameter_value


def _sanitize_error_context(context: dict[str, Any]) -> dict[str, Any]:
    """Sanitize sensitive information from error context."""
    return {k: _sanitize_context_value(k, v) for k, v in context.items()}


def _sanitize_param_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return "***REDACTED***"
    if isinstance(value, str) and len(value) > 100:
        return value[:100] + "...[TRUNCATED]"
    return value


def _sanitize_context_value(key: str, value: Any) -> Any:
    """Sanitize a single key-value pair for logging."""
    if _is_sensitive_key(key):
        return "***REDACTED***"
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[TRUNCATED]"
    if isinstance(value, list | tuple) and len(value) > 10:
        return list(value[:10]) + ["...[TRUNCATED]"]
    if isinstance(value, dict) and len(value) > 20:
        truncated = _sanitize_error_context(dict(list(value.items())[:20]))
        return {**truncated, "__truncated__": True}
    return value


def _is_sensitive_key(key: str) -> bool:
    return any(s in key.lower() for s in _SENSITIVE_KEYS)
