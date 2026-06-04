"""TSAAdapter — benchmark arm backed by tree-sitter-analyzer's AST cache.

Supports two modes:
  - ``arm_id="tsa-cold"``: deletes .ast-cache/ and triggers a fresh index build.
  - ``arm_id="tsa-warm"``: verifies .ast-cache/index.db is populated;
    rebuilds if absent or empty.

The index is populated by running tree-sitter-analyzer from this checkout via
``uv run --project <analyzer-root> ... --project-root <repo_path>``, which parses
the target source tree and populates the target repo's SQLite cache.
Errors are logged, not raised, so the harness can continue with partial data.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from . import BenchmarkAdapter, IndexStats, RunConfig, ToolMetrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inline default system prompt
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """\
You are answering an architecture question about a software codebase.
tree-sitter-analyzer has been pre-run and its AST cache is available.

You may run ``python -m tree_sitter_analyzer <subcommand> --format json``
via Bash to query the AST cache. Treat TSA output as already-read evidence.

When answering:
- Start with one codegraph-query answer pack for the relevant symbol or concept.
- Do not use raw grep/find/rg/read for discovery; TSA is the index.
- Use at most one narrow raw file read only if TSA output misses a required
  detail, and explain the miss.
- Cite the specific file path and symbol name for every claim you make.
- Do not guess — only report what you find via the tool or in the files.
- If a subcommand returns no results, say so and try an alternative query
  or subcommand; do not fabricate an answer.
- Keep Bash calls focused: pass --path or --file flags to narrow scope.
"""

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_FILE = _PROMPTS_DIR / "system_tsa.md"
_ANALYZER_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# AST cache paths
# ---------------------------------------------------------------------------

_CACHE_DIR = ".ast-cache"
_CACHE_INDEX = ".ast-cache/index.db"

# Tools Claude is allowed in this arm (TSA via its MCP facade tools)
_ALLOWED_TOOLS = [
    "Read",
    "Bash(grep *)",
    "Bash(find *)",
    "Bash(ls *)",
    "Glob",
    "Grep",
    "mcp__tree-sitter-analyzer__nav",
    "mcp__tree-sitter-analyzer__search",
    "mcp__tree-sitter-analyzer__structure",
    "mcp__tree-sitter-analyzer__health",
    "mcp__tree-sitter-analyzer__index",
    "mcp__tree-sitter-analyzer__project",
]

# Patterns used for parse_tool_metrics
_FILE_READ_TOOLS = frozenset({"read"})
_SEARCH_TOOLS = frozenset({"grep", "glob", "bash"})
# MCP tool calls to the TSA server count as index queries
_TSA_MCP_PREFIX = "mcp__tree-sitter-analyzer__"


class TSAAdapter(BenchmarkAdapter):
    """Benchmark arm: tree-sitter-analyzer AST cache available via Bash."""

    def __init__(self, arm_id: str = "tsa-warm") -> None:
        if arm_id not in ("tsa-cold", "tsa-warm"):
            raise ValueError(f"arm_id must be 'tsa-cold' or 'tsa-warm', got {arm_id!r}")
        self.arm_id = arm_id

    # ------------------------------------------------------------------
    # Index preparation
    # ------------------------------------------------------------------

    def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
        """Build or verify the TSA AST cache under *repo_path/.ast-cache/*.

        Args:
            repo_path: Absolute path to the repository root.
            cold: When True, always delete and rebuild the cache.
                  When False (warm), skip if index.db already exists.

        Returns:
            IndexStats with measured build time and cache size.
        """
        cache_dir = repo_path / _CACHE_DIR
        index_db = repo_path / _CACHE_INDEX

        if cold:
            _delete_cache(cache_dir)
            return _build_cache(repo_path, cache_dir)

        # Warm path — rebuild unless the SQLite cache is both present and
        # populated. A zero-row DB is worse than no DB: prompts tell the
        # agent "TSA is warm", but every CodeGraph query returns
        # "cache empty" and the run silently falls back to raw search/read.
        if not index_db.exists():
            logger.info("TSA index.db not found at %s; running cold build.", index_db)
            return _build_cache(repo_path, cache_dir)
        indexed_files = _indexed_file_count(index_db)
        if indexed_files is None:
            logger.info("TSA index.db at %s is unreadable; rebuilding.", index_db)
            _delete_cache(cache_dir)
            return _build_cache(repo_path, cache_dir)
        if indexed_files <= 0:
            logger.info("TSA index.db at %s is empty; rebuilding.", index_db)
            return _build_cache(repo_path, cache_dir)

        logger.info(
            "TSA index.db exists at %s with %d indexed files; warm path — skipping build.",
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
        system_prompt = _load_prompt(_PROMPT_FILE, _DEFAULT_SYSTEM_PROMPT)
        extra_context = (
            "The tree-sitter-analyzer (TSA) MCP server is connected. Use its "
            "facade tools: mcp__tree-sitter-analyzer__nav / search / structure / "
            "index. Call `nav` with action=context and query='<concept>' FIRST — "
            "one call returns entry points + definition + callers + callees + "
            "inline source. Use `nav` action=callee_tree for a full call tree in "
            "one call. Stop after 1-3 calls; do not loop per symbol. The AST "
            f"index is pre-built at {repo_path}/.ast-cache/ (warm)."
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

        mcp__tree-sitter-analyzer__* tool calls count as index_queries.
        Read counts as file_reads. Bash/Grep/Glob count as search_calls.
        Mirrors the CodeGraph adapter's MCP-arm parsing for a fair comparison.
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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _delete_cache(cache_dir: Path) -> None:
    """Remove the AST cache directory if it exists."""
    if cache_dir.exists():
        logger.info("Deleting existing TSA cache at %s (cold build).", cache_dir)
        try:
            shutil.rmtree(cache_dir)
        except OSError as exc:
            logger.error("Failed to delete %s: %s", cache_dir, exc)


def _build_cache(repo_path: Path, cache_dir: Path) -> IndexStats:
    """Run tree-sitter-analyzer's AST-cache indexer for the target repo."""
    logger.info("Building TSA AST cache in %s ...", repo_path)
    t0 = time.perf_counter()

    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(_ANALYZER_ROOT),
            "python",
            "-m",
            "tree_sitter_analyzer",
            "--ast-cache",
            "--ast-cache-mode",
            "index",
            "--project-root",
            str(repo_path),
            "--format",
            "json",
            "--quiet",
        ],
        cwd=_ANALYZER_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        logger.error(
            "tree_sitter_analyzer exited with code %d.\nstderr: %s",
            result.returncode,
            result.stderr[:2000],
        )

    size = _dir_size(cache_dir) if cache_dir.exists() else 0
    index_db = cache_dir / "index.db"
    file_count = _indexed_file_count(index_db) or (
        _count_files(cache_dir) if cache_dir.exists() else 0
    )

    logger.info(
        "TSA cache built in %.2fs, size=%d bytes, files=%d",
        elapsed,
        size,
        file_count,
    )
    return IndexStats(
        build_seconds=elapsed,
        index_size_bytes=size,
        file_count=file_count,
    )


def _dir_size(path: Path) -> int:
    """Return the total byte size of all files under *path*."""
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _count_files(path: Path) -> int:
    """Return the number of files under *path*."""
    if not path.exists():
        return 0
    return sum(1 for f in path.rglob("*") if f.is_file())


def _indexed_file_count(index_db: Path) -> int | None:
    """Return ast_index row count, or None for unreadable/corrupt DBs."""
    try:
        conn = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return int(row[0]) if row else None


def _load_prompt(prompt_file: Path, default: str) -> str:
    if prompt_file.is_file():
        return prompt_file.read_text(encoding="utf-8").strip()
    return default
