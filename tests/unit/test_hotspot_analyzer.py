"""Unit tests for hotspot_analyzer.py and output_schema.py (pure functions only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

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
