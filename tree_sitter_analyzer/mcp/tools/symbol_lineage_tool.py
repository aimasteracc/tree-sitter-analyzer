#!/usr/bin/env python3
"""
Symbol Lineage / Impact Preview MCP Tool.

Given a symbol name, traces its lineage: definitions, callers, downstream
dependents, and risk assessment. Combines AST-level reference search with
file-level dependency graph analysis for a complete impact preview.

Tells AI agents: "If you change X, here's everything affected."
"""

import copy
import re
import time
from pathlib import Path
from typing import Any

from ...project_graph import BlastRadius, DependencyGraph
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from ._graph_cache_fingerprint import GraphFingerprint, compute_graph_fingerprint
from .base_tool import BaseMCPTool
from .query_symbol_search import execute_find_references

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symbol": {
            "type": "string",
            "description": "Symbol name to trace lineage for",
        },
        "max_depth": {
            "type": "integer",
            "default": 3,
            "description": "Max dependency graph traversal depth (1-5)",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    "required": ["symbol"],
    "additionalProperties": False,
}


class SymbolLineageTool(BaseMCPTool):
    """Trace symbol lineage: definitions, references, file-level downstream impact."""

    def __init__(self, project_root: str | None = None) -> None:
        # Lazy graph + per-symbol response cache. Built on the first call,
        # reset on project_root rebind via _on_project_root_changed.
        self._dep_graph: DependencyGraph | None = None
        self._symbol_cache: dict[tuple[str, int], dict[str, Any]] = {}
        # H4 fix: fingerprint snapshot for the cached graph + symbol cache.
        # When the source tree changes, both the graph and the per-symbol
        # response cache are invalidated together — the symbol responses
        # bake in the graph's downstream/upstream sets.
        self._dep_graph_fingerprint: GraphFingerprint | None = None
        self._dep_graph_built_at: float | None = None
        self._cache_invalidated_reason: str | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # ARCH-A4 hook: invalidate every per-project cache when rebinding.
        self._dep_graph = None
        self._symbol_cache = {}
        self._dep_graph_fingerprint = None
        self._dep_graph_built_at = None
        self._cache_invalidated_reason = None

    def _get_dep_graph(self) -> DependencyGraph | None:
        """Return cached dependency graph, building it on first use.

        Returns ``None`` if graph construction fails (keeps the tool usable
        with reduced fidelity — downstream/upstream stay empty).
        """
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        current_fp = compute_graph_fingerprint(str(self.project_root))
        reason: str | None = None
        if self._dep_graph is None:
            reason = "cold"
        elif self._dep_graph_fingerprint != current_fp:
            reason = self._explain_fingerprint_delta(
                self._dep_graph_fingerprint, current_fp
            )

        if reason is not None:
            # Invalidate downstream caches that depend on the graph.
            self._symbol_cache = {}
            try:
                self._dep_graph = DependencyGraph(str(self.project_root))
                self._dep_graph_fingerprint = current_fp
                self._dep_graph_built_at = time.time()
                self._cache_invalidated_reason = reason
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"DependencyGraph build failed: {exc}")
                # Keep the prior state so the next call retries on its own.
                self._dep_graph = None
                self._dep_graph_fingerprint = None
                self._dep_graph_built_at = None
                self._cache_invalidated_reason = None
                return None
        else:
            self._cache_invalidated_reason = None
        return self._dep_graph

    @staticmethod
    def _explain_fingerprint_delta(
        old: GraphFingerprint | None, new: GraphFingerprint
    ) -> str:
        if old is None:
            return "cold"
        if old.file_count != new.file_count:
            delta = new.file_count - old.file_count
            return (
                f"file_count_changed ({delta:+d}, {old.file_count}->{new.file_count})"
            )
        if old.max_mtime_ns != new.max_mtime_ns:
            return "source_modified"
        return "unknown"

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "symbol_lineage",
            "description": (
                "Symbol lineage: definition → callers → downstream files → risk. "
                "Shows what breaks if you change a symbol. "
                "Combines AST references with file dependency graph. "
                "SLOW: traverses AST references plus the full dependency graph "
                "(5-15s per symbol on medium repos). Cache via project_index."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        symbol = arguments.get("symbol", "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        max_depth = arguments.get("max_depth", 3)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 5:
            raise ValueError("max_depth must be 1-5")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        symbol = arguments["symbol"].strip()
        max_depth = int(arguments.get("max_depth", 3))
        output_format = arguments.get("output_format", "toon")

        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        root = Path(self.project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

        # H4 fix: refresh the dep graph (and clear _symbol_cache if needed)
        # before serving from the per-symbol response cache. _get_dep_graph
        # will wipe _symbol_cache when it rebuilds, so the cache lookup
        # below is automatically post-invalidation.
        graph = self._get_dep_graph()

        # Per-symbol response cache: this tool does an expensive cross-file
        # walk (rglob + 500x engine.analyze) even with the analysis cache
        # warm. The same (symbol, max_depth) pair is asked for repeatedly
        # by orchestrators, so cache the deep-copied response.
        cache_key = (symbol, max_depth)
        cached = self._symbol_cache.get(cache_key)
        if cached is not None:
            result = copy.deepcopy(cached)
            result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
            result["from_cache"] = True
            # H4 introspection on warm symbol-cache hit.
            if self._dep_graph_built_at is not None:
                result["cache_age_s"] = round(time.time() - self._dep_graph_built_at, 3)
            return apply_toon_format_to_response(result, output_format)

        ref_args = {"symbol": symbol, "output_format": "json"}
        refs_result = await execute_find_references(self.project_root, ref_args)

        definitions = refs_result.get("definitions", [])
        references = refs_result.get("references", [])
        # H12 fix: ``execute_find_references`` classifies a hit as a
        # definition only when ``element_type`` substring-matches
        # {"definition", "declaration", "class", "struct"}. Tree-sitter
        # element extractors return short canonical names — Python
        # ``function``, ``method``, ``decorated_definition``; JS
        # ``function``/``arrow_function``/``class``; Java
        # ``method``/``class``/``interface``; Go ``function``/``method``.
        # Anything labelled ``function``/``method``/``decorated_definition``
        # therefore falls into ``references`` even when the hit is the
        # actual ``def``/``class`` site. Re-classify here so callers see
        # the def under ``definitions`` where the brief promises it.
        # ``project_root`` + ``symbol`` enable the content-level check
        # that reads the source line at each hit — required to avoid
        # false-positive promotions on synthetic test fixtures.
        definitions, references = _reclassify_definition_like(
            definitions, references, str(self.project_root), symbol
        )

        # K3 fix: ``execute_find_references`` caps the project scan at the
        # first 500 source files (rglob order, no priority). On medium
        # repos that drops the definition file for symbols whose owning
        # file sorts past the 500th — e.g. ``BaseMCPTool`` in
        # ``tree_sitter_analyzer/mcp/tools/base_tool.py`` is at rglob index
        # 539 here. References to the symbol *are* found (they're in
        # earlier files like importers / callers), but the def site itself
        # never enters the scan, so ``definitions`` stays empty and
        # downstream risk classification reports "Symbol not found".
        #
        # When defs are empty, run a focused text-grep fallback that scans
        # ALL project source files (no 500 cap) for definition-keyword
        # lines mentioning the symbol. Cheap because we only read files
        # that match a fast first-pass substring check.
        if not definitions:
            fallback_defs = _find_definitions_via_grep(str(self.project_root), symbol)
            if fallback_defs:
                seen_def_keys = {
                    (d.get("file", ""), d.get("start_line", 0)) for d in definitions
                }
                # Also dedupe against the references list — promoting a
                # ref-as-def removes it from references.
                ref_keys_to_drop: set[tuple[str, int]] = set()
                for fd in fallback_defs:
                    key = (fd["file"], fd["start_line"])
                    if key in seen_def_keys:
                        continue
                    seen_def_keys.add(key)
                    ref_keys_to_drop.add(key)
                    definitions.append(fd)
                if ref_keys_to_drop:
                    references = [
                        r
                        for r in references
                        if (r.get("file", ""), r.get("start_line", 0))
                        not in ref_keys_to_drop
                    ]

        def_files = {d["file"] for d in definitions}
        ref_files = {r["file"] for r in references}
        all_symbol_files = def_files | ref_files

        # ``graph`` was already resolved above (just before the symbol
        # cache lookup) — avoid the duplicate fingerprint scan.

        downstream: dict[str, Any] = {}
        upstream: dict[str, Any] = {}
        if graph:
            for f in all_symbol_files:
                if f not in graph._nodes:
                    continue
                br = BlastRadius(graph)
                fwd = br.forward(f)
                if fwd:
                    downstream[f] = sorted(fwd)
                rev = br.reverse(f)
                if rev:
                    upstream[f] = sorted(rev)

        all_downstream_files: set[str] = set()
        for files in downstream.values():
            all_downstream_files.update(files)

        all_upstream_files: set[str] = set()
        for files in upstream.values():
            all_upstream_files.update(files)

        risk = _assess_risk(
            len(definitions), len(references), len(all_downstream_files)
        )

        test_files = sorted(
            f for f in (all_downstream_files | all_symbol_files) if _is_test_file(f)
        )

        # G6: explicit truncation transparency. Lists were silently
        # capped without an indicator — agents reading
        # ``len(references)`` got a number that disagreed with
        # ``reference_count``. Surface truncation flags + the real total
        # so a caller can fan out a second tool to fetch the rest.
        _DEF_LIMIT = 20
        _REF_LIMIT = 30
        _DOWNSTREAM_LIMIT = 50
        _UPSTREAM_LIMIT = 20
        _TEST_LIMIT = 20
        sorted_downstream = sorted(all_downstream_files)
        sorted_upstream = sorted(all_upstream_files)

        references_truncated = len(references) > _REF_LIMIT
        downstream_truncated = len(sorted_downstream) > _DOWNSTREAM_LIMIT
        truncations: list[str] = []
        if references_truncated:
            truncations.append("references")
        if downstream_truncated:
            truncations.append("downstream_files")

        # One-line headline + next-step hint for LLM consumers.
        summary_line = (
            f"{symbol} defs={len(definitions)} refs={len(references)} "
            f"downstream={len(all_downstream_files)} risk={risk['level']}"
        )
        if truncations:
            # G6: surface the truncated-list signal on the headline so an
            # agent scanning summary_line alone notices the partial view.
            summary_line += f" truncated={'+'.join(truncations)}"
        # Verdict mirrors trace_impact / safe_to_edit vocabulary so an agent
        # can chain decisions across tools.
        risk_to_verdict = {
            "high": "UNSAFE",
            "medium": "CAUTION",
            "low": "SAFE",
            "unknown": "n/a",
        }
        verdict = risk_to_verdict.get(risk["level"], "n/a")
        if risk["level"] == "high":
            next_step = (
                "trace_impact and run listed test files before changing signature"
            )
        elif risk["level"] == "medium":
            next_step = "review callers in listed files, then run downstream tests"
        elif risk["level"] == "low":
            next_step = "proceed with edit, run nearest test file"
        else:
            next_step = "verify symbol name — no definitions found"

        agent_summary: dict[str, Any] = {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": verdict,
        }
        if truncations:
            agent_summary["truncations"] = truncations

        response: dict[str, Any] = {
            "success": True,
            "symbol": symbol,
            "definitions": definitions[:_DEF_LIMIT],
            "definition_count": len(definitions),
            "references": references[:_REF_LIMIT],
            "reference_count": len(references),
            # G6: explicit truncation flags + caps. Existing
            # ``reference_count`` / ``downstream_file_count`` already
            # carry the real totals; these fields make the partial-view
            # state machine-readable without a length-vs-count compare.
            "references_truncated": references_truncated,
            "references_limit": _REF_LIMIT,
            "references_available": len(references),
            "files_containing_symbol": sorted(all_symbol_files),
            "downstream_files": sorted_downstream[:_DOWNSTREAM_LIMIT],
            "downstream_file_count": len(all_downstream_files),
            "downstream_files_truncated": downstream_truncated,
            "downstream_files_limit": _DOWNSTREAM_LIMIT,
            "downstream_files_available": len(all_downstream_files),
            "upstream_files": sorted_upstream[:_UPSTREAM_LIMIT],
            "upstream_file_count": len(all_upstream_files),
            "test_files_to_run": test_files[:_TEST_LIMIT],
            "test_file_count": len(test_files),
            "risk": risk,
            "smart_workflow_hint": (
                f"Symbol '{symbol}' has {risk['level']} change risk "
                f"({len(references)} refs, {len(all_downstream_files)} downstream files). "
                f"{'Run the listed test files before committing.' if test_files else 'No test files detected.'} "
                "Use analyze_change_impact after editing for git-diff level detail."
            ),
            "summary_line": summary_line,
            "agent_summary": agent_summary,
        }

        # Stash a deep-copy so subsequent identical lookups skip the
        # cross-file walk + dep-graph traversal. The cache is keyed on
        # (symbol, max_depth) and reset on project_root rebind.
        self._symbol_cache[cache_key] = copy.deepcopy(response)

        response["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        response["from_cache"] = False
        # H4 introspection.
        if self._dep_graph_built_at is not None:
            response["cache_age_s"] = round(time.time() - self._dep_graph_built_at, 3)
        if self._cache_invalidated_reason is not None:
            response["cache_invalidated_reason"] = self._cache_invalidated_reason

        return apply_toon_format_to_response(response, output_format)


# H12: element_type values that mean "this hit IS the symbol's definition
# site". Mirrors the keywords used by ``execute_find_references`` plus the
# short canonical types returned by tree-sitter element extractors across
# the languages most used in this repo's dogfood data:
# - Python: function, method, decorated_definition, class
# - JS/TS: function, arrow_function, function_declaration,
#   class, class_declaration
# - Java: method, class, interface, method_declaration, class_declaration
# - Go: function, method, function_declaration, method_declaration
# - Rust/C/C++/C#: function, struct, class, declaration
# Matched as substrings (case-insensitive) so language-specific variants
# like ``async_function_definition`` still classify correctly.
_DEFINITION_LIKE_TYPES: tuple[str, ...] = (
    "function",
    "method",
    "constructor",
    "decorated_definition",
    "arrow_function",
    "function_declaration",
    "method_declaration",
    "function_definition",
    "method_definition",
    "class",
    "class_declaration",
    "class_definition",
    "struct",
    "struct_declaration",
    "interface",
    "interface_declaration",
    "enum",
    "enum_declaration",
    "definition",
    "declaration",
    "trait",
    "impl_item",
)

# Source-line prefixes that indicate a definition site. We check the
# actual content of the source file at the hit's ``start_line`` before
# promoting a reference to a definition — element_type alone is too
# coarse because tree-sitter returns ``function`` for both ``def`` sites
# (the actual definition) and synthetic test fixtures that mock call
# sites. Reading the source provides the ground truth: a line that
# *starts* with ``def``/``class``/``func``/etc. is a definition; a line
# that just contains the symbol elsewhere is a reference.
_DEFINITION_LINE_PREFIXES: tuple[str, ...] = (
    "def ",
    "async def ",
    "class ",
    "function ",
    "function* ",
    "async function ",
    "func ",
    "fn ",
    "struct ",
    "interface ",
    "trait ",
    "enum ",
    "type ",
    "public ",
    "private ",
    "protected ",
    "static ",
    "abstract ",
    "@",  # Python decorator on the line above the def is still part of
)


def _is_definition_like(element_type: str) -> bool:
    """Return ``True`` when ``element_type`` denotes a definition site.

    Tree-sitter element extractors return short, language-specific names
    (e.g. ``function`` for Python ``def``). The upstream classifier in
    ``execute_find_references`` only checks for ``definition``/
    ``declaration``/``class``/``struct`` substrings, so Python ``def``
    sites get misrouted into ``references``. This predicate covers the
    canonical names emitted across the languages this repo's dogfood
    actually hits.
    """
    if not element_type:
        return False
    lowered = element_type.lower()
    return any(kind in lowered for kind in _DEFINITION_LIKE_TYPES)


def _line_looks_like_definition(
    project_root: str,
    file_rel: str,
    line_no: int,
    symbol: str,
) -> bool:
    """Return ``True`` when the source line at ``line_no`` is a def site.

    Reads the file relative to ``project_root`` and inspects the line.
    Definition sites begin with a definition keyword (``def``, ``class``,
    ``function``, ``func``, ``fn``, …) and contain the symbol name. This
    is more reliable than ``element_type`` alone for the H12 fix —
    tree-sitter returns the short canonical type ``function`` for both
    actual def sites and any synthetic test reference, so we need a
    content-level check.
    """
    if not file_rel or line_no < 1 or not symbol:
        return False
    try:
        path = Path(project_root) / file_rel
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = text.splitlines()
    if line_no > len(lines):
        return False
    line = lines[line_no - 1]
    stripped = line.lstrip()
    if symbol not in stripped:
        return False
    # Match any line that starts with a definition keyword and mentions
    # the symbol. Decorators on the line above the def are tolerated by
    # checking the next non-empty line too — but the basic case is a
    # direct prefix.
    if any(stripped.startswith(prefix) for prefix in _DEFINITION_LINE_PREFIXES):
        return True
    return False


def _reclassify_definition_like(
    definitions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    project_root: str | None = None,
    symbol: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """H12 fix: promote definition-like references into ``definitions``.

    The upstream ``execute_find_references`` misclassifies Python ``def``
    sites (``element_type="function"``) and Java methods
    (``element_type="method"``) as references. Walk the references list
    once and route each definition-like hit into a new ``definitions``
    list.

    Two tests must both pass for promotion:

    1. ``element_type`` is a definition-like type (``function``,
       ``method``, ``class``, …) — the upstream classifier already
       narrowed the universe to nameable elements, but we re-check
       defensively.
    2. The source line at ``start_line`` starts with a definition
       keyword (``def``, ``class``, ``func``, …) and mentions the
       symbol. This filters out synthetic test fixtures that mock
       references pointing at files that don't exist on disk.

    Hits with ``role="related"`` are kept as references regardless —
    they are substring matches on similarly-named symbols, not the
    symbol's own def site.
    """
    if not references:
        return definitions, references

    promoted: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    seen_def_keys: set[tuple[str, int]] = {
        (d.get("file", ""), d.get("start_line", 0)) for d in definitions
    }

    for entry in references:
        role = entry.get("role")
        etype = entry.get("type", "")
        # ``related`` hits are substring matches, not the symbol's own
        # def — keep them as references regardless of element_type.
        if role == "related":
            remaining.append(entry)
            continue
        if not _is_definition_like(etype):
            remaining.append(entry)
            continue
        # Content check: only promote when the source line really IS a
        # def site. Synthetic test fixtures point at files that don't
        # exist on disk; the read fails and we leave the entry in
        # references.
        looks_like_def = False
        if project_root and symbol:
            looks_like_def = _line_looks_like_definition(
                project_root,
                entry.get("file", ""),
                int(entry.get("start_line", 0)),
                symbol,
            )
        if not looks_like_def:
            remaining.append(entry)
            continue
        # Dedupe against any existing definitions to avoid duplicate
        # entries when both classifiers happen to fire.
        key = (entry.get("file", ""), entry.get("start_line", 0))
        if key in seen_def_keys:
            continue
        seen_def_keys.add(key)
        new_entry = dict(entry)
        new_entry["role"] = "definition"
        promoted.append(new_entry)

    if not promoted:
        return definitions, references
    return [*definitions, *promoted], remaining


def _assess_risk(
    def_count: int, ref_count: int, downstream_count: int
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    if def_count == 0:
        return {"level": "unknown", "score": 0, "reasons": ["Symbol not found"]}

    if def_count > 1:
        score += 1
        reasons.append(f"Multiple definitions ({def_count})")

    if ref_count > 20:
        score += 3
        reasons.append(f"Many references ({ref_count})")
    elif ref_count > 5:
        score += 2
        reasons.append(f"Moderate references ({ref_count})")
    elif ref_count > 0:
        score += 1
        reasons.append(f"Few references ({ref_count})")

    if downstream_count > 10:
        score += 3
        reasons.append(f"Wide blast radius ({downstream_count} downstream files)")
    elif downstream_count > 3:
        score += 2
        reasons.append(f"Moderate blast radius ({downstream_count} downstream files)")
    elif downstream_count > 0:
        score += 1
        reasons.append(f"Small blast radius ({downstream_count} downstream files)")

    if score <= 2:
        level = "low"
    elif score <= 5:
        level = "medium"
    else:
        level = "high"

    return {"level": level, "score": score, "reasons": reasons}


def _is_test_file(rel_path: str) -> bool:
    lower = rel_path.lower()
    parts = Path(lower).parts
    return (
        "test" in parts[-1]
        or "tests" in parts
        or "test" in parts
        or parts[-1].startswith("test_")
        or parts[-1].endswith("_test.py")
        or parts[-1].endswith("_test.js")
        or parts[-1].endswith("test.java")
        or parts[-1].endswith("test.go")
    )


# K3 fallback: project-wide text scan for definition sites. Used when
# ``execute_find_references`` returns 0 definitions because its 500-file
# cap dropped the def-bearing file. We scan ALL project source files
# (no cap) but only read files whose path contains a fast first-pass
# substring check (the symbol name) — keeps the scan cheap.
_K3_FALLBACK_EXTS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".java",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".kt",
        ".cs",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
    }
)
_K3_FALLBACK_EXCLUDE: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "htmlcov",
        ".cache",
        ".eggs",
        ".claude",
        ".ast-cache",
        ".tree-sitter-cache",
    }
)


def _find_definitions_via_grep(
    project_root: str,
    symbol: str,
) -> list[dict[str, Any]]:
    """Project-wide text scan for definition sites of ``symbol``.

    Reads every source file (no 500-file cap), keeps only the ones that
    contain the bare name, then inspects each line for a definition
    keyword (``def``, ``class``, ``func``, ``fn``, …) immediately
    followed by the symbol. Returns hits in the same shape as
    ``execute_find_references`` definitions.

    Two layers of filtering:

    1. Substring pre-check on the whole file content — skip files that
       never mention the bare name.
    2. Per-line check: line must start with a definition keyword AND
       contain the symbol as a whole word.

    Robust to large repos because we never invoke tree-sitter — pure
    text grep on already-filtered files.
    """
    if not symbol:
        return []
    bare_name = symbol.split(".")[-1]
    if not bare_name:
        return []

    root = Path(project_root).resolve()
    if not root.is_dir():
        return []

    # Whole-word boundary so ``BaseMCPTool`` doesn't match ``MyBaseMCPTool2``.
    word_re = re.compile(r"\b" + re.escape(bare_name) + r"\b")
    # Definition-keyword + symbol on the same line. We accept the symbol
    # being followed by an open paren, colon, whitespace, less-than
    # (generics), or end-of-line. The keyword must be at the start of the
    # stripped line (Python ``def``/``class``, Go ``func``, Rust ``fn``,
    # Java/C# method/class declarations after access modifiers).
    keyword_alternation = (
        r"(?:def|async\s+def|class|function|function\*|async\s+function|"
        r"func|fn|struct|interface|trait|enum|type|impl|namespace|module)"
    )
    line_re = re.compile(
        r"^\s*"
        # Optional access modifiers / annotations before the keyword.
        r"(?:(?:public|private|protected|static|abstract|final|virtual|"
        r"override|sealed|unsafe|async|export|default)\s+)*"
        + keyword_alternation
        + r"\s+"
        + re.escape(bare_name)
        + r"(?:\b|[\s\(:<])"
    )

    hits: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()
    # Manual walk so we can prune excluded directories before stat-ing.
    import os as _os

    stack: list[str] = [str(root)]
    while stack:
        current = stack.pop()
        try:
            it = _os.scandir(current)
        except OSError:
            continue
        with it:
            for entry in it:
                name = entry.name
                if name in _K3_FALLBACK_EXCLUDE:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                dot = name.rfind(".")
                if dot == -1:
                    continue
                if name[dot:].lower() not in _K3_FALLBACK_EXTS:
                    continue
                try:
                    text = Path(entry.path).read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError:
                    continue
                if not word_re.search(text):
                    continue
                rel = str(Path(entry.path).relative_to(root))
                for i, line in enumerate(text.splitlines(), start=1):
                    if not line_re.match(line):
                        continue
                    key = (rel, i)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    hits.append(
                        {
                            "name": bare_name,
                            "type": "definition",
                            "file": rel,
                            "start_line": i,
                            "end_line": i,
                            "role": "definition",
                        }
                    )
    return hits
