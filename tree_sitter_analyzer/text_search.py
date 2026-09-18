"""在实时项目源码中执行有界、无索引的字面量文本检索。"""

from __future__ import annotations

import fnmatch
import json
import re
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from .index_candidate_walker import (
    CandidateDiscoveryBudgetExceeded,
    CandidateDiscoveryError,
    walk_candidate_entries,
)
from .indexing_snapshot import decode_index_source
from .source_oracle import SourceOracleError, safe_index_source_path

CaseMode = Literal["smart", "sensitive", "insensitive"]

_MAX_ENTRIES = 100_000
_MAX_PATH_BYTES = 16 * 1024 * 1024
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_MATCHES = 100_000
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
_EXCLUDED_DIR_NAMES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", "target"}
)


class TextSearchError(RuntimeError):
    """文本检索无法证明完整结果时返回的稳定错误。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TextSearchRequest:
    """原生检索进程使用的冻结请求。"""

    project_root: str
    root: str
    query: str
    case_mode: CaseMode
    word_match: bool
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    timeout: float = 5.0


@dataclass(frozen=True, slots=True)
class TextSearchHit:
    """单个命中行；同一行的多次出现只产生一个记录。"""

    file: str
    line: int
    column: int
    text: str


@dataclass(frozen=True, slots=True)
class TextSearchReport:
    """只有完整扫描成功后才会构造的文本检索报告。"""

    hits: tuple[TextSearchHit, ...]
    files_scanned: int
    bytes_scanned: int
    binary_files_skipped: int
    scan_complete: bool = True

    @property
    def total_count(self) -> int:
        return len(self.hits)

    @property
    def file_count(self) -> int:
        return len({hit.file for hit in self.hits})


def _validate_scope(request: TextSearchRequest) -> tuple[Path, Path]:
    root = Path(request.project_root)
    if root.is_symlink():
        raise TextSearchError("SOURCE_ROOT_SYMLINK")
    try:
        project_root = root.resolve(strict=True)
    except OSError as exc:
        raise TextSearchError("SOURCE_ROOT_UNAVAILABLE") from exc
    if not project_root.is_dir():
        raise TextSearchError("SOURCE_ROOT_UNAVAILABLE")

    raw_scope = request.root.replace("\\", "/")
    scope_parts = PurePosixPath(raw_scope).parts
    if not raw_scope or PurePosixPath(raw_scope).is_absolute() or ".." in scope_parts:
        raise TextSearchError("SOURCE_ROOT_OUTSIDE_PROJECT")
    scope = project_root
    for part in scope_parts:
        if part in ("", "."):
            continue
        scope = scope / part
        if scope.is_symlink():
            raise TextSearchError("SOURCE_ROOT_SYMLINK")
    try:
        scope = scope.resolve(strict=True)
        scope.relative_to(project_root)
    except (OSError, ValueError) as exc:
        raise TextSearchError("SOURCE_ROOT_UNAVAILABLE") from exc
    if not scope.is_dir():
        raise TextSearchError("SOURCE_ROOT_UNAVAILABLE")
    return project_root, scope


def _matches_glob(path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or (pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]))
        for pattern in patterns
    )


def _compile_matcher(request: TextSearchRequest) -> re.Pattern[str]:
    sensitive = request.case_mode == "sensitive" or (
        request.case_mode == "smart" and any(char.isupper() for char in request.query)
    )
    expression = re.escape(request.query)
    if request.word_match:
        expression = rf"(?<!\w){expression}(?!\w)"
    return re.compile(expression, 0 if sensitive else re.IGNORECASE)


def _map_oracle_error(exc: SourceOracleError) -> TextSearchError:
    mapping = {
        "DIFF_SNAPSHOT_CAPACITY": "SOURCE_FILE_BUDGET_EXCEEDED",
        "DIFF_SNAPSHOT_TIMEOUT": "SOURCE_SCAN_BUDGET_EXCEEDED",
        "DIFF_SNAPSHOT_SOURCE_CHANGED": "SOURCE_FILE_CHANGED",
        "DIFF_SNAPSHOT_SPECIAL_FILE": "SOURCE_FILE_CHANGED",
        "DIFF_SNAPSHOT_UNSAFE_PATH": "SOURCE_FILE_UNAVAILABLE",
        "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED": "SOURCE_WORKSPACE_UNSUPPORTED",
    }
    return TextSearchError(mapping.get(str(exc), "SOURCE_FILE_UNAVAILABLE"))


def search_text(request: TextSearchRequest) -> TextSearchReport:
    """完整扫描当前 admitted scope；任何不确定性都拒绝返回部分结果。"""
    project_root, scope = _validate_scope(request)
    deadline = time.monotonic() + request.timeout
    matcher = _compile_matcher(request)
    hits: list[TextSearchHit] = []
    files_scanned = 0
    bytes_scanned = 0
    binary_files_skipped = 0

    try:
        candidates = walk_candidate_entries(
            str(project_root),
            excluded_dir_names=_EXCLUDED_DIR_NAMES,
            entry_budget=_MAX_ENTRIES,
            path_byte_budget=_MAX_PATH_BYTES,
            discovery_seconds=max(deadline - time.monotonic(), 0.0),
            budget_error="SOURCE_DISCOVERY_BUDGET_EXCEEDED",
            start_relative=(
                ""
                if scope == project_root
                else scope.relative_to(project_root).as_posix()
            ),
        )
        for raw_path in candidates:
            if time.monotonic() >= deadline:
                raise TextSearchError("SOURCE_SCAN_BUDGET_EXCEEDED")
            path = Path(raw_path)
            try:
                root_relative = path.relative_to(project_root).as_posix()
                scope_relative = path.relative_to(scope).as_posix()
            except ValueError:
                continue
            if any(part.startswith(".") for part in PurePosixPath(root_relative).parts):
                continue
            if (
                request.include_globs
                and not _matches_glob(scope_relative, request.include_globs)
            ) or _matches_glob(scope_relative, request.exclude_globs):
                continue
            try:
                admitted = path.lstat()
            except OSError as exc:
                raise TextSearchError("SOURCE_FILE_UNAVAILABLE") from exc
            if stat.S_ISLNK(admitted.st_mode) or not stat.S_ISREG(admitted.st_mode):
                continue
            try:
                captured = safe_index_source_path(
                    str(project_root),
                    root_relative,
                    deadline=deadline,
                    limit=_MAX_FILE_BYTES,
                )
            except SourceOracleError as exc:
                raise _map_oracle_error(exc) from exc
            if captured.kind != "file" or captured.data is None:
                raise TextSearchError("SOURCE_FILE_CHANGED")
            raw = captured.data
            files_scanned += 1
            bytes_scanned += len(raw)
            if bytes_scanned > _MAX_TOTAL_BYTES:
                raise TextSearchError("SOURCE_SCAN_BUDGET_EXCEEDED")
            if b"\x00" in raw:
                binary_files_skipped += 1
                continue
            for number, line in enumerate(decode_index_source(raw).splitlines(), 1):
                match = matcher.search(line)
                if match is None:
                    continue
                hits.append(
                    TextSearchHit(
                        file=root_relative,
                        line=number,
                        column=match.start() + 1,
                        text=line,
                    )
                )
                if len(hits) > _MAX_MATCHES:
                    raise TextSearchError("SOURCE_MATCH_BUDGET_EXCEEDED")
    except CandidateDiscoveryBudgetExceeded as exc:
        raise TextSearchError("SOURCE_DISCOVERY_BUDGET_EXCEEDED") from exc
    except CandidateDiscoveryError as exc:
        raise TextSearchError("SOURCE_DISCOVERY_FAILED") from exc

    hits.sort(key=lambda hit: (hit.file, hit.line, hit.column))
    return TextSearchReport(
        hits=tuple(hits),
        files_scanned=files_scanned,
        bytes_scanned=bytes_scanned,
        binary_files_skipped=binary_files_skipped,
    )


def _request_payload(request: TextSearchRequest) -> dict[str, Any]:
    payload = asdict(request)
    payload["include_globs"] = list(request.include_globs)
    payload["exclude_globs"] = list(request.exclude_globs)
    return payload


def _report_payload(report: TextSearchReport) -> dict[str, Any]:
    return {
        "hits": [asdict(hit) for hit in report.hits],
        "files_scanned": report.files_scanned,
        "bytes_scanned": report.bytes_scanned,
        "binary_files_skipped": report.binary_files_skipped,
        "scan_complete": report.scan_complete,
    }


def _report_from_payload(payload: Any) -> TextSearchReport:
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
        raise TextSearchError("SOURCE_WORKER_INVALID_RESPONSE")
    try:
        hits = tuple(TextSearchHit(**item) for item in payload["hits"])
        return TextSearchReport(
            hits=hits,
            files_scanned=int(payload["files_scanned"]),
            bytes_scanned=int(payload["bytes_scanned"]),
            binary_files_skipped=int(payload["binary_files_skipped"]),
            scan_complete=payload["scan_complete"] is True,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TextSearchError("SOURCE_WORKER_INVALID_RESPONSE") from exc


def search_text_bounded(request: TextSearchRequest) -> TextSearchReport:
    """在可终止的 Python 子进程中运行检索并验证 JSON 协议。"""
    process = subprocess.Popen(
        [sys.executable, "-I", "-X", "utf8", "-m", "tree_sitter_analyzer.text_search"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        stdout, _stderr = process.communicate(
            json.dumps(_request_payload(request), ensure_ascii=False),
            timeout=request.timeout + 0.5,
        )
    except subprocess.TimeoutExpired as exc:
        process.kill()
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            raise TextSearchError("SOURCE_WORKER_CLEANUP_FAILED") from exc
        raise TextSearchError("SOURCE_SCAN_BUDGET_EXCEEDED") from exc
    if process.returncode:
        raise TextSearchError("SOURCE_WORKER_FAILED")
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise TextSearchError("SOURCE_WORKER_INVALID_RESPONSE") from exc
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        raise TextSearchError(payload["error"])
    return _report_from_payload(payload)


def _main() -> None:
    """内部 worker 协议只在标准输入和标准输出传递 JSON。"""
    try:
        payload = json.loads(sys.stdin.read(1024 * 1024))
        request = TextSearchRequest(
            project_root=payload["project_root"],
            root=payload["root"],
            query=payload["query"],
            case_mode=payload["case_mode"],
            word_match=payload["word_match"],
            include_globs=tuple(payload["include_globs"]),
            exclude_globs=tuple(payload["exclude_globs"]),
            timeout=float(payload["timeout"]),
        )
        encoded = json.dumps(_report_payload(search_text(request)), ensure_ascii=False)
    except (KeyError, TypeError, ValueError, TextSearchError) as exc:
        code = (
            exc.code
            if isinstance(exc, TextSearchError)
            else "SOURCE_WORKER_INVALID_REQUEST"
        )
        encoded = json.dumps({"error": code})
    if len(encoded.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        encoded = json.dumps({"error": "SOURCE_RESPONSE_BUDGET_EXCEEDED"})
    print(encoded)


if __name__ == "__main__":
    _main()
