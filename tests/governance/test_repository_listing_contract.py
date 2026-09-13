"""Contract tests for the published repository listing.

The GitHub description, its topics, and the MCP registry entry in
``server.json`` are read before the README is.  They must advertise only
current capabilities and only quantitative claims the claim registry
authorizes at E4.  See ``docs/repository-listing.md`` for the rules and the
canonical text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LISTING_PATH = PROJECT_ROOT / "docs" / "repository-listing.md"
REGISTRY_PATH = PROJECT_ROOT / "benchmarks" / "codegraph_compare" / "claim_registry.json"

# Capabilities a released breaking change removed; CHANGELOG.md owns the record.
# A listing that advertises one sends users after something that is not there.
REMOVED_FEATURES = ("TOON", "search-content", "find-and-grep")

# A ratio such as ``124x`` or ``390×``.  Authorized only at evidence level E4.
RATIO_CLAIM = re.compile(r"\d+(?:\.\d+)?\s*[x×]", re.IGNORECASE)


def _fenced_block_after(heading: str) -> str:
    """Return the first fenced block under ``heading``, whitespace-collapsed."""
    text = LISTING_PATH.read_text(encoding="utf-8")
    assert heading in text, f"{LISTING_PATH.name} lost its {heading!r} section"
    section = text.split(heading, 1)[1]
    block = section.split("```", 2)[1]
    return " ".join(block.split())


def _listing_texts() -> dict[str, str]:
    server = json.loads((PROJECT_ROOT / "server.json").read_text(encoding="utf-8"))
    return {
        "docs/repository-listing.md description": _fenced_block_after(
            "## GitHub description"
        ),
        "docs/repository-listing.md topics": _fenced_block_after("## Topics"),
        "server.json description": server["description"],
    }


def _authorized_e4_claims() -> list[dict]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [
        claim
        for claim in registry.get("claims", [])
        if claim.get("evidence_level") == "E4"
    ]


def _generated_pipeline_language_count() -> str:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"(\d+) pipeline-registered", readme)
    assert match, "README lost its generated language-support inventory"
    return match.group(1)


def test_listings_advertise_no_removed_capability() -> None:
    for name, text in _listing_texts().items():
        lowered = text.lower()
        for capability in REMOVED_FEATURES:
            assert capability.lower() not in lowered, (
                f"{name} advertises {capability!r}, which a released breaking "
                "change removed (see CHANGELOG.md and docs/MIGRATION.md)"
            )


def test_listings_publish_no_unauthorized_quantitative_claim() -> None:
    if _authorized_e4_claims():
        return
    for name, text in _listing_texts().items():
        assert not RATIO_CLAIM.search(text), (
            f"{name} publishes a competitive ratio while {REGISTRY_PATH.name} "
            "authorizes no E4 claim; land the evidence first, or move the "
            "measured detail to its benchmark report"
        )


def test_listings_agree_with_the_generated_language_count() -> None:
    expected = _generated_pipeline_language_count()
    for name in ("docs/repository-listing.md description", "server.json description"):
        text = _listing_texts()[name]
        assert expected in text, (
            f"{name} does not restate the generated count {expected} from "
            "README.md; a listing count is a restatement, not a second source"
        )
