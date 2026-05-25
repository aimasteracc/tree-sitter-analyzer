"""CodeGraphAdapter — benchmark arm backed by the CodeGraph AST index.

Supports two modes:
  - ``arm_id="codegraph-cold"``: deletes .codegraph/ and rebuilds from scratch.
  - ``arm_id="codegraph-warm"``: verifies the index exists; rebuilds only if absent.

Index build is done via ``codegraph init -i`` with cwd=repo_path.
Errors are logged, not raised, so the harness can continue with partial data.
"""

from __future__ import annotations

import logging
import re
import shutil
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
A CodeGraph AST index has been pre-built for this repository.

Tools available to you: Read, Bash, Grep, Glob, and the codegraph_* MCP tools.

When answering:
- Start with codegraph_context or codegraph_search to locate relevant symbols
  before falling back to raw Grep or Read.
- Cite the specific file path and symbol name for every claim you make.
- Do not guess — only report what you find in the index or in the files.
- If the index returns no results for a query, say so and try an alternative
  search term; do not fabricate an answer.
- Prefer a single codegraph_explore call over many individual codegraph_node calls.
"""

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_FILE = _PROMPTS_DIR / "system_codegraph.md"

# ---------------------------------------------------------------------------
# CodeGraph index directory
# ---------------------------------------------------------------------------

_INDEX_DIR = ".codegraph"

# Tools Claude is allowed to call in this arm
_ALLOWED_TOOLS = [
    "Read",
    "Bash",
    "Grep",
    "Glob",
    "mcp__codegraph__codegraph_context",
    "mcp__codegraph__codegraph_search",
    "mcp__codegraph__codegraph_callers",
    "mcp__codegraph__codegraph_callees",
    "mcp__codegraph__codegraph_explore",
    "mcp__codegraph__codegraph_node",
    "mcp__codegraph__codegraph_files",
    "mcp__codegraph__codegraph_impact",
]

# Patterns used for parse_tool_metrics
_FILE_READ_TOOLS = frozenset({"read"})
_SEARCH_TOOLS = frozenset({"grep", "glob", "bash"})
_CODEGRAPH_PREFIX = "codegraph_"


class CodeGraphAdapter(BenchmarkAdapter):
    """Benchmark arm: CodeGraph AST index available to Claude."""

    def __init__(self, arm_id: str = "codegraph-warm") -> None:
        if arm_id not in ("codegraph-cold", "codegraph-warm"):
            raise ValueError(
                f"arm_id must be 'codegraph-cold' or 'codegraph-warm', got {arm_id!r}"
            )
        self.arm_id = arm_id

    # ------------------------------------------------------------------
    # Index preparation
    # ------------------------------------------------------------------

    def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
        """Build or verify the CodeGraph index under *repo_path/.codegraph/*.

        Args:
            repo_path: Absolute path to the repository root.
            cold: When True, always delete and rebuild. When False (warm),
                  skip the build if the index directory already exists.

        Returns:
            IndexStats with measured build time and index size.
        """
        index_dir = repo_path / _INDEX_DIR

        if cold:
            _delete_index(index_dir)
            return _build_index(repo_path, index_dir)

        # Warm path — rebuild only if absent
        if not index_dir.exists():
            logger.info(
                "CodeGraph index not found at %s; running cold build.", index_dir
            )
            return _build_index(repo_path, index_dir)

        logger.info(
            "CodeGraph index exists at %s; warm path — skipping build.", index_dir
        )
        size = _dir_size(index_dir)
        file_count = _count_files(index_dir)
        return IndexStats(
            build_seconds=0.0, index_size_bytes=size, file_count=file_count
        )

    # ------------------------------------------------------------------
    # Run configuration
    # ------------------------------------------------------------------

    def build_run_config(self, repo_path: Path, question_prompt: str) -> RunConfig:
        system_prompt = _load_prompt(_PROMPT_FILE, _DEFAULT_SYSTEM_PROMPT)
        extra_context = (
            f"CodeGraph index is ready in {repo_path}/.codegraph/. "
            "Use codegraph_context first, then explore as needed."
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

        codegraph_* tool mentions count as index_queries.
        Read counts as file_reads. Bash/Grep/Glob count as search_calls.
        """
        tool_calls = 0
        file_reads = 0
        search_calls = 0
        index_queries = 0

        for match in re.finditer(r"Tool:\s*(\S+)", transcript_text, re.IGNORECASE):
            name = match.group(1).lower().rstrip("()")
            tool_calls += 1
            if _CODEGRAPH_PREFIX in name:
                index_queries += 1
            elif name in _FILE_READ_TOOLS:
                file_reads += 1
            elif name in _SEARCH_TOOLS:
                search_calls += 1

        for match in re.finditer(r"\[(\w+)\]", transcript_text):
            name = match.group(1).lower()
            line_start = transcript_text.rfind("\n", 0, match.start()) + 1
            line = transcript_text[line_start : match.end()]
            if "Tool:" in line or "tool:" in line:
                continue
            tool_calls += 1
            if _CODEGRAPH_PREFIX in name:
                index_queries += 1
            elif name in _FILE_READ_TOOLS:
                file_reads += 1
            elif name in _SEARCH_TOOLS:
                search_calls += 1

        return ToolMetrics(
            tool_calls=tool_calls,
            file_reads=file_reads,
            search_calls=search_calls,
            index_queries=index_queries,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _delete_index(index_dir: Path) -> None:
    """Remove the index directory if it exists."""
    if index_dir.exists():
        logger.info("Deleting existing CodeGraph index at %s (cold build).", index_dir)
        try:
            shutil.rmtree(index_dir)
        except OSError as exc:
            logger.error("Failed to delete %s: %s", index_dir, exc)


def _build_index(repo_path: Path, index_dir: Path) -> IndexStats:
    """Run ``codegraph init -i`` and return IndexStats."""
    logger.info("Building CodeGraph index in %s ...", repo_path)
    t0 = time.perf_counter()

    result = subprocess.run(
        ["codegraph", "init", "-i"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        logger.error(
            "codegraph init -i exited with code %d.\nstdout: %s\nstderr: %s",
            result.returncode,
            result.stdout[:2000],
            result.stderr[:2000],
        )

    size = _dir_size(index_dir) if index_dir.exists() else 0
    file_count = _count_files(index_dir) if index_dir.exists() else 0

    logger.info(
        "CodeGraph index built in %.2fs, size=%d bytes, files=%d",
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


def _load_prompt(prompt_file: Path, default: str) -> str:
    if prompt_file.is_file():
        return prompt_file.read_text(encoding="utf-8").strip()
    return default
