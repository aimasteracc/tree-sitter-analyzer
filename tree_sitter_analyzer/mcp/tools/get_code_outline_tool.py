#!/usr/bin/env python3
"""
get_code_outline MCP Tool

返回文件或模块的层次化结构大纲（package → class → method），
不包含代码正文内容，供 AI 在取回完整内容之前先导航结构。

这是 outline-first 检索模式的核心工具：
AI 先看大纲，再决定要取哪个具体方法/类，从而大幅降低 token 消耗。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...core.analysis_engine import (
    AnalysisRequest,
    get_analysis_engine,
)
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils import get_performance_monitor
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    language_mismatch_error_response,
)

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Byte-budget constants (Issue #513 leg 3 — honest-truncation pattern)
#
# The MCP path applies a default cap on listed classes / top-level functions
# so giant declaration files (e.g. vscode.d.ts, 21k lines) don't blow agent
# context windows.  CLI output is UNAFFECTED — CLI defaults to JSON (full
# output) and the user can pipe to jq.
#
# Statistics (class_count / method_count) are ALWAYS computed over ALL
# elements BEFORE truncation — the cap only slices the listed arrays.
# ---------------------------------------------------------------------------
DEFAULT_OUTLINE_CLASSES_CAP: int = 50
DEFAULT_OUTLINE_FUNCTIONS_CAP: int = 50


def _outline_diagnostics_next_step(diagnostics: dict[str, Any]) -> str:
    """Return the next action for parse/encoding diagnostic warnings."""
    if diagnostics.get("parse_errors"):
        return (
            "Parse errors detected — outline symbols may be phantom "
            "(wrong language for the file extension, or corrupt source). "
            "Verify the file's language before trusting this outline."
        )
    warnings = diagnostics.get("encoding_warnings") or []
    if "null_bytes" in warnings:
        return (
            "Raw NUL bytes detected — line spans may be unreliable. "
            "Inspect or clean the source bytes before trusting this outline."
        )
    return (
        "Non-UTF8 or replacement-decoded source detected — verify the file "
        "encoding before trusting names and line spans from this outline."
    )


class GetCodeOutlineTool(BaseMCPTool):
    """
    MCP Tool: get_code_outline

    返回代码文件的层次化结构大纲，不含方法体内容。
    输出格式：package → class（含行号范围） → method（含签名和行号），
    token 消耗远低于 analyze_code_structure 的表格格式。

    典型用法：
        AI 调用 get_code_outline 得到结构树，
        再调用 extract_code_section 只取需要的方法体。
    """

    def __init__(self, project_root: str | None = None) -> None:
        """初始化 get_code_outline 工具。"""
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        self.logger = logger

    def _on_project_root_changed(self, project_root: str | None) -> None:
        """Hook fired by ``BaseMCPTool.set_project_path`` (ARCH-A4).

        Single source of truth for project-root reactions — do NOT override
        ``set_project_path`` itself. Refresh the analysis engine so it is
        scoped to the new root.
        """
        self.analysis_engine = get_analysis_engine(project_root)
        logger.info(f"GetCodeOutlineTool project path updated to: {project_root}")

    def get_tool_schema(self) -> dict[str, Any]:
        """返回 MCP tool JSON Schema。"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to the source file to outline. "
                        "Must be within project boundaries."
                    ),
                },
                "language": {
                    "type": "string",
                    "description": (
                        "Programming language (optional, auto-detected from file extension). "
                        "Example: 'java', 'python', 'go'"
                    ),
                },
                "include_fields": {
                    "type": "boolean",
                    "description": (
                        "Include class fields/attributes in the outline. "
                        "Default false to keep outline compact."
                    ),
                    "default": False,
                },
                "include_imports": {
                    "type": "boolean",
                    "description": (
                        "Include import statements summary in the outline. "
                        "Default false."
                    ),
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": (
                        "Output format: 'toon' for compact TOON format (50-70% token savings), "
                        "or 'json' for standard JSON. Default 'toon'."
                    ),
                    "default": "toon",
                },
                "listed_cap": {
                    "type": "integer",
                    "description": (
                        "Maximum number of classes (and top-level functions) to list in the "
                        "response.  Default 50.  Raise for larger files; pre-cap totals "
                        "(classes_total, top_level_functions_total) are always present so you "
                        "know how many elements exist.  "
                        "NEVER mark this required — runtime-resolved param."
                    ),
                    "default": 50,
                    "minimum": 1,
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        校验工具参数。

        Args:
            arguments: 工具调用参数

        Returns:
            True 表示参数合法

        Raises:
            ValueError: 参数不合法时抛出
        """
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")

        file_path = arguments["file_path"]
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("file_path must be a non-empty string")

        if "language" in arguments and arguments["language"] is not None:
            if not isinstance(arguments["language"], str):
                raise ValueError("language must be a string")

        for bool_field in ("include_fields", "include_imports"):
            if bool_field in arguments and not isinstance(arguments[bool_field], bool):
                raise ValueError(f"{bool_field} must be a boolean")

        # 验证 output_format
        if "output_format" in arguments:
            output_format = arguments["output_format"]
            if output_format not in ("json", "toon"):
                return False  # 无效格式返回 False

        # 验证 listed_cap
        if "listed_cap" in arguments and arguments["listed_cap"] is not None:
            cap = arguments["listed_cap"]
            if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
                raise ValueError("listed_cap must be a positive integer")

        return True

    def _build_outline(
        self,
        analysis_result: Any,
        include_fields: bool,
        include_imports: bool,
    ) -> dict[str, Any]:
        """从分析结果构建层次化大纲。

        大纲结构：
            package (str | None)
            imports_count (int)
            classes: list of
                name, type, line_start, line_end
                extends, implements
                methods: list of
                    name, return_type, parameters, visibility
                    line_start, line_end, is_constructor, is_static
                fields (if include_fields): list of
                    name, type, visibility, line_start, line_end
            top_level_functions: list of
                name, return_type, parameters, line_start, line_end
            statistics: class_count, method_count, field_count, import_count

        r37d2 (dogfood): 312 lines → ~25 lines of phase dispatch.
        Language-specific enrichment lifted to module helpers
        (``_enrich_markup_outline`` / ``_enrich_sql_outline`` /
        ``_enrich_markdown_outline`` / ``_enrich_yaml_outline`` /
        ``_enrich_json_outline``). Helpers ``_method_entry`` /
        ``_field_entry`` / ``_in_class_ranges`` are now module-level
        utilities. Output dict keys are preserved byte-for-byte.
        """
        elements = analysis_result.elements or []
        packages = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)]
        imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
        classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
        all_methods = [
            e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ]
        all_fields = [
            e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
        ]

        class_outlines = _build_class_outlines(
            classes, all_methods, all_fields, include_fields
        )
        class_ranges = [
            (getattr(cls, "start_line", 0), getattr(cls, "end_line", 0))
            for cls in classes
        ]
        class_names = [getattr(cls, "name", "") for cls in classes]
        # Build function span ranges so nested functions can be excluded from
        # top_level_functions.  A function is top-level only when NO other
        # function's span strictly contains it (Issue #534 — span containment).
        fn_spans = [
            (getattr(m, "start_line", 0), getattr(m, "end_line", 0))
            for m in all_methods
        ]
        top_level_fns = [
            _method_entry(m)
            for i, m in enumerate(all_methods)
            if not _in_class_ranges(m, class_ranges, class_names)
            and not _in_function_spans(i, fn_spans)
        ]
        top_level_fns.sort(key=lambda x: x["line_start"])

        outline: dict[str, Any] = {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "total_lines": analysis_result.line_count,
            "package": packages[0].name if packages else None,
            "classes": class_outlines,
            "top_level_functions": top_level_fns,
            "statistics": {
                "class_count": len(classes),
                "method_count": len(all_methods),
                "field_count": len(all_fields),
                "import_count": len(imports),
            },
        }
        # Module-level constants/fields (outside every class span) — without
        # this, field_count includes them but no rendered section shows them
        # (Codex P2 on #645; the #639 dogfood ask was to SEE them). Emitted
        # only when non-empty (token budget; byte-pin tests stay untouched
        # for constant-free files).
        top_level_fields = sorted(
            (
                _field_entry(f)
                for f in all_fields
                if not _in_class_ranges(f, class_ranges, class_names)
            ),
            key=lambda x: x["line_start"],
        )
        if top_level_fields:
            outline["top_level_fields"] = top_level_fields
        if include_imports:
            outline["imports"] = [
                getattr(imp, "import_statement", getattr(imp, "name", ""))
                for imp in imports
            ]
        # Language-specific enrichment (only when no class structure is
        # present — these tools are mutually exclusive with classes).
        _enrich_markup_outline(outline, elements, classes)
        _enrich_sql_outline(outline, elements, classes)
        _enrich_markdown_outline(outline, elements, classes)
        _enrich_yaml_outline(outline, elements, classes)
        _enrich_json_outline(outline, elements, classes)
        return outline

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行 get_code_outline 工具。

        r37d1 (dogfood): 136 lines → ~25 lines of phase dispatch.
        Sub-helpers: ``_resolve_outline_request`` (path + language + mismatch
        guard), ``_run_outline_analysis`` (analysis engine call),
        ``_assemble_outline_response`` (canonical dict + field hoisting),
        ``_attach_outline_summary`` (summary_line + agent_summary).
        TOON default LOCKED — output_format default stays ``toon``.
        Issue #513 leg 3: listed_cap caps classes + top_level_functions on the
        MCP path; honest-truncation fields added to response.
        """
        try:
            self.validate_arguments(arguments)

            file_path = arguments["file_path"]
            language = arguments.get("language")
            include_fields = arguments.get("include_fields", False)
            include_imports = arguments.get("include_imports", False)
            output_format = arguments.get("output_format", "toon")
            listed_cap = int(arguments.get("listed_cap") or DEFAULT_OUTLINE_CLASSES_CAP)

            resolved = self._resolve_outline_request(file_path, language, output_format)
            if "early_response" in resolved:
                return dict(resolved["early_response"])

            analysis_result = await self._run_outline_analysis(
                resolved["resolved_path"], resolved["language"], file_path
            )
            outline = self._build_outline(
                analysis_result,
                include_fields=include_fields,
                include_imports=include_imports,
            )

            result = self._assemble_outline_response(
                file_path, resolved["language"], outline, listed_cap=listed_cap
            )
            self._attach_outline_summary(result, file_path)
            self._attach_input_diagnostics(result, resolved["resolved_path"])
            return apply_toon_format_to_response(result, output_format)

        except Exception as e:
            self.logger.error(f"Error in get_code_outline: {e}")
            raise

    def _resolve_outline_request(
        self, file_path: str, language: str | None, output_format: str
    ) -> dict[str, Any]:
        """Resolve + validate the file path, then run the language-mismatch gate.

        Returns either ``{"resolved_path": ..., "language": ...}`` for the
        happy path, or ``{"early_response": <dict>}`` when the mismatch
        guard fires (caller returns it unchanged).
        """
        resolved_path = self.resolve_and_validate_file_path(file_path)
        if not Path(resolved_path).exists():
            raise ValueError(f"File not found: {file_path}")
        # O3 (round-30 dogfood): strict mismatch gate against the explicit
        # ``language`` override before we hand it to the analysis engine.
        mismatch = detect_language_mismatch(
            resolved_path,
            language if isinstance(language, str) else None,
            project_root=self.project_root,
        )
        if mismatch:
            response = language_mismatch_error_response(
                tool_name="get_code_outline",
                file_path=file_path,
                warning=mismatch,
            )
            response["output_format"] = output_format
            return {"early_response": response}
        if not language:
            language = detect_language_from_file(
                resolved_path, project_root=self.project_root
            )
        return {"resolved_path": resolved_path, "language": language}

    async def _run_outline_analysis(
        self, resolved_path: str, language: str, original_path: str
    ) -> Any:
        """Run the analysis engine inside the perf monitor span.

        Raises ``RuntimeError`` with the original (unresolved) path in the
        message when the engine returns ``None`` — preserves the legacy
        error string format.
        """
        monitor = get_performance_monitor()
        with monitor.measure_operation("get_code_outline"):
            request = AnalysisRequest(
                file_path=resolved_path,
                language=language,
                include_complexity=False,
                include_details=True,
            )
            analysis_result = await self.analysis_engine.analyze(request)
        if analysis_result is None:
            raise RuntimeError(f"Failed to analyze file: {original_path}")
        # Theme-D fix: the engine returns ``AnalysisResult(success=False)`` when
        # the parse fails (e.g. a detected-but-unparseable language whose
        # tree-sitter grammar is not installed). Honor that flag instead of
        # building an empty-success outline that lies to the agent ("0 classes,
        # 0 methods" for a real, non-empty file). Propagating the engine's
        # ``error_message`` lets the MCP boundary classify it (a message
        # containing "Unsupported language" maps to ``language_unsupported``),
        # matching the honest error the CLI already returns for the same file.
        if getattr(analysis_result, "success", True) is False:
            # RuntimeError (not ValueError): a parse failure is an internal
            # condition, not a caller-validation error. When the engine's
            # message contains "Unsupported language" the boundary still maps
            # it to ``language_unsupported`` (substring match wins over the
            # exception type); the degenerate ``error_message is None`` case
            # then falls back to ``internal`` rather than the misleading
            # ``validation`` classification.
            raise RuntimeError(
                getattr(analysis_result, "error_message", None)
                or f"Failed to analyze file: {original_path}"
            )
        return analysis_result

    @staticmethod
    def _assemble_outline_response(
        file_path: str,
        language: str | None,
        outline: Any,
        listed_cap: int = DEFAULT_OUTLINE_CLASSES_CAP,
    ) -> dict[str, Any]:
        """Build the canonical response dict + hoist outline-level fields.

        We hoist outline.classes / top_level_functions / imports onto the
        response so callers don't need an extra ``outline`` indirection —
        matching the convention every other analysis tool uses.
        ``top_level_functions`` is also mirrored as ``methods`` (the
        natural name callers reach for). Count summaries from
        ``outline.statistics`` are also hoisted.

        Issue #513 leg 3: honest-truncation cap on classes and top_level_functions.
        Statistics (class_count / method_count) are hoisted from the PRE-cap
        outline.statistics — the cap never corrupts totals (#505 lesson).
        """
        result: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "language": language,
            "outline": outline,
        }
        if not isinstance(outline, dict):
            return result

        # --- Honest-truncation cap (Issue #513 leg 3) ---
        # Apply BEFORE hoisting so both `result` and the inlined `outline` dict
        # carry the capped list.  Pre-cap totals are always recorded.
        classes_all: list = outline.get("classes") or []
        fns_all: list = outline.get("top_level_functions") or []

        classes_total = len(classes_all)
        fns_total = len(fns_all)

        classes_listed_count = min(classes_total, listed_cap)
        fns_listed_count = min(fns_total, listed_cap)
        truncated = classes_total > listed_cap or fns_total > listed_cap

        # Slice both lists (keep sorted order — _build_outline already sorts by
        # start_line, so slicing preserves that invariant deterministically).
        classes_capped = classes_all[:listed_cap]
        fns_capped = fns_all[:listed_cap]

        # Issue #571: the top-level cap above bounds the class COUNT, but a
        # single wide class (10k methods in generated protobuf/ORM stubs)
        # detonates the response (2.75MB, truncated=False). Cap each listed
        # class's methods/fields under the same listed_cap with per-class totals.
        per_class_truncated = False
        new_classes_capped = []
        for cls in classes_capped:
            capped_cls, was_truncated = _cap_class_members(cls, listed_cap)
            new_classes_capped.append(capped_cls)
            per_class_truncated = per_class_truncated or was_truncated
        classes_capped = new_classes_capped
        truncated = truncated or per_class_truncated

        # Patch the outline dict in-place (shallow copy to avoid mutating caller's
        # reference — we create a new dict for outline to keep immutability).
        outline = dict(outline)
        outline["classes"] = classes_capped
        outline["top_level_functions"] = fns_capped
        result["outline"] = outline

        # --- Hoist outline-level fields ---
        # 1) Scalar fields first.
        for key in ("imports", "total_lines", "package"):
            if key in outline and key not in result:
                result[key] = outline[key]
        # 2) Hoisted lists use the capped versions.
        result["classes"] = classes_capped
        result["top_level_functions"] = fns_capped
        if outline.get("top_level_fields"):
            result["top_level_fields"] = outline["top_level_fields"]
        # 3) Hoist the count summaries from outline.statistics — PRE-cap totals
        #    (aggregate-mode invariant: totals must equal the full element count,
        #    never the capped slice).
        stats = outline.get("statistics")
        if isinstance(stats, dict):
            for key in (
                "class_count",
                "method_count",
                "field_count",
                "import_count",
            ):
                if key in stats and key not in result:
                    result[key] = stats[key]

        # --- Honest-truncation fields (same pattern as DF-13 / DF-1) ---
        result["classes_total"] = classes_total
        result["classes_listed"] = classes_listed_count
        result["top_level_functions_total"] = fns_total
        result["top_level_functions_listed"] = fns_listed_count
        result["listed_cap"] = listed_cap
        result["truncated"] = truncated

        return result

    @staticmethod
    def _attach_outline_summary(result: dict[str, Any], file_path: str) -> None:
        """Add ``summary_line`` + ``verdict`` + ``agent_summary`` to ``result``.

        r37w envelope ratchet: top-level verdict must equal
        ``agent_summary.verdict``. Both are pinned to ``INFO`` for the
        outline tool — outlines never raise alarms by themselves.

        Issue #513 leg 3: when the response was truncated, the next_step
        includes a narrowing hint (how to raise listed_cap or filter by type).
        """
        class_count = int(result.get("class_count") or 0)
        method_count = int(result.get("method_count") or 0)
        field_count = int(result.get("field_count") or 0)
        summary_line = (
            f"{file_path} outline: {class_count} classes, "
            f"{method_count} methods, {field_count} fields"
        )
        result["summary_line"] = summary_line
        result["verdict"] = "INFO"

        # Honest-truncation next_step hint. Name whichever list(s) actually
        # exceeded the cap — a function-heavy module with zero classes must
        # not be told "showing 0 of 0 classes" (Codex P2 on #542).
        truncated = result.get("truncated", False)
        classes_total = result.get("classes_total", class_count)
        classes_listed = result.get("classes_listed", class_count)
        functions_total = result.get("top_level_functions_total", 0)
        functions_listed = result.get("top_level_functions_listed", 0)
        listed_cap = result.get("listed_cap", DEFAULT_OUTLINE_CLASSES_CAP)
        if truncated:
            overflow_parts = []
            if classes_listed < classes_total:
                overflow_parts.append(f"{classes_listed} of {classes_total} classes")
            if functions_listed < functions_total:
                overflow_parts.append(
                    f"{functions_listed} of {functions_total} top-level functions"
                )
            # #571 (Codex P2): truncation can come ONLY from the per-class
            # method/field cap, in which case the top-level counts above match
            # and overflow_parts would be empty — losing the reason. Name the
            # member-capped classes so the note is never reasonless.
            member_capped = sum(
                1
                for c in (result.get("classes") or [])
                if isinstance(c, dict) and ("methods_total" in c or "fields_total" in c)
            )
            if member_capped:
                overflow_parts.append(
                    f"methods/fields capped in {member_capped} class(es)"
                )
            next_step = (
                f"truncated: showing {', '.join(overflow_parts)} "
                f"(listed_cap={listed_cap}). "
                "To see more, raise listed_cap or narrow with a specific element type. "
                "Use extract_code_section with line ranges from the listed entries."
            )
        else:
            next_step = "extract_code_section for the method you need (use line ranges from outline)"

        result["agent_summary"] = {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": "INFO",
        }

    @staticmethod
    def _attach_input_diagnostics(result: dict[str, Any], resolved_path: str) -> None:
        """Attach parse/encoding warnings to a successful outline response."""
        from .utils.parse_validity import file_input_diagnostics

        diagnostics = file_input_diagnostics(resolved_path, result.get("language"))
        if not diagnostics:
            return
        result.update(diagnostics)
        result["verdict"] = "WARN"
        agent_summary = result.get("agent_summary")
        if isinstance(agent_summary, dict):
            agent_summary["verdict"] = "WARN"
            agent_summary["next_step"] = _outline_diagnostics_next_step(diagnostics)

    def get_tool_definition(self) -> dict[str, Any]:
        """返回 MCP tool 定义。"""
        return {
            "name": "get_code_outline",
            "description": (
                "Get the structural navigation map of a file — hierarchy of packages, classes, "
                "and methods with line numbers, WITHOUT the method bodies. "
                "\n\n"
                "This is the outline-first workflow: understand the architecture, then use "
                "extract_code_section to fetch only the specific code you need. "
                "TOON format (default) delivers 54-56% token savings vs JSON. "
                "\n\n"
                "WHEN TO USE:\n"
                "- After check_code_scale shows a file is > 200 lines — get the map before diving in\n"
                "- When you need to understand a file's class/method organization without reading bodies\n"
                "- To locate which line range contains the method you want before extract_code_section\n"
                "- To understand a file's architecture at a glance (inheritance, method count, line spans)\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- When you need the actual code content (method bodies) — use extract_code_section\n"
                "- When you're searching for specific text patterns — use search_content instead\n"
                "- Files < 100 lines — just Read them directly, an outline adds no value\n"
                "\n"
                "IMPORTANT: get_code_outline = navigation map (structure without content). "
                "analyze_code_structure = detailed map (every element with full metadata, visibility, "
                "complexity). Use outline for navigation, use analyze_code_structure for deep analysis."
            ),
            "inputSchema": self.get_tool_schema(),
            # MCP annotations: outline is a pure read of the parser cache —
            # safe, idempotent, no side effects, no network calls.
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


# ---------------------------------------------------------------------------
# Outline helpers (r37d2) — lifted from ``_build_outline`` so the latter
# stays at ~25 lines of phase dispatch. Each helper preserves byte-for-byte
# the dict layout the original code produced.
# ---------------------------------------------------------------------------


from .utils.outline_enrichers import (  # noqa: E402 (after class definition)
    _enrich_json_outline,
    _enrich_markdown_outline,
    _enrich_markup_outline,
    _enrich_sql_outline,
    _enrich_yaml_outline,
)
from .utils.outline_extractors import (  # noqa: E402
    _build_class_outlines,
    _cap_class_members,
    _field_entry,
    _in_class_ranges,
    _in_function_spans,
    _method_entry,
    _method_owned_by_class,  # noqa: F401 — re-exported for test compatibility
    _normalize_receiver_type,  # noqa: F401 — re-exported for test compatibility
    _resolve_extends,  # noqa: F401 — re-exported for test compatibility
    _resolve_implements,  # noqa: F401 — re-exported for test compatibility
)

# 模块级实例，供直接访问使用
get_code_outline_tool = GetCodeOutlineTool()
