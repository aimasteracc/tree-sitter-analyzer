"""RFC-0018 R10 — trace_impact must not ship a duplicate ``results`` array.

``trace_impact`` built ``"usages": usages`` and ``"results": usages`` — the
SAME list object under two keys. The array is the largest part of the
response and is re-encoded into ``toon_content`` as well, so the duplicate
doubled the dominant cost on both surfaces for zero added signal.

``usages`` is the canonical key (``usage_count`` counts it). ``results``
(the cross-tool *search* key) is dropped from trace; trace does not route
through ``search_envelope``, so nothing downstream depends on it.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool


def _project() -> str:
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "pkg"))
    with open(os.path.join(d, "pkg", "a.py"), "w") as fh:
        fh.write("def target():\n    return 1\n")
    with open(os.path.join(d, "pkg", "b.py"), "w") as fh:
        fh.write(
            "from pkg.a import target\n"
            "def caller():\n    return target()\n"
            "def caller2():\n    return target()\n"
        )
    return d


def test_trace_has_no_duplicate_results_array() -> None:
    d = _project()
    res = asyncio.run(
        TraceImpactTool(project_root=d).execute(
            {"symbol": "target", "output_format": "json"}
        )
    )
    # Canonical array present and populated.
    assert isinstance(res["usages"], list)
    assert res["usage_count"] == len(res["usages"])
    # The duplicate is gone — no second copy of the same array.
    assert "results" not in res, (
        "trace_impact still ships a duplicate 'results' array (== usages)"
    )


def test_trace_not_found_has_no_results_key() -> None:
    d = _project()
    res = asyncio.run(
        TraceImpactTool(project_root=d).execute(
            {"symbol": "does_not_exist_anywhere", "output_format": "json"}
        )
    )
    assert res["usages"] == []
    assert "results" not in res


def test_trace_response_does_not_pay_for_the_duplicate_array() -> None:
    """RFC-0018 R11 cost invariant: dropping the duplicate is a measured win.

    Not just "is the key absent?" (conformance) but "is it actually cheaper?"
    (value) — per CLAUDE.md §11. The emitted JSON response must be strictly
    smaller than the same response with the old ``results == usages``
    duplicate restored, and the saving must be at least the serialized size
    of the usages array itself (i.e. the whole duplicate array is gone, not a
    stray byte). Relationship form, never a hand-waved byte ceiling.
    """
    import json

    d = _project()
    res = asyncio.run(
        TraceImpactTool(project_root=d).execute(
            {"symbol": "target", "output_format": "json"}
        )
    )
    assert res["usages"], "fixture must produce a non-empty usages array"
    with_dup = {**res, "results": res["usages"]}
    now = len(json.dumps(res))
    before = len(json.dumps(with_dup))
    array_bytes = len(json.dumps(res["usages"]))
    assert now < before, (
        "duplicate-free response is not smaller than the duplicated one"
    )
    assert before - now >= array_bytes, (
        f"saving {before - now}B is smaller than the usages array "
        f"({array_bytes}B) — the full duplicate array was not eliminated"
    )
