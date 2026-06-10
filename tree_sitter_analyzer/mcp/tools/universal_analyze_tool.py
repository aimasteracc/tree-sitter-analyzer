#!/usr/bin/env python3
"""
Universal Analyze Tool for MCP

Universal code analysis through the MCP protocol, supporting multiple
programming languages with automatic language detection.
"""

from pathlib import Path
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file, is_language_supported
from ...mcp.utils import get_performance_monitor
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from ..utils.error_sanitizer import safe_error_message
from ..utils.file_metrics import compute_file_metrics
from ..utils.format_helper import apply_toon_format_to_response
from .analyze_code_structure_helpers import convert_analysis_result_to_structure_dict
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    format_summary_line,
    language_mismatch_error_response,
)
from .universal_analyze_helpers import (
    TOOL_SCHEMA as _TOOL_SCHEMA,
)
from .universal_analyze_helpers import (
    count_dict_elements_by_type,
    count_elements_by_type,
    elements_to_summary,
)

logger = setup_logger(__name__)


def _attach_canonical_envelope(base: dict[str, Any]) -> None:
    """Inject ``success``/``summary_line``/``agent_summary`` into the response.

    Finding 2: round 11 standardized the canonical envelope across MCP
    tools but ``universal_analyze`` was missed — JSON keys were only the
    analysis payload (``classes``/``methods``/``metrics``/...) with no
    ``success`` or summary fields. Agents consuming the response could not
    branch on the same fields they see on every other tool. This helper
    is idempotent: callers that already populate ``summary_line`` or
    ``agent_summary`` keep their values.
    """
    base.setdefault("success", True)

    file_path = base.get("file_path", "<unknown>")
    language = base.get("language", "unknown")

    raw_metrics = base.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    line_count = metrics.get("lines_total") or metrics.get("lines_code") or 0
    classes = base.get("classes") or []
    methods = base.get("methods") or []
    fields = base.get("fields") or []
    n_classes = len(classes) if isinstance(classes, list) else 0
    n_methods = len(methods) if isinstance(methods, list) else 0
    n_fields = len(fields) if isinstance(fields, list) else 0

    # J5 (round-22): single-space join via helper — never reintroduces the
    # ``"... lines  "`` double-space we shipped earlier in this builder.
    summary_line = format_summary_line(
        file_path,
        language,
        f"{line_count} lines",
        f"classes={n_classes}",
        f"methods={n_methods}",
        f"fields={n_fields}",
    )
    base.setdefault("summary_line", summary_line)

    agent_summary = base.get("agent_summary")
    if not isinstance(agent_summary, dict):
        agent_summary = {}
    agent_summary.setdefault("summary_line", summary_line)
    agent_summary.setdefault(
        "next_step",
        "Call analyze_code_structure for per-element detail.",
    )
    agent_summary.setdefault("verdict", "n/a")
    base["agent_summary"] = agent_summary
    # r37x (envelope ratchet): top-level verdict mirror (r37u contract).
    base.setdefault("verdict", agent_summary["verdict"])


def _attach_structure_detail(base: dict[str, Any], result: Any) -> None:
    """Hoist per-element detail onto the response.

    Reuses the same converters that :class:`AnalyzeCodeStructureTool` runs, so
    both tools emit identical ``classes``/``methods``/``fields``/``imports``
    arrays (signatures, line ranges, complexity, modifiers, annotations).
    """
    try:
        rich = convert_analysis_result_to_structure_dict(result)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"structure detail conversion failed: {exc}")
        return

    for key in ("classes", "methods", "fields", "imports"):
        items = rich.get(key, [])
        # Top-level hoist for agents reading either tool's response.
        base[key] = items
        # Enrich the structure envelope so analysis_type='structure'/'metrics'
        # consumers also see the detailed entries.
        structure = base.get("structure")
        if isinstance(structure, dict):
            structure[key] = items
    # Carry the package info forward when present.
    package = rich.get("package")
    structure = base.get("structure")
    if (
        package is not None
        and isinstance(structure, dict)
        and not structure.get("package")
    ):
        structure["package"] = package


def _summarize_annotation(a: Any) -> dict[str, Any]:
    """Return the summary dict for one annotation element.

    Prefers the element's own ``to_summary_item()`` when defined (gives
    each language plugin a hook to expose richer metadata), otherwise
    falls back to ``{"name": <annotation_name>}``.

    r37e2 (dogfood): lifted from ``_extract_structure_info`` to flatten
    the inline ternary-in-list-comp from depth 6 to a flat helper call.
    """
    if hasattr(a, "to_summary_item"):
        result: dict[str, Any] = a.to_summary_item()
        return result
    return {"name": getattr(a, "name", "unknown")}


class UniversalAnalyzeTool(BaseMCPTool):
    """Universal MCP Tool for code analysis across multiple languages."""

    def __init__(self, project_root: str | None = None) -> None:
        self.analysis_engine: Any = None  # set by the hook below
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self.analysis_engine = get_analysis_engine(project_root)

    def get_tool_schema(self) -> dict[str, Any]:
        return _TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "analyze_code_universal",
            "description": (
                "One-call file analyzer with automatic language detection "
                "across every supported language (Python, Java, JS/TS, Go, "
                "Rust, C/C++, ...). Pick the depth via ``analysis_type``: "
                "``basic`` (counts + summary), ``detailed`` (adds element "
                "lists), ``structure`` (full classes/methods/fields/imports "
                "with line ranges, complexity, modifiers, annotations), or "
                "``metrics`` (numeric LOC / complexity only). Returns the "
                "canonical ``{success, summary_line, agent_summary, ...}`` "
                "envelope so an agent can branch on the same shape it sees "
                "from every other tool.\n\n"
                "WHEN TO USE:\n"
                "- First touch on an unfamiliar file — get language, size, "
                "and structure in one call\n"
                "- SMART workflow ``Analyze`` step before edits or "
                "refactors\n"
                "- Producing a token-efficient summary of a file for "
                "downstream agents\n"
                "- Comparing metrics (LOC, complexity, element counts) "
                "between files\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- You only need raw text by line range — use "
                "``extract_code_section``\n"
                "- You want a Markdown table outline — call "
                "``analyze_code_structure`` directly\n"
                "- You need to search by symbol name — use ``query_code``\n"
                "- You want project-wide stats — use ``project_overview`` "
                "or ``analyze_scale``"
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path, language, and output arguments."""
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")
        file_path = arguments["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")
        if not file_path.strip():
            raise ValueError("file_path cannot be empty")
        if "language" in arguments and not isinstance(arguments["language"], str):
            raise ValueError("language must be a string")
        if "analysis_type" in arguments:
            if not isinstance(arguments["analysis_type"], str):
                raise ValueError("analysis_type must be a string")
            valid = ["basic", "detailed", "structure", "metrics"]
            if arguments["analysis_type"] not in valid:
                raise ValueError(f"analysis_type must be one of {valid}")
        if "include_ast" in arguments and not isinstance(
            arguments["include_ast"], bool
        ):
            raise ValueError("include_ast must be a boolean")
        if "include_queries" in arguments and not isinstance(
            arguments["include_queries"], bool
        ):
            raise ValueError("include_queries must be a boolean")
        return True

    @handle_mcp_errors("universal_analyze")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute universal analysis using the analysis engine."""
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        analysis_type = arguments.get("analysis_type", "basic")
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)

        # O3 (round-30 dogfood): silent acceptance of mismatched
        # ``--language``/``language:`` override. ``foo.py`` with
        # ``language='java'`` previously emitted success=true with zero
        # results — the agent passing the wrong tag had no signal that
        # something was wrong. Strict gate (Option A): refuse the bad
        # input with a canonical validation envelope.
        mismatch = detect_language_mismatch(
            resolved,
            language,
            project_root=self.project_root,
        )
        if mismatch:
            response = language_mismatch_error_response(
                tool_name="universal_analyze",
                file_path=file_path,
                warning=mismatch,
            )
            response["output_format"] = output_format
            return response
        if analysis_type:
            analysis_type = self.security_validator.sanitize_input(
                analysis_type, max_length=50
            )

        if not Path(resolved).exists():
            raise ValueError("Invalid file path: file does not exist")

        if not language:
            language = detect_language_from_file(
                resolved, project_root=self.project_root
            )
            if language == "unknown":
                raise ValueError(f"Could not detect language for file: {resolved}")

        if not is_language_supported(language):
            raise ValueError(f"Language '{language}' is not supported by tree-sitter")

        valid_types = ["basic", "detailed", "structure", "metrics"]
        if analysis_type not in valid_types:
            valid_str = ", ".join(valid_types)
            raise ValueError(
                f"Invalid analysis_type '{analysis_type}'. Valid: {valid_str}"
            )

        logger.info(
            f"Analyzing {resolved} (language: {language}, type: {analysis_type})"
        )

        # r37e2 (dogfood): flatten nesting 6 → 3 via _run_universal_analysis.
        try:
            return await self._run_universal_analysis(
                resolved, language, analysis_type, arguments, output_format
            )
        except Exception as e:
            logger.error(f"Error analyzing {resolved}: {e}")
            raise

    async def _run_universal_analysis(
        self,
        resolved: str,
        language: str,
        analysis_type: str,
        arguments: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        """Execute the analysis inside the perf monitor span.

        Picks the Java-specific advanced path or the generic universal
        path based on ``language``. Honours ``include_queries=True`` by
        attaching ``available_queries``. TOON default is preserved —
        ``output_format`` defaults to ``toon`` upstream and is passed
        through unchanged.

        r37e2 (dogfood): lifted from ``execute`` to flatten nesting
        from depth 6 to 3 (try → with → if branch → kwargs).
        """
        monitor = get_performance_monitor()
        with monitor.measure_operation("universal_analyze"):
            if language == "java":
                result = await self._analyze_advanced(
                    resolved, language, analysis_type, arguments
                )
            else:
                result = await self._analyze_universal(
                    resolved, language, analysis_type, arguments
                )
            if arguments.get("include_queries", False):
                result["available_queries"] = await self._get_available_queries(
                    language
                )
            return apply_toon_format_to_response(result, output_format)

    async def _analyze_advanced(
        self,
        file_path: str,
        language: str,
        analysis_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze using the advanced analyzer (Java-specific)."""
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_complexity=True,
            include_details=True,
        )
        result = await self.analysis_engine.analyze(request)
        if result is None:
            raise RuntimeError(f"Failed to analyze file: {file_path}")
        # Theme-D parity: honor the engine's parse-failure flag instead of
        # stamping ``success: True`` onto a failed analysis (matches the
        # structure-facade fix in PR #414).
        if not result.success:
            raise RuntimeError(
                getattr(result, "error_message", None)
                or f"Failed to analyze file: {file_path}"
            )

        base: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "language": language,
            "analyzer_type": "advanced",
            "analysis_type": analysis_type,
        }

        if analysis_type == "basic":
            base.update(self._extract_basic_metrics(result))
        elif analysis_type == "detailed":
            base.update(self._extract_detailed_metrics(result))
        elif analysis_type == "structure":
            base.update(self._extract_structure_info(result))
        elif analysis_type == "metrics":
            base.update(self._extract_comprehensive_metrics(result))

        # Hoist the rich per-element detail so agents reading either
        # ``universal_analyze`` or ``analyze_code_structure`` see the same
        # shape (signatures, line ranges, complexity, modifiers).
        _attach_structure_detail(base, result)

        if arguments.get("include_ast", False):
            base["ast_info"] = {"node_count": result.line_count, "depth": 0}

        _attach_canonical_envelope(base)
        return base

    async def _analyze_universal(
        self,
        file_path: str,
        language: str,
        analysis_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze using the universal analyzer."""
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_details=(analysis_type == "detailed"),
        )
        result = await self.analysis_engine.analyze(request)

        if not result or not result.success:
            msg = result.error_message if result else "Unknown error"
            raise RuntimeError(f"Failed to analyze file: {file_path} - {msg}")

        analysis_dict = result.to_dict()
        # Inject typed elements so extractors can count via element_type.
        # AnalysisResult.to_dict() splits into classes/methods/fields/imports
        # buckets and does NOT expose an `elements` key — without this,
        # count_dict_elements_by_type sees an empty list and returns zeros.
        analysis_dict["elements"] = result.elements or []
        # Finding 1: classify code/comment/blank lines via the shared file_metrics
        # helper so the universal path produces the same counts as analyze_scale.
        # Previously this branch hardcoded lines_comment=0 and lines_blank=0
        # while copying line_count into lines_code (lying about every file).
        try:
            line_metrics = compute_file_metrics(
                file_path,
                language=language,
                project_root=self.project_root,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"file_metrics computation failed for {file_path}: {exc}")
            line_metrics = {}
        analysis_dict["_file_metrics"] = line_metrics

        base: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "language": language,
            "analyzer_type": "universal",
            "analysis_type": analysis_type,
        }

        if analysis_type == "basic":
            base.update(self._extract_universal_basic_metrics(analysis_dict))
        elif analysis_type == "detailed":
            base.update(self._extract_universal_detailed_metrics(analysis_dict))
        elif analysis_type == "structure":
            base.update(self._extract_universal_structure_info(analysis_dict))
        elif analysis_type == "metrics":
            base.update(self._extract_universal_comprehensive_metrics(analysis_dict))

        # Hoist the rich per-element detail so agents reading either
        # ``universal_analyze`` or ``analyze_code_structure`` see the same
        # shape (signatures, line ranges, complexity, modifiers).
        _attach_structure_detail(base, result)

        if arguments.get("include_ast", False):
            base["ast_info"] = analysis_dict.get("ast_info", {})

        _attach_canonical_envelope(base)
        return base

    # -- Advanced analyzer extractors --

    def _extract_basic_metrics(self, result: Any) -> dict[str, Any]:
        """Extract basic file metrics (lines, functions, classes)."""
        stats = result.get_statistics()
        counts = count_elements_by_type(result.elements)
        return {
            "metrics": {
                "lines_total": result.line_count,
                "lines_code": stats.get("lines_of_code", 0),
                "lines_comment": stats.get("comment_lines", 0),
                "lines_blank": stats.get("blank_lines", 0),
                "elements": counts,
            }
        }

    def _extract_detailed_metrics(self, result: Any) -> dict[str, Any]:
        """Extract detailed metrics with complexity and dependencies."""
        data = self._extract_basic_metrics(result)
        methods = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ]
        cx_scores = [getattr(m, "complexity_score", 0) or 0 for m in methods]
        total_cx = sum(cx_scores)
        data["metrics"]["complexity"] = {
            "total": total_cx,
            "average": round(total_cx / len(methods) if methods else 0, 2),
            "max": max(cx_scores, default=0),
        }
        return data

    def _extract_structure_info(self, result: Any) -> dict[str, Any]:
        """Extract structure information from analysis result.

        r37e2 (dogfood): flatten nesting 6 → 3 by extracting the
        annotation-summary list comp into ``_summarize_annotation``.
        """
        annotations = [
            _summarize_annotation(a) for a in getattr(result, "annotations", [])
        ]
        return {
            "structure": {
                "package": result.package.name if result.package else None,
                "classes": elements_to_summary(result.elements, ELEMENT_TYPE_CLASS),
                "methods": elements_to_summary(result.elements, ELEMENT_TYPE_FUNCTION),
                "fields": elements_to_summary(result.elements, ELEMENT_TYPE_VARIABLE),
                "imports": elements_to_summary(result.elements, ELEMENT_TYPE_IMPORT),
                "annotations": annotations,
            }
        }

    def _extract_comprehensive_metrics(self, result: Any) -> dict[str, Any]:
        """Extract comprehensive metrics combining all dimensions."""
        data = self._extract_detailed_metrics(result)
        data.update(self._extract_structure_info(result))
        return data

    # -- Universal analyzer extractors --

    def _extract_universal_basic_metrics(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract basic metrics using universal tree-sitter path.

        Finding 1: prefer the file_metrics classifier (same as analyze_scale)
        so comments and blank lines are counted correctly. Falls back to
        ``line_count`` from the analysis result when the classifier could
        not run (e.g. file disappeared between dispatch and extract).
        """
        elements = analysis_dict.get("elements", [])
        counts = count_dict_elements_by_type(elements)
        raw_metrics = analysis_dict.get("_file_metrics")
        line_metrics: dict[str, Any] = (
            raw_metrics if isinstance(raw_metrics, dict) else {}
        )
        total_lines_raw = line_metrics.get("total_lines")
        total_lines = (
            total_lines_raw
            if isinstance(total_lines_raw, int)
            else analysis_dict.get("line_count", 0)
        )
        code_lines = line_metrics.get("code_lines")
        comment_lines = line_metrics.get("comment_lines")
        blank_lines = line_metrics.get("blank_lines")
        if not isinstance(code_lines, int):
            code_lines = total_lines
        if not isinstance(comment_lines, int):
            comment_lines = 0
        if not isinstance(blank_lines, int):
            blank_lines = 0
        return {
            "metrics": {
                "lines_total": total_lines,
                "lines_code": code_lines,
                "lines_comment": comment_lines,
                "lines_blank": blank_lines,
                "elements": counts,
            }
        }

    def _extract_universal_detailed_metrics(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract detailed metrics using universal tree-sitter path."""
        data = self._extract_universal_basic_metrics(analysis_dict)
        if "query_results" in analysis_dict:
            data["query_results"] = analysis_dict["query_results"]
        return data

    def _extract_universal_structure_info(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract structure info using universal tree-sitter path.

        AnalysisResult.to_dict() exposes ``classes``/``methods``/``fields``/
        ``imports``/``annotations`` at the top level, so build the structure
        envelope from those buckets rather than the non-existent
        ``structure`` key.
        """
        structure_payload = analysis_dict.get("structure")
        if not isinstance(structure_payload, dict) or not structure_payload:
            structure_payload = {
                "package": analysis_dict.get("package"),
                "classes": analysis_dict.get("classes", []),
                "methods": analysis_dict.get("methods", []),
                "fields": analysis_dict.get("fields", []),
                "imports": analysis_dict.get("imports", []),
                "annotations": analysis_dict.get("annotations", []),
            }
        return {
            "structure": structure_payload,
            "queries_executed": analysis_dict.get("queries_executed", []),
        }

    def _extract_universal_comprehensive_metrics(
        self, analysis_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract comprehensive metrics using universal tree-sitter path."""
        data = self._extract_universal_detailed_metrics(analysis_dict)
        data.update(self._extract_universal_structure_info(analysis_dict))
        return data

    async def _get_available_queries(self, language: str) -> dict[str, Any]:
        """Return available query keys for a language."""
        try:
            if language == "java":
                return {
                    "language": language,
                    "queries": [],
                    "note": "Advanced analyzer uses built-in analysis logic",
                }
            queries = self.analysis_engine.get_supported_languages()
            return {"language": language, "queries": queries, "count": len(queries)}
        except Exception as e:
            logger.warning(f"Failed to get queries for {language}: {e}")
            return {
                "language": language,
                "queries": [],
                "error": safe_error_message(e, self.project_root),
            }
