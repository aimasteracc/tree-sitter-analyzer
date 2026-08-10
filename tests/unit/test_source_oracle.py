import os

import pytest

import tree_sitter_analyzer.source_oracle as oracle


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
