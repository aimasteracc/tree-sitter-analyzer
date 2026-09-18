"""运行 NO1-010B 第一条任务的 E0 参考 transcript。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404 - 仅以列表 argv 启动受信任的参考夹具
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..mcp.tools.edit_facade import build_edit_facade
from ..mcp.tools.index_facade import build_index_facade
from ..mcp.tools.search_facade import build_search_facade
from ..mcp.tools.structure_facade import build_structure_facade
from .oracle import ORACLE_TIMEOUT_S, OracleStatus
from .oracle import _parse_result_line as parse_declared_result
from .record import BenchmarkRecord, path_allowed
from .runner import allowlist_violations, diff_paths, preflight_agent_patch

REFERENCE_TASK_ID = "no1-010b/0001-bugfix-dispatch-unknown-route"
_REFERENCE_PATH = "src/dispatch.py"
_BEFORE = "    return None\n"
_AFTER = '    return Response(404, "not found")\n'
_IGNORED_PARTS = frozenset({".ast-cache", ".git", ".pytest_cache", "__pycache__"})
_GIT_TIMEOUT_S = 30
_VERIFICATION_TIMEOUT_S = 120


class ReferenceTranscriptError(RuntimeError):
    """表示参考链路未能形成可信的 E0 PASS。"""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _tree_digest(root: Path, allowed_paths: tuple[str, ...]) -> str:
    """摘要非 allowed 文件，并忽略工具及解释器产生的缓存。"""
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        rel_path = relative.as_posix()
        if path_allowed(rel_path, allowed_paths):
            continue
        entries.append((rel_path, _sha256_bytes(path.read_bytes())))
    return _sha256_bytes(
        json.dumps(entries, separators=(",", ":"), ensure_ascii=True).encode()
    )


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # nosec B603 B607
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_S,
        check=False,
    )
    if completed.returncode != 0:
        raise ReferenceTranscriptError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def _prepare_candidate(source: Path, destination: Path) -> None:
    """复制参考夹具并建立供 impact 使用的干净 Git 基线。"""
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*sorted(_IGNORED_PARTS)),
    )
    _run_git(destination, "init", "-q")
    _run_git(destination, "config", "user.email", "tsa-reference@example.invalid")
    _run_git(destination, "config", "user.name", "TSA Reference Harness")
    _run_git(destination, "add", ".")
    _run_git(destination, "commit", "-qm", "reference baseline")


def _apply_reference_edit(root: Path) -> dict[str, Any]:
    """应用首条任务唯一预注册的参考改动。"""
    target = root / _REFERENCE_PATH
    before = target.read_text(encoding="utf-8")
    if before.count(_BEFORE) != 1:
        raise ReferenceTranscriptError("reference edit anchor is not unique")
    after = before.replace(_BEFORE, _AFTER, 1)
    target.write_text(after, encoding="utf-8", newline="\n")
    return {
        "path": _REFERENCE_PATH,
        "before_sha256": _sha256_bytes(before.encode()),
        "after_sha256": _sha256_bytes(after.encode()),
    }


def _touched_paths(patch: str) -> list[str]:
    """从同一份已校验补丁取得完整、有序的 touched path 集合。"""
    return [item.rel_path for item in diff_paths(patch)]


def _require_tool_success(label: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("success") is not True:
        raise ReferenceTranscriptError(f"{label} failed: {result!r}")
    return result


def _tool_call(
    calls: list[dict[str, Any]],
    *,
    facade: str,
    action: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    """保存完整调用参数和足以判定下一步的有界响应证据。"""
    calls.append(
        {
            "sequence": len(calls) + 1,
            "kind": "tsa",
            "facade": facade,
            "action": action,
            "arguments": arguments,
            "success": result["success"],
            "verdict": result.get("verdict"),
            "evidence": evidence,
        }
    )


def _host_call(
    calls: list[dict[str, Any]],
    action: str,
    arguments: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    calls.append(
        {
            "sequence": len(calls) + 1,
            "kind": "host",
            "action": action,
            "arguments": arguments,
            "success": True,
            "evidence": evidence,
        }
    )


def _run_registered_verification(root: Path, argv: tuple[str, ...]) -> dict[str, Any]:
    """以记录中的列表 argv 运行完整验证，不经过 shell。"""
    completed = subprocess.run(  # nosec B603
        list(argv),
        cwd=str(root),
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=_VERIFICATION_TIMEOUT_S,
        check=False,
    )
    return {
        "argv": list(argv),
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "output_tail": (completed.stdout + completed.stderr)[-2000:],
    }


def _run_reference_oracle(
    root: Path, oracle_path: Path, expected_reason: str
) -> dict[str, Any]:
    """只对仓库自带参考夹具运行 oracle；不授予 B1 沙箱资格。"""
    completed = subprocess.run(  # nosec B603
        [sys.executable, "-u", str(oracle_path)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=ORACLE_TIMEOUT_S,
        check=False,
    )
    output = completed.stdout + completed.stderr
    status = (
        parse_declared_result(output, expected_reason)
        if completed.returncode == 0
        else OracleStatus.UNKNOWN
    )
    return {
        "status": status.value,
        "reason": expected_reason,
        "exit_code": completed.returncode,
        "output_tail": output[-2000:],
    }


async def run_reference_transcript(
    record: BenchmarkRecord,
    corpus_root: Path,
    *,
    workspace_parent: Path | None = None,
) -> dict[str, Any]:
    """在临时副本运行首条真实 TSA→宿主编辑→验证→oracle 链路。"""
    if record.id != REFERENCE_TASK_ID:
        raise ReferenceTranscriptError(f"unsupported reference task: {record.id}")
    if record.expected_terminal.verdict != "PASS":
        raise ReferenceTranscriptError("reference task must register terminal PASS")

    source = (corpus_root / record.repo).resolve()
    oracle_path = (corpus_root / record.oracle).resolve()
    if not source.is_dir() or not oracle_path.is_file():
        raise ReferenceTranscriptError("reference fixture or oracle is missing")

    parent = str(workspace_parent) if workspace_parent is not None else None
    with tempfile.TemporaryDirectory(prefix="tsa-no1-010b-", dir=parent) as temp_dir:
        root = Path(temp_dir) / "candidate"
        _prepare_candidate(source, root)
        non_allowed_before = _tree_digest(root, record.allowed_paths)
        calls: list[dict[str, Any]] = []

        index_args = {"action": "full", "output_format": "json"}
        index_result = _require_tool_success(
            "index.full", await build_index_facade(str(root)).execute(index_args)
        )
        _tool_call(
            calls,
            facade="index",
            action="full",
            arguments=index_args,
            result=index_result,
            evidence={
                "published": index_result.get("published"),
                "scope_complete": index_result.get("scope_complete"),
                "total_files": index_result.get("total_files"),
                "total_symbols": index_result.get("total_symbols"),
            },
        )

        search_args = {
            "action": "symbol",
            "query": "dispatch",
            "kind": "function",
            "limit": 5,
            "output_format": "json",
        }
        search_result = _require_tool_success(
            "search.symbol",
            await build_search_facade(str(root)).execute(search_args),
        )
        matches = [
            item
            for item in search_result.get("results", [])
            if item.get("name") == "dispatch" and item.get("file") == _REFERENCE_PATH
        ]
        freshness = (search_result.get("source_evidence") or {}).get("freshness")
        if len(matches) != 1 or freshness != "fresh":
            raise ReferenceTranscriptError(
                "symbol lookup did not produce one fresh target"
            )
        _tool_call(
            calls,
            facade="search",
            action="symbol",
            arguments=search_args,
            result=search_result,
            evidence={
                "freshness": freshness,
                "target": {
                    "file": matches[0]["file"],
                    "name": matches[0]["name"],
                    "kind": matches[0]["kind"],
                    "line": matches[0]["line"],
                },
            },
        )

        outline_args = {
            "action": "outline",
            "file_path": _REFERENCE_PATH,
            "output_format": "json",
        }
        outline_result = _require_tool_success(
            "structure.outline",
            await build_structure_facade(str(root)).execute(outline_args),
        )
        _tool_call(
            calls,
            facade="structure",
            action="outline",
            arguments=outline_args,
            result=outline_result,
            evidence={
                "file_path": outline_result.get("file_path"),
                "top_level_functions": outline_result.get("top_level_functions"),
            },
        )

        edit_facade = build_edit_facade(str(root))
        safe_args = {
            "action": "safe",
            "file_path": _REFERENCE_PATH,
            "edit_type": "fix_bug",
            "output_format": "json",
        }
        safe_result = _require_tool_success(
            "edit.safe", await edit_facade.execute(safe_args)
        )
        _tool_call(
            calls,
            facade="edit",
            action="safe",
            arguments=safe_args,
            result=safe_result,
            evidence={
                "risk_level": safe_result.get("risk_level"),
                "verification_command": (safe_result.get("agent_summary") or {}).get(
                    "verification_command"
                ),
            },
        )

        edit_receipt = _apply_reference_edit(root)
        _host_call(
            calls,
            "edit",
            {"path": _REFERENCE_PATH, "replacement": "unknown route -> 404"},
            edit_receipt,
        )

        patch = _run_git(root, "diff", "--binary", "--no-ext-diff")
        patch_preflight = preflight_agent_patch(patch)
        if patch_preflight is not None:
            raise ReferenceTranscriptError(
                f"reference patch rejected: {patch_preflight.as_reason()}"
            )
        changed_paths = _touched_paths(patch)
        violations = allowlist_violations(changed_paths, record.allowed_paths)
        if violations:
            raise ReferenceTranscriptError(f"reference patch violations: {violations}")
        if changed_paths != [_REFERENCE_PATH]:
            raise ReferenceTranscriptError(f"unexpected changed paths: {changed_paths}")

        impact_args = {
            "action": "impact",
            "mode": "diff",
            "resource_profile": "default",
            "output_format": "json",
        }
        impact_result = _require_tool_success(
            "edit.impact", await edit_facade.execute(impact_args)
        )
        request = impact_result.get("verification_request")
        if not isinstance(request, str):
            raise ReferenceTranscriptError(
                "impact did not issue a verification request"
            )
        _tool_call(
            calls,
            facade="edit",
            action="impact",
            arguments=impact_args,
            result=impact_result,
            evidence={
                "changed_files": impact_result.get("changed_files"),
                "verification_command": impact_result.get("verification_command"),
                "verification_request_sha256": _sha256_bytes(request.encode()),
            },
        )

        verify_args = {
            "action": "verify",
            "request": request,
            "output_format": "json",
        }
        verify_result = _require_tool_success(
            "edit.verify", await edit_facade.execute(verify_args)
        )
        if verify_result.get("status") != "passed":
            raise ReferenceTranscriptError("edit.verify did not pass")
        _tool_call(
            calls,
            facade="edit",
            action="verify",
            arguments=verify_args,
            result=verify_result,
            evidence={
                "status": verify_result.get("status"),
                "total_steps": verify_result.get("total_steps"),
                "executed_steps": [
                    {
                        "role": step.get("role"),
                        "status": step.get("status"),
                        "exit_code": step.get("exit_code"),
                    }
                    for step in verify_result.get("executed_steps", [])
                ],
            },
        )

        verification = _run_registered_verification(root, record.verification_argv)
        _host_call(
            calls,
            "registered_verification",
            {"argv": list(record.verification_argv)},
            verification,
        )
        if verification["passed"] is not True:
            raise ReferenceTranscriptError("registered verification failed")

        oracle = _run_reference_oracle(root, oracle_path, record.oracle_baseline_reason)
        _host_call(
            calls,
            "oracle",
            {"path": record.oracle, "reason": record.oracle_baseline_reason},
            oracle,
        )
        if oracle["status"] != "PASS":
            raise ReferenceTranscriptError("reference oracle did not declare PASS")

        non_allowed_after = _tree_digest(root, record.allowed_paths)
        unchanged = non_allowed_before == non_allowed_after
        if not unchanged:
            raise ReferenceTranscriptError("non-allowed tree digest changed")

        return {
            "schema": "no1-010b/transcript/1",
            "evidence_level": "E0",
            "qualification": "REFERENCE_ONLY",
            "task_id": record.id,
            "arm_id": "reference-tsa-first",
            "model_executed": False,
            "public_claim": None,
            "calls": calls,
            "patch": {
                "changed_paths": changed_paths,
                "allowed_paths": list(record.allowed_paths),
                "allowlist_violations": [],
                "sha256": _sha256_bytes(patch.encode()),
            },
            "verification": verification,
            "oracle": oracle,
            "non_allowed_tree": {
                "before_sha256": non_allowed_before,
                "after_sha256": non_allowed_after,
                "unchanged": True,
            },
            "terminal": {"verdict": "PASS", "reason_code": None},
            "limitations": [
                "repository-owned reference edit; no model was executed",
                "candidate execution is not protected by the RFC-0026 B1 sandbox",
                "result cannot support a public VCSR or default-tool claim",
            ],
        }
