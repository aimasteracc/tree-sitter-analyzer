"""Drift test for docs/agent-envelope-contract.md (#520).

The envelope-contract guide documents two live constants:

* the canonical verdict alphabet
  (:data:`tree_sitter_analyzer.mcp.tools.tool_response.CANONICAL_VERDICTS`)
* the RFC-0012 ``compact_only`` control-surface allowlist
  (:data:`tree_sitter_analyzer.mcp.utils.format_helper.TOON_CONTROL_SURFACE`)

Hand-copied lists rot. This test extracts the documented sets from the
marked tables in the doc and asserts EXACT set equality with the live
constants, in both directions: a verdict/field added to the source without
a doc update goes red, and a stale doc row that no longer exists in the
source also goes red.
"""

import re
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.tool_response import CANONICAL_VERDICTS
from tree_sitter_analyzer.mcp.utils.format_helper import TOON_CONTROL_SURFACE

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DOC_PATH = PROJECT_ROOT / "docs" / "agent-envelope-contract.md"


def _extract_marked_table_tokens(content: str, marker: str) -> set[str]:
    """Return the first-column backticked tokens of the table between
    ``<!-- drift:<marker>:start -->`` and ``<!-- drift:<marker>:end -->``.
    """
    section_re = re.compile(
        rf"<!-- drift:{marker}:start -->(.*?)<!-- drift:{marker}:end -->",
        re.DOTALL,
    )
    match = section_re.search(content)
    assert match is not None, (
        f"docs/agent-envelope-contract.md is missing the "
        f"<!-- drift:{marker}:start/end --> markers"
    )
    tokens = set()
    for line in match.group(1).splitlines():
        row = re.match(r"\|\s*`([A-Za-z_]+)`", line)
        if row:
            tokens.add(row.group(1))
    return tokens


class TestAgentEnvelopeContractDoc:
    def test_doc_exists(self) -> None:
        assert DOC_PATH.exists(), (
            "docs/agent-envelope-contract.md does not exist (#520)"
        )

    def test_verdict_alphabet_matches_canonical_set(self) -> None:
        documented = _extract_marked_table_tokens(
            DOC_PATH.read_text(encoding="utf-8"), "verdict-alphabet"
        )
        assert documented == set(CANONICAL_VERDICTS), (
            f"verdict table drifted from CANONICAL_VERDICTS: "
            f"missing from doc={sorted(set(CANONICAL_VERDICTS) - documented)}, "
            f"stale in doc={sorted(documented - set(CANONICAL_VERDICTS))}"
        )

    def test_control_surface_matches_allowlist(self) -> None:
        documented = _extract_marked_table_tokens(
            DOC_PATH.read_text(encoding="utf-8"), "control-surface"
        )
        assert documented == set(TOON_CONTROL_SURFACE), (
            f"control-surface table drifted from TOON_CONTROL_SURFACE: "
            f"missing from doc={sorted(set(TOON_CONTROL_SURFACE) - documented)}, "
            f"stale in doc={sorted(documented - set(TOON_CONTROL_SURFACE))}"
        )

    def test_cross_links_present(self) -> None:
        """toon-format-guide.md and CODEMAPS/mcp-tools.md must link the page."""
        for doc in ("toon-format-guide.md", "CODEMAPS/mcp-tools.md"):
            content = (PROJECT_ROOT / "docs" / doc).read_text(encoding="utf-8")
            assert "agent-envelope-contract.md" in content, (
                f"docs/{doc} does not link docs/agent-envelope-contract.md"
            )
