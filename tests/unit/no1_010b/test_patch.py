"""Contracts for NO1-010B canonical patch parsing and metadata."""

from __future__ import annotations

import zlib

import pytest

from tree_sitter_analyzer.no1_010b.git_binary import GIT_BASE85_ALPHABET
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
DELTA_BINARY_PATCH = (
    "diff --git a/assets/payload.bin b/assets/payload.bin\n"
    "index 0000000000000000000000000000000000000000.."
    "1111111111111111111111111111111111111111 100644\n"
    "GIT binary patch\n"
    "delta 7\n"
    "Oc${NlVaZD^=K=r(E&*Wx\n\n"
)


def _binary_patch_from_compressed(
    kind: str, declared_size: int, compressed: bytes
) -> str:
    encoded_lines: list[str] = []
    for start in range(0, len(compressed), 52):
        chunk = compressed[start : start + 52]
        count = len(chunk)
        prefix = (
            chr(ord("A") + count - 1) if count <= 26 else chr(ord("a") + count - 27)
        )
        padded = chunk + b"\0" * (-count % 4)
        encoded = []
        for offset in range(0, len(padded), 4):
            value = int.from_bytes(padded[offset : offset + 4], "big")
            digits = []
            for _ in range(5):
                value, digit = divmod(value, 85)
                digits.append(GIT_BASE85_ALPHABET[digit])
            encoded.extend(reversed(digits))
        encoded_lines.append(prefix + "".join(encoded))
    body = "\n".join(encoded_lines)
    return (
        "diff --git a/assets/payload.bin b/assets/payload.bin\n"
        "index 0000000000000000000000000000000000000000.."
        "1111111111111111111111111111111111111111 100644\n"
        f"GIT binary patch\n{kind} {declared_size}\n{body}\n\n"
    )


def _binary_patch(kind: str, declared_size: int, inflated: bytes) -> str:
    return _binary_patch_from_compressed(kind, declared_size, zlib.compress(inflated))


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


@pytest.mark.parametrize(
    "patch",
    [
        "diff --git a/x.py b/x.py\nold mode 100644\ndiff --git a/y.py b/y.py\n",
        "rename from x.py\n",
        "diff --git a/x.py b/x.py\nrename from x.py\nrename from x.py\n",
        "old mode 100644\n",
        "diff --git a/x.py b/x.py\nold mode 100644\nold mode 100755\n",
        "index abc..def\n",
        (
            "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
            "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
        ),
    ],
    ids=[
        "unfinished-block",
        "orphan-rename",
        "duplicate-rename",
        "orphan-mode",
        "duplicate-mode",
        "orphan-index",
        "duplicate-paired-header",
    ],
)
def test_validate_patch_rejects_misplaced_or_duplicate_metadata(patch: str) -> None:
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


@pytest.mark.parametrize(
    "patch",
    [
        (
            "diff --git a/x.py b/x.py\nnew file mode 100644\n"
            "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n+new\n"
        ),
        (
            "diff --git a/x.py b/x.py\ndeleted file mode 100644\n"
            "--- a/x.py\n+++ b/x.py\n@@ -1 +0,0 @@\n-old\n"
        ),
    ],
    ids=["new-file", "deleted-file"],
)
def test_validate_patch_rejects_mode_with_nonnull_paired_side(patch: str) -> None:
    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


@pytest.mark.parametrize(
    "patch",
    [
        (
            "diff --git a/x.py b/x.py\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/x.py\n@@ -0,0 +1 @@\n+new\n"
        ),
        (
            "diff --git a/x.py b/x.py\ndeleted file mode 100644\n"
            "--- a/x.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n"
        ),
    ],
    ids=["new-file", "deleted-file"],
)
def test_validate_patch_accepts_mode_with_canonical_null_side(patch: str) -> None:
    assert [path.rel_path for path in validate_patch(patch)] == ["x.py"]


def test_validate_patch_accepts_mode_only_change() -> None:
    assert [path.rel_path for path in validate_patch(MODE_ONLY_PATCH)] == [
        "scripts/run.sh"
    ]


def test_validate_patch_accepts_abbreviated_index_for_text_patch() -> None:
    patch = "diff --git a/x.py b/x.py\nindex abc..def 100644\n" + PATCH

    assert [path.rel_path for path in validate_patch(patch)] == ["x.py"]


def test_validate_patch_accepts_canonical_git_binary_patch() -> None:
    # PR #1307 review: git diff --binary output is a changed patch.
    assert [path.rel_path for path in validate_patch(BINARY_PATCH)] == [
        "assets/payload.bin"
    ]


@pytest.mark.parametrize(
    "patch",
    [
        BINARY_PATCH.replace(
            "index eaf36c1daccfdf325514461cd1a2ffbc139b5464.."
            "f75c32acfbf126176c30bf9bda9a5f2bb8f78d06 100644\n",
            "",
        ),
        BINARY_PATCH.replace(
            "index eaf36c1daccfdf325514461cd1a2ffbc139b5464.."
            "f75c32acfbf126176c30bf9bda9a5f2bb8f78d06 100644",
            "index eaf36c1..f75c32a 100644",
        ),
    ],
    ids=["missing", "abbreviated"],
)
def test_validate_patch_rejects_binary_without_full_index(patch: str) -> None:
    with pytest.raises(PatchFormatError, match="full index line"):
        validate_patch(patch)


def test_validate_patch_accepts_binary_new_file_with_zero_old_object() -> None:
    patch = _binary_patch("literal", 3, b"new").replace(
        "diff --git a/assets/payload.bin b/assets/payload.bin\n",
        "diff --git a/assets/payload.bin b/assets/payload.bin\nnew file mode 100644\n",
    )

    assert [path.rel_path for path in validate_patch(patch)] == ["assets/payload.bin"]


def test_validate_patch_rejects_corrupt_binary_payload_checksum() -> None:
    # PR #1307: legal base85 text must still decode to an intact zlib stream.
    corrupted = BINARY_PATCH.replace("LcmZQzWMTmT01p5N", "LcmZQzWMTmT01p5O")
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(corrupted)


def test_validate_patch_accepts_canonical_binary_delta() -> None:
    assert [path.rel_path for path in validate_patch(DELTA_BINARY_PATCH)] == [
        "assets/payload.bin"
    ]


@pytest.mark.parametrize(
    "delta",
    [
        b"\x80\x80\x04\x80\x80\x04\x80",
        b"\x85\x8a\x94\x08\x81\x84\x0c\xff\x04\x03\x02\x01\x01\x02\x03",
    ],
    ids=["default-copy-size", "all-copy-fields"],
)
def test_validate_patch_accepts_canonical_delta_copy(delta: bytes) -> None:
    assert [
        path.rel_path
        for path in validate_patch(_binary_patch("delta", len(delta), delta))
    ] == ["assets/payload.bin"]


@pytest.mark.parametrize(
    "delta",
    [
        b"\x80" * 10,
        b"\x04\x05\x04data",
        b"\x04\x04\x81",
        b"\x04\x04\x90",
        b"\x04\x04\x91\x04\x01",
        b"\x04\x04\x04abc",
        b"\x04\x04\x00",
        b"\x04\x04\x05abcde",
        b"\x04\x04\x03abc",
    ],
    ids=[
        "bad-varint",
        "result-size",
        "copy-offset",
        "copy-size",
        "copy-source",
        "insert",
        "zero-command",
        "long-output",
        "short-output",
    ],
)
def test_validate_patch_rejects_malformed_binary_delta(delta: bytes) -> None:
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(_binary_patch("delta", len(delta), delta))


def test_validate_patch_bounds_internal_delta_result() -> None:
    delta = b"\x00\x81\x80\x40"

    with pytest.raises(PatchBoundError, match="exceeds output bound"):
        validate_patch(_binary_patch("delta", len(delta), delta))


@pytest.mark.parametrize("line", ["A~~~~~", "A00001"], ids=["overflow", "padding"])
def test_validate_patch_rejects_noncanonical_base85_value(line: str) -> None:
    prefix = BINARY_PATCH.split("GIT binary patch\n", 1)[0]
    patch = f"{prefix}GIT binary patch\nliteral 1\n{line}\n\n"
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(patch)


def test_validate_patch_rejects_literal_size_mismatch() -> None:
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(_binary_patch("literal", 4, b"abc"))


def test_validate_patch_rejects_truncated_zlib_stream() -> None:
    compressed = zlib.compress(b"abc")[:-1]
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(_binary_patch_from_compressed("literal", 3, compressed))


def test_validate_patch_rejects_concatenated_zlib_streams() -> None:
    compressed = zlib.compress(b"abc") + zlib.compress(b"def")
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(_binary_patch_from_compressed("literal", 3, compressed))


def test_validate_patch_rejects_inflated_instruction_bomb() -> None:
    inflated = b"x" * (PATCH_MAX_BYTES * 2 + 65)
    with pytest.raises(PatchFormatError, match="corrupt binary patch payload"):
        validate_patch(_binary_patch("literal", 1, inflated))


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
def test_validate_patch_uses_metadata_to_disambiguate_git_header(
    operation: str,
) -> None:
    patch = (
        "diff --git a/left b/mid b/right\n"
        f"similarity index 100%\n{operation} from left b/mid\n"
        f"{operation} to right\n"
    )

    assert [path.rel_path for path in validate_patch(patch)] == [
        "left b/mid",
        "right",
    ]


def test_validate_patch_rejects_ambiguous_header_with_mismatched_metadata() -> None:
    patch = (
        "diff --git a/left b/mid b/right\n"
        "similarity index 100%\nrename from different\nrename to right\n"
    )

    with pytest.raises(PatchFormatError, match="non-canonical"):
        validate_patch(patch)


def test_validate_patch_rejects_semantically_empty_replacement() -> None:
    patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+old\n"

    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


def test_validate_patch_accepts_newline_status_change() -> None:
    patch = (
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n"
        "-old\n\\ No newline at end of file\n+old\n"
    )

    assert [path.rel_path for path in validate_patch(patch)] == ["x.py"]


def test_validate_patch_rejects_empty_replacement_without_newlines() -> None:
    patch = (
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n"
        "-old\n\\ No newline at end of file\n"
        "+old\n\\ No newline at end of file\n"
    )

    with pytest.raises(PatchFormatError, match="changed canonical"):
        validate_patch(patch)


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
