"""在实时项目源码中执行有界、无索引的字面量文本检索。"""

from __future__ import annotations

import fnmatch
import json
import re
import stat
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from .index_candidate_walker import (
    CandidateDiscoveryBudgetExceeded,
    CandidateDiscoveryError,
    walk_candidate_entries,
)
from .indexing_snapshot import decode_index_source
from .source_oracle import SafePath, SourceBatchReader, SourceOracleError

CaseMode = Literal["smart", "sensitive", "insensitive"]

_MAX_ENTRIES = 100_000
_MAX_PATH_BYTES = 16 * 1024 * 1024
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_MATCHES = 100_000
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
# #1783：5 s 在冷缓存 + 实时防护的 Windows 上连 500 个文件都扫不完；与候选发现
# 预算（discovery_budget.DISCOVERY_BASE_SECONDS）保持同一量级。
DEFAULT_TEXT_SEARCH_TIMEOUT_SECONDS = 30.0
# 解释器启动与导入不计入扫描预算，只由父进程的强制终止点额外放宽。
_WORKER_STARTUP_SECONDS = 15.0
_READ_WORKERS = 8
_READ_AHEAD = 2 * _READ_WORKERS
_PROGRESS_INTERVAL_SECONDS = 0.25
_EXCLUDED_DIR_NAMES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", "target"}
)


class TextSearchError(RuntimeError):
    """文本检索无法证明完整结果时返回的稳定错误。

    ``details`` 在预算类失败时说明哪个预算 (``budget.name``)、上限
    (``budget.limit`` / ``budget.unit``) 以及失败时的扫描进度 (``progress``)。
    """

    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.details = details
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
    timeout: float = DEFAULT_TEXT_SEARCH_TIMEOUT_SECONDS


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


@dataclass(frozen=True, slots=True)
class _AdmittedSource:
    """通过统一发现与源码认证后的单文件字节。"""

    file: str
    data: bytes


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


class _ScanProgress:
    """扫描进度计数器；只用于错误载荷，从不代表完整结果。"""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.phase = "scan"
        self.candidates_discovered = 0
        self.files_scanned = 0
        self.bytes_scanned = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "candidates_discovered": self.candidates_discovered,
            "files_scanned": self.files_scanned,
            "bytes_scanned": self.bytes_scanned,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
        }


def _budget_error(
    code: str,
    progress: _ScanProgress | None,
    *,
    name: str,
    limit: float | None,
    unit: str,
    **extra: Any,
) -> TextSearchError:
    """构造说明哪个预算、上限多少、扫描到哪里的稳定错误。"""
    details: dict[str, Any] = {
        "budget": {"name": name, "limit": limit, "unit": unit, **extra},
    }
    if progress is not None:
        details["progress"] = progress.snapshot()
    return TextSearchError(code, details)


def _admitted_paths(
    request: TextSearchRequest,
    project_root: Path,
    scope: Path,
    deadline: float,
    progress: _ScanProgress | None,
) -> Iterator[str]:
    """按统一发现顺序产生通过路径 admission 的 project-relative 路径。

    文件类型 admission（lstat）在读取线程中完成，见 ``_read_admitted``。
    """
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
                raise _budget_error(
                    "SOURCE_SCAN_BUDGET_EXCEEDED",
                    progress,
                    name="time",
                    limit=request.timeout,
                    unit="seconds",
                )
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
            if progress is not None:
                progress.candidates_discovered += 1
            yield root_relative
    except CandidateDiscoveryBudgetExceeded as exc:
        raise _budget_error(
            "SOURCE_DISCOVERY_BUDGET_EXCEEDED",
            progress,
            name=exc.budget,
            limit=exc.limit,
            unit={"entries": "entries", "path_bytes": "bytes", "time": "seconds"}.get(
                exc.budget, "unknown"
            ),
            entries_seen=exc.entries,
        ) from exc
    except CandidateDiscoveryError as exc:
        raise TextSearchError("SOURCE_DISCOVERY_FAILED") from exc


def _read_admitted(
    reader: SourceBatchReader, project_root: Path, relative: str
) -> SafePath | None:
    """在读取线程中完成 lstat admission 与认证读取；symlink/非普通文件返回 None。

    Windows 上 ``lstat`` 本身也要打开句柄，串行执行时同样计入扫描耗时（#1783）。
    """
    try:
        admitted = (project_root / relative).lstat()
    except OSError as exc:
        raise TextSearchError("SOURCE_FILE_UNAVAILABLE") from exc
    if stat.S_ISLNK(admitted.st_mode) or not stat.S_ISREG(admitted.st_mode):
        return None
    return reader.read(relative, limit=_MAX_FILE_BYTES)


def _oracle_failure(
    exc: SourceOracleError,
    request: TextSearchRequest,
    progress: _ScanProgress | None,
    relative: str | None = None,
) -> TextSearchError:
    """把认证读取失败映射为稳定错误；预算类失败附带预算与进度。"""
    where = {} if relative is None else {"file": relative}
    if str(exc) == "DIFF_SNAPSHOT_TIMEOUT":
        return _budget_error(
            "SOURCE_SCAN_BUDGET_EXCEEDED",
            progress,
            name="time",
            limit=request.timeout,
            unit="seconds",
            **where,
        )
    if str(exc) == "DIFF_SNAPSHOT_CAPACITY":
        return _budget_error(
            "SOURCE_FILE_BUDGET_EXCEEDED",
            progress,
            name="file_bytes",
            limit=_MAX_FILE_BYTES,
            unit="bytes",
            **where,
        )
    return _map_oracle_error(exc)


def _capture(
    future: Future[SafePath | None],
    relative: str,
    request: TextSearchRequest,
    progress: _ScanProgress | None,
) -> _AdmittedSource | None:
    try:
        captured = future.result()
    except SourceOracleError as exc:
        raise _oracle_failure(exc, request, progress, relative) from exc
    if captured is None:
        return None
    if captured.kind != "file" or captured.data is None:
        raise TextSearchError("SOURCE_FILE_CHANGED")
    return _AdmittedSource(file=relative, data=captured.data)


def _admitted_sources(
    request: TextSearchRequest,
    project_root: Path,
    scope: Path,
    deadline: float,
    progress: _ScanProgress | None = None,
) -> Iterator[_AdmittedSource]:
    """按发现顺序产生权威文件字节，供原生与资格扫描共享。

    #1783：逐个串行读取时，每个文件的首次打开在开启实时防护的 Windows 上要付出
    数十毫秒的扫描延迟，553 个文件就超过 5 s 预算。这里用有界线程池预读最多
    ``_READ_AHEAD`` 个文件（内存仍有界），产出顺序与发现顺序一致；批量读取器在
    全部文件产出后统一复核目录身份，复核失败则整次扫描失败。
    """
    try:
        reader = SourceBatchReader(str(project_root), deadline=deadline)
    except SourceOracleError as exc:
        raise _oracle_failure(exc, request, progress) from exc
    try:
        with reader:
            yield from _read_ahead(
                reader,
                project_root,
                _admitted_paths(request, project_root, scope, deadline, progress),
                request,
                progress,
            )
            reader.verify()
    except SourceOracleError as exc:
        raise _oracle_failure(exc, request, progress) from exc


def _read_ahead(
    reader: SourceBatchReader,
    project_root: Path,
    paths: Iterator[str],
    request: TextSearchRequest,
    progress: _ScanProgress | None,
) -> Iterator[_AdmittedSource]:
    """有界并发预读；读取线程在读取器释放目录句柄之前全部结束。"""
    pool = ThreadPoolExecutor(
        max_workers=_READ_WORKERS, thread_name_prefix="tsa-text-search"
    )
    pending: deque[tuple[str, Future[SafePath | None]]] = deque()

    def drain_one() -> _AdmittedSource | None:
        path, future = pending.popleft()
        return _capture(future, path, request, progress)

    try:
        for relative in paths:
            pending.append(
                (
                    relative,
                    pool.submit(_read_admitted, reader, project_root, relative),
                )
            )
            if len(pending) >= _READ_AHEAD and (source := drain_one()) is not None:
                yield source
        while pending:
            if (source := drain_one()) is not None:
                yield source
    finally:
        for _path, future in pending:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)


def search_text(
    request: TextSearchRequest,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> TextSearchReport:
    """完整扫描当前 admitted scope；任何不确定性都拒绝返回部分结果。"""
    project_root, scope = _validate_scope(request)
    matcher = _compile_matcher(request)
    # 解码器的首次导入（chardet 原生扩展）不属于扫描工作量，在计时开始前完成。
    from . import encoding_utils  # noqa: F401

    progress = _ScanProgress()
    deadline = progress.started + request.timeout
    hits: list[TextSearchHit] = []
    binary_files_skipped = 0

    for source in _admitted_sources(request, project_root, scope, deadline, progress):
        raw = source.data
        progress.files_scanned += 1
        progress.bytes_scanned += len(raw)
        if progress.bytes_scanned > _MAX_TOTAL_BYTES:
            raise _budget_error(
                "SOURCE_SCAN_BUDGET_EXCEEDED",
                progress,
                name="total_bytes",
                limit=_MAX_TOTAL_BYTES,
                unit="bytes",
            )
        if on_progress is not None:
            on_progress(progress.snapshot())
        if b"\x00" in raw:
            binary_files_skipped += 1
            continue
        for number, line in enumerate(decode_index_source(raw).splitlines(), 1):
            match = matcher.search(line)
            if match is None:
                continue
            hits.append(
                TextSearchHit(
                    file=source.file,
                    line=number,
                    column=match.start() + 1,
                    text=line,
                )
            )
            if len(hits) > _MAX_MATCHES:
                raise _budget_error(
                    "SOURCE_MATCH_BUDGET_EXCEEDED",
                    progress,
                    name="matches",
                    limit=_MAX_MATCHES,
                    unit="lines",
                )

    hits.sort(key=lambda hit: (hit.file, hit.line, hit.column))
    return TextSearchReport(
        hits=tuple(hits),
        files_scanned=progress.files_scanned,
        bytes_scanned=progress.bytes_scanned,
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


def _last_progress(stderr: str | None) -> dict[str, Any] | None:
    """从 worker 的 stderr 进度行中取最后一条合法快照。"""
    for line in reversed((stderr or "").splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("progress"), dict):
            return dict(payload["progress"])
    return None


def search_text_bounded(request: TextSearchRequest) -> TextSearchReport:
    """在可终止的 Python 子进程中运行检索并验证 JSON 协议。

    扫描预算 ``request.timeout`` 在 worker 完成解释器启动与导入后才开始计时；
    父进程的强制终止点额外给出 ``_WORKER_STARTUP_SECONDS``，避免冷启动把预算
    吃掉（#1783）。终止时从 stderr 进度行报告扫描进度。
    """
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
            timeout=request.timeout + _WORKER_STARTUP_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        process.kill()
        try:
            _stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            raise TextSearchError("SOURCE_WORKER_CLEANUP_FAILED") from exc
        progress = _last_progress(stderr) or {"phase": "worker_startup"}
        raise TextSearchError(
            "SOURCE_SCAN_BUDGET_EXCEEDED",
            {
                "budget": {
                    "name": "time",
                    "limit": request.timeout,
                    "unit": "seconds",
                    "worker_startup_allowance": _WORKER_STARTUP_SECONDS,
                    "enforced_by": "worker_kill",
                },
                "progress": progress,
            },
        ) from exc
    if process.returncode:
        raise TextSearchError("SOURCE_WORKER_FAILED")
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise TextSearchError("SOURCE_WORKER_INVALID_RESPONSE") from exc
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        details = payload.get("details")
        raise TextSearchError(
            payload["error"], details if isinstance(details, dict) else None
        )
    return _report_from_payload(payload)


def _progress_writer() -> Callable[[dict[str, Any]], None]:
    """把进度节流写到 stderr，父进程强制终止时仍能说明扫描到哪里。"""
    last = [0.0]

    def write(snapshot: dict[str, Any]) -> None:
        now = time.monotonic()
        if now - last[0] < _PROGRESS_INTERVAL_SECONDS:
            return
        last[0] = now
        sys.stderr.write(json.dumps({"progress": snapshot}) + "\n")
        sys.stderr.flush()

    return write


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
        report = search_text(request, on_progress=_progress_writer())
        encoded = json.dumps(_report_payload(report), ensure_ascii=False)
    except (KeyError, TypeError, ValueError, TextSearchError) as exc:
        if isinstance(exc, TextSearchError):
            failure: dict[str, Any] = {"error": exc.code}
            if exc.details is not None:
                failure["details"] = exc.details
        else:
            failure = {"error": "SOURCE_WORKER_INVALID_REQUEST"}
        encoded = json.dumps(failure, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        encoded = json.dumps(
            {
                "error": "SOURCE_RESPONSE_BUDGET_EXCEEDED",
                "details": {
                    "budget": {
                        "name": "response_bytes",
                        "limit": _MAX_RESPONSE_BYTES,
                        "unit": "bytes",
                    }
                },
            }
        )
    print(encoded)


if __name__ == "__main__":
    _main()
