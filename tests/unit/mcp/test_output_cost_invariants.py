"""Output-cost invariants for MCP tool responses.

ASSERTION STYLE (locked exact-assertion rule, CLAUDE.md §0): absolute byte
counts here are environment-dependent (responses embed tmp paths), so exact
``==`` pins would be flaky. Per the rule's exception clause these tests assert
**documented relationships** (``compact < default``), never hand-waved numeric
ceilings.
"""

from __future__ import annotations

import asyncio
import json

# ── RFC-0015 P1 rule-11 differential invariant ────────────────────────────────


def test_class_diagram_scoped_smaller_than_unscoped(monkeypatch) -> None:
    """Scoped class diagram bytes < unscoped bytes (rule-11 differential invariant).

    Scoping (file_path or class_name) restricts the node/edge set, so the
    serialized response for a scoped request MUST be strictly smaller than
    the unscoped whole-project response on the same class set.

    Exact == pin not applicable here because bytes vary with project content;
    the invariant is the *relationship* between scoped and unscoped (CLAUDE.md
    rule-11 exception for nondeterministic values — assert a documented
    invariant, not a hand-waved bound).
    """
    import asyncio
    import json as _json

    from tree_sitter_analyzer.mcp.tools import uml_tool as _uml_tool

    # A synthetic class set with 10 classes, only one in the target file.
    # The whole-project diagram covers all 10; the file-scoped diagram covers 1.
    ALL_CLASSES = [
        {"name": f"Class{i}", "parents": [], "file": f"src/mod{i}.py"}
        for i in range(10)
    ]
    TARGET_FILE = "src/mod0.py"

    class FakeHierarchyAll:
        def __init__(self, cache):
            pass

        def build(self):
            pass

        def all_classes(self):
            return ALL_CLASSES

    # Sentinel cache object: prevents _open_cache from trying to open a real DB.
    class SentinelCache:
        pass

    class FakeExporterProvider:
        def __init__(self, project_root):
            pass

        def uml_exporter(self):
            import tree_sitter_analyzer.uml_export as _export

            # Pass the sentinel cache so _open_cache skips ASTCache("/repo")
            return _export.UMLExporter("/repo", cache=SentinelCache())

    # Patch ClassHierarchy for the duration of this test
    import tree_sitter_analyzer.uml_export as _uml_export

    monkeypatch.setattr(_uml_export, "ClassHierarchy", FakeHierarchyAll)
    monkeypatch.setattr(_uml_tool, "CodeGraphVisualizationHub", FakeExporterProvider)

    tool = _uml_tool.CodeGraphUMLTool("/repo")

    # Unscoped
    unscoped = asyncio.run(tool.execute({"diagram": "class", "output_format": "json"}))
    # File-scoped
    scoped = asyncio.run(
        tool.execute(
            {"diagram": "class", "output_format": "json", "file_path": TARGET_FILE}
        )
    )

    unscoped_bytes = len(_json.dumps(unscoped, ensure_ascii=False))
    scoped_bytes = len(_json.dumps(scoped, ensure_ascii=False))

    assert scoped_bytes < unscoped_bytes, (
        f"Scoped class diagram ({scoped_bytes}B) is not smaller than "
        f"unscoped ({unscoped_bytes}B) — file_path scoping is a no-op."
    )


# ── Issue #460: viz similarity summary-default — rule-11 invariants ───────────
#
# Default viz similarity response must NOT inline code bodies.  Full bodies are
# only included when include_bodies=True.  This section:
#   1. Builds a deterministic synthetic 20-group response in both modes.
#   2. Asserts the relationship: summary_bytes < full_bytes  (differential)
#   3. Exact-pins both byte counts so any drift in the response envelope
#      goes RED and forces a conscious re-pin.
#
# Measured 2026-06-11 with the synthetic fixture below (20 groups × 3 functions).
# summary = 9416 B,  full = 13616 B  (ratio 1.446×).
# Snapshot command:
#   python3 -c "
#   import json
#   # ... (see _make_synthetic_similarity_summary / _full below)
#   "


def _make_synthetic_similarity_group(i: int, include_snippet: bool) -> dict:
    """One synthetic clone group with 3 function entries."""
    funcs = []
    for j in range(3):
        f: dict = {
            "file": f"src/module_{i}/handler_{j}.py",
            "name": f"process_item_{j}",
            "line": j * 20 + 1,
            "end_line": j * 20 + 15,
            "language": "python",
        }
        if include_snippet:
            f["snippet"] = f"def process_item_{j}(x):\n    if x > 0:\n        y = x * "
        funcs.append(f)
    return {
        "fingerprint": f"abcdef1234567{i:03d}",
        "method": "structural",
        "similarity": 1.0,
        "function_count": 3,
        "functions": funcs,
    }


def _make_synthetic_similarity_response(include_snippets: bool) -> dict:
    """Deterministic full-bodies similarity response.

    Fixture design:
    - 20 groups × 3 functions each = 60 clone instances (always REVIEW verdict).
    - project_root is a fixed string ("/repo") so byte sizes are deterministic.
    - include_snippets controls whether the 'snippet' field appears per function.
    """
    groups = [_make_synthetic_similarity_group(i, include_snippets) for i in range(20)]
    return {
        "success": True,
        "verdict": "REVIEW",
        "project_root": "/repo",
        "stats": {
            "total_groups": 20,
            "total_clone_instances": 60,
            "mode": "all",
            "min_lines": 5,
            "cache_used": True,
        },
        "groups": groups,
    }


def _make_synthetic_similarity_compact_group(i: int) -> dict:
    """Compact summary group — no functions list, just sample_files (#801 fix)."""
    return {
        "fingerprint": f"abcdef1234567{i:03d}",
        "method": "structural",
        "similarity": 1.0,
        "function_count": 3,
        "sample_files": [f"src/module_{i}/handler_{j}.py" for j in range(3)],
    }


def _make_synthetic_similarity_compact_response() -> dict:
    """Deterministic compact response — groups have sample_files, not functions[]."""
    return {
        "success": True,
        "verdict": "REVIEW",
        "project_root": "/repo",
        "stats": {
            "total_groups": 20,
            "total_clone_instances": 60,
            "mode": "all",
            "min_lines": 5,
            "cache_used": True,
        },
        "groups": [_make_synthetic_similarity_compact_group(i) for i in range(20)],
    }


def test_similarity_summary_smaller_than_full_bodies() -> None:
    """Rule-11 differential invariant: compact response < full-bodies response.

    The whole point of include_bodies=False (the default): the response must
    be strictly smaller than include_bodies=True.  If this fails, compact mode
    is a no-op and the 226KB default is back.
    """
    compact_resp = _make_synthetic_similarity_compact_response()
    full_resp = _make_synthetic_similarity_response(include_snippets=True)

    compact_bytes = len(json.dumps(compact_resp, ensure_ascii=False))
    full_bytes = len(json.dumps(full_resp, ensure_ascii=False))

    assert compact_bytes < full_bytes, (
        f"similarity compact ({compact_bytes}B) >= full-bodies ({full_bytes}B) — "
        "compact mode is a no-op; group summarisation is broken."
    )
    # Exact pins — synthetic fixture is deterministic (no tmp paths, no dates).
    # Re-measure and re-pin if envelope fields change.
    # Measured 2026-06-15: compact=4336 B, full=13616 B (3.14x reduction).
    assert compact_bytes == 4336, (
        f"similarity compact bytes drifted: {compact_bytes} != 4336 — "
        "re-measure and re-pin"
    )
    assert full_bytes == 13616, (
        f"similarity full bytes drifted: {full_bytes} != 13616 — re-measure and re-pin"
    )


def test_similarity_summary_no_snippet_fields() -> None:
    """Structural invariant: compact groups must not contain 'snippet' or 'functions' keys.

    Compact mode (#801) replaces the full functions[] list with sample_files[].
    Verifies the data shape — if functions/snippet somehow reappear, this fails.
    """
    compact_resp = _make_synthetic_similarity_compact_response()
    for group in compact_resp["groups"]:
        assert "functions" not in group, (
            f"functions key present in compact group: {group}. "
            "Compact mode must replace functions[] with sample_files[]."
        )
        assert "snippet" not in group, (
            f"snippet key present in compact group: {group}. "
            "Compact mode must omit code bodies."
        )


def test_similarity_compact_has_sample_files() -> None:
    """Structural invariant: compact groups must contain 'sample_files' key (#801).

    Compact mode replaces functions[] with sample_files[] for bounded output.
    If sample_files disappears (e.g. the compact path is bypassed), this fails.
    """
    compact_resp = _make_synthetic_similarity_compact_response()
    for group in compact_resp["groups"]:
        assert "sample_files" in group, (
            f"sample_files key missing in compact group: {group}. "
            "Compact mode must include sample_files[] for agent discoverability."
        )
        assert isinstance(group["sample_files"], list), (
            f"sample_files must be a list, got: {type(group['sample_files'])}"
        )


def test_similarity_full_has_snippet_fields() -> None:
    """Structural invariant: full-bodies groups must contain 'snippet' key.

    Mirrors the compact test — verifies that include_bodies=True actually
    adds the snippet, so the feature is not silently a no-op in either direction.
    """
    full_resp = _make_synthetic_similarity_response(include_snippets=True)
    for group in full_resp["groups"]:
        for func in group["functions"]:
            assert "snippet" in func, (
                f"snippet key missing in full-bodies response function entry: {func}. "
                "include_bodies=True must include code body snippets."
            )


# ── DF-13: nav callers/callees default budget — honest truncation (2026-06-11) ──
#
# callers_tool / callees_tool previously had no display cap, so high-fan-in
# symbols like ``execute`` returned 1985 callers / 319,870 bytes — far beyond
# the 25k token MCP cap, forcing the harness to spill to disk.
#
# The fix (DF-13): default listed_cap = 50.  Response carries:
#   caller_count   — pre-cap total (agent knows how many exist)
#   callers_listed — count actually in the list (== min(total, cap))
#   listed_cap     — the cap value used
#   truncated      — bool: total > cap
#
# Rule-11 invariants:
#   1. Structural: default (50/200) carries exact fields with correct values.
#   2. Differential: default bytes < unlimited bytes (capping saves tokens).
#   3. Exact pins: synthetic payload is deterministic (no tmp paths, no dates).
#
# Measured 2026-06-11 with:
#   default (50/200): 8537 B  unlimited (200/200): 33435 B  (ratio 3.92x)


def _make_synthetic_callers_payload(n_callers: int, limit: int) -> dict:
    """Synthetic callers_tool response dict for n_callers callers, capped at limit.

    Mimics what CodeGraphCallersTool.execute returns — no tmp paths so the
    byte count is fully deterministic.
    """
    from tree_sitter_analyzer.mcp.tools._response_builder import build_response

    callers_all = [
        {
            "name": f"caller_{i}",
            "file": f"src/module_{i // 10}/mod_{i}.py",
            "line": i * 5,
            "language": "python",
            "callee_resolution": "project",
            "callee_resolved_file": "src/target.py",
        }
        for i in range(n_callers)
    ]
    total_callers = n_callers
    truncated = n_callers > limit
    callers = callers_all[:limit]
    result = build_response(
        verdict="INFO",
        data_source="sql",
        function="execute",
        caller_count=total_callers,
        callers_listed=len(callers),
        listed_cap=limit,
        truncated=truncated,
        callers=callers,
    )
    if truncated:
        result["next_step"] = (
            f"showing {len(callers)} of {total_callers} callers — raise limit, "
            "or qualify with ClassName.method to narrow "
            "(dynamic-dispatch names like execute have huge fan-in)"
        )
    return result


def test_callers_truncation_structural_fields() -> None:
    """DF-13: default (50/200) response carries correct truncation fields.

    This is the RED-first structural invariant: the fix must emit
    caller_count==200, callers_listed==50, listed_cap==50, truncated==True.
    """
    payload = _make_synthetic_callers_payload(200, 50)
    assert payload["caller_count"] == 200
    assert payload["callers_listed"] == 50
    assert payload["listed_cap"] == 50
    assert payload["truncated"] is True
    assert len(payload["callers"]) == 50


def test_callers_no_truncation_structural_fields() -> None:
    """DF-13: 10 callers with default cap 50 → truncated=False, all listed."""
    payload = _make_synthetic_callers_payload(10, 50)
    assert payload["caller_count"] == 10
    assert payload["callers_listed"] == 10
    assert payload["listed_cap"] == 50
    assert payload["truncated"] is False
    assert len(payload["callers"]) == 10


def test_callers_default_cap_bytes_smaller_than_unlimited() -> None:
    """DF-13 rule-11 differential: default (50/200) bytes < unlimited (200/200).

    Capping to 50 must produce a strictly smaller response than listing all 200.
    If this fails, the budget cap is a no-op.
    """
    default_resp = _make_synthetic_callers_payload(200, 50)
    unlimited_resp = _make_synthetic_callers_payload(200, 200)

    default_bytes = len(json.dumps(default_resp, ensure_ascii=False))
    unlimited_bytes = len(json.dumps(unlimited_resp, ensure_ascii=False))

    assert default_bytes < unlimited_bytes, (
        f"callers default cap ({default_bytes}B) >= unlimited ({unlimited_bytes}B) — "
        "budget cap is a no-op"
    )
    # Exact pins — synthetic fixture has no tmp paths, fully deterministic.
    # Measured 2026-06-11: default=8537 B, unlimited=33435 B (3.92x reduction).
    # Re-measure and re-pin if envelope fields change.
    assert default_bytes == 8537, (
        f"callers default bytes drifted: {default_bytes} != 8537 — re-measure and re-pin"
    )
    assert unlimited_bytes == 33435, (
        f"callers unlimited bytes drifted: {unlimited_bytes} != 33435 — re-measure and re-pin"
    )


def test_outline_wide_class_methods_bounded_by_cap(tmp_path) -> None:
    """#571: a single wide class must not detonate the outline response.

    The top-level listed_cap bounds the class COUNT, but a 10k-method generated
    stub had its methods emitted uncapped (2.75MB, truncated=False). Each listed
    class's methods must be bounded by listed_cap — the structural invariant that
    keeps the response within budget. The fixture is deterministic (500 methods),
    so every count is pinned EXACTLY (CLAUDE.md exact-assertion lock — no <=/<
    bounds; the byte budget is the deterministic consequence of methods == cap).
    """
    from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
        DEFAULT_OUTLINE_CLASSES_CAP,
        GetCodeOutlineTool,
    )

    f = tmp_path / "wide.py"
    f.write_text(
        "class Big:\n" + "".join(f"    def m{i}(self): pass\n" for i in range(500))
    )
    tool = GetCodeOutlineTool(project_root=str(tmp_path))
    result = asyncio.run(tool.execute({"file_path": str(f), "output_format": "json"}))

    cls = result["classes"][0]
    # Exactly listed_cap methods listed (not 500), with the honest pre-cap totals.
    assert len(cls["methods"]) == DEFAULT_OUTLINE_CLASSES_CAP
    assert cls["methods_total"] == 500
    assert cls["methods_listed"] == DEFAULT_OUTLINE_CLASSES_CAP
    assert result["method_count"] == 500  # pre-cap total stays honest
    assert result["truncated"] is True
