"""Contract tests for the NO1-010B patch-verifier core (RFC-0026 §2/§3)."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.no1_010b.runner import (
    PatchBoundError,
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


def test_allowlist_violations_excludes_trusted_artifacts() -> None:
    allowed = ("src/dispatch.py", "tests/")
    touched = [
        "src/dispatch.py",
        "tests/__pycache__/test_dispatch.cpython-311.pyc",
        ".pytest_cache/README.md",
    ]
    assert allowlist_violations(touched, allowed) == []


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
        # UNKNOWN always wins over every FAIL.
        (
            {
                "path_ok": False,
                "oracle_ok": False,
                "verification_ok": False,
                "stale_ok": False,
                "unsupported_ok": False,
                "unknown": True,
            },
            "UNKNOWN",
        ),
    ],
)
def test_classify_maps_criteria_to_exact_reason_codes(
    kwargs: dict, expected: str
) -> None:
    verdict = classify(**kwargs)
    assert verdict.as_reason() == expected
    assert verdict.status == ("PASS" if expected == "PASS" else "FAIL")


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
