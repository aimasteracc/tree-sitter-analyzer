#!/usr/bin/env python3
"""执行 RFC-0034 阶段 A 的固定 ripgrep 差分资格矩阵。"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tree_sitter_analyzer.text_search import (
    TextSearchRequest,
    _admitted_sources,
    _validate_scope,
    search_text,
)

RG_VERSION = "15.1.0"
_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
_MAX_EXECUTABLE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RgAsset:
    """一个声明平台的固定上游资产。"""

    version: str
    filename: str
    sha256: str
    url: str


def _asset(filename: str, sha256: str) -> RgAsset:
    return RgAsset(
        version=RG_VERSION,
        filename=filename,
        sha256=sha256,
        url=f"https://github.com/BurntSushi/ripgrep/releases/download/{RG_VERSION}/{filename}",
    )


RG_ASSETS = {
    ("Darwin", "arm64"): _asset(
        "ripgrep-15.1.0-aarch64-apple-darwin.tar.gz",
        "378e973289176ca0c6054054ee7f631a065874a352bf43f0fa60ef079b6ba715",  # pragma: allowlist secret - 上游资产摘要
    ),
    ("Darwin", "x86_64"): _asset(
        "ripgrep-15.1.0-x86_64-apple-darwin.tar.gz",
        "64811cb24e77cac3057d6c40b63ac9becf9082eedd54ca411b475b755d334882",  # pragma: allowlist secret - 上游资产摘要
    ),
    ("Linux", "x86_64"): _asset(
        "ripgrep-15.1.0-x86_64-unknown-linux-musl.tar.gz",
        "1c9297be4a084eea7ecaedf93eb03d058d6faae29bbc57ecdaf5063921491599",  # pragma: allowlist secret - 上游资产摘要
    ),
    ("Windows", "AMD64"): _asset(
        "ripgrep-15.1.0-x86_64-pc-windows-msvc.zip",
        "124510b94b6baa3380d051fdf4650eaa80a302c876d611e9dba0b2e18d87493a",  # pragma: allowlist secret - 上游资产摘要
    ),
}


@dataclass(frozen=True, slots=True)
class QualificationCase:
    """一个预注册的确定性语义分区。"""

    case_id: str
    files: tuple[tuple[str, bytes], ...]
    query: str
    case_mode: str = "sensitive"
    word_match: bool = False
    expected_equivalent: bool = True


CASES = (
    QualificationCase("lf_literal", (("sample.py", b"zero\nneedle\n"),), "needle"),
    QualificationCase(
        "cr_only",
        (("sample.py", b"zero\rneedle\r"),),
        "needle",
        expected_equivalent=False,
    ),
    QualificationCase(
        "nul_after_match",
        (("sample.py", b"needle\n\x00tail"),),
        "needle",
        expected_equivalent=False,
    ),
    QualificationCase(
        "ignored_scope",
        ((".gitignore", b"ignored.py\n"), ("ignored.py", b"needle\n")),
        "needle",
    ),
    QualificationCase(
        "unicode_word",
        (("sample.py", "café caféine\n".encode()),),
        "café",
        word_match=True,
    ),
    QualificationCase(
        "smart_case",
        (("sample.py", b"Needle needle\n"),),
        "Needle",
        case_mode="smart",
    ),
    QualificationCase("zero_match", (("sample.py", b"haystack\n"),), "needle"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def extract_rg(archive: Path, destination: Path, *, executable_name: str) -> Path:
    """只提取一个安全的普通 rg 文件，不展开归档其余成员。"""
    payload: bytes | None = None
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            candidates = [
                member
                for member in bundle.infolist()
                if PurePosixPath(member.filename).name == executable_name
                and _safe_archive_name(member.filename)
                and not member.is_dir()
                and stat.S_IFMT(member.external_attr >> 16) != stat.S_IFLNK
                and member.file_size <= _MAX_EXECUTABLE_BYTES
            ]
            if len(candidates) == 1:
                payload = bundle.read(candidates[0])
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            candidates = [
                member
                for member in bundle.getmembers()
                if PurePosixPath(member.name).name == executable_name
                and _safe_archive_name(member.name)
                and member.isfile()
                and member.size <= _MAX_EXECUTABLE_BYTES
            ]
            if len(candidates) == 1:
                stream = bundle.extractfile(candidates[0])
                payload = (
                    None if stream is None else stream.read(_MAX_EXECUTABLE_BYTES + 1)
                )
    if payload is None or not payload or len(payload) > _MAX_EXECUTABLE_BYTES:
        raise ValueError(
            "archive does not contain exactly one safe regular rg executable"
        )
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / executable_name
    target.write_bytes(payload)
    target.chmod(0o755)
    return target


def download_pinned_rg(destination: Path) -> tuple[Path, RgAsset]:
    """下载当前平台的固定资产并在解包前核验完整摘要。"""
    key = (platform.system(), platform.machine())
    if key not in RG_ASSETS:
        raise RuntimeError(f"unsupported qualification axis: {key[0]}/{key[1]}")
    asset = RG_ASSETS[key]
    archive = destination / asset.filename
    destination.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        asset.url, headers={"User-Agent": "tsa-rfc0034-qualification"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - 固定 HTTPS 上游
        payload = response.read(_MAX_ARCHIVE_BYTES + 1)
    if len(payload) > _MAX_ARCHIVE_BYTES:
        raise RuntimeError("pinned rg archive exceeds byte budget")
    archive.write_bytes(payload)
    if sha256_file(archive) != asset.sha256:
        raise RuntimeError("pinned rg archive digest mismatch")
    executable = "rg.exe" if platform.system() == "Windows" else "rg"
    return extract_rg(archive, destination / "bin", executable_name=executable), asset


def rg_command(rg: Path, request: TextSearchRequest, files: list[Path]) -> list[str]:
    """构造固定参数、无 shell、无宿主配置的候选命令。"""
    sensitive = request.case_mode == "sensitive" or (
        request.case_mode == "smart" and any(char.isupper() for char in request.query)
    )
    command = [
        str(rg),
        "--no-config",
        "--json",
        "--fixed-strings",
        "--case-sensitive" if sensitive else "--ignore-case",
    ]
    if request.word_match:
        command.append("--word-regexp")
    return [*command, "--", request.query, *(str(path) for path in files)]


def _line_without_lf(text: str) -> str:
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith("\n"):
        return text[:-1]
    return text


def parse_rg_hits(payload: str, root: Path) -> list[dict[str, Any]]:
    """把 rg JSON 转成 TSA 行级坐标，同时保留 CR-only 差异。"""
    hits: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in payload.splitlines():
        record = json.loads(raw)
        if record.get("type") != "match":
            continue
        data = record["data"]
        path = Path(data["path"]["text"]).resolve(strict=False)
        relative = path.relative_to(root.resolve()).as_posix()
        line_text = _line_without_lf(data["lines"]["text"])
        first = data["submatches"][0]
        prefix = line_text.encode("utf-8")[: int(first["start"])].decode("utf-8")
        line = int(data["line_number"])
        hits.setdefault(
            (relative, line),
            {
                "file": relative,
                "line": line,
                "column": len(prefix) + 1,
                "text": line_text,
            },
        )
    return sorted(
        hits.values(), key=lambda row: (row["file"], row["line"], row["column"])
    )


def _request(case: QualificationCase, root: Path) -> TextSearchRequest:
    return TextSearchRequest(
        project_root=str(root),
        root=".",
        query=case.query,
        case_mode=case.case_mode,  # type: ignore[arg-type]
        word_match=case.word_match,
        include_globs=(),
        exclude_globs=(),
        timeout=10.0,
    )


def _write_case(case: QualificationCase, root: Path) -> None:
    for relative, payload in case.files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _stage_admitted_sources(
    request: TextSearchRequest, destination: Path
) -> list[Path]:
    project_root, scope = _validate_scope(request)
    sources = _admitted_sources(
        request, project_root, scope, time.monotonic() + request.timeout
    )
    paths: list[Path] = []
    for source in sources:
        path = destination / source.file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.data)
        paths.append(path)
    return paths


def run_case(rg: Path, case: QualificationCase, root: Path) -> dict[str, Any]:
    """运行一个原生/候选配对并保留完整差异。"""
    project = root / "project"
    stage = root / "stage"
    project.mkdir(parents=True)
    stage.mkdir(parents=True)
    _write_case(case, project)
    request = _request(case, project)
    native_started = time.perf_counter()
    native_report = search_text(request)
    native_seconds = time.perf_counter() - native_started
    files = _stage_admitted_sources(request, stage)
    candidate_started = time.perf_counter()
    if files:
        completed = subprocess.run(  # nosec B603 - 固定 argv，不经 shell
            rg_command(rg, request, files),
            cwd=stage,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=10,
        )
        if completed.returncode not in (0, 1) or completed.stderr:
            raise RuntimeError(
                f"rg candidate failed: returncode={completed.returncode}, stderr={completed.stderr!r}"
            )
        candidate_hits = parse_rg_hits(completed.stdout, stage)
    else:
        candidate_hits = []
    candidate_seconds = time.perf_counter() - candidate_started
    native_hits = [asdict(hit) for hit in native_report.hits]
    equivalent = native_hits == candidate_hits
    return {
        "case_id": case.case_id,
        "expected_equivalent": case.expected_equivalent,
        "equivalent": equivalent,
        "expectation_met": equivalent == case.expected_equivalent,
        "native": {
            "hits": native_hits,
            "files_scanned": native_report.files_scanned,
            "bytes_scanned": native_report.bytes_scanned,
            "binary_files_skipped": native_report.binary_files_skipped,
            "duration_seconds": native_seconds,
        },
        "candidate": {
            "hits": candidate_hits,
            "files_scanned": len(files),
            "duration_seconds": candidate_seconds,
        },
    }


def qualify(rg: Path) -> dict[str, Any]:
    version = subprocess.run(  # nosec B603 - 固定版本探针，不经 shell
        [str(rg), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    ).stdout.splitlines()[0]
    if (
        re.fullmatch(
            rf"ripgrep {re.escape(RG_VERSION)}(?: \(rev [0-9a-f]+\))?", version
        )
        is None
    ):
        raise RuntimeError(f"unexpected rg version: {version!r}")
    with tempfile.TemporaryDirectory(prefix="tsa-rg-qualification-") as tmp:
        root = Path(tmp)
        cases = [run_case(rg, case, root / case.case_id) for case in CASES]
    return {
        "schema_version": "rfc0034-stage-a-v1",
        "qualification_id": "RFC-0034-A",
        "production_backend_enabled": False,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "tool": {
            "version": version,
            "sha256": sha256_file(rg),
            "size": rg.stat().st_size,
        },
        "cases": cases,
        "passed": all(case["expectation_met"] for case in cases),
        "all_equivalent": all(case["equivalent"] for case in cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rg", type=Path)
    source.add_argument("--download-pinned-rg", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        if args.download_pinned_rg:
            temporary = tempfile.TemporaryDirectory(prefix="tsa-pinned-rg-")
            rg, asset = download_pinned_rg(Path(temporary.name))
        else:
            rg = args.rg.resolve(strict=True)
            asset = None
        report = qualify(rg)
        report["archive"] = None if asset is None else asdict(asset)
        payload = (
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0 if report["passed"] else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
