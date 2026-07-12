"""TSA1ToolAdapter — Condition B of the tool-menu-size experiment.

Exposes only ``tsa_explore`` as the single MCP tool surface (1 tool vs 8 tools
in Condition A / ``TSAAdapter``).  This is the benchmark arm for the
Phase 1b research question:

  Does reducing MCP tool count from 8 to 1 improve agent task-completion
  and reduce tool mis-pick rate on TSA's 21-question benchmark?

Architecture
------------
* Index preparation reuses the same AST cache path as ``TSAAdapter`` (warm
  only — the index must already exist or be built via ``TSAAdapter``).
  Condition B does NOT define a cold-build arm; cache construction happens
  through the Condition A adapter.

* Allowed tools for Claude are restricted to ``tsa_explore`` + the
  infrastructure ``set_project_path`` entry.  File-system tools (Read,
  Grep, Glob) are included for parity with Condition A's baseline surface
  so that Claude can still verify citations; they count as their own metric
  category in ``parse_tool_metrics``.

* The ``tsa_explore`` prototype lives at:
  ``tree_sitter_analyzer/mcp/tsa_explore.py``
  It is NOT wired into the production MCP server.  A live pilot run requires
  either (a) wiring via an ``TSA_EXPOSE_ONLY`` env-var switch in server.py
  (Phase 2 Case B engineering) or (b) a standalone MCP server that registers
  only ``tsa_explore``.

See: benchmarks/codegraph_compare/TOOL-MENU-EXPERIMENT-FINDINGS.md
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import BenchmarkAdapter, IndexStats, RunConfig, ToolMetrics

# Re-use private helpers from the 8-tool adapter to avoid duplication.
# The leading-underscore names are module-internal by convention but fully
# importable — sharing them is intentional here (experiment infrastructure).
from .tree_sitter_analyzer import (
    _CACHE_DIR,
    _CACHE_INDEX,
    _build_cache,
    _delete_cache,
    _dir_size,
    _indexed_file_count,
    _load_prompt,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inline default system prompt (Condition B — 1-tool surface)
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """\
You are answering an architecture question about a software codebase.
tree-sitter-analyzer has been pre-run and its AST cache is available.

You have ONE tool for code intelligence: ``tsa_explore``.

``tsa_explore`` routes your natural-language query to the correct backend:
- Symbol search and navigation (entrypoint-tracing, call-chain questions)
- Structural analysis (module-boundary questions)
- Impact and dependency analysis (change-impact questions)
- Project-level overview (subsystem-overview questions)

How to use it:
- Pass your question or symbol name as the ``query`` parameter.
- Optionally supply ``task_type`` from:
    entrypoint-tracing | call-chain | module-boundary
    change-impact | subsystem-overview
- The tool returns results from the appropriate backend(s) automatically.

When answering:
- Call ``tsa_explore`` with the symbol or concept you want to investigate.
- Use ``task_type`` when the category is obvious from the question.
- Cite the specific file path and symbol name for every claim you make.
- Do not guess — only report what you find via the tool or in verified files.
- If ``tsa_explore`` returns no results, rephrase the query or try a shorter
  symbol name; do not fabricate an answer.
"""

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_FILE = _PROMPTS_DIR / "system_tsa_1tool.md"

# ---------------------------------------------------------------------------
# Allowed tools for Condition B
# ---------------------------------------------------------------------------
# tsa_explore is the single MCP tool.  set_project_path is the infrastructure
# entry (mutates server-level analysis_engine / rebind loop — not a content
# tool).  File-system tools are included at the same level as Condition A for
# citation verification; they count separately in parse_tool_metrics.

_ALLOWED_TOOLS = [
    "Read",
    "Bash(grep *)",
    "Bash(find *)",
    "Bash(ls *)",
    "Glob",
    "Grep",
    "mcp__tree-sitter-analyzer__tsa_explore",
    "mcp__tree-sitter-analyzer__set_project_path",
]

# ---------------------------------------------------------------------------
# Metric classification patterns
# ---------------------------------------------------------------------------

_FILE_READ_TOOLS = frozenset({"read"})
_SEARCH_TOOLS = frozenset({"grep", "glob", "bash"})
# tsa_explore calls count as index_queries (mirrors the 8-tool adapter's
# mcp__tree-sitter-analyzer__* → index_queries mapping).
_TSA_EXPLORE_TOOL_LOWER = "mcp__tree-sitter-analyzer__tsa_explore"
_TSA_MCP_PREFIX = "mcp__tree-sitter-analyzer__"


class TSA1ToolAdapter(BenchmarkAdapter):
    """Benchmark arm: tree-sitter-analyzer AST cache via single ``tsa_explore`` tool."""

    def __init__(self, arm_id: str = "tsa-1tool-warm") -> None:
        if arm_id != "tsa-1tool-warm":
            raise ValueError(
                f"arm_id must be 'tsa-1tool-warm', got {arm_id!r}.  "
                "Condition B only supports warm mode (cold build is handled by TSAAdapter)."
            )
        self.arm_id = arm_id

    # ------------------------------------------------------------------
    # Index preparation
    # ------------------------------------------------------------------

    def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
        """Build or verify the TSA AST cache under *repo_path/.ast-cache/*.

        Condition B always uses the warm path — the same AST cache as
        Condition A (``TSAAdapter``).  A cold build is performed only if the
        index is absent or empty, matching the warm-path semantics.

        Args:
            repo_path: Absolute path to the repository root.
            cold: Accepted for interface compatibility; always treated as warm
                  (Condition B has no separate cold arm).

        Returns:
            IndexStats with measured build time and cache size.
        """
        if cold:
            logger.warning(
                "TSA1ToolAdapter: cold=True received but Condition B is warm-only; "
                "running warm path.  Use TSAAdapter for cold builds."
            )

        cache_dir = repo_path / _CACHE_DIR
        index_db = repo_path / _CACHE_INDEX

        if not index_db.exists():
            logger.info("TSA1ToolAdapter: index.db not found at %s; building.", index_db)
            return _build_cache(repo_path, cache_dir)

        indexed_files = _indexed_file_count(index_db)
        if indexed_files is None:
            logger.info("TSA1ToolAdapter: index.db at %s is unreadable; rebuilding.", index_db)
            _delete_cache(cache_dir)
            return _build_cache(repo_path, cache_dir)
        if indexed_files <= 0:
            logger.info("TSA1ToolAdapter: index.db at %s is empty; rebuilding.", index_db)
            return _build_cache(repo_path, cache_dir)

        logger.info(
            "TSA1ToolAdapter: index.db exists at %s with %d indexed files; warm path.",
            index_db,
            indexed_files,
        )
        size = _dir_size(cache_dir)
        return IndexStats(
            build_seconds=0.0, index_size_bytes=size, file_count=indexed_files
        )

    # ------------------------------------------------------------------
    # Run configuration
    # ------------------------------------------------------------------

    def build_run_config(self, repo_path: Path, question_prompt: str) -> RunConfig:
        """Return a RunConfig that exposes only ``tsa_explore`` as the index tool."""
        system_prompt = _load_prompt(_PROMPT_FILE, _DEFAULT_SYSTEM_PROMPT)
        extra_context = (
            "The tree-sitter-analyzer (TSA) MCP server is connected with ONE tool: "
            "``tsa_explore``.  Use it with a natural-language ``query`` and an "
            "optional ``task_type`` hint.  The tool routes internally to the correct "
            "backend (nav / search / structure / health) and returns combined results. "
            f"The AST index is pre-built at {repo_path}/.ast-cache/ (warm)."
        )

        return RunConfig(
            arm_id=self.arm_id,
            repo_path=repo_path,
            system_prompt=system_prompt,
            allowed_tools=list(_ALLOWED_TOOLS),
            forbidden_tools=[],
            extra_context=extra_context,
        )

    # ------------------------------------------------------------------
    # Transcript parsing
    # ------------------------------------------------------------------

    def parse_tool_metrics(self, transcript_text: str) -> ToolMetrics:
        """Count tool invocations from raw transcript text.

        ``mcp__tree-sitter-analyzer__tsa_explore`` calls count as
        ``index_queries``.  ``Read`` counts as ``file_reads``.
        ``Bash``/``Grep``/``Glob`` count as ``search_calls``.
        Mirrors the 8-tool adapter's parsing for a fair comparison.
        """
        tool_calls = 0
        file_reads = 0
        search_calls = 0
        index_queries = 0

        def classify(name: str) -> None:
            nonlocal tool_calls, file_reads, search_calls, index_queries
            tool_calls += 1
            if _TSA_MCP_PREFIX in name:
                index_queries += 1
            elif name in _FILE_READ_TOOLS:
                file_reads += 1
            elif name in _SEARCH_TOOLS:
                search_calls += 1

        for match in re.finditer(r"Tool:\s*(\S+)", transcript_text, re.IGNORECASE):
            classify(match.group(1).lower().rstrip("()"))

        for match in re.finditer(r"\[([\w-]+)\]", transcript_text):
            name = match.group(1).lower()
            line_start = transcript_text.rfind("\n", 0, match.start()) + 1
            line_text = transcript_text[line_start : match.end()]
            if "Tool:" in line_text or "tool:" in line_text:
                continue
            classify(name)

        return ToolMetrics(
            tool_calls=tool_calls,
            file_reads=file_reads,
            search_calls=search_calls,
            index_queries=index_queries,
        )
