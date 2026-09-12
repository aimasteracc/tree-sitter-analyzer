"""Claim invariant: a resolved caller list is never a confident absence.

RFC-0028 §1, as an executable invariant.  The moat is honesty, not precision:
TSA need not *resolve* an edge, but it must never answer a bare zero over a case
where an edge genuinely exists.

Corpus: ``tests/fixtures/call_graph/undecidable_project``.  Five symbols are
reached only through dispatch a text search cannot follow — a string-keyed
handler registry, ``getattr(self, name)``, ``globals()[name]``, and
``importlib`` + ``getattr``.  A search for ``handle_alpha(`` finds the
definition and never a call, which is precisely what tempts a confident "0
callers".  Ground truth is hand-checked in ``_CASES`` below.

Reconciliation with ``test_unknown_rate_ratchet.py`` (RFC-0028 §1.2).  The two
gates point in opposite directions and do not conflict, because they measure
different denominators:

===========================  ==============================  ==========================
                             unknown-rate cap (existing)      honesty ratchet (this file)
===========================  ==============================  ==========================
denominator                  every ``kind='calls'`` row        the hand-checked corpus
unit                         a percentage                      a count
measures                     resolution quality                honesty where resolution
                                                               is impossible
direction                    down is better                    fewer silent zeros is better
===========================  ==============================  ==========================

**§1 wins on collision.**  A change that lowers the repo-wide unknown rate by
turning an undecidable case into a confident empty fails this file, and the
existing cap may be re-pinned upward with a reviewed decision where this one may
not be relaxed at all.  The accepted transitions are ``unknown -> resolved`` and
``complete -> incomplete``; the forbidden one is ``unknown -> confident empty``.

Scope guard (§1.2, against §3.1): §1 applies only to symbols whose containing
file holds at least one unresolved edge.  A symbol in a fully-resolved file must
answer ``complete``, so "answer unknown whenever the file contains a dynamic
construct" is not a legal way to satisfy this ratchet.  Recorded here because
the guard is what makes the corpus below meaningful rather than a blanket
pessimism.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.claims_benchmark,
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CORPUS = PROJECT_ROOT / "tests" / "fixtures" / "call_graph" / "undecidable_project"

#: ``(symbol, declaring file, the dispatch that reaches it)``.  Each entry is a
#: real runtime edge that a call-site text search cannot find.
_CASES: tuple[tuple[str, str, str], ...] = (
    ("handle_alpha", "plugins.py", 'HANDLERS[name]() registry dispatch'),
    ("handle_beta", "plugins.py", 'HANDLERS[name]() registry dispatch'),
    ("method_one", "dynamic.py", "getattr(self, name)()"),
    ("method_two", "dynamic.py", "getattr(self, name)()"),
    ("module_level_target", "dynamic.py", "globals()[name]() and getattr(module, attr)()"),
)

#: Recorded, not ratcheted: the number of corpus cases the corpus itself proves
#: are undecidable.  A zero here means the fixture stopped exercising the shape
#: and the invariant below became vacuous, so it fails loudly instead.
_EXPECTED_CORPUS_CASES = 5

#: The honesty ratchet (RFC-0028 §1.2): corpus cases answered *without* a
#: confident empty.  It may increase or hold, never decrease.
#:
#: It counts honest answers rather than ``unknown`` ones on purpose.  §1.2 says
#: the count of ``unknown`` answers may never decrease, and in the same breath
#: that ``unknown -> resolved`` is accepted — which a decreasing count cannot
#: express.  The transition the ratchet exists to block is
#: ``unknown -> confident empty``, so that is what it counts.
_HONEST_ANSWER_FLOOR = 5


@pytest.fixture(scope="module")
def corpus_project(tmp_path_factory) -> str:
    """Index the corpus once and answer every case from that index."""
    from tree_sitter_analyzer.ast_cache import ASTCache

    root = tmp_path_factory.mktemp("undecidable")
    for source in CORPUS.glob("*.py"):
        (root / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    cache = ASTCache(str(root))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(root)


def _call_site_text_hits(symbol: str) -> int:
    """Hits for the naive tool: a call-site search for ``symbol(``."""
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    hits = 0
    for source in CORPUS.glob("*.py"):
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith(("def ", "class ", "async def ")):
                continue
            hits += len(pattern.findall(line))
    return hits


def test_the_corpus_still_exercises_the_undecidable_shape() -> None:
    """Guard against the fixture quietly becoming trivially decidable."""
    assert len(_CASES) == _EXPECTED_CORPUS_CASES
    for symbol, _declaring, _dispatch in _CASES:
        assert _call_site_text_hits(symbol) == 0, (
            f"{symbol} is now called by name in the corpus, so the naive tool "
            "would find it and the invariant below no longer tests anything"
        )


def test_corpus_records_unresolved_dispatch_under_the_expression(corpus_project) -> None:
    """What TSA does today with a computed callee: it names the expression.

    This is recorded rather than asserted as correct.  It is why a per-symbol
    completeness query cannot see these cases: the unresolved row is attributed
    to ``HANDLERS[name]``, which is no symbol's name, so a lookup for
    ``handle_alpha`` finds nothing unresolved and reports a complete zero.
    """
    import sqlite3

    conn = sqlite3.connect(f"{corpus_project}/.ast-cache/index.db")
    try:
        rows = conn.execute(
            "SELECT callee_name FROM edges WHERE kind='calls' "
            "AND callee_resolution NOT IN ('project','builtin','stdlib','local')"
        ).fetchall()
    finally:
        conn.close()
    names = {row[0] for row in rows}
    # A dynamic site leaves a placeholder row, but keyed by the source text.
    assert any("[" in name or "(" in name for name in names), (
        "computed dispatch sites no longer leave an unresolved row at all; the "
        "gap this file records has changed shape and needs re-measuring"
    )
    assert not names & {symbol for symbol, _f, _d in _CASES}, (
        "a corpus symbol now appears as an unresolved callee name; re-measure "
        "the finding this file records"
    )


@pytest.mark.asyncio
async def test_a_symbol_in_a_fully_resolved_file_still_answers_complete(
    tmp_path,
) -> None:
    """The scope guard cuts both ways (§1.2, against §3.1).

    Answering ``unknown`` for every symbol in a project that contains any
    dynamic construct would satisfy the invariant above while destroying what
    the field is for.  The guard admits ``unknown`` only for a symbol whose own
    file holds an unresolved edge, so a symbol in a fully-resolved file must
    still answer ``complete`` even when a sibling file is full of dispatch.
    """
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    (tmp_path / "clean.py").write_text(
        "def helper():\n    return 1\n\n\ndef clean_symbol():\n    return helper()\n",
        encoding="utf-8",
    )
    # The unresolved edge lives here, in a file that declares clean_symbol not.
    (tmp_path / "noisy.py").write_text(
        "def noisy():\n    return HANDLERS[name]()\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    tool = CodeGraphCallersTool(str(tmp_path))
    result = await tool.execute({"function_name": "clean_symbol", "output_format": "json"})

    assert result["completeness"] == "complete", (
        "a symbol whose own file is fully resolved must not inherit a sibling "
        "file's unresolved edges"
    )


@pytest.mark.asyncio
async def test_undecidable_edge_is_never_reported_as_confidently_absent(
    corpus_project,
) -> None:
    """The moat, as an executable invariant.

    A confident empty answer where an edge genuinely exists is the single
    failure mode that makes an agent conclude "safe to change" and be wrong.
    This test does not require TSA to *resolve* the edge — being unable to
    resolve it is acceptable and expected. It requires TSA to say so.
    """
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(corpus_project)
    offenders = []
    for symbol, declaring, dispatch in _CASES:
        result = await tool.execute({"function_name": symbol, "output_format": "json"})
        if result.get("caller_count", 0) == 0 and result.get("completeness") == "complete":
            offenders.append((symbol, declaring, dispatch, result.get("completeness")))
    assert offenders == [], (
        "these corpus symbols have a real inbound edge but were answered with a "
        f"confident zero: {json.dumps(offenders, indent=2)}"
    )


@pytest.mark.asyncio
async def test_honesty_ratchet_never_decreases(corpus_project) -> None:
    """The ratchet half of §1.2.

    A change that converts an undecidable case into a confident empty lowers
    this count, and fails here even when every other test is green.  Raising the
    floor is allowed when the resolver genuinely improves a case (the answer
    becomes the edge itself); relaxing it is not.
    """
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(corpus_project)
    honest = 0
    confident_zeros = []
    for symbol, _declaring, _dispatch in _CASES:
        result = await tool.execute({"function_name": symbol, "output_format": "json"})
        if result.get("caller_count", 0) == 0 and result.get("completeness") == "complete":
            confident_zeros.append(symbol)
        else:
            honest += 1

    assert honest >= _HONEST_ANSWER_FLOOR, (
        f"honest answers fell to {honest}, below the pinned floor "
        f"{_HONEST_ANSWER_FLOOR}; these corpus cases became confident empties: "
        f"{confident_zeros}"
    )
