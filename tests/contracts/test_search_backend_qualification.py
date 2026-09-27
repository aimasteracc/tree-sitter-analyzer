"""RFC-0034 阶段 A 搜索后端资格合同。"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import qualify_search_backend as qualification
from tree_sitter_analyzer.text_search import TextSearchRequest


def test_pinned_rg_assets_cover_declared_runner_axes_exactly() -> None:
    assert sorted(qualification.RG_ASSETS) == [
        ("Darwin", "arm64"),
        ("Darwin", "x86_64"),
        ("Linux", "x86_64"),
        ("Windows", "AMD64"),
    ]
    assert {asset.version for asset in qualification.RG_ASSETS.values()} == {"15.1.0"}
    assert {len(asset.sha256) for asset in qualification.RG_ASSETS.values()} == {64}
    assert all(
        asset.url.endswith(asset.filename) for asset in qualification.RG_ASSETS.values()
    )


def test_archive_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "forged.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        payload = b"forged"
        member = tarfile.TarInfo("../rg")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))

    with pytest.raises(ValueError, match="safe regular rg executable"):
        qualification.extract_rg(archive, tmp_path / "bin", executable_name="rg")


def test_windows_zip_extracts_only_the_exact_rg_executable(tmp_path: Path) -> None:
    archive = tmp_path / "rg.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("ripgrep/rg.exe", b"trusted-rg")
        bundle.writestr("ripgrep/README.md", b"ignored")

    executable = qualification.extract_rg(
        archive, tmp_path / "bin", executable_name="rg.exe"
    )

    assert executable.read_bytes() == b"trusted-rg"
    assert sorted(path.name for path in executable.parent.iterdir()) == ["rg.exe"]


def test_rg_json_parser_preserves_cr_only_line_and_unicode_column(
    tmp_path: Path,
) -> None:
    root = tmp_path / "stage"
    path = root / "unicode.py"
    path.parent.mkdir()
    path.write_text("前needle后", encoding="utf-8")
    records = [
        {
            "type": "match",
            "data": {
                "path": {"text": str(path)},
                "lines": {"text": "zero\rneedle\r"},
                "line_number": 1,
                "submatches": [{"start": 5, "end": 11, "match": {"text": "needle"}}],
            },
        },
        {
            "type": "match",
            "data": {
                "path": {"text": str(path)},
                "lines": {"text": "前needle后\n"},
                "line_number": 2,
                "submatches": [{"start": 3, "end": 9, "match": {"text": "needle"}}],
            },
        },
    ]
    payload = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    assert qualification.parse_rg_hits(payload, root) == [
        {"file": "unicode.py", "line": 1, "column": 6, "text": "zero\rneedle\r"},
        {"file": "unicode.py", "line": 2, "column": 2, "text": "前needle后"},
    ]


def test_rg_command_has_fixed_non_shell_boundary(tmp_path: Path) -> None:
    request = TextSearchRequest(
        project_root=str(tmp_path),
        root=".",
        query="needle",
        case_mode="insensitive",
        word_match=True,
        include_globs=(),
        exclude_globs=(),
    )
    files = [tmp_path / "a.py", tmp_path / "b.py"]

    assert qualification.rg_command(tmp_path / "rg", request, files) == [
        str(tmp_path / "rg"),
        "--no-config",
        "--json",
        "--fixed-strings",
        "--ignore-case",
        "--word-regexp",
        "--",
        "needle",
        str(tmp_path / "a.py"),
        str(tmp_path / "b.py"),
    ]


def test_qualification_cases_freeze_known_semantic_partition() -> None:
    assert [case.case_id for case in qualification.CASES] == [
        "lf_literal",
        "cr_only",
        "nul_after_match",
        "ignored_scope",
        "unicode_word",
        "smart_case",
        "zero_match",
    ]
    assert [case.expected_equivalent for case in qualification.CASES] == [
        True,
        False,
        False,
        True,
        True,
        True,
        True,
    ]
