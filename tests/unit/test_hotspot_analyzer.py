"""Unit tests for hotspot_analyzer.py and output_schema.py (pure functions only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.hotspot_analyzer import (
    _detect_source_dir,
    _iter_resolved_imports,
    _resolve_import_mod,
    build_ca_from_source_imports,
    build_test_focus,
    classify_severity,
    compute_scores,
)
from tree_sitter_analyzer.output_schema import (
    HotspotEntry,
    paginate,
    result_to_dict,
)
from tree_sitter_analyzer.output_schema import (
    TestFocus as _TestFocus,
)
from tree_sitter_analyzer.subgraph_traverser import bfs_reachable

# Alias to avoid pytest collecting TestFocus as a test class
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


def make_entry(rank=1, file="a.py", severity="OK", score=50.0, ca_raw=5, ca_alias=5, max_cc=10, hops=None):
    return HotspotEntry(
        rank=rank, file=file, severity=severity, score=score,
        ca_raw=ca_raw, ca_alias=ca_alias, max_cc=max_cc,
        test_focus=TestFocus("fn", max_cc, "ok"), hops=hops,
    )


# ── P2: Basic score ───────────────────────────────────────────────────────────

def test_score_calculation_basic():
    ca_map = {"a.py": 5}
    hm = FakeHeatmap("a.py", max_complexity=10, functions=[FakeFunc("f", 10)])
    entries = compute_scores(ca_map, {"a.py": hm})
    assert entries[0].score == 50.0
    assert entries[0].ca_raw == 5
    assert entries[0].ca_alias == 5


# ── P4: Severity boundaries ───────────────────────────────────────────────────

def test_severity_critical_boundary():
    assert classify_severity(400) == "CRITICAL"
    assert classify_severity(399) == "REVIEW"


def test_severity_review_boundary():
    assert classify_severity(100) == "REVIEW"
    assert classify_severity(99) == "OK"


def test_empty_results_is_success():
    ca_map = {"a.py": 1}
    hm = FakeHeatmap("a.py", max_complexity=0)
    entries = compute_scores(ca_map, {"a.py": hm})
    assert all(e.score == 0 for e in entries)
    # Caller (capability_commands) treats empty ranked -> success: true
    # Verify paginate handles empty list
    sliced, meta = paginate([], 1, 20)
    assert sliced == []
    assert meta.files_in_output == 0


def test_test_focus_extraction():
    hm = FakeHeatmap("a.py", max_complexity=12,
                     functions=[FakeFunc("parse", 12), FakeFunc("init", 3)])
    tf = build_test_focus(hm, "CRITICAL")
    assert tf.function == "parse"
    assert tf.cc == 12
    assert "edge cases" in tf.suggestion


# ── P3: alias-aware Ca ────────────────────────────────────────────────────────

def test_alias_resolution_python(tmp_path):
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    # Create a minimal Python project structure in tmp_path
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("from .core import Foo\n")
    (tmp_path / "pkg" / "core.py").write_text("class Foo: pass\n")
    (tmp_path / "main.py").write_text("from pkg import Foo\n")

    import_edges = {
        "main.py": {"pkg/__init__.py": 1},
        "pkg/__init__.py": {"pkg/core.py": 1},
    }
    ca_raw = {"pkg/__init__.py": 1, "pkg/core.py": 1}
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path))
    # main.py imports pkg/__init__.py (Ca=1), which re-exports pkg/core.py
    # so alias Ca for core.py must be ca_raw + 1 extra caller via __init__
    assert alias_ca.get("pkg/core.py", 0) == ca_raw.get("pkg/core.py", 0) + 1


def test_alias_resolution_typescript(tmp_path):
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export { Foo } from './utils'\n")
    (tmp_path / "src" / "utils.ts").write_text("export class Foo {}\n")
    (tmp_path / "main.ts").write_text("import { Foo } from './src'\n")

    import_edges = {
        "main.ts": {"src/index.ts": 1},
        "src/index.ts": {"src/utils.ts": 1},
    }
    ca_raw = {"src/index.ts": 1, "src/utils.ts": 1}
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path))
    # main.ts imports src/index.ts (Ca=1), which re-exports src/utils.ts
    # so alias Ca for utils.ts must be ca_raw + 1 extra caller via index.ts
    assert alias_ca.get("src/utils.ts", 0) == ca_raw.get("src/utils.ts", 0) + 1


# ── P6: Error categories ──────────────────────────────────────────────────────

def test_error_index_not_built():
    from tree_sitter_analyzer.output_schema import HotspotResult
    r = HotspotResult(success=False, error="index_not_built",
                      error_category="state", recovery_hint="fix_then_retry",
                      message="Index not found")
    d = result_to_dict(r)
    assert d["error_category"] == "state"
    assert d["recovery_hint"] == "fix_then_retry"
    assert d["success"] is False


def test_error_entry_point_not_found():
    from tree_sitter_analyzer.output_schema import HotspotResult
    r = HotspotResult(success=False, error="entry_point_not_found",
                      error_category="data", recovery_hint="try_alternative",
                      message="Not found")
    d = result_to_dict(r)
    assert d["error_category"] == "data"
    assert d["recovery_hint"] == "try_alternative"


def test_error_transient():
    from tree_sitter_analyzer.output_schema import HotspotResult
    r = HotspotResult(success=False, error="parse_timeout",
                      error_category="transient", recovery_hint="retry",
                      message="Timeout")
    d = result_to_dict(r)
    assert d["error_category"] == "transient"
    assert d["recovery_hint"] == "retry"


def test_error_invalid_depth():
    from tree_sitter_analyzer.output_schema import HotspotResult
    r = HotspotResult(success=False, error="invalid_argument",
                      error_category="configuration", recovery_hint="fix_argument",
                      message="Invalid value for --depth: must be 1-5")
    d = result_to_dict(r)
    assert d["error_category"] == "configuration"
    assert d["recovery_hint"] == "fix_argument"


# ── P1: Pagination ────────────────────────────────────────────────────────────

def test_pagination_slice():
    entries = [make_entry(rank=i, score=float(100 - i)) for i in range(1, 11)]
    sliced, meta = paginate(entries, 2, 5)
    assert [e.rank for e in sliced] == [6, 7, 8, 9, 10]
    assert meta.page == 2
    assert meta.page_size == 5


def test_pagination_overflow():
    entries = [make_entry(rank=i) for i in range(1, 6)]
    sliced, meta = paginate(entries, 999, 5)
    assert sliced == []
    assert meta.files_in_output == 0


def test_pagination_merge():
    entries = [make_entry(rank=i, score=float(100 - i)) for i in range(1, 11)]
    p1, _ = paginate(entries, 1, 5)
    p2, _ = paginate(entries, 2, 5)
    merged = p1 + p2
    full, _ = paginate(entries, 1, 10)
    assert [e.rank for e in merged] == [e.rank for e in full]


# ── P5: BFS ───────────────────────────────────────────────────────────────────

def test_bfs_subgraph_smaller():
    edges = {
        "main.py": {"a.py": 1, "b.py": 1},
        "a.py": {"c.py": 1},
        "b.py": {"d.py": 1},
    }
    all_files = {"main.py", "a.py", "b.py", "c.py", "d.py", "e.py"}
    reachable = bfs_reachable("main.py", edges, 2)
    assert len(reachable) < len(all_files)
    assert "e.py" not in reachable


def test_bfs_depth_cap(capsys):
    from tree_sitter_analyzer.subgraph_traverser import get_subgraph
    dm = MagicMock()
    dm._import_edges = {"main.py": {"a.py": 1}, "a.py": {}}
    result = get_subgraph(dm, "main.py", 10)
    captured = capsys.readouterr()
    assert "capping" in captured.err
    assert result is not None


def test_hops_in_result():
    ca_map = {"main.py": 0, "a.py": 2, "b.py": 1}
    hm_map = {
        "main.py": FakeHeatmap("main.py", max_complexity=5),
        "a.py": FakeHeatmap("a.py", max_complexity=10),
    }
    reachable = {"main.py": 0, "a.py": 1}
    entries = compute_scores(ca_map, hm_map, reachable=reachable)
    hop_map = {e.file: e.hops for e in entries}
    assert hop_map == {"main.py": 0, "a.py": 1}


# ── top_n edge cases ──────────────────────────────────────────────────────────

def test_compute_scores_top_n_zero_returns_empty():
    ca_map = {"a.py": 5}
    hm = FakeHeatmap("a.py", max_complexity=10, functions=[FakeFunc("f", 10)])
    entries = compute_scores(ca_map, {"a.py": hm}, top_n=0)
    assert entries == []


def test_compute_scores_top_n_negative_clamps_to_empty():
    ca_map = {"a.py": 5, "b.py": 3}
    hm_map = {
        "a.py": FakeHeatmap("a.py", max_complexity=10, functions=[FakeFunc("f", 10)]),
        "b.py": FakeHeatmap("b.py", max_complexity=5, functions=[FakeFunc("g", 5)]),
    }
    entries = compute_scores(ca_map, hm_map, top_n=-1)
    assert entries == []


# ── _resolve_import_mod ────────────────────────────────────────────────────────

def test_resolve_absolute_import():
    file_set = {"pkg/utils.py", "pkg/__init__.py"}
    assert _resolve_import_mod("pkg.utils", "main.py", file_set) == "pkg/utils.py"


def test_resolve_relative_import_dot():
    file_set = {"pkg/utils.py", "pkg/__init__.py", "pkg/foo.py"}
    # from .utils import X  (called from pkg/foo.py)
    assert _resolve_import_mod(".utils", "pkg/foo.py", file_set) == "pkg/utils.py"


def test_resolve_relative_import_double_dot():
    file_set = {"pkg/utils.py", "pkg/__init__.py", "pkg/sub/foo.py"}
    # from ..utils import X  (called from pkg/sub/foo.py) → pkg/utils.py
    assert _resolve_import_mod("..utils", "pkg/sub/foo.py", file_set) == "pkg/utils.py"


def test_resolve_bare_relative_not_in_fileset_returns_none():
    file_set = {"pkg/utils.py"}
    # from . import nonexistent — not in file_set → None
    assert _resolve_import_mod(".nonexistent", "pkg/foo.py", file_set) is None


# ── _iter_resolved_imports: bare relative imports ─────────────────────────────

def test_iter_resolved_bare_dot_import():
    file_set = {"pkg/__init__.py", "pkg/utils.py", "pkg/foo.py"}
    text = "from . import utils\n"
    results = list(_iter_resolved_imports(text, "pkg/foo.py", file_set))
    assert "pkg/utils.py" in results


def test_iter_resolved_bare_double_dot_import():
    file_set = {"pkg/__init__.py", "pkg/utils.py", "pkg/sub/__init__.py", "pkg/sub/mod.py"}
    text = "from .. import utils\n"
    results = list(_iter_resolved_imports(text, "pkg/sub/mod.py", file_set))
    assert "pkg/utils.py" in results


def test_iter_resolved_no_duplicate_from_both_passes():
    file_set = {"pkg/__init__.py", "pkg/utils.py", "pkg/foo.py"}
    # "from .utils import X" is a normal relative import (pass 1 handles it)
    # ensure no duplicate even if somehow both passes fire
    text = "from .utils import X\n"
    results = list(_iter_resolved_imports(text, "pkg/foo.py", file_set))
    assert results.count("pkg/utils.py") == 1


# ── build_ca_from_source_imports ──────────────────────────────────────────────

def test_ca_counts_standard_imports(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "utils.py").write_text("def f(): pass\n")
    (tmp_path / "pkg" / "main.py").write_text("from pkg.utils import f\n")
    (tmp_path / "pkg" / "other.py").write_text("from pkg.utils import f\n")

    scan = ["pkg/utils.py", "pkg/main.py", "pkg/other.py"]
    ca = build_ca_from_source_imports(str(tmp_path), scan)
    assert ca.get("pkg/utils.py", 0) == 2


def test_ca_counts_bare_relative_imports(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("from . import utils\n")
    (tmp_path / "pkg" / "utils.py").write_text("def f(): pass\n")

    scan = ["pkg/__init__.py", "pkg/utils.py"]
    ca = build_ca_from_source_imports(str(tmp_path), scan)
    assert ca.get("pkg/utils.py", 0) == 1


def test_ca_windows_path_normalization(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "utils.py").write_text("def f(): pass\n")
    (tmp_path / "pkg" / "main.py").write_text("from pkg.utils import f\n")

    # Pass Windows-style backslash paths — should still normalize correctly
    scan = ["pkg\\utils.py", "pkg\\main.py"]
    ca = build_ca_from_source_imports(str(tmp_path), scan)
    assert ca.get("pkg/utils.py", 0) == 1


# ── _detect_source_dir ────────────────────────────────────────────────────────

def test_detect_source_dir_pyproject(tmp_path):
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.hatch.build.targets.wheel]\npackages = ["mypkg"]\n'
    )
    assert _detect_source_dir(str(tmp_path)) == "mypkg"


def test_detect_source_dir_heuristic_skips_non_source(tmp_path):
    # tests/ appears before mypkg/ alphabetically, but is in blocklist
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    assert _detect_source_dir(str(tmp_path)) == "mypkg"


def test_detect_source_dir_none_when_empty(tmp_path):
    assert _detect_source_dir(str(tmp_path)) is None


# ── build_ca_raw_map ──────────────────────────────────────────────────────────

def test_build_ca_raw_map_no_result():
    """When dm._result is None, returns an empty dict."""
    from tree_sitter_analyzer.hotspot_analyzer import build_ca_raw_map
    dm = MagicMock()
    dm._result = None
    result = build_ca_raw_map(dm)
    assert result == {}


def test_build_ca_raw_map_with_module_stats():
    """Returns {file: afferent_coupling} from dm._result.module_stats."""
    from tree_sitter_analyzer.hotspot_analyzer import build_ca_raw_map
    dm = MagicMock()
    stat1 = MagicMock()
    stat1.file = "pkg/foo.py"
    stat1.afferent_coupling = 7
    stat2 = MagicMock()
    stat2.file = "pkg/bar.py"
    stat2.afferent_coupling = 3
    dm._result.module_stats = [stat1, stat2]
    result = build_ca_raw_map(dm)
    assert result == {"pkg/foo.py": 7, "pkg/bar.py": 3}


# ── build_heatmap_map ─────────────────────────────────────────────────────────

def test_build_heatmap_map_normalizes_backslash():
    """Backslash paths in FileHeatmap.file are normalized to forward slash."""
    from tree_sitter_analyzer.hotspot_analyzer import build_heatmap_map

    @dataclass
    class _FH:
        file: str
        language: str = "python"
        functions: list = field(default_factory=list)
        total_complexity: int = 0
        avg_complexity: float = 0.0
        max_complexity: int = 0

    hm = _FH(file="pkg\\foo.py")
    result = build_heatmap_map([hm])  # type: ignore[arg-type]
    assert "pkg/foo.py" in result
    assert result["pkg/foo.py"] is hm


# ── build_test_focus: no-functions branch ─────────────────────────────────────

def test_build_test_focus_no_functions():
    """FakeHeatmap with empty functions list → TestFocus with function='(no functions)'."""
    hm = FakeHeatmap("a.py", max_complexity=0, functions=[])
    tf = build_test_focus(hm, "OK")
    assert tf.function == "(no functions)"
    assert tf.cc == 0
    assert "(low impact" in tf.suggestion


# ── build_import_edges_from_source ────────────────────────────────────────────

def test_build_import_edges_from_source_basic(tmp_path):
    """Import edges are built correctly from Python source files."""
    from tree_sitter_analyzer.hotspot_analyzer import build_import_edges_from_source

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "pkg" / "main.py").write_text("from pkg.utils import helper\n")

    scan = ["pkg/utils.py", "pkg/main.py"]
    edges = build_import_edges_from_source(str(tmp_path), scan)
    assert "pkg/main.py" in edges
    assert "pkg/utils.py" in edges["pkg/main.py"]
    # utils.py imports nothing in the scan set
    assert edges.get("pkg/utils.py", {}) == {}


# ── heatmaps_from_project_analysis ────────────────────────────────────────────

def test_heatmaps_from_project_analysis_empty_dir(tmp_path):
    """Empty project directory yields no heatmaps."""
    from tree_sitter_analyzer.hotspot_analyzer import heatmaps_from_project_analysis

    result = heatmaps_from_project_analysis(str(tmp_path))
    assert result == []


def test_heatmaps_from_project_analysis_transforms_result(tmp_path):
    """FileHeatmap objects are built correctly from analyze_project_heatmap output."""
    from tree_sitter_analyzer.hotspot_analyzer import heatmaps_from_project_analysis

    fake_result = {
        "file_heatmaps": [
            {
                "file": "src/foo.py",
                "language": "python",
                "total_complexity": 15,
                "avg_complexity": 7.5,
                "max_complexity": 12,
                "top_functions": [
                    {"name": "parse", "line": 10, "complexity": 12},
                    {"name": "load", "line": 40, "complexity": 3},
                ],
            }
        ]
    }
    with patch(
        "tree_sitter_analyzer.complexity_heatmap.analyze_project_heatmap",
        return_value=fake_result,
    ):
        result = heatmaps_from_project_analysis(str(tmp_path))

    assert len(result) == 1
    fh = result[0]
    assert fh.file == "src/foo.py"
    assert fh.language == "python"
    assert fh.max_complexity == 12
    assert fh.total_complexity == 15
    assert len(fh.functions) == 2
    assert fh.functions[0].name == "parse"
    assert fh.functions[0].complexity == 12


# ── _detect_source_dir: setuptools and edge cases ─────────────────────────────

def test_detect_source_dir_setuptools_packages(tmp_path):
    """pyproject.toml with [tool.setuptools] packages is resolved when hatch is absent."""
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    # Only setuptools key — no hatch section
    (tmp_path / "pyproject.toml").write_text(
        '[tool.setuptools]\npackages = ["mypkg"]\n'
    )
    assert _detect_source_dir(str(tmp_path)) == "mypkg"


def test_detect_source_dir_dot_prefix_dir_ignored(tmp_path):
    """Directories starting with '.' are skipped by the heuristic fallback."""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "__init__.py").write_text("")
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    # No pyproject.toml — heuristic must skip .hidden and pick mypkg
    assert _detect_source_dir(str(tmp_path)) == "mypkg"


# ── build_alias_ca_map: short-circuit on empty import_edges ──────────────────

def test_build_alias_ca_map_empty_import_edges_returns_copy():
    """When import_edges is empty, returns a new dict copy of ca_raw without rglob walk."""
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    ca_raw = {"a.py": 5, "b.py": 3}
    result = build_alias_ca_map(ca_raw, {}, project_root="/fake/path")
    assert result == {"a.py": 5, "b.py": 3}
    assert result is not ca_raw  # must be a distinct dict object


# ── compute_scores: alias_ca_map overrides raw Ca ────────────────────────────

def test_compute_scores_alias_ca_map_overrides_raw():
    """When alias_ca_map is provided, ca_alias uses alias value and score reflects it."""
    ca_map = {"a.py": 3}
    alias_ca_map_arg = {"a.py": 8}
    hm = FakeHeatmap("a.py", max_complexity=10, functions=[FakeFunc("f", 10)])
    entries = compute_scores(ca_map, {"a.py": hm}, alias_ca_map=alias_ca_map_arg)
    assert len(entries) == 1
    assert entries[0].ca_raw == 3
    assert entries[0].ca_alias == 8
    assert entries[0].score == 80.0  # 8 * 10


# ── _resolve_import_mod: bare-dot and empty-string edges ─────────────────────

def test_resolve_import_mod_bare_dot_resolves_to_package_init():
    """raw_mod='.' → empty mod after strip → resolves to pkg/__init__.py."""
    file_set = {"pkg/__init__.py", "pkg/foo.py"}
    result = _resolve_import_mod(".", "pkg/foo.py", file_set)
    assert result == "pkg/__init__.py"


def test_resolve_import_mod_empty_string_returns_none():
    """raw_mod='' has no dots and no module path → returns None (line 200 branch)."""
    file_set = {"a.py"}
    assert _resolve_import_mod("", "main.py", file_set) is None


# ── _iter_resolved_imports: dedup and pass-2 edge cases ──────────────────────

def test_iter_resolved_imports_deduplicates_pass1():
    """Same module imported on two lines — yielded exactly once (236->224 branch)."""
    file_set = {"pkg/utils.py"}
    text = "from pkg.utils import X\nfrom pkg.utils import Y\n"
    results = list(_iter_resolved_imports(text, "main.py", file_set))
    assert results == ["pkg/utils.py"]


def test_iter_resolved_imports_pass2_skips_non_identifier_name():
    """Pass-2 names that parse to empty string or non-identifier trigger continue (line 252)."""
    file_set = {"pkg/__init__.py", "pkg/utils.py", "pkg/foo.py"}
    # "(garbage)" after split("(")[0] → "" which is not an identifier
    text = "from . import utils, (garbage)\n"
    results = list(_iter_resolved_imports(text, "pkg/foo.py", file_set))
    assert results == ["pkg/utils.py"]


def test_iter_resolved_imports_pass2_skips_unresolvable():
    """Pass-2 name not in file_set → resolved is None, not yielded (254->248 branch)."""
    file_set = {"pkg/__init__.py", "pkg/utils.py"}
    text = "from . import nonexistent_module\n"
    results = list(_iter_resolved_imports(text, "pkg/foo.py", file_set))
    assert results == []


# ── build_import_edges_from_source: non-py skip and OSError ──────────────────

def test_build_import_edges_skips_non_python_files(tmp_path):
    """Non-.py files in scan list are skipped; result is empty (line 276 continue)."""
    from tree_sitter_analyzer.hotspot_analyzer import build_import_edges_from_source

    (tmp_path / "main.ts").write_text("import { Foo } from './utils'\n")
    scan = ["main.ts"]
    edges = build_import_edges_from_source(str(tmp_path), scan)
    assert edges == {}


def test_build_import_edges_oserror_on_read_is_skipped(tmp_path):
    """File listed in scan but not on disk → OSError caught, file skipped (lines 279-280)."""
    from tree_sitter_analyzer.hotspot_analyzer import build_import_edges_from_source

    # nonexistent_file.py is listed but does not exist → read_text raises FileNotFoundError
    edges = build_import_edges_from_source(str(tmp_path), ["nonexistent_file.py"])
    assert edges == {}


# ── build_ca_from_source_imports: non-py skip and OSError ────────────────────

def test_ca_from_source_imports_skips_non_python_files(tmp_path):
    """Non-.py files in scan list are skipped; ca result is empty (line 313 continue)."""
    (tmp_path / "main.ts").write_text("import { Foo } from './utils'\n")
    ca = build_ca_from_source_imports(str(tmp_path), ["main.ts"])
    assert ca == {}


def test_ca_from_source_imports_oserror_on_read_is_skipped(tmp_path):
    """File not on disk → OSError caught, file skipped (lines 316-317)."""
    ca = build_ca_from_source_imports(str(tmp_path), ["nonexistent_file.py"])
    assert ca == {}


# ── _detect_source_dir: malformed TOML and OSError on iterdir ────────────────

def test_detect_source_dir_malformed_toml_falls_back_to_heuristic(tmp_path):
    """pyproject.toml with invalid TOML → except Exception caught, heuristic used (100-101)."""
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_text("invalid = [unclosed bracket\n")
    # TOML parse fails → falls back to heuristic → finds mypkg
    assert _detect_source_dir(str(tmp_path)) == "mypkg"


def test_detect_source_dir_oserror_on_iterdir_returns_none():
    """Non-existent project_root → iterdir raises FileNotFoundError (OSError) → None (114-115)."""
    assert _detect_source_dir("/nonexistent_tsa_test_dir_xyz/project") is None


# ── _parse_python_reexports: OSError and false branches ──────────────────────

def test_parse_python_reexports_oserror_returns_empty():
    """Unreadable path → OSError caught → returns [] (lines 417-418)."""
    from pathlib import Path

    from tree_sitter_analyzer.hotspot_analyzer import _parse_python_reexports

    result = _parse_python_reexports(Path("/nonexistent/__init__.py"))
    assert result == []


def test_parse_python_reexports_skips_non_from_dot_lines(tmp_path):
    """Lines without 'from .' prefix are skipped (branch 421->419)."""
    from tree_sitter_analyzer.hotspot_analyzer import _parse_python_reexports

    init = tmp_path / "__init__.py"
    init.write_text("import os\nfrom pkg import Foo\nx = 1\n")
    result = _parse_python_reexports(init)
    assert result == []


def test_parse_python_reexports_skips_star_imports(tmp_path):
    """Star imports ('from .core import *') are skipped (branch 423->419)."""
    from tree_sitter_analyzer.hotspot_analyzer import _parse_python_reexports

    init = tmp_path / "__init__.py"
    init.write_text("from .core import *\n")
    result = _parse_python_reexports(init)
    assert result == []


# ── _parse_ts_reexports: OSError and false branch ────────────────────────────

def test_parse_ts_reexports_oserror_returns_empty():
    """Unreadable path → OSError caught → returns [] (lines 437-438)."""
    from pathlib import Path

    from tree_sitter_analyzer.hotspot_analyzer import _parse_ts_reexports

    result = _parse_ts_reexports(Path("/nonexistent/index.ts"))
    assert result == []


def test_parse_ts_reexports_skips_non_export_lines(tmp_path):
    """Lines with from clause but not starting with 'export' are skipped (branch 441->439)."""
    from tree_sitter_analyzer.hotspot_analyzer import _parse_ts_reexports

    index = tmp_path / "index.ts"
    index.write_text("import { Foo } from './utils'\nconst x = 1\n")
    result = _parse_ts_reexports(index)
    assert result == []


# ── build_alias_ca_map: known_files paths and missing module on disk ──────────

def test_build_alias_ca_map_known_files_python_branch(tmp_path):
    """known_files provided: uses list-based init discovery (line 472 True branch)."""
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("from .core import Foo\n")
    (tmp_path / "pkg" / "core.py").write_text("class Foo: pass\n")

    import_edges = {"main.py": {"pkg/__init__.py": 1}}
    ca_raw = {"pkg/__init__.py": 1, "pkg/core.py": 0}
    known_files = ["pkg/__init__.py", "pkg/core.py"]
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path), known_files=known_files)
    # __init__.py has 1 importer, re-exports core → core gets +1
    assert alias_ca["pkg/core.py"] == 1


def test_build_alias_ca_map_reexport_module_not_on_disk(tmp_path):
    """Re-exported module not on disk → suffix loop exhausted without match (491->489 branch)."""
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    (tmp_path / "pkg").mkdir()
    # __init__.py re-exports a module that doesn't exist on disk
    (tmp_path / "pkg" / "__init__.py").write_text("from .ghost import Foo\n")

    import_edges = {"main.py": {"pkg/__init__.py": 1}}
    ca_raw = {"pkg/__init__.py": 1}
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path))
    # ghost.py doesn't exist → no alias bump; ca_raw preserved as-is
    assert alias_ca == {"pkg/__init__.py": 1}


def test_build_alias_ca_map_known_files_typescript_branch(tmp_path):
    """known_files provided: uses list-based index discovery (line 504 True branch)."""
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export { Foo } from './utils'\n")
    (tmp_path / "src" / "utils.ts").write_text("export class Foo {}\n")

    import_edges = {"main.ts": {"src/index.ts": 1}}
    ca_raw = {"src/index.ts": 1, "src/utils.ts": 0}
    known_files = ["src/index.ts", "src/utils.ts"]
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path), known_files=known_files)
    # index.ts has 1 importer, re-exports utils → utils gets +1
    assert alias_ca["src/utils.ts"] == 1


def test_build_alias_ca_map_ts_reexport_module_not_on_disk(tmp_path):
    """TS re-exported module not on disk → suffix loop exhausted (521->519 branch)."""
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export { Ghost } from './ghost'\n")

    import_edges = {"main.ts": {"src/index.ts": 1}}
    ca_raw = {"src/index.ts": 1}
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path))
    # ghost.ts doesn't exist → no alias bump; ca_raw preserved
    assert alias_ca == {"src/index.ts": 1}


def test_build_alias_ca_map_first_suffix_missing_second_exists(tmp_path):
    """First suffix (.ts) doesn't exist but second (.js) does → 523->521 branch taken."""
    from tree_sitter_analyzer.hotspot_analyzer import build_alias_ca_map

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export { Foo } from './utils'\n")
    # Only .js exists, not .ts
    (tmp_path / "src" / "utils.js").write_text("export class Foo {}\n")

    import_edges = {"main.ts": {"src/index.ts": 1}}
    ca_raw = {"src/index.ts": 1, "src/utils.js": 0}
    alias_ca = build_alias_ca_map(ca_raw, import_edges, str(tmp_path))
    # Should find utils.js on second suffix attempt
    assert alias_ca["src/utils.js"] == 1
