"""NO1-010B B1 第一切片：补丁验证流水线（RFC-0026 §2/§3/§5）。

``verify_patch`` 接收一条 corpus 记录与外部提供的补丁，依次执行：

1. 补丁输入界限 → ``UNKNOWN/PATCH_OVER_BOUND``；不可解析/不可应用 →
   ``UNKNOWN/PATCH_NOT_APPLICABLE``（隔离副本中 ``git apply --check``，不 fuzz）；
2. 段感知 allowlist 对照实际应用的差分 → ``FAIL/PATH_VIOLATION``；
3. 经受信 wrapper 运行 oracle → 加载/执行/协议/超时 UNKNOWN 子码或
   ``FAIL/ORACLE_FAILED``；
4. 冻结环境下运行类型化 ``verification_argv`` → ``FAIL/VERIFICATION_FAILED`` 或
   ``VERIFICATION_EXECUTION_ERROR`` / ``VERIFICATION_TIMEOUT``；
5. 每条命令之后复核候选树快照（含未跟踪文件）→ 任何改变即 ``PATH_VIOLATION``。

流水线在第一个已判定的终态处停止。命令结束后先复核快照再解释其结局：候选树
被写入是已观察到的证据，无论命令以何种方式结束。

**诚实上报（绝不伪造 PASS）**：内核只读挂载、写入日志、网络隔离、STALE_ROWS
投影比较、UNSUPPORTED_RELATIONSHIP、TEST_SELECTION_FAILED 与注册表尚未实现。
因此已实现检查全部通过时 ``checks_verdict`` 为 PASS，但 ``terminal`` 为
``None``——该 attempt 尚未到达任何 RFC 终态；只有 FAIL/UNKNOWN 才是终态，因为
排序在前的判据一旦失败，后续未实现的判据不会改变结果。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .candidate import (
    CandidateError,
    apply_patch,
    changed_entries,
    changed_files,
    copy_fixture,
    frozen_env,
    run_bounded,
    tree_snapshot,
)
from .oracle import ORACLE_OUTPUT_MAX_BYTES, ORACLE_TIMEOUT_S, OracleStatus
from .oracle import _parse_result_line as parse_declared_result
from .patch import PatchBoundError, PatchFormatError, validate_patch
from .record import BenchmarkRecord
from .runner import Verdict, allowlist_violations

VERIFICATION_TIMEOUT_S = 120.0
_WRAPPER = Path(__file__).with_name("oracle_wrapper.py")
_NOT_IMPLEMENTED = (
    "read_only_candidate_mount",
    "write_journal",
    "network_isolation",
    "stale_rows",
    "unsupported_relationship",
    "registration_registry",
)
_PASS = Verdict("PASS")


@dataclass(frozen=True)
class AttemptOutcome:
    """一次 attempt 的结果：已实现检查的判定 + 未实现检查的显式清单。"""

    checks_verdict: Verdict
    checks_not_implemented: tuple[str, ...]

    @property
    def terminal(self) -> Verdict | None:
        """RFC 终态；已实现检查全过但仍有未实现检查时为 ``None``（非 PASS）。"""
        if self.checks_verdict == _PASS and self.checks_not_implemented:
            return None
        return self.checks_verdict


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


def _oracle_verdict(
    record: BenchmarkRecord,
    corpus_root: Path,
    root: Path,
    scratch: Path,
    env: dict[str, str],
    timeout_s: float,
) -> Verdict:
    """经受信 wrapper 运行 oracle，并把控制记录映射为精确判定。"""
    control = scratch / "oracle-control.json"
    argv = [
        sys.executable,
        "-I",
        "-X",
        f"pycache_prefix={scratch / 'pycache'}",
        "-u",
        str(_WRAPPER),
        str((corpus_root / record.oracle).resolve()),
        str(control),
    ]
    result = run_bounded(
        argv, cwd=root, env=env, timeout_s=timeout_s, log_path=scratch / "oracle.log"
    )
    if result.status == "timeout":
        return Verdict("UNKNOWN", "ORACLE_TIMEOUT")
    if result.status != "exited" or result.returncode != 0 or not control.is_file():
        return Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")
    raw = control.read_bytes()
    if len(raw) > ORACLE_OUTPUT_MAX_BYTES:
        return Verdict("UNKNOWN", "ORACLE_PROTOCOL_ERROR")
    try:
        payload = json.loads(raw.decode("utf-8"))
        phase, stdout = payload["phase"], payload["stdout"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")
    if phase == "load_error":
        return Verdict("UNKNOWN", "ORACLE_LOAD_ERROR")
    if phase != "completed" or not isinstance(stdout, str):
        return Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")
    status = parse_declared_result(stdout, record.oracle_baseline_reason)
    if status is OracleStatus.FAIL:
        return Verdict("FAIL", "ORACLE_FAILED")
    if status is OracleStatus.PASS:
        return _PASS
    return Verdict("UNKNOWN", "ORACLE_PROTOCOL_ERROR")


def _verification_verdict(
    record: BenchmarkRecord,
    root: Path,
    scratch: Path,
    env: dict[str, str],
    timeout_s: float,
) -> Verdict:
    """运行类型化 argv：普通非 0 退出是产品失败，启动/信号失败是基础设施。"""
    result = run_bounded(
        record.verification_argv,
        cwd=root,
        env=env,
        timeout_s=timeout_s,
        log_path=scratch / "verification.log",
    )
    if result.status == "timeout":
        return Verdict("UNKNOWN", "VERIFICATION_TIMEOUT")
    if result.status != "exited" or result.returncode is None or result.returncode < 0:
        return Verdict("UNKNOWN", "VERIFICATION_EXECUTION_ERROR")
    if result.returncode != 0:
        return Verdict("FAIL", "VERIFICATION_FAILED")
    return _PASS


def _run_checks(
    record: BenchmarkRecord,
    corpus_root: Path,
    patch_text: str,
    workspace: Path,
    oracle_timeout_s: float,
    verification_timeout_s: float,
) -> Verdict:
    root = workspace / "candidate"
    scratch = workspace / "scratch"
    scratch.mkdir()
    env = frozen_env(scratch)
    copy_fixture((corpus_root / record.repo).resolve(), root)
    patch_path = scratch / "candidate.patch"
    patch_path.write_bytes(patch_text.encode("utf-8"))

    baseline = tree_snapshot(root)
    if not apply_patch(root, patch_path, env):
        return Verdict("UNKNOWN", "PATCH_NOT_APPLICABLE")
    applied = tree_snapshot(root)
    touched = {path.rel_path for path in validate_patch(patch_text)}
    touched.update(changed_files(baseline, applied))
    if allowlist_violations(sorted(touched), record.allowed_paths):
        return Verdict("FAIL", "PATH_VIOLATION")

    oracle = _oracle_verdict(record, corpus_root, root, scratch, env, oracle_timeout_s)
    if changed_entries(applied, tree_snapshot(root)):
        return Verdict("FAIL", "PATH_VIOLATION")
    if oracle != _PASS:
        return oracle
    verification = _verification_verdict(
        record, root, scratch, env, verification_timeout_s
    )
    if changed_entries(applied, tree_snapshot(root)):
        return Verdict("FAIL", "PATH_VIOLATION")
    return verification


def verify_patch(
    record: BenchmarkRecord,
    corpus_root: Path,
    patch_text: str,
    *,
    oracle_timeout_s: float = ORACLE_TIMEOUT_S,
    verification_timeout_s: float = VERIFICATION_TIMEOUT_S,
) -> AttemptOutcome:
    """在一次性隔离副本中验证外部补丁，返回精确的已实现检查判定。"""
    not_implemented = _not_implemented(record)
    rejected = _patch_input_verdict(patch_text)
    if rejected is not None:
        return AttemptOutcome(rejected, not_implemented)
    # 不用 mkdtemp：Windows 上其 0o700 ACL 会让 Git for Windows 无法读取 cwd。
    workspace = (
        Path(tempfile.gettempdir()).resolve() / f"tsa-no1-010b-b1-{uuid.uuid4().hex}"
    )
    try:
        workspace.mkdir()
        verdict = _run_checks(
            record,
            corpus_root,
            patch_text,
            workspace,
            oracle_timeout_s,
            verification_timeout_s,
        )
    except (CandidateError, OSError):
        verdict = Verdict("UNKNOWN", "SANDBOX_FAILURE")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    return AttemptOutcome(verdict, not_implemented)
