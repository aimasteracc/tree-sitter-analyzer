"""Contract tests for the NO1-010B patch-verifier core (RFC-0026 §2/§3)."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.no1_010b.runner import (
    DiffPath,
    PatchBoundError,
    PatchFormatError,
    allowlist_violations,
    bound_patch,
    classify,
    diff_paths,
)

PATCH_OK = (
    "--- a/src/dispatch.py\n"
    "+++ b/src/dispatch.py\n"
    "@@ -12,1 +12,2 @@\n"
    " def dispatch(route):\n"
    "+    return {'status': 404}\n"
)
PATCH_TWO_FILES = (
    "--- a/src/dispatch.py\n"
    "+++ b/src/dispatch.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
    "--- a/tests/test_dispatch.py\n"
    "+++ b/tests/test_dispatch.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


def test_diff_paths_parse_canonical_headers() -> None:
    paths = diff_paths(PATCH_TWO_FILES)
    assert [p.rel_path for p in paths] == [
        "src/dispatch.py",
        "tests/test_dispatch.py",
    ]
    assert diff_paths("no headers here\n") == []
    assert diff_paths("no headers here") == []


def test_diff_paths_retains_source_path_for_deletion() -> None:
    patch = "--- a/secret.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-secret\n"
    assert [path.rel_path for path in diff_paths(patch)] == ["secret.py"]


def test_diff_paths_retains_both_paths_for_rename() -> None:
    patch = "--- a/old.py\n+++ b/new.py\n@@ -1 +1 @@\n-old\n+new\n"
    assert [path.rel_path for path in diff_paths(patch)] == ["old.py", "new.py"]


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        (
            (
                "diff --git a/scripts/run.sh b/scripts/run.sh\n"
                "old mode 100644\n"
                "new mode 100755\n"
            ),
            ["scripts/run.sh"],
        ),
        (
            (
                "diff --git a/assets/payload.bin b/assets/payload.bin\n"
                "new file mode 100644\n"
                "index 0000000..0123456\n"
                "GIT binary patch\n"
            ),
            ["assets/payload.bin"],
        ),
    ],
    ids=["mode-only", "binary"],
)
def test_diff_paths_reads_git_headers_without_text_headers(
    patch: str, expected: list[str]
) -> None:
    assert [path.rel_path for path in diff_paths(patch)] == expected


def test_diff_paths_fails_closed_on_ambiguous_git_header() -> None:
    with pytest.raises(PatchFormatError, match="non-canonical"):
        diff_paths('diff --git "a/path with spaces" "b/path with spaces"\n')
    with pytest.raises(PatchFormatError, match="non-canonical"):
        diff_paths("diff --git b/wrong-side.py b/wrong-side.py\n")


@pytest.mark.parametrize(
    ("token", "side"),
    [
        ("b/wrong.py", "a/"),
        ("a/", "a/"),
        ("a//absolute.py", "a/"),
        ("a/dir\\file.py", "a/"),
        ("a/nested//file.py", "a/"),
        ("a/nested/./file.py", "a/"),
        ("a/nested/../file.py", "a/"),
    ],
)
def test_git_header_token_rejects_noncanonical_paths(token: str, side: str) -> None:
    assert DiffPath.from_git_token(token, side) is None


@pytest.mark.parametrize(
    ("header", "marker"),
    [
        ("+++ b/ok.py", "---"),
        ("--- a//abs.py", "---"),
        ("--- a/./rel.py", "---"),
        ("--- a/nested/./rel.py", "---"),
        ("--- a/nested//rel.py", "---"),
        ("--- a/a/../b.py", "---"),
        ("--- a/dir\\file.py", "---"),
        ("--- a/", "---"),
        ("+++ not-a-header", "+++"),
    ],
)
def test_diff_path_rejects_non_canonical_header(header: str, marker: str) -> None:
    assert DiffPath.from_diff_header(header, marker) is None


def test_diff_paths_ignores_unpaired_file_header() -> None:
    assert diff_paths("+++ b/ok.py\n") == []


def test_bound_patch_enforces_canonical_limits() -> None:
    bound_patch(PATCH_OK)  # in bounds
    with pytest.raises(PatchBoundError, match="max bytes"):
        bound_patch("x" * (1024 * 1024 + 1))
    many_hunks = "".join(f"@@ -{i} +{i} @@\n" for i in range(513))
    with pytest.raises(PatchBoundError, match="max hunks"):
        bound_patch(many_hunks)
    long_hunk = "@@ -1 +1 @@\n" + "+x\n" * 2001
    with pytest.raises(PatchBoundError, match="max lines per hunk"):
        bound_patch(long_hunk)


def test_bound_patch_accepts_exact_physical_line_limit_with_final_newline() -> None:
    exact = "@@ -1 +1 @@\n" + "+x\n" * 2000
    bound_patch(exact)

    exact_with_blank = "@@ -1 +1 @@\n" + "+x\n" * 1999 + "\n"
    bound_patch(exact_with_blank)
    with pytest.raises(PatchBoundError, match="max lines per hunk"):
        bound_patch(exact_with_blank + "\n")


def test_bound_patch_counts_context_lines_in_hunk_limit() -> None:
    long_hunk = "@@ -1 +1 @@\n" + " context\n" * 2001
    with pytest.raises(PatchBoundError, match="max lines per hunk"):
        bound_patch(long_hunk)


def test_allowlist_violations_is_segment_aware() -> None:
    allowed = ("src/dispatch.py", "tests/")
    touched = [
        "src/dispatch.py",
        "tests/test_dispatch.py",
        "tests-escape/file.py",
        "src/routes.py",
    ]
    assert allowlist_violations(touched, allowed) == [
        "tests-escape/file.py",
        "src/routes.py",
    ]


def test_allowlist_violations_rejects_candidate_tree_tool_artifacts() -> None:
    touched = [
        "tests/__pycache__/test_dispatch.cpython-311.pyc",
        ".pytest_cache/README.md",
        ".coverage",
        ".coverage.host.123.456",
    ]
    assert allowlist_violations(touched, ("src/app.py",)) == touched


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "path_ok": True,
                "oracle_ok": True,
                "verification_ok": True,
                "stale_ok": True,
                "unsupported_ok": True,
            },
            "PASS",
        ),
        (
            {
                "path_ok": False,
                "oracle_ok": True,
                "verification_ok": True,
                "stale_ok": True,
                "unsupported_ok": True,
            },
            "PATH_VIOLATION",
        ),
        (
            {
                "path_ok": True,
                "oracle_ok": False,
                "verification_ok": True,
                "stale_ok": True,
                "unsupported_ok": True,
            },
            "ORACLE_FAILED",
        ),
        (
            {
                "path_ok": True,
                "oracle_ok": True,
                "verification_ok": False,
                "stale_ok": True,
                "unsupported_ok": True,
            },
            "VERIFICATION_FAILED",
        ),
        (
            {
                "path_ok": True,
                "oracle_ok": True,
                "verification_ok": True,
                "stale_ok": False,
                "unsupported_ok": True,
            },
            "STALE_ROWS",
        ),
        (
            {
                "path_ok": True,
                "oracle_ok": True,
                "verification_ok": True,
                "stale_ok": True,
                "unsupported_ok": False,
            },
            "UNSUPPORTED_RELATIONSHIP",
        ),
        (
            {
                "path_ok": True,
                "oracle_ok": True,
                "verification_ok": True,
                "stale_ok": True,
                "unsupported_ok": True,
                "selection_ok": False,
            },
            "TEST_SELECTION_FAILED",
        ),
        # UNKNOWN always wins over every FAIL and retains its closed subcode.
        (
            {
                "path_ok": False,
                "oracle_ok": False,
                "verification_ok": False,
                "stale_ok": False,
                "unsupported_ok": False,
                "unknown_reason": "ORACLE_TIMEOUT",
            },
            "ORACLE_TIMEOUT",
        ),
    ],
)
def test_classify_maps_criteria_to_exact_reason_codes(
    kwargs: dict, expected: str
) -> None:
    verdict = classify(**kwargs)
    assert verdict.as_reason() == expected
    expected_status = {"PASS": "PASS", "ORACLE_TIMEOUT": "UNKNOWN"}.get(
        expected, "FAIL"
    )
    assert verdict.status == expected_status


def test_verdict_pass_has_no_reason_code() -> None:
    verdict = classify(
        path_ok=True,
        oracle_ok=True,
        verification_ok=True,
        stale_ok=True,
        unsupported_ok=True,
    )
    assert verdict.status == "PASS"
    assert verdict.reason_code is None
