"""Contracts for NO1-010B canonical patch parsing and metadata."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.no1_010b.patch import (
    PatchFormatError,
    diff_paths,
    validate_patch,
)

PATCH = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
MODE_ONLY_PATCH = (
    "diff --git a/scripts/run.sh b/scripts/run.sh\nold mode 100644\nnew mode 100755\n"
)


def test_diff_paths_rejects_quoted_git_header() -> None:
    with pytest.raises(PatchFormatError, match="non-canonical"):
        diff_paths('diff --git "a/path with spaces" "b/path with spaces"\n')


def test_diff_paths_rejects_wrong_side_git_header() -> None:
    with pytest.raises(PatchFormatError, match="non-canonical"):
        diff_paths("diff --git b/wrong.py b/wrong.py\n")


def test_diff_paths_rejects_traversal_in_extended_header() -> None:
    patch = PATCH + "diff --git a/x.py b/x.py\nrename from ../secret.py\n"
    with pytest.raises(PatchFormatError, match="extended path"):
        diff_paths(patch)


def test_diff_paths_preserves_trailing_space_before_timestamp_tab() -> None:
    patch = "--- a/x \t\n+++ b/x \t\n@@ -1 +1 @@\n-old\n+new\n"
    assert [path.rel_path for path in diff_paths(patch)] == ["x "]


def test_validate_patch_accepts_crlf() -> None:
    assert validate_patch(PATCH.replace("\n", "\r\n")) == diff_paths(PATCH)


def test_validate_patch_rejects_invalid_mode_metadata() -> None:
    patch = "diff --git a/x.py b/x.py\nold mode xyz\n" + PATCH
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


@pytest.mark.parametrize(
    "metadata",
    [
        "old mode 100644\n",
        "new file mode 100644\ndeleted file mode 100644\n",
        "old mode 100644\nnew mode 100644\n",
    ],
)
def test_validate_patch_rejects_invalid_mode_relationships(metadata: str) -> None:
    patch = "diff --git a/x.py b/x.py\n" + metadata
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


def test_validate_patch_rejects_mode_change_between_different_paths() -> None:
    patch = "diff --git a/old.py b/new.py\nold mode 100644\nnew mode 100755\n"
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


def test_validate_patch_rejects_standalone_metadata_garbage() -> None:
    patch = "diff --git a/x.py b/x.py\nGARBAGE\n" + PATCH
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


def test_validate_patch_accepts_mode_only_change() -> None:
    assert [path.rel_path for path in validate_patch(MODE_ONLY_PATCH)] == [
        "scripts/run.sh"
    ]


@pytest.mark.parametrize("operation", ["rename", "copy"])
def test_validate_patch_accepts_consistent_path_metadata(operation: str) -> None:
    patch = (
        "diff --git a/old.py b/new.py\n"
        f"{operation} from old.py\n"
        f"{operation} to new.py\n"
    )
    assert [path.rel_path for path in validate_patch(patch)] == ["old.py", "new.py"]


@pytest.mark.parametrize("operation", ["rename", "copy"])
def test_validate_patch_rejects_unpaired_path_metadata(operation: str) -> None:
    patch = f"diff --git a/old.py b/new.py\n{operation} from old.py\n"
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


@pytest.mark.parametrize("operation", ["rename", "copy"])
def test_validate_patch_rejects_metadata_inconsistent_with_git_header(
    operation: str,
) -> None:
    patch = (
        "diff --git a/old.py b/new.py\n"
        f"{operation} from different.py\n"
        f"{operation} to new.py\n"
        "--- a/old.py\n"
        "+++ b/new.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)
