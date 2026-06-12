#!/usr/bin/env python3
"""``structure`` facade — Wave B of the FacadeTool framework (P0 geode layer).

Folds seven structural analysis capabilities behind one ``action`` parameter:

============  ==========================================  ==================================
action        inner / route                               engine
============  ==========================================  ==================================
outline       ``get_code_outline``                        AST-based symbol outline
analyze       ``analyze_code_structure``                  complexity + structure analysis
ast_path      ``codegraph_ast_path``                      AST path from node to root
sitemap       ``codegraph_sitemap``                       file/symbol sitemap
class_tree    ``codegraph_class_hierarchy``               class inheritance tree
class_detail  ``codegraph_class_inspect``                 detailed class member view
explore       ``codegraph_explore``                       multi-symbol source explorer
read          ``extract_code_section`` (BESPOKE, F5)      single/batch file partial read
============  ==========================================  ==================================

F3 (PRD §0): ``query`` (tree-sitter .scm DSL) lives in the ``search`` facade.
Do NOT register ``query`` here — it would duplicate the search facade's F3 route.

F5 bespoke route — ``read`` → ``extract_code_section``
    ``server._handle_extract_code_section`` performs single-vs-batch reshaping:
    if ``requests`` is present it forwards straight to ``ReadPartialTool.execute``;
    otherwise it builds an 11-key ``full_args`` dict from the flat single-file
    params before calling the tool. That logic is re-homed into the
    ``_read_route`` closure below so the facade is fully self-contained and does
    NOT depend on the server object at all (spec §3 recommendation).
    The bespoke inner (``ReadPartialTool``) is registered via
    ``facade.register_bespoke_inner(inner)`` so G3 rebind propagation reaches it.

All structure actions are read-only → annotations declare ``readOnlyHint=True``
(see spec §6; this is the correct annotation for a pure-read facade).
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# ---------------------------------------------------------------------------
# Annotations — every structure action is read-only (spec §6)
# ---------------------------------------------------------------------------
_STRUCTURE_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

# ---------------------------------------------------------------------------
# Description — one line per action (LLM reads this to pick ``action``)
# ---------------------------------------------------------------------------
_STRUCTURE_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) structural analysis facade. "
    "Covers codegraph_explore (multi-symbol source), codegraph_class_hierarchy, "
    "codegraph_class_inspect, codegraph_sitemap, codegraph_ast_path, "
    "and code-outline/complexity in one tool. "
    "Pick a capability via `action`:\n"
    "- action=outline — AST-based symbol outline for a file or directory. "
    "Params: file_path, language, depth.\n"
    "- action=analyze — complexity + structure analysis (cyclomatic, nesting, "
    "cohesion). Params: file_path, language.\n"
    "- action=signatures — LIGHTWEIGHT method-directory (~25 %% of full tokens). "
    "Lists every method as 'name →returnType(Np) startLine-endLine' grouped by "
    "class. Use FIRST for large files (>500 lines) to pick methods by name, then "
    "action=read to fetch bodies. Supports Python, Java, and other languages. "
    "Params: file_path[, language] (language auto-detected from file extension "
    "when omitted).\n"
    "- action=ast_path — AST path from a specific node up to the file root "
    "(navigate the parse tree, codegraph_ast_path equivalent). "
    "Params: file_path, line, column.\n"
    "- action=sitemap — high-level symbol sitemap of a directory or the whole "
    "project (what is defined where, codegraph_sitemap equivalent). "
    "Params: mode (full|api|module|flat), directory (relative path, optional), "
    "language, max_files. NOTE: takes a directory, not file_path — omit "
    "directory for the whole project.\n"
    "- action=class_tree — class inheritance/subclass hierarchy "
    "(codegraph_class_hierarchy equivalent). "
    "Params: class_name, mode (subclasses|supers|tree).\n"
    "- action=class_detail — detailed class inspection: fields, methods, "
    "visibility, inherited members (codegraph_class_inspect equivalent). "
    "Params: class_name, language.\n"
    "- action=explore — multi-symbol source explorer: show source of several "
    "related symbols grouped in one capped response "
    "(codegraph_explore equivalent). Params: symbols (list) or "
    "symbol/query (string), maxSymbols, maxFiles.\n"
    "- action=read — extract a file section (single) or multiple sections "
    "(batch). Single: file_path + start_line [+ end_line + column bounds]. "
    "Batch: requests=[{file_path, sections:[{start_line, end_line}]}]."
)


def build_structure_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``structure`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build this facade (matches the lazy-import convention used in
    ``_tool_registry.py`` and ``search_facade.py``).
    """
    from .analyze_code_structure_tool import AnalyzeCodeStructureTool
    from .ast_path_tool import CodeGraphASTPathTool
    from .class_hierarchy_tool import ClassHierarchyTool
    from .class_inspect_tool import ClassInspectTool
    from .codegraph_explore_tool import CodeGraphExploreTool
    from .codegraph_sitemap_tool import CodeGraphSitemapTool
    from .get_code_outline_tool import GetCodeOutlineTool
    from .read_partial_tool import ReadPartialTool

    # ------------------------------------------------------------------
    # F5 bespoke route: ``read`` → ``extract_code_section``
    #
    # Re-homes the single-vs-batch reshaping logic from
    # ``server._handle_extract_code_section`` (server.py ~309-334) into a
    # self-contained closure. The facade holds ``_read_tool`` directly so it
    # can be registered for G3 rebind.
    # ------------------------------------------------------------------
    _read_tool = ReadPartialTool(project_root)
    _analyze_tool = AnalyzeCodeStructureTool(project_root)

    # ------------------------------------------------------------------
    # Signatures bespoke route — lightweight method-directory (~25 % tokens)
    # ------------------------------------------------------------------
    async def _signatures_route(args: dict[str, Any]) -> Any:
        """Return signatures-format output for a file.

        Delegates to ``AnalyzeCodeStructureTool`` with ``format_type=signatures``
        so the full analysis pipeline (security, encoding, plugin dispatch) is
        preserved.  The tool already supports ``signatures`` after the patch to
        ``_format_table`` and ``_validate_format_type``.
        """
        if "file_path" not in args:
            raise ValueError("signatures action requires file_path")
        forward: dict[str, Any] = {
            "file_path": args["file_path"],
            "format_type": "signatures",
            "output_format": args.get("output_format", "toon"),
        }
        if "language" in args:
            forward["language"] = args["language"]
        return await _analyze_tool.execute(forward)

    async def _read_route(args: dict[str, Any]) -> Any:
        """F5 bespoke: single-vs-batch reshape for extract_code_section.

        Mirrors ``server._handle_extract_code_section``:
        - If ``requests`` is present → forward to ReadPartialTool verbatim
          (the tool's own batch dispatcher takes over).
        - Otherwise → build the 11-key ``full_args`` from flat single-file
          params and call the tool with that explicit dict.

        Args arrive with facade control keys already stripped by
        ``FacadeTool._clean_bespoke_args`` (i.e. ``action`` is gone).
        """
        if args.get("requests") is not None:
            # Batch mode — tool owns dispatching; forward as-is.
            return await _read_tool.execute(args)

        # Single-file mode — explicit reshape to 11-key full_args.
        if "file_path" not in args or "start_line" not in args:
            raise ValueError("read action requires file_path and start_line")

        # Coerce line/column bounds to int at the facade boundary. They arrive as
        # strings when an agent passes them as undeclared additionalProperties
        # (the flat facade schema does not type them), and the downstream
        # extract_code_section does ``str < int`` comparisons -> TypeError. This
        # made the documented single-file read escape hatch fail 100% of the time.
        def _as_int(value: Any) -> Any:
            if value is None or isinstance(value, bool):
                return value
            if isinstance(value, int):
                return value
            # A fractional JSON number (start_line=2.9) is a malformed bound, not
            # something to silently truncate — enforce the integer-only contract
            # (Codex P3 on #328). Integral floats (2.0) coerce cleanly.
            if isinstance(value, float):
                if value.is_integer():
                    return int(value)
                raise ValueError(
                    f"read action: line/column bounds must be integers, got {value!r}"
                )
            try:
                return int(str(value))  # base-10 integer strings only ("88")
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"read action: line/column bounds must be integers, got {value!r}"
                ) from exc

        full_args: dict[str, Any] = {
            "file_path": args["file_path"],
            "start_line": _as_int(args["start_line"]),
            "end_line": _as_int(args.get("end_line")),
            "start_column": _as_int(args.get("start_column")),
            "end_column": _as_int(args.get("end_column")),
            "format": args.get("format", "text"),
            "output_file": args.get("output_file"),
            "suppress_output": args.get("suppress_output", False),
            "output_format": args.get("output_format", "toon"),
            "allow_truncate": args.get("allow_truncate", False),
            "fail_fast": args.get("fail_fast", False),
        }
        return await _read_tool.execute(full_args)

    # ------------------------------------------------------------------
    # Build the facade
    # ------------------------------------------------------------------
    facade = FacadeTool(
        facade_name="structure",
        action_map={
            "outline": GetCodeOutlineTool(project_root),
            "analyze": _analyze_tool,
            "ast_path": CodeGraphASTPathTool(project_root),
            "sitemap": CodeGraphSitemapTool(project_root),
            "class_tree": ClassHierarchyTool(project_root),
            "class_detail": ClassInspectTool(project_root),
            "explore": CodeGraphExploreTool(project_root),
        },
        bespoke_map={
            "read": _read_route,  # F5: single/batch reshape via ReadPartialTool
            "signatures": _signatures_route,  # lightweight method-directory
        },
        description=_STRUCTURE_DESCRIPTION,
        annotations=_STRUCTURE_ANNOTATIONS,
        project_root=project_root,
    )

    # G3: register bespoke inners so set_project_path reaches them.
    # FacadeTool auto-rebinds action_map instances; bespoke inners need manual
    # registration.
    facade.register_bespoke_inner(_read_tool)
    facade.register_bespoke_inner(_analyze_tool)
    return facade
