"""Tests for the RFC-0025 Layer 1 incremental dependents index.

``edit action=safe`` is the pre-edit safety gate. Before this module the
"who imports this file" answer was re-derived on every call by walking the
whole tree and reading every source file, then substring-matching the target's
basename. These tests pin the two properties that replaced it:

1. the answer comes from the persisted AST index, and only files the index
   cannot vouch for are read (incremental derivation), and
2. the answer is never silently downgraded: the basis and the certification
   state are reported with it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.utils import dependents_index
from tree_sitter_analyzer.mcp.tools.utils.dependents_index import (
    DELTA_READ_CAP,
    DependentsAnswer,
    prefilter_needles,
    resolve_dependents,
)


def _write(root: Path, rel_path: str, body: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A small multi-package project with a cross-package basename collision."""
    root = tmp_path / "proj"
    root.mkdir()
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/target.py", "VALUE = 1\n")
    _write(root, "pkg/importer.py", "from .target import VALUE\n")
    _write(root, "pkg/absolute_importer.py", "from pkg.target import VALUE\n")
    # Same basename in another package: this must NOT be a dependent of
    # pkg/target.py, and pkg/importer.py must NOT be a dependent of it.
    _write(root, "other/__init__.py", "")
    _write(root, "other/target.py", "VALUE = 2\n")
    # Mentions the basename in prose only. The pre-L1 substring scan counted
    # this as a dependent.
    _write(root, "pkg/mentions_only.py", '"""Talks about target a lot."""\n')
    return root


def _index(root: Path) -> None:
    ASTCache(str(root)).index_project()


def test_index_derived_answer_is_exact_for_relative_and_absolute_imports(
    project: Path,
) -> None:
    _index(project)

    answer = resolve_dependents("pkg/target.py", project)

    assert answer.dependents == frozenset(
        {"pkg/absolute_importer.py", "pkg/importer.py"}
    )


def test_prose_mention_is_not_a_dependent(project: Path) -> None:
    # The pre-L1 scan matched the bare basename anywhere in the file text,
    # which made 782 of 821 reported dependents false on this repository.
    _index(project)

    answer = resolve_dependents("pkg/target.py", project)

    assert "pkg/mentions_only.py" not in answer.dependents


def test_same_basename_in_another_package_is_not_a_dependent(project: Path) -> None:
    _index(project)

    answer = resolve_dependents("other/target.py", project)

    assert answer.dependents == frozenset()


def test_fresh_index_reads_no_source_files(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(project)
    reads: list[str] = []
    original = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        reads.append(str(self))
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.basis, answer.delta_files, reads) == ("index", 0, [])


def test_only_the_edited_file_is_re_read_after_an_edit(project: Path) -> None:
    _index(project)
    _write(project, "pkg/late.py", "from .target import VALUE\n")

    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.basis, answer.delta_files) == ("index_delta", 1)


def test_a_file_created_after_indexing_is_still_found_as_a_dependent(
    project: Path,
) -> None:
    # Missing a dependent is the dangerous failure mode: the agent is told a
    # change is safe when it is not. A file the index has never seen must be
    # established by reading it, not skipped.
    _index(project)
    _write(project, "pkg/late.py", "from .target import VALUE\n")

    answer = resolve_dependents("pkg/target.py", project)

    assert "pkg/late.py" in answer.dependents


def test_answer_is_certified_when_the_call_graph_marker_is_current(
    project: Path,
) -> None:
    _index(project)

    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.certified, answer.certification_reason) == (True, None)


def test_revoked_call_graph_marker_labels_the_answer_uncertified(
    project: Path,
) -> None:
    # A revoked marker must not be read as authoritative, but it also must not
    # make the dependents set unavailable: the marker certifies the call-edge
    # pipeline, and this answer reads no call edges.
    _index(project)
    from tree_sitter_analyzer.cache.callgraph_state import (
        clear_call_graph_built_strict,
    )

    conn = sqlite3.connect(project / ".ast-cache" / "index.db")
    try:
        clear_call_graph_built_strict(conn)
    finally:
        conn.close()

    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.basis, answer.certified, answer.certification_reason) == (
        "index",
        False,
        "CALL_GRAPH_INCOMPLETE",
    )


def test_revoked_marker_still_returns_the_full_dependents_set(project: Path) -> None:
    _index(project)
    from tree_sitter_analyzer.cache.callgraph_state import (
        clear_call_graph_built_strict,
    )

    conn = sqlite3.connect(project / ".ast-cache" / "index.db")
    try:
        clear_call_graph_built_strict(conn)
    finally:
        conn.close()

    answer = resolve_dependents("pkg/target.py", project)

    assert answer.dependents == frozenset(
        {"pkg/absolute_importer.py", "pkg/importer.py"}
    )


def test_absent_index_falls_back_to_the_scan_and_says_so(project: Path) -> None:
    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.basis, answer.certified, answer.certification_reason) == (
        "scan",
        False,
        "INDEX_ABSENT",
    )


def test_scan_fallback_is_a_superset_of_the_index_answer(project: Path) -> None:
    # The fallback must never be smaller than the derived answer: reporting a
    # smaller set is the failure mode that causes a wrong edit.
    scan = resolve_dependents("pkg/target.py", project)
    _index(project)
    indexed = resolve_dependents("pkg/target.py", project)

    assert indexed.dependents <= scan.dependents


def test_delta_cap_exceeded_falls_back_to_the_scan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(project)
    monkeypatch.setattr(dependents_index, "DELTA_READ_CAP", 0)
    _write(project, "pkg/late.py", "from .target import VALUE\n")

    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.basis, answer.certification_reason) == (
        "scan",
        "DELTA_CAP_EXCEEDED",
    )


def test_delta_read_cap_is_a_positive_bound() -> None:
    assert DELTA_READ_CAP == 400


def test_unreadable_file_is_reported_rather_than_dropped(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _index(project)
    _write(project, "pkg/late.py", "from .target import VALUE\n")
    original = Path.read_text

    def failing_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "late.py":
            raise OSError("permission denied")
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", failing_read_text)

    answer = resolve_dependents("pkg/target.py", project)

    assert (answer.unestablished, answer.certification_reason) == (
        ("pkg/late.py",),
        "UNESTABLISHED_FILES",
    )


def test_out_of_scope_target_reports_an_unestablished_empty_set(
    project: Path,
) -> None:
    # A .cs target cannot be named by any resolver this module runs, so the
    # empty set must not look like a proven "nothing imports this".
    _write(project, "pkg/Thing.cs", "class Thing {}\n")
    _index(project)

    answer = resolve_dependents("pkg/Thing.cs", project)

    assert (
        answer.dependents,
        answer.certified,
        answer.certification_reason,
        answer.unestablished,
    ) == (frozenset(), False, "TARGET_OUT_OF_SCOPE", ("pkg/Thing.cs",))


def test_index_row_the_enumeration_missed_is_reconciled(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the enumeration disagrees with the indexer (e.g. os.walk follows a
    # symlinked directory and scandir(follow_symlinks=False) does not), the
    # missed file must be read, not dropped: dropping it loses a dependent.
    _index(project)
    real_inventory = dependents_index._live_inventory

    def blind_inventory(root: Path) -> dict[str, tuple[int, int]]:
        inventory = real_inventory(root)
        inventory.pop("pkg/importer.py", None)
        return inventory

    monkeypatch.setattr(dependents_index, "_live_inventory", blind_inventory)

    answer = resolve_dependents("pkg/target.py", project)

    assert "pkg/importer.py" in answer.dependents


def test_prefilter_covers_a_parent_package_relative_import() -> None:
    # ``from .. import lua_plugin`` names the package initializer without
    # containing the initializer's own path or dotted module. A prefilter built
    # only from those needles would drop a real dependent.
    needles = prefilter_needles("a/b/lua_plugin/__init__.py")

    assert "lua_plugin" in needles


def test_prefilter_covers_a_directory_index_import() -> None:
    # ``import x from "./dir"`` resolves to ``dir/index.ts``.
    needles = prefilter_needles("a/dir/index.ts")

    assert needles == frozenset({"index", "dir"})


def test_prefilter_covers_a_java_wildcard_package_import() -> None:
    # ``import com.foo.*;`` never names Bar.
    needles = prefilter_needles("com/foo/Bar.java")

    assert "foo" in needles


def test_mjs_importer_of_an_mts_target_is_a_dependent(tmp_path: Path) -> None:
    # .mjs/.cjs/.mts/.cts support and the ESM dispatch fix landed recently; the
    # index-derived answer must not regress them.
    root = tmp_path / "esm"
    root.mkdir()
    _write(root, "src/target.mts", "export const V = 1;\n")
    _write(root, "src/consumer.mts", 'import { V } from "./target.mjs";\n')
    _index(root)

    answer = resolve_dependents("src/target.mts", root)

    assert answer.dependents == frozenset({"src/consumer.mts"})


def test_answer_shape_is_frozen() -> None:
    answer = DependentsAnswer(
        dependents=frozenset({"a.py"}),
        basis="index",
        certified=True,
        certification_reason=None,
        scanned_files=1,
        delta_files=0,
        unestablished=(),
    )

    with pytest.raises(AttributeError):
        answer.basis = "scan"  # type: ignore[misc]


def test_index_derivation_reads_less_than_the_scan(project: Path) -> None:
    # A relationship, not a millisecond ceiling: the derived path must read
    # strictly fewer source files than the whole-tree scan it replaces.
    _index(project)
    reads_index: list[str] = []
    reads_scan: list[str] = []
    original = Path.read_text

    def make_counter(sink: list[str]):
        def counting(self: Path, *args: object, **kwargs: object) -> str:
            sink.append(str(self))
            return original(self, *args, **kwargs)  # type: ignore[arg-type]

        return counting

    import unittest.mock as mock

    with mock.patch.object(Path, "read_text", make_counter(reads_index)):
        resolve_dependents("pkg/target.py", project)
    with mock.patch.object(Path, "read_text", make_counter(reads_scan)):
        dependents_index.scan_dependents("pkg/target.py", project)

    assert len(reads_index) < len(reads_scan)
