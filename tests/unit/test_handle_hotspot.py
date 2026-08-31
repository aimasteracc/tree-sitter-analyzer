"""Unit tests for _handle_hotspot in capability_commands.py.

Tests argument validation, DependencyMatrix build errors, heatmap parse errors,
trace_from scenarios (not-found / isolated-file / subgraph), and show_alias_diff
gap summary. Each test asserts a real behavioral contract — no coverage stuffing.
"""
from __future__ import annotations

import json
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
    assert r["alias_gap_summary"]["total_files"] == 1


# ── _ensure_tsa_config ────────────────────────────────────────────────────────

def test_ensure_tsa_config_skips_if_exists(tmp_path):
    """Existing .tsa/config.json is not overwritten by _ensure_tsa_config."""
    from tree_sitter_analyzer.cli.capability_commands import _ensure_tsa_config

    cfg_dir = tmp_path / ".tsa"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "config.json"
    original = {"existing": True, "custom_key": 42}
    cfg_path.write_text(json.dumps(original), encoding="utf-8")

    _ensure_tsa_config(str(tmp_path))

    written = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert written["existing"] is True
    assert written["custom_key"] == 42


def test_ensure_tsa_config_creates_if_missing(tmp_path):
    """When no config exists, _ensure_tsa_config creates .tsa/config.json with defaults."""
    from tree_sitter_analyzer.cli.capability_commands import _ensure_tsa_config

    _ensure_tsa_config(str(tmp_path))

    cfg_path = tmp_path / ".tsa" / "config.json"
    assert cfg_path.exists()
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert config["severity_thresholds"] == {"critical": 400, "review": 100}
    assert config["default_top_n"] == 20


# ── _write_index_meta ─────────────────────────────────────────────────────────

def test_write_index_meta_creates_file(tmp_path):
    """_write_index_meta writes .tsa/index-meta.json with correct fields."""
    from tree_sitter_analyzer.cli.capability_commands import _write_index_meta

    _write_index_meta(str(tmp_path), files_indexed=42, languages=["python", "typescript"])

    meta_path = tmp_path / ".tsa" / "index-meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["files_indexed"] == 42
    assert meta["languages"] == ["python", "typescript"]
    assert "built_at" in meta
    assert "tsa_version" in meta


# ── top_n capping at 200 ──────────────────────────────────────────────────────

def test_top_n_capped_at_200():
    """top_n=300 is silently capped to 200; compute_scores receives top_n=200."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    compute_spy = MagicMock(return_value=[])
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[]),
        patch(_CA_RAW, return_value={"a.py": 1}),
        patch(_ALIAS_CA, return_value={"a.py": 1}),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_COMPUTE, compute_spy),
    ):
        rc = _handle_hotspot(make_args(hotspot_top_n=300), ctx, "json")
    assert rc == 0
    _, kwargs = compute_spy.call_args
    assert kwargs["top_n"] == 200


# ── Ca fallback source scanning ───────────────────────────────────────────────

def test_ca_fallback_when_import_edges_empty(tmp_path):
    """When dm._import_edges is empty, fallback source scanning is invoked and succeeds."""
    ctx, captured = make_context()
    MockDM = MagicMock()
    dm = MockDM.return_value
    dm.build.return_value = None
    dm._import_edges = {}   # triggers import_edges rebuild branch
    dm._result = None       # build_ca_raw_map returns {} → triggers ca_map branch too

    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[]),
        patch(_CA_RAW, return_value={}),
        patch(
            "tree_sitter_analyzer.complexity_heatmap._collect_source_files",
            return_value=[],
        ),
        patch(
            "tree_sitter_analyzer.hotspot_analyzer.build_ca_from_source_imports",
            return_value={},
        ),
        patch(
            "tree_sitter_analyzer.hotspot_analyzer.build_import_edges_from_source",
            return_value={},
        ),
        patch(_ALIAS_CA, return_value={}),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_COMPUTE, return_value=[]),
    ):
        rc = _handle_hotspot(make_args(project_root=str(tmp_path)), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True


# ── Pagination beyond total pages ─────────────────────────────────────────────

def test_page_beyond_total_returns_empty_results_success():
    """Requesting page=999 with only one page of data returns success=True, results=[]."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    review_entry = make_hotspot_entry(
        file="src/mod.py", severity="REVIEW", score=150.0,
        ca_raw=5, ca_alias=5, max_cc=30,
    )
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[FakeHeatmap("src/mod.py", max_complexity=30)]),
        patch(_CA_RAW, return_value={"src/mod.py": 5}),
        patch(_ALIAS_CA, return_value={"src/mod.py": 5}),
        patch(
            _HEATMAP_MAP,
            return_value={"src/mod.py": FakeHeatmap("src/mod.py", max_complexity=30)},
        ),
        patch(_COMPUTE, return_value=[review_entry]),
    ):
        rc = _handle_hotspot(make_args(page=999, page_size=20), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True
    assert r["results"] == []


# ── _write_index_meta: PackageNotFoundError fallback ─────────────────────────

def test_write_index_meta_package_not_found_uses_dev_version(tmp_path):
    """PackageNotFoundError when querying package version → tsa_version='0.0.0+dev' (lines 61-62)."""
    import importlib.metadata
    import json
    from unittest.mock import patch

    from tree_sitter_analyzer.cli.capability_commands import _write_index_meta

    with patch.object(
        importlib.metadata,
        "version",
        side_effect=importlib.metadata.PackageNotFoundError("tree-sitter-analyzer"),
    ):
        _write_index_meta(str(tmp_path), files_indexed=10, languages=["python"])

    meta = json.loads((tmp_path / ".tsa" / "index-meta.json").read_text(encoding="utf-8"))
    assert meta["tsa_version"] == "0.0.0+dev"
    assert meta["files_indexed"] == 10


# ── Ca fallback: one-sided branches (ca_map vs import_edges) ─────────────────

def test_ca_fallback_only_import_edges_empty(tmp_path):
    """ca_map is populated but import_edges is empty → only import_edges is rebuilt (222->225)."""
    ctx, captured = make_context()
    MockDM = MagicMock()
    dm = MockDM.return_value
    dm.build.return_value = None
    dm._import_edges = {}  # empty → triggers outer fallback block
    # ca_map is populated via dm._result
    stat = MagicMock()
    stat.file = "src/foo.py"
    stat.afferent_coupling = 3
    dm._result = MagicMock()
    dm._result.module_stats = [stat]

    import_edges_spy = MagicMock(return_value={"src/foo.py": {}})

    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[]),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_ALIAS_CA, return_value={"src/foo.py": 3}),
        patch(_COMPUTE, return_value=[]),
        patch(
            "tree_sitter_analyzer.complexity_heatmap._collect_source_files",
            return_value=[],
        ),
        patch(
            "tree_sitter_analyzer.hotspot_analyzer.build_ca_from_source_imports",
            return_value={"src/foo.py": 3},
        ) as ca_spy,
        patch(
            "tree_sitter_analyzer.hotspot_analyzer.build_import_edges_from_source",
            import_edges_spy,
        ),
    ):
        rc = _handle_hotspot(make_args(project_root=str(tmp_path)), ctx, "json")

    assert rc == 0
    # ca_from_source_imports should NOT have been called (ca_map was already populated)
    ca_spy.assert_not_called()
    # import_edges WAS rebuilt
    import_edges_spy.assert_called_once()


def test_trace_from_with_real_subgraph():
    """get_subgraph returns a non-None reachable map → subgraph_summary built (242->256 branch)."""
    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    hm_a = FakeHeatmap("a.py", max_complexity=8)
    hm_b = FakeHeatmap("b.py", max_complexity=4)
    # get_subgraph returns real subgraph (not None) → skips isolated-file branch
    fake_reachable = {"a.py": 0, "b.py": 1}
    entry = make_hotspot_entry(file="a.py", severity="REVIEW", score=120.0, ca_raw=3, ca_alias=3, max_cc=8)
    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[hm_a, hm_b]),
        patch(_CA_RAW, return_value={"a.py": 3, "b.py": 1}),
        patch(_ALIAS_CA, return_value={"a.py": 3, "b.py": 1}),
        patch(_HEATMAP_MAP, return_value={"a.py": hm_a, "b.py": hm_b}),
        patch(_COMPUTE, return_value=[entry]),
        patch(_GET_SUBGRAPH, return_value=fake_reachable),
    ):
        rc = _handle_hotspot(make_args(trace_from="a.py"), ctx, "json")
    assert rc == 0
    r = captured["result"]
    assert r["success"] is True
    assert r["subgraph_summary"]["entry_point"] == "a.py"
    assert r["subgraph_summary"]["files_in_subgraph"] == 2


def test_handle_capability_actions_dispatches_hotspot():
    """handle_capability_actions routes args.hotspot=True to _handle_hotspot."""
    from tree_sitter_analyzer.cli.capability_commands import handle_capability_actions

    ctx, captured = make_context()
    MockDM, _ = make_dm_mock()
    args = MagicMock()
    args.project_card = False
    args.plan_rename = None
    args.refactor_queue = False
    args.hotspot = True
    args.output_format = "json"
    args.project_root = None
    args.hotspot_top_n = 20
    args.page = 1
    args.page_size = 20
    args.hotspot_show_alias_diff = False
    args.trace_from = None
    args.depth = 3

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
        rc = handle_capability_actions(args, ctx)
    assert rc == 0
    assert captured["result"]["success"] is True


def test_handle_capability_actions_returns_none_when_no_flag():
    """handle_capability_actions returns None when no capability flag is set."""
    from tree_sitter_analyzer.cli.capability_commands import handle_capability_actions

    ctx, _ = make_context()
    args = MagicMock()
    args.project_card = False
    args.plan_rename = None
    args.refactor_queue = False
    args.hotspot = False
    args.output_format = "json"
    assert handle_capability_actions(args, ctx) is None


def test_ca_fallback_only_ca_map_empty(tmp_path):
    """import_edges is populated but ca_map is empty → only ca_map is rebuilt (225->228)."""
    ctx, captured = make_context()
    MockDM = MagicMock()
    dm = MockDM.return_value
    dm.build.return_value = None
    dm._import_edges = {"src/foo.py": {}}  # non-empty → outer block entered only if ca_map empty
    dm._result = None  # build_ca_raw_map returns {} → ca_map empty → enters outer block

    ca_spy = MagicMock(return_value={"src/foo.py": 2})

    with (
        patch(_DM, MockDM),
        patch(_ENSURE_CFG),
        patch(_WRITE_META),
        patch(_HEATMAPS, return_value=[]),
        patch(_HEATMAP_MAP, return_value={}),
        patch(_ALIAS_CA, return_value={"src/foo.py": 2}),
        patch(_COMPUTE, return_value=[]),
        patch(
            "tree_sitter_analyzer.complexity_heatmap._collect_source_files",
            return_value=[],
        ),
        patch(
            "tree_sitter_analyzer.hotspot_analyzer.build_ca_from_source_imports",
            ca_spy,
        ),
        patch(
            "tree_sitter_analyzer.hotspot_analyzer.build_import_edges_from_source",
            return_value={},
        ) as ie_spy,
    ):
        rc = _handle_hotspot(make_args(project_root=str(tmp_path)), ctx, "json")

    assert rc == 0
    # ca_from_source was called (ca_map was empty)
    ca_spy.assert_called_once()
    # build_import_edges should NOT have been called (import_edges was already populated)
    ie_spy.assert_not_called()
