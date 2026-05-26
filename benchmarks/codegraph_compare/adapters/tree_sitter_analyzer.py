"""TSAAdapter — benchmark arm backed by tree-sitter-analyzer's AST cache.

Supports two modes:
  - ``arm_id="tsa-cold"``: deletes .ast-cache/ and triggers a fresh index build.
  - ``arm_id="tsa-warm"``: verifies .ast-cache/index.db exists; rebuilds if absent.

The index is populated by running tree-sitter-analyzer from this checkout via
``uv run --project <analyzer-root> ... --project-root <repo_path>``, which parses
the target source tree and populates the target repo's SQLite cache.
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
tree-sitter-analyzer has been pre-run and its AST cache is available.

Tools available to you: Read, Bash, Grep, Glob.
You may run ``python -m tree_sitter_analyzer <subcommand> --format json``
via Bash to query the AST cache.

When answering:
- Start with a tree-sitter-analyzer subcommand (smart-context, project-graph,
  or call-graph) before falling back to raw Grep or Read.
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

# Tools Claude is allowed in this arm (TSA is invoked via Bash)
_ALLOWED_TOOLS = ["Read", "Bash", "Grep", "Glob"]

# Patterns used for parse_tool_metrics
_FILE_READ_TOOLS = frozenset({"read"})
_SEARCH_TOOLS = frozenset({"grep", "glob"})
# Bash tool calls that mention the TSA module count as index queries
_TSA_PATTERNS = re.compile(
    r"tree[_\-]sitter[_\-]analyzer|python\s+-m\s+tree_sitter_analyzer|\btsa\b",
    re.IGNORECASE,
)


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

        # Warm path — rebuild only if the index DB is absent
        if not index_db.exists():
            logger.info("TSA index.db not found at %s; running cold build.", index_db)
            return _build_cache(repo_path, cache_dir)

        logger.info("TSA index.db exists at %s; warm path — skipping build.", index_db)
        size = _dir_size(cache_dir)
        file_count = _count_files(cache_dir)
        return IndexStats(
            build_seconds=0.0, index_size_bytes=size, file_count=file_count
        )

    # ------------------------------------------------------------------
    # Run configuration
    # ------------------------------------------------------------------

    def build_run_config(self, repo_path: Path, question_prompt: str) -> RunConfig:
        system_prompt = _load_prompt(_PROMPT_FILE, _DEFAULT_SYSTEM_PROMPT)
        command_prefix = (
            f"uv run --project {_ANALYZER_ROOT} python -m tree_sitter_analyzer"
        )
        extra_context = (
            "tree-sitter-analyzer is available through this command prefix: "
            f"`{command_prefix}`. "
            "Run it from the benchmark repo root with `--project-root .`. "
            "Useful queries: `--symbol-search <name>`, `--codegraph-explore <query>`, "
            "`--codegraph-overview`, and `--call-graph callers|callees "
            "--call-graph-function <name>`. "
            f"The AST cache is at {repo_path}/.ast-cache/"
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

        Bash lines that contain ``tree_sitter_analyzer``, ``tsa``, or
        ``python -m tree_sitter_analyzer`` count as index_queries.
        Read counts as file_reads. Grep/Glob count as search_calls.
        Plain Bash calls count as search_calls unless they reference TSA.
        """
        tool_calls = 0
        file_reads = 0
        search_calls = 0
        index_queries = 0

        # Split transcript into lines for per-line context
        lines = transcript_text.splitlines()

        # Track whether we are inside a Bash tool invocation so we can
        # classify the call once we see the command text.
        in_bash_call = False
        pending_bash_lines: list[str] = []

        for line in lines:
            # Detect "Tool: <name>" annotation lines
            tool_match = re.match(r"\s*Tool:\s*(\S+)", line, re.IGNORECASE)
            if tool_match:
                # Flush any pending bash call first
                if in_bash_call:
                    _classify_bash(
                        "\n".join(pending_bash_lines),
                        result=_MutableCounts(
                            tool_calls_ref=[tool_calls],
                            search_calls_ref=[search_calls],
                            index_queries_ref=[index_queries],
                        ),
                    )
                    # Update locals from mutable containers
                    tool_calls = _MutableCounts(
                        tool_calls_ref=[tool_calls],
                        search_calls_ref=[search_calls],
                        index_queries_ref=[index_queries],
                    ).tool_calls_ref[0]
                    in_bash_call = False
                    pending_bash_lines = []

                name = tool_match.group(1).lower().rstrip("()")
                tool_calls += 1

                if name == "bash":
                    in_bash_call = True
                    pending_bash_lines = []
                elif name in _FILE_READ_TOOLS:
                    file_reads += 1
                elif name in _SEARCH_TOOLS:
                    search_calls += 1
                continue

            # If we are collecting a bash invocation, gather the line
            if in_bash_call:
                pending_bash_lines.append(line)

        # Flush trailing bash call
        if in_bash_call and pending_bash_lines:
            bash_body = "\n".join(pending_bash_lines)
            if _TSA_PATTERNS.search(bash_body):
                index_queries += 1
            else:
                search_calls += 1

        # Fallback: bracket notation [ToolName] for transcripts that don't
        # use "Tool:" prefix
        for match in re.finditer(r"\[(\w+)\]", transcript_text):
            name = match.group(1).lower()
            line_start = transcript_text.rfind("\n", 0, match.start()) + 1
            line_text = transcript_text[line_start : match.end()]
            if "Tool:" in line_text or "tool:" in line_text:
                continue
            tool_calls += 1
            if name in _FILE_READ_TOOLS:
                file_reads += 1
            elif name == "bash":
                # Can't determine context; count generically as search
                search_calls += 1
            elif name in _SEARCH_TOOLS:
                search_calls += 1

        # Also scan the whole transcript for TSA invocations that appear in
        # command blocks without a "Tool: Bash" prefix (e.g. inline code fences)
        for match in _TSA_PATTERNS.finditer(transcript_text):
            # Only count if on a line that looks like a shell command, not prose
            line_start = transcript_text.rfind("\n", 0, match.start()) + 1
            line_end = transcript_text.find("\n", match.end())
            if line_end == -1:
                line_end = len(transcript_text)
            cmd_line = transcript_text[line_start:line_end].strip()
            if cmd_line.startswith(("$", "python", "uv run")):
                index_queries += 1

        return ToolMetrics(
            tool_calls=tool_calls,
            file_reads=file_reads,
            search_calls=search_calls,
            index_queries=index_queries,
        )


# ---------------------------------------------------------------------------
# Internal helper dataclass for mutable counter passing
# ---------------------------------------------------------------------------


class _MutableCounts:
    """Tiny mutable container used to pass counters by reference."""

    __slots__ = ("tool_calls_ref", "search_calls_ref", "index_queries_ref")

    def __init__(
        self,
        tool_calls_ref: list[int],
        search_calls_ref: list[int],
        index_queries_ref: list[int],
    ) -> None:
        self.tool_calls_ref = tool_calls_ref
        self.search_calls_ref = search_calls_ref
        self.index_queries_ref = index_queries_ref


def _classify_bash(bash_body: str, result: _MutableCounts) -> None:
    """Classify one Bash call as either an index_query or a search_call."""
    if _TSA_PATTERNS.search(bash_body):
        result.index_queries_ref[0] += 1
    else:
        result.search_calls_ref[0] += 1


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
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        logger.error(
            "tree_sitter_analyzer exited with code %d.\nstdout: %s\nstderr: %s",
            result.returncode,
            result.stdout[:2000],
            result.stderr[:2000],
        )

    size = _dir_size(cache_dir) if cache_dir.exists() else 0
    file_count = _count_files(cache_dir) if cache_dir.exists() else 0

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


def _load_prompt(prompt_file: Path, default: str) -> str:
    if prompt_file.is_file():
        return prompt_file.read_text(encoding="utf-8").strip()
    return default
