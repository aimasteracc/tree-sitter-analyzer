"""Benchmark adapter base interface and factory.

Each adapter encapsulates one arm of the benchmark:
  - how to build / verify its index
  - which tools Claude is allowed (or forbidden) to use
  - how to parse raw transcript text into ToolMetrics

Adapters are stateless value objects — no side effects at import time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IndexStats:
    """Statistics collected during index preparation."""

    build_seconds: float
    index_size_bytes: int
    file_count: int


@dataclass
class ToolMetrics:
    """Tool-usage counts parsed from a single transcript run."""

    tool_calls: int
    file_reads: int
    search_calls: int
    index_queries: int


@dataclass
class RunConfig:
    """Full configuration for one benchmark question run."""

    arm_id: str
    repo_path: Path
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    # Injected verbatim into the first user message (e.g. "index is at .codegraph/")
    extra_context: str = ""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BenchmarkAdapter(ABC):
    """Base class for all benchmark arms."""

    arm_id: str

    @abstractmethod
    def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
        """Build (cold=True) or verify (cold=False, warm) the index.

        Must always return an IndexStats even if preparation is a no-op.
        Implementations should log errors rather than raise so the harness
        can continue.
        """
        ...

    @abstractmethod
    def build_run_config(self, repo_path: Path, question_prompt: str) -> RunConfig:
        """Return the RunConfig for a single question run against *repo_path*."""
        ...

    @abstractmethod
    def parse_tool_metrics(self, transcript_text: str) -> ToolMetrics:
        """Parse raw transcript text and return aggregated tool-usage counts."""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_adapter(arm_id: str) -> BenchmarkAdapter:
    """Return the right adapter instance for *arm_id*.

    Recognised arm IDs:
      - ``"native-only"``
      - ``"codegraph-cold"``
      - ``"codegraph-warm"``
      - ``"tsa-cold"``
      - ``"tsa-warm"``
    """
    # Lazy imports keep module-level side effects out of this file.
    from .codegraph import CodeGraphAdapter
    from .native import NativeAdapter
    from .tree_sitter_analyzer import TSAAdapter

    if arm_id == "native-only":
        return NativeAdapter()
    if arm_id in ("codegraph-cold", "codegraph-warm"):
        return CodeGraphAdapter(arm_id=arm_id)
    if arm_id in ("tsa-cold", "tsa-warm"):
        return TSAAdapter(arm_id=arm_id)

    raise ValueError(
        f"Unknown arm_id {arm_id!r}. "
        "Valid values: 'native-only', 'codegraph-cold', 'codegraph-warm', "
        "'tsa-cold', 'tsa-warm'."
    )
