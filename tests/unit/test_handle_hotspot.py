"""Unit tests for _handle_hotspot in capability_commands.py.

Tests argument validation, DependencyMatrix build errors, heatmap parse errors,
trace_from scenarios (not-found / isolated-file / subgraph), and show_alias_diff
gap summary. Each test asserts a real behavioral contract — no coverage stuffing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.cli.capability_commands import _handle_hotspot
from tree_sitter_analyzer.output_schema import HotspotEntry
from tree_sitter_analyzer.output_schema import TestFocus as _TestFocus

# Prevent pytest from collecting TestFocus as a test class
TestFocus = _TestFocus
TestFocus.__test__ = False  # type: ignore[attr-defined]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@dataclass
class FakeFunc:
    name: str
    complexity: int
    class_name: str | None = None
    decision_points: dict = field(default_factory=dict)


@dataclass
class FakeHeatmap:
    file: str
    language: str = "python"
    functions: list = field(default_factory=list)
    total_complexity: int = 0
    avg_complexity: float = 0.0
    max_complexity: int = 0


def make_context():
    """Minimal SpecialCommandContext stub that captures output_json / output_error."""
    ctx = MagicMock()
    captured: dict = {}

    def output_json(result):
        captured["result"] = result

    def output_error(msg):
        captured["error"] = msg

    ctx.output_json.side_effect = output_json
    ctx.output_error.side_effect = output_error
    return ctx, captured


def make_args(**kwargs):
    """Build a minimal args namespace stub with sensible defaults."""
    args = MagicMock()
    args.project_root = kwargs.get("project_root", None)
    args.hotspot_top_n = kwargs.get("hotspot_top_n", 20)
    args.page = kwargs.get("page", 1)
    args.page_size = kwargs.get("page_size", 20)
    args.hotspot_show_alias_diff = kwargs.get("hotspot_show_alias_diff", False)
    args.trace_from = kwargs.get("trace_from", None)
    args.depth = kwargs.get("depth", 3)
    return args


def make_dm_mock(build_side_effect=None, import_edges=None):
    """Return (MockDMClass, dm_instance) where dm_instance.build behaves as specified."""
    MockDM = MagicMock()
    dm = MockDM.return_value
    if build_side_effect is not None:
        dm.build.side_effect = build_side_effect
    dm._import_edges = import_edges if import_edges is not None else {"a.py": {}}
    dm._result = None  # build_ca_raw_map checks this; None → empty dict
    return MockDM, dm


def make_hotspot_entry(
    file: str = "src/big.py",
    severity: str = "CRITICAL",
    score: float = 500.0,
    ca_raw: int = 25,
    ca_alias: int = 25,
    max_cc: int = 20,
    rank: int = 1,
) -> HotspotEntry:
    return HotspotEntry(
        rank=rank,
        file=file,
        severity=severity,
        score=score,
        ca_raw=ca_raw,
        ca_alias=ca_alias,
        max_cc=max_cc,
        test_focus=TestFocus("heavy_fn", max_cc, "test edge cases and error paths"),
    )


# ── Patch target constants ────────────────────────────────────────────────────

_DM = "tree_sitter_analyzer.dependency_matrix.DependencyMatrix"
_HEATMAPS = "tree_sitter_analyzer.hotspot_analyzer.heatmaps_from_project_analysis"
_CA_RAW = "tree_sitter_analyzer.hotspot_analyzer.build_ca_raw_map"
_ALIAS_CA = "tree_sitter_analyzer.hotspot_analyzer.build_alias_ca_map"
_HEATMAP_MAP = "tree_sitter_analyzer.hotspot_analyzer.build_heatmap_map"
_COMPUTE = "tree_sitter_analyzer.hotspot_analyzer.compute_scores"
_GET_SUBGRAPH = "tree_sitter_analyzer.subgraph_traverser.get_subgraph"
_ENSURE_CFG = "tree_sitter_analyzer.cli.capability_commands._ensure_tsa_config"
_WRITE_META = "tree_sitter_analyzer.cli.capability_commands._write_index_meta"


# ── Argument validation ───────────────────────────────────────────────────────

def test_invalid_top_n_zero():
    """top_n=0 returns exit code 1 with error='invalid_argument', category='configuration'."""
    ctx, captured = make_context()
    rc = _handle_hotspot(make_args(hotspot_top_n=0), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "invalid_argument"
    assert r["error_category"] == "configuration"
    assert r["recovery_hint"] == "fix_argument"


def test_invalid_page_zero():
    """page=0 returns exit code 1 with error='invalid_argument', category='configuration'."""
    ctx, captured = make_context()
    rc = _handle_hotspot(make_args(page=0), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "invalid_argument"
    assert r["error_category"] == "configuration"


def test_invalid_page_size_zero():
    """page_size=0 returns exit code 1 with error='invalid_argument', category='configuration'."""
    ctx, captured = make_context()
    rc = _handle_hotspot(make_args(page_size=0), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "invalid_argument"
    assert r["error_category"] == "configuration"


def test_invalid_depth_zero():
    """depth=0 returns exit code 1 with error='invalid_argument', category='configuration'."""
    ctx, captured = make_context()
    rc = _handle_hotspot(make_args(depth=0), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "invalid_argument"
    assert r["error_category"] == "configuration"
    assert "depth" in r["message"]


def test_depth_over_5_capped_with_warning(capsys):
    """depth=10 is capped to 5 with a stderr warning; overall result is success."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[]),
        patch(_CA_RAW, return_value={"a.py": 5}),
        patch(_ALIAS_CA, return_value={"a.py": 5}),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_COMPUTE, return_value=[]),
    ):
        rc = _handle_hotspot(make_args(depth=10), ctx, "json")
    assert rc == 0
    err = capsys.readouterr().err
    assert "capping" in err.lower()


# ── DependencyMatrix build errors ─────────────────────────────────────────────

def test_index_not_built_file_not_found():
    """dm.build() raising FileNotFoundError → error='index_not_built', category='state'."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock(build_side_effect=FileNotFoundError("no index"))
    with patch(_DM, MockDM), patch(_ENSURE_CFG):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "index_not_built"
    assert r["error_category"] == "state"
    assert r["recovery_hint"] == "fix_then_retry"


def test_index_build_os_error():
    """dm.build() raising OSError → error='index_build_error', category='transient'."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock(build_side_effect=OSError("disk busy"))
    with patch(_DM, MockDM), patch(_ENSURE_CFG):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "index_build_error"
    assert r["error_category"] == "transient"
    assert r["recovery_hint"] == "retry"


def test_index_not_built_generic_error():
    """dm.build() raising RuntimeError → error='index_not_built' (generic except branch)."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock(build_side_effect=RuntimeError("unexpected failure"))
    with patch(_DM, MockDM), patch(_ENSURE_CFG):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "index_not_built"
    assert r["error_category"] == "state"


# ── Heatmap errors ────────────────────────────────────────────────────────────

def test_parse_timeout():
    """heatmaps_from_project_analysis raising TimeoutError → error='parse_timeout'."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_HEATMAPS, side_effect=TimeoutError("parse took too long")),
    ):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "parse_timeout"
    assert r["error_category"] == "transient"
    assert r["recovery_hint"] == "retry"


def test_fs_busy():
    """heatmaps_from_project_analysis raising OSError → error='fs_busy'."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_HEATMAPS, side_effect=OSError("filesystem busy")),
    ):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "fs_busy"
    assert r["error_category"] == "transient"
    assert r["recovery_hint"] == "retry"


# ── Success paths ─────────────────────────────────────────────────────────────

def test_success_empty_heatmap():
    """When compute_scores returns [], result is success=True, verdict='OK', message set."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[]),
        patch(_CA_RAW, return_value={"a.py": 1}),
        patch(_ALIAS_CA, return_value={"a.py": 1}),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_COMPUTE, return_value=[]),
    ):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True
    assert r["verdict"] == "OK"
    assert "message" in r
    assert "No files exceed" in r["message"]


def test_success_with_critical_file():
    """When compute_scores returns a CRITICAL entry, verdict='CRITICAL' in result."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    critical_entry = make_hotspot_entry(
        file="src/big.py", severity="CRITICAL", score=500.0, ca_raw=25, ca_alias=25, max_cc=20
    )
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[FakeHeatmap("src/big.py", max_complexity=20)]),
        patch(_CA_RAW, return_value={"src/big.py": 25}),
        patch(_ALIAS_CA, return_value={"src/big.py": 25}),
        patch(_HEATMAP_MAP, return_value={"src/big.py": FakeHeatmap("src/big.py", max_complexity=20)}),
        patch(_COMPUTE, return_value=[critical_entry]),
    ):
        rc = _handle_hotspot(make_args(), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True
    assert r["verdict"] == "CRITICAL"
    assert len(r["results"]) == 1
    assert r["results"][0]["severity"] == "CRITICAL"
    assert r["results"][0]["score"] == 500.0


# ── trace_from scenarios ──────────────────────────────────────────────────────

def test_trace_from_entry_point_not_found():
    """trace_from file not in subgraph and not in heatmap → error='entry_point_not_found'."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_HEATMAPS, return_value=[]),
        patch(_CA_RAW, return_value={"a.py": 1}),
        patch(_ALIAS_CA, return_value={"a.py": 1}),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_GET_SUBGRAPH, return_value=None),
    ):
        rc = _handle_hotspot(make_args(trace_from="nonexistent.py"), ctx, "json")
    assert rc == 1
    r = captured["result"]
    assert r["success"] is False
    assert r["error"] == "entry_point_not_found"
    assert r["error_category"] == "data"
    assert r["recovery_hint"] == "try_alternative"


def test_trace_from_isolated_file():
    """trace_from in heatmap but get_subgraph=None → reachable={file:0}, success=True."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    isolated_hm = FakeHeatmap("isolated.py", max_complexity=5)
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[isolated_hm]),
        patch(_CA_RAW, return_value={"isolated.py": 0}),
        patch(_ALIAS_CA, return_value={"isolated.py": 0}),
        patch(_HEATMAP_MAP, return_value={"isolated.py": isolated_hm}),
        patch(_COMPUTE, return_value=[]),
        patch(_GET_SUBGRAPH, return_value=None),
    ):
        rc = _handle_hotspot(make_args(trace_from="isolated.py"), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True
    assert "subgraph_summary" in r
    assert r["subgraph_summary"]["entry_point"] == "isolated.py"
    # Isolated file counts as 1 file in subgraph (hop 0 only)
    assert r["subgraph_summary"]["files_in_subgraph"] == 1


# ── show_alias_diff ───────────────────────────────────────────────────────────

def test_show_alias_diff_populates_gap_summary():
    """show_alias_diff=True with alias_ca > ca_raw for a file → alias_gap_summary populated."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    hm = FakeHeatmap("a.py", max_complexity=5)
    # alias_ca_map has a gap: alias=10 > ca_raw=3
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[hm]),
        patch(_CA_RAW, return_value={"a.py": 3}),
        patch(_ALIAS_CA, return_value={"a.py": 10}),
        patch(_HEATMAP_MAP, return_value={"a.py": hm}),
        patch(_COMPUTE, return_value=[]),
    ):
        rc = _handle_hotspot(make_args(hotspot_show_alias_diff=True), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True
    assert "alias_gap_summary" in r
    # One file ("a.py") has alias_ca (10) > ca_raw (3) → gap count = 1
    assert r["alias_gap_summary"]["files_with_alias_gap"] == 1
    assert r["alias_gap_summary"]["total_files"] >= 1
