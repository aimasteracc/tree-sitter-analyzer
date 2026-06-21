"""Guard the PyPI-visible ``pyproject.toml`` description against stale or
disproven marketing claims.

The ``[project].description`` field renders on the PyPI project page, so it is
a public credibility surface. This test pins three invariants:

1. The advertised MCP tool count matches the registry-measured value
   (``create_tool_registry``), not a stale hand-written number.
2. The withdrawn "beats CodeGraph on the benchmark median" claim — which the
   README itself retracts — never reappears.
3. The legacy ``63 MCP tools`` count (pre-facade consolidation) is gone.

If the facade count changes, update the description and this test together —
the same discipline in the split contract suites applies to the 8-facade surface.
"""

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10 — tomllib landed in 3.11; tomli is a conditional dep.
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def _description() -> str:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return data["project"]["description"]


def _registry_tool_count() -> int:
    sys.path.insert(0, str(PROJECT_ROOT))
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(str(PROJECT_ROOT))
    return len(tools)


def test_description_advertises_registry_tool_count() -> None:
    """The tool count in the description equals the registry-measured count."""
    description = _description()
    count = _registry_tool_count()
    # Word-boundary match on the COUNT digit so a stale '18 facade MCP tools'
    # cannot pass on the substring '8 facade MCP tools' (Codex P3 #339).
    assert re.search(rf"\b{count} facade MCP tools\b", description), (
        f"Description should advertise '{count} facade MCP tools' as a whole "
        f"number; got: {description!r}"
    )


def test_description_drops_disproven_benchmark_claim() -> None:
    """The withdrawn 'beats CodeGraph median' claim must not reappear.

    The README itself retracts the median-win claim and concedes CodeGraph is
    currently cheaper, so the public-facing description must not assert it.
    """
    description = _description().lower()
    assert "beats codegraph" not in description, (
        "Description must not claim it beats CodeGraph — the benchmark claim "
        "was withdrawn (see README)."
    )
    assert not re.search(r"benchmark\s+median", description), (
        "Description must not assert a benchmark-median win."
    )


def test_description_drops_legacy_tool_count() -> None:
    """The pre-facade '63 MCP tools' count must not survive."""
    description = _description()
    assert "63 MCP tools" not in description, (
        "Description still advertises the legacy 63-tool count; should be 8 facades."
    )
