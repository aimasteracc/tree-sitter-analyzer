"""类型化索引写入准入失败（RFC-0032 slice 4，#1554）。

写入路由（MCP ``index``/``sync``、CLI、watcher）此前把准入失败报告为裸异常文本，
例如 ``Sync failed: OperationalError: database is locked``，调用方无法区分
"稍后重试即可" 与 "需要人工恢复"。本模块是三类准入码的唯一定义：

* ``INDEX_CANDIDATE_SUPERSEDED``：候选所属父版本或源码已变化，必须重新捕获；
* ``INDEX_WRITER_BUSY``：另一写入者持有发布租约，或 Windows 无法原子替换选择器；
* ``INDEX_RECOVERY_REQUIRED``：选择器损坏/缺失或存储路径不安全，重试无效。

异常消息（``str(exc)``）保持为细粒度原因码（``cause_code``），已有 ``error``
文本与 CLI 退出码 1 不变；类型化字段是追加的。本模块只依赖标准库，
供 ``_win_fileops`` 等底层模块导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INDEX_CANDIDATE_SUPERSEDED = "INDEX_CANDIDATE_SUPERSEDED"
INDEX_WRITER_BUSY = "INDEX_WRITER_BUSY"
INDEX_RECOVERY_REQUIRED = "INDEX_RECOVERY_REQUIRED"

RETRY_AFTER_MS = 5000
_CAUSE_CHAIN_LIMIT = 5


@dataclass(frozen=True)
class AdmissionContract:
    """一个准入码的机器字段与给代理的下一步。"""

    retryable: bool
    retry_after_ms: int
    next_action: str
    summary: str
    next_step: str


ADMISSION_CODES: dict[str, AdmissionContract] = {
    INDEX_CANDIDATE_SUPERSEDED: AdmissionContract(
        retryable=True,
        retry_after_ms=RETRY_AFTER_MS,
        next_action="recapture",
        summary="the index candidate was superseded by a newer index state",
        next_step=(
            "Nothing was written and the current index is unchanged: another "
            "write or a source edit superseded this candidate. Retry the same "
            "index call; it captures a fresh candidate. Do not replay the old "
            "candidate."
        ),
    ),
    INDEX_WRITER_BUSY: AdmissionContract(
        retryable=True,
        retry_after_ms=RETRY_AFTER_MS,
        next_action="recapture",
        summary="another writer holds the index",
        next_step=(
            "Nothing was written and the current index is unchanged: another "
            "TSA process is writing this index. Wait retry_after_ms, then retry "
            "the same index call; if it stays busy, stop the other writer "
            "(watcher, MCP server or CLI run) for this project."
        ),
    ),
    INDEX_RECOVERY_REQUIRED: AdmissionContract(
        retryable=False,
        retry_after_ms=0,
        next_action="recover_index",
        summary="the index storage needs recovery",
        next_step=(
            "Nothing was written: the index selector or writer state is damaged "
            "or missing, or the index storage path is a link. Retrying will not "
            "help and TSA does not repair it automatically. Stop every TSA "
            "process for this project, move the project's .ast-cache directory "
            "(or the custom index database) aside, replacing a linked .ast-cache "
            "with a real directory, then rebuild with `index action=full "
            "mode=full` (CLI `--full-index --full-index-mode full`)."
        ),
    ),
}

# 细粒度原因码（异常消息）→ 准入码。RFC-0032 Revision 1 的映射加上同类原因：
# 存储目录被替换、跨存储候选、退役竞争都是“父身份已变化，重新捕获即可”；
# 锁文件不安全与路径不安全同属需要人工处理的存储状态。
CAUSE_CODES: dict[str, str] = {
    "INDEX_GENERATION_SUPERSEDED": INDEX_CANDIDATE_SUPERSEDED,
    "INDEX_GENERATION_SOURCE_CHANGED": INDEX_CANDIDATE_SUPERSEDED,
    "INDEX_GENERATION_DIRECTORY_CHANGED": INDEX_CANDIDATE_SUPERSEDED,
    "INDEX_GENERATION_FOREIGN_STORE": INDEX_CANDIDATE_SUPERSEDED,
    "INDEX_GENERATION_RETIRING": INDEX_CANDIDATE_SUPERSEDED,
    # slice 5：自定义路径的修订号 CAS 失败，或数据库被整体替换（cache_uuid 变化）。
    "INDEX_WRITER_REVISION_SUPERSEDED": INDEX_CANDIDATE_SUPERSEDED,
    "INDEX_WRITER_CACHE_REPLACED": INDEX_CANDIDATE_SUPERSEDED,
    "INDEX_WRITER_BUSY": INDEX_WRITER_BUSY,
    "INDEX_GENERATION_SELECTOR_INVALID": INDEX_RECOVERY_REQUIRED,
    "INDEX_GENERATION_SELECTOR_MISSING": INDEX_RECOVERY_REQUIRED,
    "INDEX_GENERATION_PATH_UNSAFE": INDEX_RECOVERY_REQUIRED,
    "INDEX_GENERATION_LOCK_UNSAFE": INDEX_RECOVERY_REQUIRED,
    # slice 5：schema 18 的写入状态行缺失或损坏，写入失败关闭。
    "INDEX_WRITER_STATE_MISSING": INDEX_RECOVERY_REQUIRED,
}


class IndexWriteAdmissionError(RuntimeError):
    """写入在修改任何行之前被拒绝；``str(exc)`` 仍是细粒度原因码。"""

    default_code = INDEX_CANDIDATE_SUPERSEDED

    def __init__(self, cause_code: str) -> None:
        super().__init__(cause_code)
        self.cause_code = cause_code

    @property
    def code(self) -> str:
        return CAUSE_CODES.get(self.cause_code, self.default_code)

    @property
    def retryable(self) -> bool:
        return ADMISSION_CODES[self.code].retryable

    @property
    def retry_after_ms(self) -> int:
        return ADMISSION_CODES[self.code].retry_after_ms

    @property
    def next_action(self) -> str:
        return ADMISSION_CODES[self.code].next_action


class Superseded(IndexWriteAdmissionError):
    """候选所属的父版本或写入修订号已被替换，不能借用新状态的写入权限。

    默认定位符由发布选择器 CAS 抛出，自定义路径由 ``ast_writer_state`` 修订号
    CAS 抛出（slice 5）；准入码见 ``CAUSE_CODES``（通常为
    ``INDEX_CANDIDATE_SUPERSEDED``）。``generation_store.Superseded`` 是同一类。
    """


@dataclass(frozen=True)
class AdmissionFailure:
    """从任一异常归类出的准入失败。"""

    code: str
    cause_code: str

    @property
    def contract(self) -> AdmissionContract:
        return ADMISSION_CODES[self.code]


def _classify_one(exc: BaseException) -> AdmissionFailure | None:
    if isinstance(exc, IndexWriteAdmissionError):
        return AdmissionFailure(exc.code, exc.cause_code)
    # 选择器/路径错误是 ValueError，源码变化是 RuntimeError；它们的消息就是原因码。
    if isinstance(exc, (RuntimeError, ValueError)) and len(exc.args) == 1:
        cause = exc.args[0]
        if isinstance(cause, str) and cause in CAUSE_CODES:
            return AdmissionFailure(CAUSE_CODES[cause], cause)
    return None


def admission_failure_of(exc: BaseException) -> AdmissionFailure | None:
    """归类异常及其有界的 ``__cause__`` 链；非准入失败返回 None。"""
    current: BaseException | None = exc
    for _ in range(_CAUSE_CHAIN_LIMIT):
        if current is None:
            return None
        failure = _classify_one(current)
        if failure is not None:
            return failure
        current = current.__cause__
    return None


def admission_fields(failure: AdmissionFailure) -> dict[str, Any]:
    """RFC-0032 规定的机器字段；路由可把它们并入已有的失败答复。"""
    contract = failure.contract
    return {
        "error_code": failure.code,
        "cause_code": failure.cause_code,
        "retryable": contract.retryable,
        "retry_after_ms": contract.retry_after_ms,
        "next_action": contract.next_action,
        "next_step": contract.next_step,
    }


def admission_failure_payload(failure: AdmissionFailure, error: str) -> dict[str, Any]:
    """CLI、MCP 与 watcher 共用的失败答复；``error`` 由路由给出且保持原文。"""
    summary_line = (
        f"index not written: {failure.code} ({failure.cause_code}): "
        f"{failure.contract.summary}"
    )
    fields = admission_fields(failure)
    return {
        "success": False,
        "verdict": "ERROR",
        "error": error,
        **fields,
        "summary_line": summary_line,
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": fields["next_step"],
        },
    }
