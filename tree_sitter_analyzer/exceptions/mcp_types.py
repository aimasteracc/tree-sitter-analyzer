"""MCP-specific exception types."""

from typing import Any

from .core import MCPError, ValidationError
from .sanitization import _sanitize_parameter_value, _sanitize_params


class MCPToolError(MCPError):
    """Raised when MCP tool execution fails."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        input_params: dict[str, Any] | None = None,
        execution_stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if input_params:
            context["input_params"] = _sanitize_params(input_params)
        if execution_stage:
            context["execution_stage"] = execution_stage

        super().__init__(message, tool_name=tool_name, context=context, **kwargs)
        self.tool_name = tool_name
        self.input_params = input_params
        self.execution_stage = execution_stage


class MCPResourceError(MCPError):
    """Raised when MCP resource access fails."""

    def __init__(
        self,
        message: str,
        resource_uri: str | None = None,
        resource_type: str | None = None,
        access_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if resource_type:
            context["resource_type"] = resource_type
        if access_mode:
            context["access_mode"] = access_mode

        super().__init__(message, resource_uri=resource_uri, context=context, **kwargs)
        self.resource_uri = resource_uri
        self.resource_type = resource_type
        self.access_mode = access_mode


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""

    def __init__(
        self,
        message: str,
        timeout_seconds: float | None = None,
        operation_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if timeout_seconds:
            context["timeout_seconds"] = timeout_seconds
        if operation_type:
            context["operation_type"] = operation_type

        super().__init__(message, context=context, **kwargs)
        self.timeout_seconds = timeout_seconds
        self.operation_type = operation_type


class MCPValidationError(ValidationError):
    """Raised when MCP input validation fails."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        parameter_name: str | None = None,
        parameter_value: Any | None = None,
        validation_rule: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if tool_name:
            context["tool_name"] = tool_name
        if parameter_name:
            context["parameter_name"] = parameter_name
        if validation_rule:
            context["validation_rule"] = validation_rule
        if parameter_value is not None:
            context["parameter_value"] = _sanitize_parameter_value(parameter_value)

        super().__init__(
            message, validation_type="mcp_parameter", context=context, **kwargs
        )
        self.tool_name = tool_name
        self.parameter_name = parameter_name
        self.validation_rule = validation_rule
