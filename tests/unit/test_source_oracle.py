import os
import subprocess
from pathlib import Path

import pytest

import tree_sitter_analyzer.source_oracle as oracle
import tree_sitter_analyzer.source_oracle_git as git_oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST
from tree_sitter_analyzer.source_oracle_budget import (
    container_storage,
    entry_map_storage,
    parse_head_entries,
)


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


@pytest.mark.parametrize("value", ["", "/absolute", "../escape", "a/../b", "bad\0name"])
def test_normalize_repo_path_rejects_unsafe_paths(value: str) -> None:
    _error(lambda: oracle.normalize_repo_path(value), "DIFF_SNAPSHOT_INVALID_PATH")


def test_remaining_rejects_expired_deadline(monkeypatch) -> None:
    monkeypatch.setattr(oracle.time, "monotonic", lambda: 10.0)
    _error(lambda: oracle._remaining(10.0), "DIFF_SNAPSHOT_TIMEOUT")


def test_canonical_root_translates_stat_error(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle, "_stat", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(lambda: oracle.canonical_root("missing"), "DIFF_SNAPSHOT_ROOT_INVALID")


def test_normalize_repo_path_strips_each_dot_prefix() -> None:
    assert oracle.normalize_repo_path("././file.py") == "file.py"


def test_normalize_repo_path_preserves_posix_backslash() -> None:
    if os.name == "nt":
        pytest.skip("tracked: POSIX path identity behavior")
    assert oracle.normalize_repo_path(r"a\b.py") == r"a\b.py"


def test_source_generation_delegates_to_git_helper(monkeypatch) -> None:
    import tree_sitter_analyzer.source_oracle_git as oracle_git

    monkeypatch.setattr(oracle_git, "source_generation", lambda root, mode: "sg_value")

    assert oracle.source_generation(".", "staged") == "sg_value"


def test_capture_consistent_delegates_to_git_helper(monkeypatch) -> None:
    import tree_sitter_analyzer.source_oracle_git as oracle_git

    monkeypatch.setattr(
        oracle_git,
        "capture_consistent",
        lambda root, capture: ("sg_value", capture()),
    )

    assert oracle.capture_consistent(".", lambda: 7) == ("sg_value", 7)


def test_git_output_wrapper_delegates(monkeypatch) -> None:
    import tree_sitter_analyzer.source_oracle_git as oracle_git

    monkeypatch.setattr(
        oracle_git, "git_output", lambda root, args, **kwargs: b"frozen"
    )
    assert oracle.git_output(".", ["status"], deadline=1e20, limit=10) == b"frozen"


def test_capture_inventory_delegates_to_git_helper(monkeypatch) -> None:
    monkeypatch.setattr(
        "tree_sitter_analyzer.source_oracle_git.capture_inventory",
        lambda *args, **kwargs: ("a.py",),
    )

    assert oracle.capture_inventory(".", "diff", deadline=1e20, limit=1) == ("a.py",)


def test_head_parser_stops_when_retained_dict_exhausts_budget() -> None:
    raw = b"100644 blob a\ta\x00100644 blob b\tb\0"
    ceiling = len(raw) + entry_map_storage({b"a": b"100644 blob a"})
    checks: list[float] = []

    _error(
        lambda: parse_head_entries(
            raw,
            deadline=7.0,
            byte_ceiling=ceiling,
            max_paths=2,
            remaining_fn=lambda deadline: checks.append(deadline) or 1.0,
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )
    assert checks == [7.0, 7.0]


@POSIX_SNAPSHOT_TEST
def test_staged_deletions_exhaust_head_budget_before_settings(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3752075938.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for number in range(200):
        (tmp_path / f"tracked-{number:03}.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "head",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "rm", "--cached", "-qr", "."], cwd=tmp_path, check=True)
    ceiling = 2048
    index_size = (tmp_path / ".git" / "index").stat().st_size
    expected_limit = (
        ceiling - index_size - entry_map_storage({}) - container_storage([])
    )
    limits: list[int] = []
    settings_calls: list[tuple[object, ...]] = []
    real_output = git_oracle.git_output

    def output(root, args, **kwargs):
        if args[0] == "ls-tree":
            limits.append(kwargs["limit"])
        return real_output(root, args, **kwargs)

    monkeypatch.setattr(git_oracle, "git_output", output)
    monkeypatch.setattr(
        git_oracle,
        "capture_settings",
        lambda *args, **kwargs: settings_calls.append(args),
    )
    _error(
        lambda: git_oracle.oracle_generation(
            str(tmp_path), "staged", byte_ceiling=ceiling
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )
    assert limits == [expected_limit]
    assert settings_calls == []


def test_byte_ledger_rejects_unavailable_temporary_storage() -> None:
    from tree_sitter_analyzer.source_oracle_budget import ByteLedger

    ledger = ByteLedger(3)
    ledger.require_available(3)
    _error(lambda: ledger.require_available(4), "DIFF_SNAPSHOT_CAPACITY")


def test_head_entries_rejects_empty_remaining_budget() -> None:
    _error(
        lambda: git_oracle._head_entries(".", deadline=1.0, byte_ceiling=0),
        "DIFF_SNAPSHOT_CAPACITY",
    )
