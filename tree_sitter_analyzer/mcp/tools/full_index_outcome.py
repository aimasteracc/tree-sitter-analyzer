"""``index action=full`` 的答复如实反映是否发布（#1674）。

``success`` 回答"这次调用有没有交付一个可用的索引"：

* 已发布：``success: true``。只缺可选语法文件时（#1562）索引照常可用，
  ``verdict: WARN``、``completeness: incomplete``，缺失的文件列在
  ``skipped_files`` 里——它们是预期的稳定跳过，不是错误。
* 未发布：``success: false``、``verdict: ERROR``，并且总带 ``error``、
  ``error_code`` 与 ``next_step``。快照交接失效与运行期间源码变化复用
  RFC-0032 的准入码 ``INDEX_CANDIDATE_SUPERSEDED``（重试即重新捕获候选）；
  其余未认证的运行是 ``INDEX_RUN_FAILED``。

此前未发布的分支只把 ``success`` 置为 false、不给 ``error``，中央信封随后
补上 ``error_type: internal`` 与 "Review the error message"——而根本没有错误
消息，也没有内部故障；已发布但缺可选语法的成功运行同样被报告为失败。
"""

from __future__ import annotations

from typing import Any

from ...cache.admission import (
    INDEX_CANDIDATE_SUPERSEDED,
    AdmissionFailure,
    admission_fields,
)
from .full_index_grammar import missing_grammar_failures

#: 未发布且不属于准入失败的运行（阶段错误、回填错误、清单未认证）。
INDEX_RUN_FAILED = "INDEX_RUN_FAILED"
#: 已知原因导致未发布时的 ``error_type``；未预料的异常仍按信封规则归类。
INDEX_NOT_PUBLISHED = "index_not_published"
#: 运行期间源码变化（与清单警告同名的原因码）。
INDEX_CANDIDATE_SNAPSHOT_CHANGED = "INDEX_CANDIDATE_SNAPSHOT_CHANGED"
#: ``skipped_files`` 列出的上限；总数始终写明。
SKIPPED_FILES_CAP = 20

_NOTHING_PUBLISHED = "Nothing was published and the active index (if any) is unchanged."
RUN_FAILED_NEXT_STEP = (
    f"{_NOTHING_PUBLISHED} Fix the cause named in `error` (see `phases` for "
    "per-phase details), then re-run index action=full mode=full."
)


def published_result(result: dict[str, Any], *, stable_only: bool) -> dict[str, Any]:
    """已发布：成功；只缺可选语法时如实标注不完整并列出跳过的文件。"""
    published: dict[str, Any] = {**result, "success": True, "published": True}
    if stable_only and not result.get("scope_complete"):
        skipped = [
            {"file": path, "reason": reason}
            for path, reason in missing_grammar_failures(result.get("phases") or {})
        ]
        published["completeness"] = "incomplete"
        published["skipped_files"] = skipped[:SKIPPED_FILES_CAP]
        published["skipped_files_total"] = len(skipped)
        published["skipped_files_truncated"] = len(skipped) > SKIPPED_FILES_CAP
    return published


def unpublished_result(result: dict[str, Any]) -> dict[str, Any]:
    """未发布：带 ``error`` / ``error_code`` / ``next_step`` 的类型化失败。"""
    failure: dict[str, Any] = {**result, "success": False, "published": False}
    if not failure.get("error_code"):
        admission = _admission_failure(result)
        if admission is not None:
            failure.update(admission_fields(admission))
            reason = f"{admission.code} ({admission.cause_code})"
        else:
            failure["error_code"] = INDEX_RUN_FAILED
            reason = f"{INDEX_RUN_FAILED} ({'; '.join(_run_failure_reasons(result))})"
        failure.setdefault("error", f"index not published: {reason}")
    if not failure.get("next_step"):
        # 工具已给出的具体补救（如清单警告的说明）优先于通用的下一步。
        own_step = (result.get("agent_summary") or {}).get("next_step")
        failure["next_step"] = (
            f"{_NOTHING_PUBLISHED} {own_step}" if own_step else RUN_FAILED_NEXT_STEP
        )
    failure.setdefault("error_type", INDEX_NOT_PUBLISHED)
    summary_line = f"codegraph_full_index: not published ({failure['error_code']})"
    failure["verdict"] = "ERROR"
    failure["summary_line"] = summary_line
    failure["agent_summary"] = {
        "verdict": "ERROR",
        "summary_line": summary_line,
        "next_step": failure["next_step"],
    }
    return failure


def _admission_failure(result: dict[str, Any]) -> AdmissionFailure | None:
    """快照交接失效、运行期间源码变化：重新捕获候选即可，复用准入码。"""
    ast_phase = (result.get("phases") or {}).get("ast_cache") or {}
    handoff = ast_phase.get("snapshot_handoff_error")
    if isinstance(handoff, str) and handoff:
        return AdmissionFailure(INDEX_CANDIDATE_SUPERSEDED, handoff)
    snapshot = result.get("candidate_snapshot") or {}
    if int(snapshot.get("changed_during_run") or 0) > 0:
        return AdmissionFailure(
            INDEX_CANDIDATE_SUPERSEDED, INDEX_CANDIDATE_SNAPSHOT_CHANGED
        )
    return None


def _run_failure_reasons(result: dict[str, Any]) -> list[str]:
    """阶段错误优先；没有阶段错误时给出使运行未被认证的条件。"""
    phases = result.get("phases") or {}
    errors = [
        f"phase {name}: {phase.get('error') or 'error'}"
        for name, phase in phases.items()
        if isinstance(phase, dict) and phase.get("status") == "error"
    ]
    if errors:
        return errors
    reasons: list[str] = []
    backfill_errors = int((phases.get("ast_cache") or {}).get("backfill_errors") or 0)
    if backfill_errors:
        reasons.append(f"{backfill_errors} backfill error(s)")
    snapshot = result.get("candidate_snapshot") or {}
    if snapshot and not (
        snapshot.get("selection_reconciled", True)
        and snapshot.get("phase_totals_reconciled", True)
    ):
        reasons.append("the candidate selection did not reconcile with the phases")
    if result.get("manifest_warning"):
        reasons.append(str(result["manifest_warning"]))
    return reasons or ["the run was not certified"]
