"""Contracts for NO1-010B canonical patch parsing and metadata."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.no1_010b.patch import (
    PATCH_MAX_BYTES,
    PatchBoundError,
    PatchFormatError,
    diff_paths,
    validate_patch,
)

PATCH = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
MODE_ONLY_PATCH = (
    "diff --git a/scripts/run.sh b/scripts/run.sh\nold mode 100644\nnew mode 100755\n"
)
BINARY_PATCH = (
    "diff --git a/assets/payload.bin b/assets/payload.bin\n"
    "index eaf36c1daccfdf325514461cd1a2ffbc139b5464.."
    "f75c32acfbf126176c30bf9bda9a5f2bb8f78d06 100644\n"
    "GIT binary patch\n"
    "literal 4\n"
    "LcmZQzWMTmT01p5N\n\n"
    "literal 4\n"
    "LcmZQzWMT#Y01f~L\n\n"
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


def test_validate_patch_accepts_canonical_git_binary_patch() -> None:
    # PR #1307 review: git diff --binary output is a changed patch.
    assert [path.rel_path for path in validate_patch(BINARY_PATCH)] == [
        "assets/payload.bin"
    ]


@pytest.mark.parametrize("size", [str(PATCH_MAX_BYTES + 1), "0" * 8])
def test_validate_patch_bounds_declared_binary_output(size: str) -> None:
    patch = BINARY_PATCH.replace("literal 4", f"literal {size}", 1)
    with pytest.raises(PatchBoundError, match="exceeds"):
        validate_patch(patch)


@pytest.mark.parametrize(
    "body",
    ["", "garbage\n", "literal 4\n\n", "literal 4\n?invalid\n\n"],
    ids=["missing-payload", "invalid-size", "missing-data", "invalid-base85"],
)
def test_validate_patch_rejects_malformed_binary_payload(body: str) -> None:
    prefix = BINARY_PATCH.split("GIT binary patch\n", 1)[0]
    patch = f"{prefix}GIT binary patch\n{body}"
    with pytest.raises(PatchFormatError, match="binary patch"):
        validate_patch(patch)


def test_validate_patch_rejects_binary_payload_without_git_header() -> None:
    patch = BINARY_PATCH.split("GIT binary patch\n", 1)[1]
    with pytest.raises(PatchFormatError, match="no Git header"):
        validate_patch(f"GIT binary patch\n{patch}")


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
