"""The SCIP manifest binds an index to one exact project state (stale = ignored)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.mcp.tools.scip_project import git, install_index, make_project
from tree_sitter_analyzer.mcp.tools import callers_scip_manifest as m


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, Path]:
    root = make_project(tmp_path / "p")
    return root, install_index(root)


def _reason(root: Path, index: Path) -> str | None:
    manifest = m.read_manifest(m.manifest_path(index))
    state = m.project_state(root, exclude=(index, m.manifest_path(index)))
    return m.stale_reason(manifest, m.file_sha256(index), state)


def test_fresh_manifest_matches(project: tuple[Path, Path]) -> None:
    root, index = project
    data = json.loads(m.manifest_path(index).read_text(encoding="utf-8"))
    assert data["format"] == m.MANIFEST_FORMAT
    assert data["dirty"] == {}
    assert data["indexer"] == {"name": "scip-typescript", "version": "0.6.1"}
    # TSA's own cache (the index lives there too) never counts as dirty.
    (root / ".ast-cache" / "other.db").write_text("x", encoding="utf-8")
    assert _reason(root, index) is None


def test_edited_file_is_stale(project: tuple[Path, Path]) -> None:
    root, index = project
    (root / "src" / "app.ts").write_text("export {}\n", encoding="utf-8")
    assert _reason(root, index) == "uncommitted files differ"


def test_untracked_and_deleted_files_are_stale(project: tuple[Path, Path]) -> None:
    root, index = project
    (root / "src" / "new.ts").write_text("export {}\n", encoding="utf-8")
    assert _reason(root, index) == "uncommitted files differ"
    (root / "src" / "new.ts").unlink()
    (root / "src" / "use.ts").unlink()
    state = m.project_state(root)
    assert state is not None and state["dirty"] == {"src/use.ts": m.DELETED}


def test_new_commit_is_stale(project: tuple[Path, Path]) -> None:
    root, index = project
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "more")
    assert _reason(root, index) == "git tree differs"


def test_lockfile_change_is_stale(project: tuple[Path, Path]) -> None:
    root, index = project
    # A lockfile git cannot see (ignored) still pins the dependency set.
    (root / ".git" / "info" / "exclude").write_text("yarn.lock\n", encoding="utf-8")
    (root / "yarn.lock").write_text("a\n", encoding="utf-8")
    m.write_manifest(root, index)
    assert _reason(root, index) is None
    (root / "yarn.lock").write_text("b\n", encoding="utf-8")
    assert _reason(root, index) == "lockfiles differ"


def test_rewritten_index_is_stale(project: tuple[Path, Path]) -> None:
    root, index = project
    index.write_bytes(index.read_bytes() + b"\n")
    assert (
        _reason(root, index) == "index file differs from the one the manifest describes"
    )


def test_unreadable_git_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert m.project_state(tmp_path) is None
    manifest = {"index_sha256": "a", "git_tree": "t", "dirty": {}, "lockfiles": {}}
    assert m.stale_reason(manifest, "a", None) == "project state unreadable (git)"
    with pytest.raises(m.ManifestError):
        m.write_manifest(tmp_path, tmp_path / "index.scip")


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '{"format": 99}', '{"format": 1, "index_sha256": 3}'],
)
def test_malformed_manifest(tmp_path: Path, content: str) -> None:
    path = tmp_path / "index.scip.manifest.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(m.ManifestError):
        m.read_manifest(path)
    with pytest.raises(m.ManifestError, match="no manifest"):
        m.read_manifest(tmp_path / "missing.json")


def test_project_in_a_subdirectory_of_a_repository(tmp_path: Path) -> None:
    repo = make_project(tmp_path / "mono")
    sub = repo / "src"
    (sub / "app.ts").write_text("export {}\n", encoding="utf-8")
    (sub / ".ast-cache").mkdir()
    (sub / ".ast-cache" / "x.db").write_text("x", encoding="utf-8")
    state = m.project_state(sub)
    assert state is not None
    assert list(state["dirty"]) == ["src/app.ts"]
    assert state["dirty"]["src/app.ts"] != m.DELETED


def test_status_parser_keeps_both_sides_of_a_rename() -> None:
    raw = b"R  new.ts\0old.ts\0?? u.ts\0 M m.ts\0\0"
    assert m._status_paths(raw) == ["new.ts", "old.ts", "u.ts", "m.ts"]


def test_cli_writes_and_checks(
    project: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, index = project
    rel = index.relative_to(root).as_posix()
    assert m.main(["--project", str(root), "--index", rel]) == 0
    assert m.main(["--project", str(root), "--index", str(index), "--check"]) == 0
    assert "fresh" in capsys.readouterr().out
    (root / "src" / "app.ts").write_text("export {}\n", encoding="utf-8")
    assert m.main(["--project", str(root), "--index", str(index), "--check"]) == 1
    assert m.main(["--project", str(root), "--index", str(root / "none.scip")]) == 2
