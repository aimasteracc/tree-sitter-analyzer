"""NativeAdapter — baseline arm that relies only on file-system tools.

No index is built. Claude is allowed to Read, Bash, Grep, and Glob.
All codegraph and TSA index tools are explicitly forbidden so the
transcript reflects raw file-search cost.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import BenchmarkAdapter, IndexStats, RunConfig, ToolMetrics

# ---------------------------------------------------------------------------
# Inline default system prompt (used when the .md file is absent)
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """\
You are answering an architecture question about a software codebase.

Tools available to you: Read, Bash, Grep, Glob.
You may NOT use any codegraph or tree-sitter-analyzer index tools.

When answering:
- Cite the specific file path and line number for every claim you make.
- Do not guess or infer from memory — only report what you actually find in the code.
- If you cannot find evidence in the files, say so explicitly.
- Prefer targeted Grep searches over reading entire files when you only need a pattern.
"""

# Prompt file path relative to the benchmarks/codegraph_compare directory
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_FILE = _PROMPTS_DIR / "system_native.md"

# ---------------------------------------------------------------------------
# Tool name patterns used by parse_tool_metrics
# ---------------------------------------------------------------------------

# These map a tool name (lowercased) to whether it counts as a file_read or
# a search_call. Any tool not in the map is counted only in tool_calls.
_FILE_READ_TOOLS = frozenset({"read"})
_SEARCH_TOOLS = frozenset({"grep", "glob", "bash"})


class NativeAdapter(BenchmarkAdapter):
    """Benchmark arm: native file-system tools only, no pre-built index."""

    arm_id = "native-only"

    # ------------------------------------------------------------------
    # Index preparation — no-op for this arm
    # ------------------------------------------------------------------

    def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
        """No index to build. Returns zeroed stats immediately."""
        return IndexStats(build_seconds=0.0, index_size_bytes=0, file_count=0)

    # ------------------------------------------------------------------
    # Run configuration
    # ------------------------------------------------------------------

    def build_run_config(self, repo_path: Path, question_prompt: str) -> RunConfig:
        system_prompt = _load_prompt(_PROMPT_FILE, _DEFAULT_SYSTEM_PROMPT)

        return RunConfig(
            arm_id=self.arm_id,
            repo_path=repo_path,
            system_prompt=system_prompt,
            allowed_tools=["Read", "Bash", "Grep", "Glob"],
            forbidden_tools=["mcp__codegraph__*", "mcp__tsa__*"],
            extra_context="",
        )

    # ------------------------------------------------------------------
    # Transcript parsing
    # ------------------------------------------------------------------

    def parse_tool_metrics(self, transcript_text: str) -> ToolMetrics:
        """Count tool invocations from raw transcript text.

        Recognises two patterns emitted by the Claude Code harness:
          - ``Tool: ToolName`` (one per invocation line)
          - ``[ToolName]``     (bracket notation)

        Read, Grep, Glob are split into file_reads vs search_calls.
        Bash counts as a search_call (it most commonly runs grep/find).
        """
        tool_calls = 0
        file_reads = 0
        search_calls = 0

        # Pattern 1 — "Tool: ToolName" or "Tool: ToolName(...)"
        for match in re.finditer(r"Tool:\s*(\w+)", transcript_text, re.IGNORECASE):
            name = match.group(1).lower()
            tool_calls += 1
            if name in _FILE_READ_TOOLS:
                file_reads += 1
            elif name in _SEARCH_TOOLS:
                search_calls += 1

        # Pattern 2 — "[ToolName]" bracket notation
        for match in re.finditer(r"\[(\w+)\]", transcript_text):
            name = match.group(1).lower()
            # Avoid double-counting if both patterns appear for the same call
            # by only counting bracket lines that are NOT preceded by "Tool:"
            line_start = transcript_text.rfind("\n", 0, match.start()) + 1
            line = transcript_text[line_start : match.end()]
            if "Tool:" in line or "tool:" in line:
                continue
            tool_calls += 1
            if name in _FILE_READ_TOOLS:
                file_reads += 1
            elif name in _SEARCH_TOOLS:
                search_calls += 1

        return ToolMetrics(
            tool_calls=tool_calls,
            file_reads=file_reads,
            search_calls=search_calls,
            index_queries=0,  # no index in this arm
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _load_prompt(prompt_file: Path, default: str) -> str:
    """Return the content of *prompt_file* if it exists, else *default*."""
    if prompt_file.is_file():
        return prompt_file.read_text(encoding="utf-8").strip()
    return default
