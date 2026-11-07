"""``setup`` installs the corpus from the copy versioned in the repo, never from dogfood folders.

The small corpus files (targets, hand labels, manifest) live byte for byte in
``benchmarks/callers_gate/corpus_data/``. GT2 is too large to version: the
versioned manifest pins its digest, and setup accepts only a gate-root copy
with exactly that digest.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from benchmarks.callers_gate import corpus
from benchmarks.callers_gate.layout import GT2_REPOS, LABEL_REPOS, REPOS, Layout

CORPUS_TARGETS = 2457


def _quiet(_msg: str) -> None:
    return None


# -- the versioned corpus itself ---------------------------------------------


def test_versioned_corpus_matches_its_manifest() -> None:
    manifest = corpus.versioned_manifest()
    for rel, digest in manifest.items():
        if rel.startswith("gt2/"):
            continue
        assert corpus.sha256_file(corpus.VERSIONED_CORPUS / rel) == digest, rel


def test_versioned_corpus_covers_every_repo_and_has_no_gt2() -> None:
    manifest = corpus.versioned_manifest()
    assert {f"targets/{name}.json" for name in REPOS} <= set(manifest)
    assert {f"labels/{name}.json" for name in LABEL_REPOS} <= set(manifest)
    assert {f"gt2/{name}.json" for name in GT2_REPOS} <= set(manifest)
    assert not (corpus.VERSIONED_CORPUS / "gt2").exists()
    total = sum(
        len(json.loads((corpus.VERSIONED_CORPUS / f"targets/{n}.json").read_bytes()))
        for n in REPOS
    )
    assert total == CORPUS_TARGETS


def test_versioned_manifest_with_a_wrong_digest_is_refused(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    (source / "targets" / "rich.json").write_bytes(b"[2]")
    with pytest.raises(corpus.CorpusError, match="versioned corpus file changed"):
        corpus.versioned_manifest(source)


# -- install_corpus on a fake versioned corpus -------------------------------


def _fake_source(tmp_path: Path) -> Path:
    """A versioned corpus with one target file, one label file and one GT2 digest."""
    source = tmp_path / "versioned"
    (source / "targets").mkdir(parents=True)
    (source / "labels").mkdir()
    (source / "targets" / "rich.json").write_bytes(b"[\r\n{}]")
    (source / "labels" / "hono.json").write_bytes(b'{"_note": "x"}\n')
    gt2 = tmp_path / "gt2-rich.json"
    gt2.write_bytes(b'{"callers": {}}')
    manifest = {
        "gt2/rich.json": corpus.sha256_file(gt2),
        "labels/hono.json": corpus.sha256_file(source / "labels" / "hono.json"),
        "targets/rich.json": corpus.sha256_file(source / "targets" / "rich.json"),
    }
    (source / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return source


def _place_gt2(tmp_path: Path, layout: Layout) -> None:
    layout.gt2("rich").parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_path / "gt2-rich.json", layout.gt2("rich"))


def test_install_copies_the_versioned_files_byte_for_byte(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    _place_gt2(tmp_path, layout)
    manifest = corpus.install_corpus(layout, _quiet, source)
    assert layout.targets("rich").read_bytes() == b"[\r\n{}]"
    assert layout.labels("hono").read_bytes() == b'{"_note": "x"}\n'
    assert (layout.corpus / "manifest.json").read_bytes() == (
        source / "manifest.json"
    ).read_bytes()
    assert corpus.verify_corpus(layout, expected=manifest) == manifest


def test_install_without_gt2_fails_clearly_and_writes_nothing(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    with pytest.raises(corpus.CorpusError, match=r"gt2/rich\.json.*not reproducible"):
        corpus.install_corpus(layout, _quiet, source)
    assert not layout.corpus.exists()


def test_install_refuses_a_gt2_with_another_digest(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    _place_gt2(tmp_path, layout)
    layout.gt2("rich").write_bytes(b'{"callers": {"x": []}}')
    with pytest.raises(corpus.CorpusError, match=r"gt2/rich\.json.*differs"):
        corpus.install_corpus(layout, _quiet, source)


def test_install_restores_an_edited_target_file(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    _place_gt2(tmp_path, layout)
    corpus.install_corpus(layout, _quiet, source)
    layout.targets("rich").write_bytes(b"[]")
    corpus.install_corpus(layout, _quiet, source)
    assert layout.targets("rich").read_bytes() == b"[\r\n{}]"


def test_install_keeps_matching_files_untouched(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    _place_gt2(tmp_path, layout)
    corpus.install_corpus(layout, _quiet, source)
    before = layout.targets("rich").stat().st_mtime_ns
    logged: list[str] = []
    corpus.install_corpus(layout, logged.append, source)
    assert layout.targets("rich").stat().st_mtime_ns == before
    assert not any("copied" in line for line in logged)


def test_install_with_no_versioned_corpus_fails_clearly(tmp_path: Path) -> None:
    layout = Layout(tmp_path / "root")
    with pytest.raises(corpus.CorpusError, match="versioned corpus manifest"):
        corpus.install_corpus(layout, _quiet, tmp_path / "missing")


# -- the gate-root copy must match the versioned corpus ----------------------


def test_a_gate_root_manifest_that_differs_from_the_versioned_one_is_refused(
    tmp_path: Path,
) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    _place_gt2(tmp_path, layout)
    manifest = corpus.install_corpus(layout, _quiet, source)
    other = {**manifest, "targets/rich.json": "0" * 64}
    with pytest.raises(corpus.CorpusError, match="differs from the versioned corpus"):
        corpus.verify_corpus(layout, expected=other)


def test_the_gate_check_uses_the_versioned_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _fake_source(tmp_path)
    layout = Layout(tmp_path / "root")
    _place_gt2(tmp_path, layout)
    corpus.install_corpus(layout, _quiet, source)
    with pytest.raises(corpus.CorpusError, match="differs from the versioned corpus"):
        corpus.verify_gate_corpus(layout)
    monkeypatch.setattr(corpus, "VERSIONED_CORPUS", source)
    assert corpus.verify_gate_corpus(layout) == corpus.versioned_manifest(source)


def test_setup_installs_the_corpus_before_cloning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing GT2 stops setup before any network clone starts."""
    cloned: list[str] = []
    monkeypatch.setattr(
        corpus, "clone_repo", lambda _l, pin, _log: cloned.append(pin.name)
    )
    monkeypatch.setattr(corpus, "VERSIONED_CORPUS", _fake_source(tmp_path))
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    with pytest.raises(corpus.CorpusError, match="not reproducible"):
        corpus.setup(Layout(tmp_path / "root"), python, _quiet)
    assert cloned == []
