"""NO1-010B B1 第一切片：补丁验证流水线（RFC-0026 §2/§3/§5）。

``verify_patch`` 接收一条 corpus 记录与外部提供的补丁，依次执行：

1. 补丁输入界限 → ``UNKNOWN/PATCH_OVER_BOUND``；不可解析/不可应用 →
   ``UNKNOWN/PATCH_NOT_APPLICABLE``（隔离副本中 ``git apply --check``，不 fuzz）；
2. 段感知 allowlist 对照实际应用的差分 → ``FAIL/PATH_VIOLATION``；
3. 经 wrapper 运行 oracle（oracle 文件先复制进 scratch）→ 加载/执行/协议/超时
   UNKNOWN 子码或 ``FAIL/ORACLE_FAILED``；
4. 冻结环境下运行类型化 ``verification_argv`` → ``FAIL/VERIFICATION_FAILED`` 或
   ``VERIFICATION_EXECUTION_ERROR`` / ``VERIFICATION_TIMEOUT``；
5. 每条命令之后复核候选树快照（含未跟踪文件、mode 与特殊文件）→ 任何改变即
   ``PATH_VIOLATION``；attempt 前后复核 corpus 中本次使用的夹具与 oracle 树 →
   任何改变即 ``UNKNOWN/SANDBOX_FAILURE``（attempt 无效）。

第 3 步起各结局经 ``runner.classify`` 的统一优先级合成（UNKNOWN 优先于任何
FAIL），不在本模块另设顺序。

**判定权（verdict authority）**：oracle 必须在同一进程内导入候选代码，没有内核
沙箱时候选代码可以伪造 oracle 结果（替换 stdout、改写控制文件、``os._exit``），
也可以篡改其后命令可见的一切。因此只有 *在任何候选控制的代码运行之前* 判定的
结局才是 RFC 终态：``UNKNOWN/PATCH_NOT_APPLICABLE``、``UNKNOWN/PATCH_OVER_BOUND``
与 allowlist 检查得出的 ``FAIL/PATH_VIOLATION``。其余一切结局（含 PASS）只作为
provisional 的 ``checks_verdict`` 上报，``terminal`` 为 ``None``，并由
``authority_requires`` 机读地给出所缺的 ``read_only_candidate_mount`` 与
``write_journal``。``checks_not_implemented`` 另列全部尚未实现的检查与隔离边界。
"""

from __future__ import annotations

import json
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .candidate import (
    COPY_IGNORED,
    CandidateError,
    OutputCap,
    apply_patch,
    changed_entries,
    changed_files,
    copy_fixture,
    env_digest,
    frozen_env,
    remove_tree,
    resolve_tools,
    run_bounded,
    tree_snapshot,
)
from .oracle import ORACLE_OUTPUT_MAX_BYTES, ORACLE_TIMEOUT_S, OracleStatus
from .oracle import _parse_result_line as parse_declared_result
from .patch import PatchBoundError, PatchFormatError, validate_patch
from .record import BenchmarkRecord, UnknownReasonCode
from .runner import Verdict, allowlist_violations, classify

VERIFICATION_TIMEOUT_S = 120.0
# Windows NTSTATUS 错误码（无符号 ≥ 0xC0000000，如 0xC0000005 访问冲突）是崩溃。
_NTSTATUS_ERROR_MIN = 0xC0000000
_CONTROL_MAX_BYTES = 16 * 1024
_WRAPPER = Path(__file__).with_name("oracle_wrapper.py")
AUTHORITY_REQUIRES = ("read_only_candidate_mount", "write_journal")
_NOT_IMPLEMENTED = (
    "read_only_candidate_mount",
    "write_journal",
    "network_isolation",
    "runner_venv_isolation",
    "home_isolation",
    "process_escape_containment",
    "stale_rows",
    "unsupported_relationship",
    "registration_registry",
)
_PASS = Verdict("PASS")
_SANDBOX_FAILURE = Verdict("UNKNOWN", "SANDBOX_FAILURE")


@dataclass(frozen=True)
class AttemptOutcome:
    """一次 attempt 的结果：已实现检查的判定 + 判定权缺口 + 未实现检查清单。"""

    checks_verdict: Verdict
    checks_not_implemented: tuple[str, ...]
    # 非空即 provisional：判定发生在候选代码运行之后，需要这些边界才有判定权。
    authority_requires: tuple[str, ...] = AUTHORITY_REQUIRES
    # 冻结环境摘要（workspace 路径已归一化）；未建立环境时为 None。
    env_digest: str | None = None

    @property
    def terminal(self) -> Verdict | None:
        """RFC 终态；provisional 判定或仍有未实现检查的 PASS 一律为 ``None``。"""
        if self.authority_requires:
            return None
        if self.checks_verdict == _PASS and self.checks_not_implemented:
            return None
        return self.checks_verdict


@dataclass(frozen=True)
class _Attempt:
    """单次 attempt 的固定输入（记录、corpus 来源路径、超时）。"""

    record: BenchmarkRecord
    fixture: Path
    oracle: Path
    oracle_timeout_s: float
    verification_timeout_s: float

    def corpus_snapshot(self) -> tuple[dict[str, str], dict[str, str]]:
        """本次使用的夹具树与 oracle 树（忽略不被复制的缓存目录）。"""
        return (
            tree_snapshot(self.fixture, COPY_IGNORED),
            tree_snapshot(self.oracle.parent, COPY_IGNORED),
        )


def _not_implemented(record: BenchmarkRecord) -> tuple[str, ...]:
    if record.task_class == "test_selection":
        return (*_NOT_IMPLEMENTED, "test_selection")
    return _NOT_IMPLEMENTED


def _patch_input_verdict(patch_text: str) -> Verdict | None:
    """补丁先过界限再解析；格式无法分类的补丁同样不可应用。"""
    try:
        validate_patch(patch_text)
    except PatchBoundError:
        return Verdict("UNKNOWN", "PATCH_OVER_BOUND")
    except (PatchFormatError, UnicodeEncodeError):
        return Verdict("UNKNOWN", "PATCH_NOT_APPLICABLE")
    return None


def _unknown_reason(*verdicts: Verdict) -> UnknownReasonCode | None:
    for verdict in verdicts:
        if verdict.status == "UNKNOWN":
            return cast(UnknownReasonCode, verdict.reason_code)
    return None


def _crashed(returncode: int) -> bool:
    """信号终止（负值）或 Windows NTSTATUS 崩溃码是基础设施失败，不是产品判定。"""
    return returncode < 0 or returncode >= _NTSTATUS_ERROR_MIN


def _read_bounded(path: Path, limit: int) -> bytes | None:
    """按原始字节读取至多 ``limit + 1`` 字节；文件缺失/不可读返回 None。"""
    try:
        with path.open("rb") as handle:
            return handle.read(limit + 1)
    except OSError:
        return None


def _control_phase(control: Path) -> str | None:
    """解析 wrapper 控制记录的阶段；缺失、超限或格式错误返回 None。"""
    raw = _read_bounded(control, _CONTROL_MAX_BYTES)
    if raw is None or len(raw) > _CONTROL_MAX_BYTES:
        return None
    try:
        phase = json.loads(raw.decode("utf-8"))["phase"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return None
    return phase if isinstance(phase, str) else None


def _declared_verdict(capture: Path, expected_reason: str) -> Verdict:
    """按 B0 规则解析合流捕获：原始字节超限/不可解码/非最终声明均为协议错误。"""
    raw = _read_bounded(capture, ORACLE_OUTPUT_MAX_BYTES)
    if raw is None:
        return Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")
    if len(raw) > ORACLE_OUTPUT_MAX_BYTES:
        return Verdict("UNKNOWN", "ORACLE_PROTOCOL_ERROR")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return Verdict("UNKNOWN", "ORACLE_PROTOCOL_ERROR")
    status = parse_declared_result(text, expected_reason)
    if status is OracleStatus.FAIL:
        return Verdict("FAIL", "ORACLE_FAILED")
    if status is OracleStatus.PASS:
        return _PASS
    return Verdict("UNKNOWN", "ORACLE_PROTOCOL_ERROR")


def _oracle_verdict(
    attempt: _Attempt, root: Path, scratch: Path, env: dict[str, str]
) -> Verdict:
    """经 wrapper 运行 scratch 中的 oracle 副本，并映射为精确判定。"""
    control = scratch / "oracle-control.json"
    capture = scratch / "oracle-capture.log"
    argv = [
        sys.executable,
        "-I",
        "-X",
        f"pycache_prefix={scratch / 'pycache'}",
        "-u",
        str(_WRAPPER),
        str(scratch / "oracle" / attempt.oracle.name),
        str(control),
        str(capture),
    ]
    result = run_bounded(
        argv,
        cwd=root,
        env=env,
        timeout_s=attempt.oracle_timeout_s,
        log_path=scratch / "oracle.log",
        # 上限在捕获期间执行（不等进程退出），持续写入者不会写满磁盘。
        output_cap=OutputCap(capture, ORACLE_OUTPUT_MAX_BYTES),
    )
    if result.status == "output_limit":
        return Verdict("UNKNOWN", "ORACLE_PROTOCOL_ERROR")
    if result.status == "timeout":
        return Verdict("UNKNOWN", "ORACLE_TIMEOUT")
    if result.status != "exited" or result.returncode != 0:
        return Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")
    phase = _control_phase(control)
    if phase == "load_error":
        return Verdict("UNKNOWN", "ORACLE_LOAD_ERROR")
    if phase != "completed":
        return Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")
    return _declared_verdict(capture, attempt.record.oracle_baseline_reason)


def _verification_verdict(
    attempt: _Attempt, root: Path, scratch: Path, env: dict[str, str]
) -> Verdict:
    """运行类型化 argv：普通非 0 退出是产品失败，启动/信号/崩溃是基础设施。"""
    result = run_bounded(
        attempt.record.verification_argv,
        cwd=root,
        env=env,
        timeout_s=attempt.verification_timeout_s,
        log_path=scratch / "verification.log",
    )
    if result.status == "timeout":
        return Verdict("UNKNOWN", "VERIFICATION_TIMEOUT")
    if result.status != "exited" or result.returncode is None:
        return Verdict("UNKNOWN", "VERIFICATION_EXECUTION_ERROR")
    if _crashed(result.returncode):
        return Verdict("UNKNOWN", "VERIFICATION_EXECUTION_ERROR")
    if result.returncode != 0:
        return Verdict("FAIL", "VERIFICATION_FAILED")
    return _PASS


def _candidate_verdict(
    attempt: _Attempt,
    root: Path,
    scratch: Path,
    env: dict[str, str],
    applied: dict[str, str],
    corpus_before: tuple[dict[str, str], dict[str, str]],
) -> Verdict:
    """运行候选控制的命令；判定一旦确定即停止，结局交给 ``classify`` 合成。

    corpus 被改动意味着 attempt 本身无效，其 SANDBOX_FAILURE 优先于命令结局。
    """
    oracle = _oracle_verdict(attempt, root, scratch, env)
    path_ok = not changed_entries(applied, tree_snapshot(root))
    verification = _PASS
    if path_ok and oracle == _PASS:
        verification = _verification_verdict(attempt, root, scratch, env)
        path_ok = not changed_entries(applied, tree_snapshot(root))
    tampered = attempt.corpus_snapshot() != corpus_before
    return classify(
        path_ok=path_ok,
        oracle_ok=oracle.status != "FAIL",
        verification_ok=verification.status != "FAIL",
        stale_ok=True,
        unsupported_ok=True,
        unknown_reason=_unknown_reason(
            _SANDBOX_FAILURE if tampered else _PASS, oracle, verification
        ),
    )


def _run_attempt(
    attempt: _Attempt,
    patch_text: str,
    workspace: Path,
    not_implemented: tuple[str, ...],
) -> AttemptOutcome:
    root, scratch = workspace / "candidate", workspace / "scratch"
    scratch.mkdir()
    tools = resolve_tools()
    env = frozen_env(scratch, tools)
    digest = env_digest(env, workspace, tools)
    corpus_before = attempt.corpus_snapshot()
    copy_fixture(attempt.fixture, root)
    (scratch / "oracle").mkdir()
    shutil.copyfile(attempt.oracle, scratch / "oracle" / attempt.oracle.name)
    patch_path = scratch / "candidate.patch"
    patch_path.write_bytes(patch_text.encode("utf-8"))

    baseline = tree_snapshot(root)
    if not apply_patch(root, patch_path, env):
        verdict = Verdict("UNKNOWN", "PATCH_NOT_APPLICABLE")
        return AttemptOutcome(verdict, not_implemented, (), digest)
    applied = tree_snapshot(root)
    touched = {path.rel_path for path in validate_patch(patch_text)}
    touched.update(changed_files(baseline, applied))
    if allowlist_violations(sorted(touched), attempt.record.allowed_paths):
        verdict = Verdict("FAIL", "PATH_VIOLATION")
        return AttemptOutcome(verdict, not_implemented, (), digest)

    verdict = _candidate_verdict(attempt, root, scratch, env, applied, corpus_before)
    return AttemptOutcome(verdict, not_implemented, AUTHORITY_REQUIRES, digest)


def verify_patch(
    record: BenchmarkRecord,
    corpus_root: Path,
    patch_text: str,
    *,
    oracle_timeout_s: float = ORACLE_TIMEOUT_S,
    verification_timeout_s: float = VERIFICATION_TIMEOUT_S,
) -> AttemptOutcome:
    """在一次性隔离副本中验证外部补丁，返回已实现检查的判定及其判定权状态。"""
    not_implemented = _not_implemented(record)
    rejected = _patch_input_verdict(patch_text)
    if rejected is not None:
        return AttemptOutcome(rejected, not_implemented, ())
    attempt = _Attempt(
        record,
        (corpus_root / record.repo).resolve(),
        (corpus_root / record.oracle).resolve(),
        oracle_timeout_s,
        verification_timeout_s,
    )
    # 不用 mkdtemp：Windows 上其 0o700 ACL 会让 Git for Windows 无法读取 cwd。
    # 名称带 128 位随机数；mkdir 拒绝已存在路径，失败时绝不删除他人目录。
    name = f"tsa-no1-010b-b1-{secrets.token_hex(16)}"
    workspace = Path(tempfile.gettempdir()).resolve() / name
    try:
        workspace.mkdir()
    except OSError:
        return AttemptOutcome(_SANDBOX_FAILURE, not_implemented)
    try:
        return _run_attempt(attempt, patch_text, workspace, not_implemented)
    except (CandidateError, OSError):
        # 无法确定候选代码是否已运行：保守地作为 provisional 上报。
        return AttemptOutcome(_SANDBOX_FAILURE, not_implemented)
    finally:
        remove_tree(workspace)
