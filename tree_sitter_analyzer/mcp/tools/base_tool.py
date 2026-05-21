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

    M10 (round-26): also mirror ``verdict`` in both directions whenever
    exactly one surface is populated. The central dispatcher does this
    too, but direct callers (tests, hive-mind workers, anything that
    bypasses server.py) still need the symmetric envelope so they can
    branch on ``verdict`` at either surface.

    Idempotent: tools that already set ``summary_line`` / ``verdict``
    keep their value.
    """
    agent_summary = result.get("agent_summary")
    if not isinstance(agent_summary, dict):
        return result
    sl = agent_summary.get("summary_line")
    if isinstance(sl, str) and sl and "summary_line" not in result:
        result["summary_line"] = sl

    # M10: bidirectional verdict mirror — see ``_mirror_verdict`` in
    # ``error_recovery.py`` for the canonical behaviour table. Kept in
    # sync here so direct callers see the same shape as MCP-routed
    # callers.
    top_value = result.get("verdict")
    agent_value = agent_summary.get("verdict")
    top_is_real = isinstance(top_value, str) and top_value and top_value != "n/a"
    agent_is_real = (
        isinstance(agent_value, str) and agent_value and agent_value != "n/a"
    )
    if top_is_real and not agent_is_real:
        agent_summary["verdict"] = top_value
    elif agent_is_real and not top_is_real:
        result["verdict"] = agent_value
    return result


def format_summary_line(*parts: Any) -> str:
    """Join non-empty segments with single spaces into a clean summary line.

    J5 (round-22 dogfood): four tools (universal_analyze_tool,
    analyze_scale_helpers ×2, analyze_code_structure_tool) shipped
    ``summary_line`` with a hard-coded ``"... lines  "`` (trailing double
    space). Pol1 only fixed ``code_patterns_tool``. This helper closes
    the door on the regression class entirely — future builders pass
    parts as positional args, get a guaranteed-clean single-space join,
    no matter how the parts are stitched. Empty/whitespace-only segments
    are dropped so optional pieces don't reintroduce double spaces.

    Examples:
        >>> format_summary_line("foo.py", "python", "42 lines",
        ...                      "classes=1", "methods=2")
        'foo.py python 42 lines classes=1 methods=2'
        >>> format_summary_line("foo.py", "", "42 lines", None)
        'foo.py 42 lines'
    """
    cleaned = [str(p).strip() for p in parts if p is not None and str(p).strip()]
    return " ".join(cleaned)


def detect_language_mismatch(
    file_path: str,
    explicit_language: str | None,
    *,
    project_root: str | None = None,
) -> str | None:
    """Return a warning message if explicit ``language`` disagrees with the file extension.

    O3 / O8 (round-30 dogfood): tools that accept an explicit ``language``
    parameter previously analysed e.g. ``foo.py`` as ``java`` whenever the
    caller passed ``language='java'`` — every downstream analyser returned
    zero classes/methods/fields and the tool happily emitted
    ``success=true`` with a clean ``SAFE`` verdict. Agents passing the
    wrong language tag had no signal that something went wrong.

    Returns ``None`` when there is no mismatch to flag:

    * ``explicit_language`` is ``None`` / empty (no override)
    * ``explicit_language`` matches the detected language (case-insensitive)
    * the file extension is unknown — we can't compare, so trust the caller

    Otherwise returns a warning string suitable for surfacing in an error
    envelope. Comparison is case-insensitive (``Python`` matches
    ``python``). Detector failures fall back to "no warning" because we
    can't be sure of the mismatch; the underlying analyser will still
    raise on truly unsupported input.
    """
    if not explicit_language or not isinstance(explicit_language, str):
        return None
    if not file_path or not isinstance(file_path, str):
        return None

    # Local import: avoid a top-level cycle (base_tool is imported by every
    # tool module, including ones loaded before ``language_detector``).
    try:
        from ...language_detector import detect_language_from_file
    except Exception:  # nosec B110 — detector import failure means no warning
        return None

    try:
        detected = detect_language_from_file(file_path, project_root=project_root)
    except Exception:  # nosec B110 — detector failure means no warning
        return None
    if not detected or detected.lower() == "unknown":
        return None
    if detected.lower() == explicit_language.lower():
        return None
    return (
        f"language={explicit_language!r} doesn't match detected language "
        f"{detected!r} from extension. Analysis may be wrong."
    )


def language_mismatch_error_response(
    *,
    tool_name: str,
    file_path: str,
    warning: str,
) -> dict[str, Any]:
    """Canonical strict error envelope for the language-mismatch gate.

    Shared so every tool that opts into the gate emits a byte-identical
    shape. Cross-tool agents branching on ``error_type=='validation'``
    can recover the same way regardless of which tool tripped the gate.

    Why strict (Option A): silent acceptance was the original bug class.
    Returning ``success=False`` forces the caller to make a deliberate
    choice — either omit ``language`` to auto-detect, or fix the
    mismatch. The envelope still carries ``agent_summary`` so the
    response shape stays uniform with other validation failures.
    """
    summary_line = f"{tool_name}: {warning}"
    next_step = (
        f"Use the correct --language for {file_path!r} or omit it to auto-detect."
    )
    return {
        "success": False,
        "error_type": "validation",
        "error": warning,
        "file_path": file_path,
        "summary_line": summary_line,
        "language_mismatch_warning": warning,
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": next_step,
        },
    }


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

    @property
    def project_root(self) -> str | None:
        """The current project root for this tool.

        J4: exposed as a property so direct attribute assignment
        (``tool.project_root = "..."``) takes the same code path as
        ``__init__`` / :meth:`set_project_path`. Setting this attribute
        rewires the security validator + path resolver and fires
        :meth:`_on_project_root_changed` so subclasses (e.g.
        AnalyzeScaleTool) refresh their analysis engine instead of
        pointing at a stale one whose validator rejects the resolved
        absolute paths.
        """
        return self._project_root

    @project_root.setter
    def project_root(self, value: str | None) -> None:
        """Setter that funnels through :meth:`_apply_project_root`.

        We always treat a re-assignment as a rebind: the security
        validator / path resolver are recreated and any
        ``_on_project_root_changed`` hook is invoked. The very first
        write (from ``_apply_project_root`` during ``__init__``) goes
        through directly via :meth:`_apply_project_root` itself to avoid
        recursion — see the ``_project_root_initialized`` guard.
        """
        if getattr(self, "_project_root_initialized", False):
            # Subsequent assignment after construction → treat as rebind.
            self._apply_project_root(value, _is_init=False)
        else:
            # First touch (raw attribute write from ``_apply_project_root``).
            self._project_root = value

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
        # Assigning to ``self.project_root`` after the init flag is set
        # would re-enter via the property setter and recurse — write the
        # underlying slot directly. The init flag is set after the first
        # write so the property setter knows when to dispatch back here.
        self._project_root = project_root
        if _is_init:
            self._project_root_initialized = True
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

    @staticmethod
    def _normalize_file_path(raw: str) -> str:
        """Strip leading ``./`` and normalize separators for consistent echo.

        K12 fix (round-24 dogfood): tools were echoing the raw ``file_path``
        argument back to the caller. Same logical path with and without a
        ``./`` prefix produced byte-different ``file_path`` strings, which
        confused downstream dedup/caching/display layers (e.g. the
        ``content_hash`` was identical but ``file_path`` was not).

        Normalization rules — minimal and reversible:
        - Convert backslash separators to forward slash (Windows compat).
        - Collapse one or more leading ``./`` segments.
        - Preserve ``../`` semantics (those carry real path info).
        - Leave absolute paths and bare filenames untouched after the
          backslash conversion above.

        Examples:
            >>> BaseMCPTool._normalize_file_path("tree_sitter_analyzer/x.py")
            'tree_sitter_analyzer/x.py'
            >>> BaseMCPTool._normalize_file_path("./tree_sitter_analyzer/x.py")
            'tree_sitter_analyzer/x.py'
            >>> BaseMCPTool._normalize_file_path("././tree_sitter_analyzer/x.py")
            'tree_sitter_analyzer/x.py'
            >>> BaseMCPTool._normalize_file_path("../sibling.py")
            '../sibling.py'
            >>> BaseMCPTool._normalize_file_path("a\\\\b.py")
            'a/b.py'
        """
        if not isinstance(raw, str) or not raw:
            return raw
        normalized = raw.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

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
