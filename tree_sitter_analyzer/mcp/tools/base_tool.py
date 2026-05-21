#!/usr/bin/env python3
"""
Base Tool Protocol for MCP Tools

This module defines the base class that all MCP tools should inherit from
to ensure consistent behavior and project path management.
"""

import functools
import inspect
from abc import ABC, abstractmethod
from typing import Any

from ...security import SecurityValidator
from ...utils import setup_logger
from ..utils.path_resolver import PathResolver
from ..utils.schema_strictness import enforce_strict_params
from ..utils.shared_cache import get_shared_cache

# Set up logging
logger = setup_logger(__name__)

# Sentinel attribute name marking a function that has already been wrapped
# by ``__init_subclass__`` so a deeper subclass doesn't double-wrap it.
_F5_WRAPPED_ATTR = "_f5_strict_params_wrapped"


def mirror_summary_line(result: dict[str, Any]) -> dict[str, Any]:
    """Mirror ``agent_summary.summary_line`` to the top-level envelope.

    Finding 6: round-16b dogfood showed seven tools shipping
    ``summary_line=None`` at the top level even though their nested
    ``agent_summary`` carried a useful one-liner. The MCP server dispatch
    layer mirrors it centrally (:func:`ensure_canonical_success_envelope`),
    but direct ``await tool.execute(args)`` callers (tests, CLI bridges)
    bypass that path — so each tool layered helper mirrors at the response
    builder too.

    Idempotent: tools that already set ``summary_line`` keep their value.
    """
    agent_summary = result.get("agent_summary")
    if not isinstance(agent_summary, dict):
        return result
    sl = agent_summary.get("summary_line")
    if isinstance(sl, str) and sl and "summary_line" not in result:
        result["summary_line"] = sl
    return result


class BaseMCPTool(ABC):
    """
    Base class for all MCP tools.

    Provides common functionality including project path management,
    security validation, and path resolution.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """F5: wrap every subclass's ``execute`` with strict-parameter check.

        We do this once per subclass — the wrapper inspects the tool's
        own ``inputSchema`` (via :meth:`get_tool_definition`) and rejects
        unknown top-level parameters with a did-you-mean hint. Direct
        ``await tool.execute(args)`` callers (tests, CLI bridges) and
        the MCP dispatcher both flow through this guard.

        Idempotent: if a subclass inherits ``execute`` from a parent that
        was already wrapped, we don't wrap again. If a subclass redefines
        ``execute``, the new definition is wrapped fresh.
        """
        super().__init_subclass__(**kwargs)
        cls_execute = cls.__dict__.get("execute")
        if cls_execute is None or not callable(cls_execute):
            return
        if getattr(cls_execute, _F5_WRAPPED_ATTR, False):
            return
        if not inspect.iscoroutinefunction(cls_execute):
            # Non-async execute means the subclass deviates from the
            # protocol. Leave it alone — the central dispatcher fallback
            # still catches MCP-routed calls.
            return

        @functools.wraps(cls_execute)
        async def _wrapped(
            self: BaseMCPTool, arguments: dict[str, Any]
        ) -> dict[str, Any]:
            self._guard_strict_parameters(arguments)
            return await cls_execute(self, arguments)  # type: ignore[no-any-return]

        setattr(_wrapped, _F5_WRAPPED_ATTR, True)
        cls.execute = _wrapped  # type: ignore[method-assign]

    def _guard_strict_parameters(self, arguments: dict[str, Any]) -> None:
        """Refuse unknown top-level parameters using the tool's own schema.

        Subclasses normally never call this directly — the
        ``__init_subclass__`` wrapper calls it before delegating to the
        subclass's ``execute``. Exposed as a method so tests and the
        legacy dispatcher can reuse the same code path.
        """
        try:
            definition = self.get_tool_definition()
        except Exception:  # noqa: BLE001 — definition errors are out of scope
            return
        if not isinstance(definition, dict):
            return
        schema = definition.get("inputSchema")
        tool_name = definition.get("name") or self.__class__.__name__
        enforce_strict_params(tool_name, schema, arguments)

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the base MCP tool.

        ARCH-A4: ``__init__`` now funnels through the same machinery as
        ``set_project_path`` so the two paths can't drift apart. Subclasses
        that need to reset lazy caches on a rebind should override
        :meth:`_on_project_root_changed` (the hook), NOT
        :meth:`set_project_path` itself. The hook is also called from
        ``__init__`` so constructor-built tools and re-bound tools see the
        same lifecycle.

        Args:
            project_root: Optional project root directory
        """
        # Wire core attributes via the same helper used by rebinds.
        self._apply_project_root(project_root, _is_init=True)

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Final-by-convention: subclasses must not override this method.
        Override :meth:`_on_project_root_changed` instead so the hook
        order (apply attributes → clear shared cache → notify subclass)
        is preserved.

        Args:
            project_path: New project root directory
        """
        self._apply_project_root(project_path, _is_init=False)

    def _apply_project_root(self, project_root: str | None, *, _is_init: bool) -> None:
        """Single internal entry point for both constructor and rebind paths."""
        self.project_root = project_root
        self.security_validator = SecurityValidator(project_root)
        self.path_resolver = PathResolver(project_root)
        # Invalidate shared caches on rebind only — at __init__ there is
        # nothing to invalidate, and clearing here would interfere with
        # other tools sharing the same cache during server bootstrap.
        if not _is_init:
            get_shared_cache().clear()
        # Notify subclasses so they can reset their own lazy state.
        try:
            self._on_project_root_changed(project_root)
        except Exception as exc:  # noqa: BLE001 — log + keep going
            logger.warning(
                f"{self.__class__.__name__}._on_project_root_changed raised: {exc}"
            )
        if _is_init:
            logger.debug(
                f"{self.__class__.__name__} initialized with project root: {project_root}"
            )
        else:
            logger.info(
                f"{self.__class__.__name__} project path updated to: {project_root}"
            )

    def _on_project_root_changed(self, project_root: str | None) -> None:
        """Hook for subclasses to reset lazy caches when project_root rebinds.

        Default is a no-op. Subclasses (e.g. RouteDetectorTool,
        CodeGraphCallTool, ASTCacheTool) override this to null out
        their cached helpers — they no longer need to override
        :meth:`set_project_path` itself. The hook fires from both
        ``__init__`` and ``set_project_path``, so a subclass that
        needs to lazy-init via the hook can rely on it running exactly
        once per binding.
        """
        del project_root  # unused at base level — subclass hook

    def resolve_and_validate_file_path(self, file_path: str) -> str:
        """
        Resolve a file path and validate it with caching to avoid redundant checks.

        This method is designed to be the single entry point used by tools that operate on
        `arguments["file_path"]`.
        """
        shared_cache = get_shared_cache()
        project_root = self.project_root

        # Validate the original input path first (pre-resolution) and cache it.
        # We intentionally validate only once per (project_root, file_path) to keep security
        # validation caching effective (tests expect 1 call when repeating within same root).
        cached_orig = shared_cache.get_security_validation(
            file_path, project_root=project_root
        )
        if cached_orig is None:
            cached_orig = self.security_validator.validate_file_path(
                file_path, base_path=project_root
            )
            shared_cache.set_security_validation(
                file_path, cached_orig, project_root=project_root
            )
        is_valid, error_msg = cached_orig
        if not is_valid:
            raise ValueError(
                f"Invalid file path: Security validation failed: {error_msg}"
            )

        # Resolve with shared cache (avoid repeating PathResolver.resolve across tools)
        resolved = shared_cache.get_resolved_path(file_path, project_root=project_root)
        if not resolved:
            try:
                resolved = self.path_resolver.resolve(file_path)
            except Exception as e:
                # Normalize resolver failures to ValueError for tool callers
                raise ValueError(f"Invalid file path: {e}") from e
            shared_cache.set_resolved_path(
                file_path, resolved, project_root=project_root
            )

        # Populate the resolved-path key for better cross-layer cache reuse without
        # performing a second validation call.
        if not shared_cache.get_security_validation(
            resolved, project_root=project_root
        ):
            shared_cache.set_security_validation(
                resolved, (True, ""), project_root=project_root
            )

        return resolved

    def resolve_and_validate_directory_path(self, dir_path: str) -> str:
        """
        Resolve a directory path and validate it.

        Args:
            dir_path: Path to the directory

        Returns:
            Resolved absolute path

        Raises:
            ValueError: If directory path is invalid or unsafe
        """
        # Resolve path
        resolved = self.path_resolver.resolve(dir_path)

        # Security validation for directory
        is_valid, error_msg = self.security_validator.validate_directory_path(
            resolved, must_exist=True
        )
        if not is_valid:
            raise ValueError(f"Invalid directory path: {error_msg}")

        return resolved

    @abstractmethod
    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition.

        Returns:
            Tool definition object compatible with MCP server
        """
        pass

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary containing execution results
        """
        pass

    @abstractmethod
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        pass


# Keep the protocol for backward compatibility
class MCPTool(BaseMCPTool):
    """
    Protocol for MCP tools (deprecated, use BaseMCPTool instead).

    All MCP tools must implement this protocol to ensure they have
    the required methods for integration with the MCP server.
    """

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition.

        Returns:
            Tool definition object compatible with MCP server
        """
        ...

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary containing execution results
        """
        raise NotImplementedError("Subclasses must implement execute method")

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        raise NotImplementedError("Subclasses must implement validate_arguments method")
