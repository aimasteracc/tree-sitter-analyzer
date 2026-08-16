"""RFC-0022 P0.4 zero-write capture payload differential contract.

The zero-write backend (``diff_snapshot_readonly_capture``) must reproduce
the frozen capture (``diff_snapshot_capture._capture_payload``) exactly on
identical source state: changed-file records, old/new bytes, and the
normalized patch — otherwise task routes comparing P0.2 payloads would
diverge between the two backends. These tests prove byte-equality across
clean/dirty/untracked/deleted/binary/symlink/rename/staged states, pin the
documented divergences (content-modified worktree moves surface as
delete+add pairs; conversion-active repositories fail closed), and assert
the zero-write invocation set never materializes a temporary index.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST
from tree_sitter_analyzer.diff_snapshot_capture import _capture_payload
from tree_sitter_analyzer.diff_snapshot_readonly import oracle_generation_readonly
from tree_sitter_analyzer.diff_snapshot_readonly_capture import (
    _git_quote_path,
    _no_index_new_file_patch,
    _pair_exact_renames,
    _patch_section_paths,
    capture_payload_readonly,
)
from tree_sitter_analyzer.source_oracle import SourceOracleError
from tree_sitter_analyzer.source_oracle_git import GitEpoch, oracle_generation

_BUDGET = 64 * 1024 * 1024


@pytest.fixture()
def git_repo(tmp_path) -> str:
    root = str(tmp_path)
    subprocess.run(["git", "init", "-q", root], check=True)
    for cfg in (
        ["user.email", "t@t"],
        ["user.name", "t"],
        ["maintenance.auto", "false"],
        ["gc.auto", "0"],
    ):
        subprocess.run(["git", "-C", root, "config", *cfg], check=True)
    (tmp_path / "base.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("keep = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "init"], check=True)
    return root


def _payloads(root: str, mode: str) -> tuple[bytes, tuple, bytes, tuple]:
    """Capture both backends on the same source state and return pairs."""
    frozen_epochs: list[GitEpoch] = []
    readonly_epochs: list[GitEpoch] = []
    frozen_manifest: dict = {}
    readonly_manifest: dict = {}
    frozen_gen, _ = oracle_generation(
        root, mode, manifest=frozen_manifest, epoch_out=frozen_epochs
    )
    readonly_gen, _ = oracle_generation_readonly(
        root, mode, manifest=readonly_manifest, epoch_out=readonly_epochs
    )
    assert frozen_gen == readonly_gen
    deadline = time.monotonic() + 60.0
    frozen_patch, frozen_files = _capture_payload(
        root,
        mode,
        deadline,
        _BUDGET,
        expected_manifest=frozen_manifest,
        epoch=frozen_epochs[0],
    )
    readonly_patch, readonly_files = capture_payload_readonly(
        root,
        mode,
        deadline,
        _BUDGET,
        expected_manifest=readonly_manifest,
        epoch=readonly_epochs[0],
    )
    return frozen_patch, frozen_files, readonly_patch, readonly_files


def _assert_equal_payloads(root: str, mode: str, expected_records: int) -> None:
    frozen_patch, frozen_files, readonly_patch, readonly_files = _payloads(root, mode)
    assert [file.record.to_dict() for file in frozen_files] == [
        file.record.to_dict() for file in readonly_files
    ]
    assert [
        (file.record.path, file.old_bytes, file.new_bytes) for file in frozen_files
    ] == [(file.record.path, file.old_bytes, file.new_bytes) for file in readonly_files]
    assert frozen_patch == readonly_patch
    assert len(frozen_files) == expected_records


@POSIX_SNAPSHOT_TEST
def test_clean_repo_payloads_match(git_repo: str) -> None:
    _assert_equal_payloads(git_repo, "diff", 0)
    _assert_equal_payloads(git_repo, "staged", 0)


@POSIX_SNAPSHOT_TEST
def test_dirty_payloads_match(git_repo: str) -> None:
    Path(git_repo, "base.py").write_text("value = 2\nline2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_untracked_text_and_dirty_payloads_match(git_repo: str) -> None:
    Path(git_repo, "base.py").write_text("value = 3\n", encoding="utf-8")
    Path(git_repo, "new.py").write_text("brand = 'new'\n", encoding="utf-8")
    Path(git_repo, ".gitignore").write_text("*.log\n", encoding="utf-8")
    Path(git_repo, "ignored.log").write_text("noise\n", encoding="utf-8")
    # base.py modified, .gitignore and new.py added; ignored.log excluded.
    _assert_equal_payloads(git_repo, "diff", 3)


@POSIX_SNAPSHOT_TEST
def test_deleted_payloads_match(git_repo: str) -> None:
    Path(git_repo, "keep.py").unlink()
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_untracked_executable_payloads_match(git_repo: str) -> None:
    script = Path(git_repo, "run.sh")
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o755)
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_untracked_no_newline_payloads_match(git_repo: str) -> None:
    Path(git_repo, "nonl.txt").write_bytes(b"no-newline")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_untracked_binary_payloads_match(git_repo: str) -> None:
    Path(git_repo, "bin.dat").write_bytes(b"\x00\x01\x02\x03binary\x00")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_untracked_symlink_payloads_match(git_repo: str) -> None:
    os.symlink("base.py", os.path.join(git_repo, "link.py"))
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_exact_worktree_rename_payloads_match(git_repo: str) -> None:
    os.rename(os.path.join(git_repo, "base.py"), os.path.join(git_repo, "moved.py"))
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_rename_plus_dirty_payloads_match(git_repo: str) -> None:
    os.rename(os.path.join(git_repo, "base.py"), os.path.join(git_repo, "moved.py"))
    Path(git_repo, "keep.py").write_text("keep = 2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 2)


@POSIX_SNAPSHOT_TEST
def test_staged_add_payloads_match(git_repo: str) -> None:
    Path(git_repo, "staged.py").write_text("s = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "staged.py"], check=True)
    # Worktree-only dirt must not leak into staged mode.
    Path(git_repo, "keep.py").write_text("keep = 2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "staged", 1)


@POSIX_SNAPSHOT_TEST
def test_staged_rename_payloads_match(git_repo: str) -> None:
    Path(git_repo, "base.py").write_text("value = 9\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "base.py"], check=True)
    subprocess.run(["git", "-C", git_repo, "mv", "keep.py", "renamed.py"], check=True)
    _assert_equal_payloads(git_repo, "staged", 2)


@POSIX_SNAPSHOT_TEST
def test_double_dirty_payloads_match(git_repo: str) -> None:
    Path(git_repo, "base.py").write_text("value = 5\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "base.py"], check=True)
    Path(git_repo, "base.py").write_text("value = 6\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_modified_worktree_move_surfaces_delete_plus_add(git_repo: str) -> None:
    """Documented divergence: an inexact move is D+A, never a fake R."""
    Path(git_repo, "base.py").write_text("value = 1\n", encoding="utf-8")
    os.rename(os.path.join(git_repo, "base.py"), os.path.join(git_repo, "moved.py"))
    Path(git_repo, "moved.py").write_text("value = 1\nchanged\n", encoding="utf-8")
    _readonly_epochs: list[GitEpoch] = []
    manifest: dict = {}
    oracle_generation_readonly(
        git_repo, "diff", manifest=manifest, epoch_out=_readonly_epochs
    )
    _patch, files = capture_payload_readonly(
        git_repo,
        "diff",
        time.monotonic() + 60.0,
        _BUDGET,
        expected_manifest=manifest,
        epoch=_readonly_epochs[0],
    )
    assert [(file.record.path, file.record.status) for file in files] == [
        ("base.py", "D"),
        ("moved.py", "A"),
    ]
    assert files[0].old_bytes == b"value = 1\n"
    assert files[1].new_bytes == b"value = 1\nchanged\n"


@POSIX_SNAPSHOT_TEST
def test_conversion_guard_fails_closed_on_autocrlf(git_repo: str) -> None:
    subprocess.run(
        ["git", "-C", git_repo, "config", "core.autocrlf", "true"], check=True
    )
    Path(git_repo, "base.py").write_bytes(b"value = 1\r\nline2\r\n")
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION"):
        _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_conversion_guard_passes_without_crlf(git_repo: str) -> None:
    subprocess.run(
        ["git", "-C", git_repo, "config", "core.autocrlf", "true"], check=True
    )
    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_conversion_guard_fails_closed_on_eol_attribute(git_repo: str) -> None:
    Path(git_repo, ".gitattributes").write_text(
        "base.py text eol=crlf\n", encoding="utf-8"
    )
    Path(git_repo, "base.py").write_bytes(b"value = 1\r\n")
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION"):
        _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_capture_never_materializes_temporary_index(
    git_repo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The zero-write capture must never invoke the temp-index machinery."""
    import tempfile

    mkstemp_calls: list[str] = []
    mkdtemp_calls: list[str] = []

    def spy_mkstemp(*args, **kwargs):
        mkstemp_calls.append("mkstemp")
        return tempfile.mkstemp(*args, **kwargs)

    def spy_mkdtemp(*args, **kwargs):
        mkdtemp_calls.append("mkdtemp")
        return tempfile.mkdtemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
    monkeypatch.setattr(tempfile, "mkdtemp", spy_mkdtemp)
    import tree_sitter_analyzer.diff_snapshot_readonly as readonly_module

    seen_env: dict[str, str] = {}
    original_runner = readonly_module.run_git_readonly

    def spy(root, args, *, deadline, limit, env=None, input_=None, ok_returncodes=None):
        seen_env.update(dict(env or {}))
        return original_runner(
            root,
            args,
            deadline=deadline,
            limit=limit,
            env=env,
            input_=input_,
            ok_returncodes=ok_returncodes or frozenset({0}),
        )

    monkeypatch.setattr(readonly_module, "run_git_readonly", spy)
    _readonly_epochs: list[GitEpoch] = []
    manifest: dict = {}
    oracle_generation_readonly(
        git_repo, "diff", manifest=manifest, epoch_out=_readonly_epochs
    )
    capture_payload_readonly(
        git_repo,
        "diff",
        time.monotonic() + 60.0,
        _BUDGET,
        expected_manifest=manifest,
        epoch=_readonly_epochs[0],
    )
    assert mkstemp_calls == []
    assert mkdtemp_calls == []
    assert "GIT_INDEX_FILE" not in seen_env
    assert seen_env.get("GIT_OPTIONAL_LOCKS") == "0"


@POSIX_SNAPSHOT_TEST
def test_no_index_patch_accepts_exit_one(git_repo: str) -> None:
    Path(git_repo, "brand-new.py").write_text("x = 1\n", encoding="utf-8")
    patch = _no_index_new_file_patch(
        git_repo, b"brand-new.py", time.monotonic() + 60.0, 1024 * 1024
    )
    assert patch.startswith(
        b"diff --git a/brand-new.py b/brand-new.py\nnew file mode 100644\n"
    )
    assert patch.endswith(b"+x = 1\n")


@POSIX_SNAPSHOT_TEST
def test_patch_section_paths_splits_and_unquotes(git_repo: str) -> None:
    # Git C-quotes the whole a/ path (including the prefix) when needed.
    raw = (
        b"diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n"
        b'\ndiff --git "a/we\tird" "b/we\tird"\n--- a/"we\tird"\n'
    )
    sections = _patch_section_paths(raw)
    assert set(sections) == {b"a.txt", b"we\tird"}
    assert sections[b"a.txt"].startswith(b"diff --git a/a.txt")
    # The split token for the second section lacks the "diff --git " prefix
    # and the header embeds the real tab byte, not the C-quoted escape.
    assert sections[b"we\tird"].startswith(b'"a/we\tird" "b/we\tird"')


@POSIX_SNAPSHOT_TEST
def test_git_quote_path_matches_git_style() -> None:
    assert _git_quote_path(b"plain.txt") == b"plain.txt"
    assert _git_quote_path(b"a\tb") == b'"a\\tb"'
    assert _git_quote_path(b'a"b') == b'"a\\"b"'
    assert _git_quote_path(b"n\x01l") == b'"n\\001l"'
    assert _git_quote_path("é".encode()) == b'"\\303\\251"'


@POSIX_SNAPSHOT_TEST
def test_pair_exact_renames_pairs_identical_content(git_repo: str) -> None:
    oid = subprocess.run(
        ["git", "-C", git_repo, "hash-object", "--stdin"],
        input=b"value = 1\n",
        check=True,
        capture_output=True,
    ).stdout.strip()
    index_entries = {b"old.py": b"100644 " + oid + b" 0"}
    safe_paths = {
        b"new.py": type(
            "Safe",
            (),
            {"kind": "file", "data": b"value = 1\n", "metadata": (b"x,100,33188",)},
        )()
    }
    rows = [("D", None, b"old.py"), ("A", None, b"new.py")]
    paired = _pair_exact_renames(
        git_repo, rows, index_entries, safe_paths, time.monotonic() + 60.0, 1024
    )
    assert paired == [("R", b"old.py", b"new.py")]


@POSIX_SNAPSHOT_TEST
def test_pair_exact_renames_keeps_modified_moves_unpaired(git_repo: str) -> None:
    oid = subprocess.run(
        ["git", "-C", git_repo, "hash-object", "--stdin"],
        input=b"value = 1\n",
        check=True,
        capture_output=True,
    ).stdout.strip()
    index_entries = {b"old.py": b"100644 " + oid + b" 0"}
    safe_paths = {
        b"new.py": type(
            "Safe",
            (),
            {
                "kind": "file",
                "data": b"value = 1\nchanged\n",
                "metadata": (b"x,100,33188",),
            },
        )()
    }
    rows = [("D", None, b"old.py"), ("A", None, b"new.py")]
    paired = _pair_exact_renames(
        git_repo, rows, index_entries, safe_paths, time.monotonic() + 60.0, 1024
    )
    assert [row[0] for row in paired] == ["D", "A"]


@POSIX_SNAPSHOT_TEST
@pytest.mark.slow_ok  # two full captures + publish: real git subprocess work
def test_dirty_gitlink_payloads_match(git_repo: str) -> None:
    """A dirty submodule yields one opaque dirty_gitlink record, no patch."""
    sub_repo = Path(git_repo, "vendor")
    sub_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(sub_repo)], check=True)
    for cfg in (["user.email", "t@t"], ["user.name", "t"]):
        subprocess.run(["git", "-C", str(sub_repo), "config", *cfg], check=True)
    (sub_repo / "lib.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(sub_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(sub_repo), "commit", "-qm", "sub"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "submodule", "add", "-q", str(sub_repo), "vendor"],
        check=True,
    )
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "add-sub"], check=True)
    (sub_repo / "lib.py").write_text("x = 2\n", encoding="utf-8")
    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 2)
    # The dirty gitlink record is opaque: no patch section, unsupported.
    _readonly_epochs: list[GitEpoch] = []
    manifest: dict = {}
    oracle_generation_readonly(
        git_repo, "diff", manifest=manifest, epoch_out=_readonly_epochs
    )
    _patch, files = capture_payload_readonly(
        git_repo,
        "diff",
        time.monotonic() + 60.0,
        _BUDGET,
        expected_manifest=manifest,
        epoch=_readonly_epochs[0],
    )
    gitlink_records = [file.record for file in files if file.record.path == "vendor"]
    assert len(gitlink_records) == 1
    assert gitlink_records[0].status == "M"
    assert gitlink_records[0].unsupported_kind == "dirty_gitlink"
    assert gitlink_records[0].patch_available is False
    assert gitlink_records[0].old_kind == "gitlink"
    assert gitlink_records[0].new_kind == "gitlink"
    assert b"vendor" not in _patch


@POSIX_SNAPSHOT_TEST
@pytest.mark.slow_ok  # two full captures + publish: real git subprocess work
def test_clean_gitlink_payloads_match(git_repo: str) -> None:
    """A clean submodule produces no record in either backend."""
    sub_repo = Path(git_repo, "vendor")
    sub_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(sub_repo)], check=True)
    for cfg in (["user.email", "t@t"], ["user.name", "t"]):
        subprocess.run(["git", "-C", str(sub_repo), "config", *cfg], check=True)
    (sub_repo / "lib.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(sub_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(sub_repo), "commit", "-qm", "sub"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "submodule", "add", "-q", str(sub_repo), "vendor"],
        check=True,
    )
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "add-sub"], check=True)
    _assert_equal_payloads(git_repo, "diff", 0)


def _registry_snapshot_fields(
    root: str, mode: str, readonly: bool
) -> tuple[dict[str, object], dict[str, object]]:
    """Create one snapshot via a backend and expose its published fields."""
    import tree_sitter_analyzer.diff_snapshot_registry as snapshots

    snapshots.reset_registry()
    created = snapshots.REGISTRY.create(root, mode, [], readonly=readonly)
    assert created.get("success"), created
    consumer, error = snapshots.REGISTRY.acquire(str(created["diff_snapshot_id"]), root)
    assert error is None
    try:
        snapshot = consumer.snapshot
        fields = {
            "source_generation": created["source_generation"],
            "changed_records": created["changed_records"],
            "assessed_scope_paths": created["assessed_scope_paths"],
            "patch": snapshot.normalized_patch,
            "files_bytes": tuple(
                (file.record.path, file.old_bytes, file.new_bytes)
                for file in snapshot.files
            ),
            "inventory_paths": snapshot.inventory_paths,
            "staged_source_matches_worktree": (snapshot.staged_source_matches_worktree),
            "staged_config_matches_worktree": snapshot.staged_config_matches_worktree,
            "constraint_config_path": snapshot.constraint_config_path,
            "constraint_config_data": snapshot.constraint_config_data,
            "constraint_config_error": snapshot.constraint_config_error,
        }
        return created, fields
    finally:
        consumer.release()


def _assert_equal_registry_snapshots(root: str, mode: str) -> None:
    _frozen_created, frozen = _registry_snapshot_fields(root, mode, False)
    _readonly_created, readonly = _registry_snapshot_fields(root, mode, True)
    assert frozen == readonly


@POSIX_SNAPSHOT_TEST
@pytest.mark.slow_ok  # two full captures + publish: real git subprocess work
def test_registry_diff_mode_snapshots_match(git_repo: str) -> None:
    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    Path(git_repo, "new.py").write_text("x = 1\n", encoding="utf-8")
    _assert_equal_registry_snapshots(git_repo, "diff")


@POSIX_SNAPSHOT_TEST
@pytest.mark.slow_ok  # two full captures + publish: real git subprocess work
def test_registry_staged_mode_snapshots_match(git_repo: str) -> None:
    Path(git_repo, "architectural-constraints.yml").write_text(
        "rules:\n  - id: r2\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    Path(git_repo, "base.py").write_text("value = 9\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "base.py"], check=True)
    _assert_equal_registry_snapshots(git_repo, "staged")


@POSIX_SNAPSHOT_TEST
def test_registry_scoped_snapshots_match(git_repo: str) -> None:
    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    Path(git_repo, "new.py").write_text("x = 1\n", encoding="utf-8")
    import tree_sitter_analyzer.diff_snapshot_registry as snapshots

    snapshots.reset_registry()
    frozen = snapshots.REGISTRY.create(git_repo, "diff", ["base.py"], readonly=False)
    assert frozen.get("success")
    snapshots.reset_registry()
    readonly = snapshots.REGISTRY.create(git_repo, "diff", ["base.py"], readonly=True)
    assert readonly.get("success")
    assert frozen["source_generation"] == readonly["source_generation"]
    assert frozen["changed_records"] == readonly["changed_records"]
    assert frozen["assessed_scope_paths"] == readonly["assessed_scope_paths"]


@POSIX_SNAPSHOT_TEST
def test_intent_to_add_payloads_match(git_repo: str) -> None:
    """``git add -N`` paths carry real worktree bytes, not the placeholder."""
    Path(git_repo, "ita.py").write_text("new content\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "-N", "ita.py"], check=True)
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_quoted_header_paths_match(git_repo: str) -> None:
    """A path needing C quoting round-trips through the section parser."""
    tab_path = Path(git_repo, "tab\tname.py")
    tab_path.write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "tab"], check=True)
    tab_path.write_text("y\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_space_paths_sections_do_not_collide(git_repo: str) -> None:
    """Unquoted space-containing headers keep distinct section keys."""
    Path(git_repo, "a b.py").write_text("two\n", encoding="utf-8")
    Path(git_repo, "a c.py").write_text("three\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "spaces"], check=True)
    Path(git_repo, "a b.py").write_text("two2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_exact_rename_with_mode_change_payloads_match(git_repo: str) -> None:
    """R100 sections carry old/new mode lines when the mode changed."""
    script = Path(git_repo, "m.sh")
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o755)
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "m"], check=True)
    os.rename(script, Path(git_repo, "n.sh"))
    Path(git_repo, "n.sh").chmod(0o644)
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_ambiguous_identical_moves_stay_delete_add(git_repo: str) -> None:
    """Ambiguous exact-rename candidates are not paired by guessing."""
    Path(git_repo, "x.py").write_text("same\n", encoding="utf-8")
    Path(git_repo, "y.py").write_text("same\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "two"], check=True)
    os.rename(Path(git_repo, "x.py"), Path(git_repo, "x2.py"))
    os.rename(Path(git_repo, "y.py"), Path(git_repo, "y2.py"))
    _readonly_epochs: list[GitEpoch] = []
    manifest: dict = {}
    oracle_generation_readonly(
        git_repo, "diff", manifest=manifest, epoch_out=_readonly_epochs
    )
    _patch, files = capture_payload_readonly(
        git_repo,
        "diff",
        time.monotonic() + 60.0,
        _BUDGET,
        expected_manifest=manifest,
        epoch=_readonly_epochs[0],
    )
    assert sorted(file.record.status for file in files) == ["A", "A", "D", "D"]


@POSIX_SNAPSHOT_TEST
def test_filemode_false_untracked_exec_payloads_match(git_repo: str) -> None:
    subprocess.run(
        ["git", "-C", git_repo, "config", "core.filemode", "false"], check=True
    )
    script = Path(git_repo, "run.sh")
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o755)
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_working_tree_encoding_fails_closed_without_crlf(git_repo: str) -> None:
    Path(git_repo, ".gitattributes").write_text(
        "*.txt working-tree-encoding=UTF-16LE\n", encoding="utf-8"
    )
    Path(git_repo, "data.txt").write_text("hello\n", encoding="utf-8")
    _readonly_epochs: list[GitEpoch] = []
    manifest: dict = {}
    oracle_generation_readonly(
        git_repo, "diff", manifest=manifest, epoch_out=_readonly_epochs
    )
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION"):
        capture_payload_readonly(
            git_repo,
            "diff",
            time.monotonic() + 60.0,
            _BUDGET,
            expected_manifest=manifest,
            epoch=_readonly_epochs[0],
        )


@POSIX_SNAPSHOT_TEST
def test_ident_attribute_fails_closed(git_repo: str) -> None:
    Path(git_repo, ".gitattributes").write_text("*.c ident\n", encoding="utf-8")
    Path(git_repo, "main.c").write_text("$Id$\n", encoding="utf-8")
    _readonly_epochs: list[GitEpoch] = []
    manifest: dict = {}
    oracle_generation_readonly(
        git_repo, "diff", manifest=manifest, epoch_out=_readonly_epochs
    )
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION"):
        capture_payload_readonly(
            git_repo,
            "diff",
            time.monotonic() + 60.0,
            _BUDGET,
            expected_manifest=manifest,
            epoch=_readonly_epochs[0],
        )


@POSIX_SNAPSHOT_TEST
def test_untracked_diff_attribute_binary_matches(git_repo: str) -> None:
    """``*.dat binary`` marks an untracked NUL-free file binary."""
    Path(git_repo, ".gitattributes").write_text("*.dat binary\n", encoding="utf-8")
    Path(git_repo, "blob.dat").write_text("plain text no nul\n", encoding="utf-8")
    # .gitattributes is itself untracked: two added records, one binary.
    _assert_equal_payloads(git_repo, "diff", 2)


@POSIX_SNAPSHOT_TEST
def test_skip_worktree_entry_matches(git_repo: str) -> None:
    Path(git_repo, "sw.py").write_text("hidden\n", encoding="utf-8")
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", git_repo, "commit", "-qm", "sw"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "update-index", "--skip-worktree", "sw.py"],
        check=True,
    )
    Path(git_repo, "sw.py").write_text("changed\n", encoding="utf-8")
    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    _assert_equal_payloads(git_repo, "diff", 1)


@POSIX_SNAPSHOT_TEST
def test_readonly_revalidation_uses_readonly_oracle(git_repo: str) -> None:
    """acquire/validate_publish revalidate readonly snapshots zero-write."""
    import tree_sitter_analyzer.diff_snapshot_registry as snapshots

    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    snapshots.reset_registry()
    created = snapshots.REGISTRY.create(git_repo, "diff", [], readonly=True)
    assert created.get("success"), created
    frozen_calls: list[str] = []
    readonly_calls: list[str] = []
    original_frozen = snapshots.oracle_generation
    original_readonly = snapshots.oracle_generation_readonly

    @__import__("functools").wraps(original_frozen)
    def spy_frozen(*args, **kwargs):
        frozen_calls.append("frozen")
        return original_frozen(*args, **kwargs)

    @__import__("functools").wraps(original_readonly)
    def spy_readonly(*args, **kwargs):
        readonly_calls.append("readonly")
        return original_readonly(*args, **kwargs)

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(snapshots, "oracle_generation", spy_frozen)
    monkeypatch.setattr(snapshots, "oracle_generation_readonly", spy_readonly)
    try:
        consumer, error = snapshots.REGISTRY.acquire(
            str(created["diff_snapshot_id"]), git_repo
        )
        assert error is None and consumer is not None
        assert snapshots.REGISTRY.validate_publish(consumer) is None
        consumer.release()
    finally:
        monkeypatch.undo()
    assert frozen_calls == []
    assert readonly_calls
