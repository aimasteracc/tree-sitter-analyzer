"""运行 NO1-010B 代表性任务的 E0 参考 transcript。"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
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
from .transcript_specs import REFERENCE_EDIT_SPECS as _REFERENCE_EDIT_SPECS
from .transcript_specs import REFERENCE_TASK_ID, ReferenceEditSpec

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


def _apply_reference_edit(
    root: Path,
    spec: ReferenceEditSpec | None = None,
) -> dict[str, Any]:
    """应用一条任务唯一预注册的固定参考改动。"""
    selected = spec or _REFERENCE_EDIT_SPECS[REFERENCE_TASK_ID]
    originals: dict[str, str] = {}
    for replacement in selected.replacements:
        target = root / replacement.path
        current = target.read_text(encoding="utf-8")
        originals.setdefault(replacement.path, current)
        if current.count(replacement.before) != 1:
            raise ReferenceTranscriptError(
                f"reference edit anchor is not unique: {replacement.path}"
            )
        target.write_text(
            current.replace(replacement.before, replacement.after, 1),
            encoding="utf-8",
            newline="\n",
        )

    files = []
    for path in selected.changed_paths:
        before = originals[path]
        after = (root / path).read_text(encoding="utf-8")
        files.append(
            {
                "path": path,
                "before_sha256": _sha256_bytes(before.encode()),
                "after_sha256": _sha256_bytes(after.encode()),
            }
        )
    return {"paths": list(selected.changed_paths), "files": files}


def _touched_paths(patch: str) -> list[str]:
    """从同一份已校验补丁取得完整、有序的 touched path 集合。"""
    return [item.rel_path for item in diff_paths(patch)]


def _reported_test_paths(command: Any) -> list[str]:
    """从验证命令提取有序 pytest 文件参数。"""
    if not isinstance(command, str):
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    return [
        token.split("::", 1)[0]
        for token in tokens
        if token.split("::", 1)[0].startswith("tests/")
        and token.split("::", 1)[0].endswith(".py")
    ]


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


def _reference_spec(record: BenchmarkRecord) -> ReferenceEditSpec:
    """校验 corpus 记录与固定参考规格完全一致。"""
    spec = _REFERENCE_EDIT_SPECS.get(record.id)
    if spec is None:
        raise ReferenceTranscriptError(f"unsupported reference task: {record.id}")
    if record.task_class != spec.task_class:
        raise ReferenceTranscriptError("reference task class does not match its spec")
    registered_fields = {
        "repo": (record.repo, spec.repo),
        "allowed_paths": (record.allowed_paths, spec.allowed_paths),
        "oracle": (record.oracle, spec.oracle),
        "oracle_baseline_reason": (
            record.oracle_baseline_reason,
            spec.oracle_baseline_reason,
        ),
        "verification_argv": (record.verification_argv, spec.verification_argv),
        "selected_tests": (record.selected_tests, spec.selected_tests),
    }
    for field, (actual, expected) in registered_fields.items():
        if actual != expected:
            raise ReferenceTranscriptError(
                f"reference task {field} does not match its spec"
            )
    terminal = (record.expected_terminal.verdict, record.expected_terminal.reason_code)
    if terminal != spec.terminal:
        if spec.terminal == ("PASS", None):
            raise ReferenceTranscriptError("reference task must register terminal PASS")
        raise ReferenceTranscriptError(
            "reference task terminal does not match its spec"
        )
    return spec


async def _record_index(root: Path, calls: list[dict[str, Any]]) -> None:
    """建立候选索引并记录发布证据。"""
    arguments = {"action": "full", "output_format": "json"}
    result = _require_tool_success(
        "index.full", await build_index_facade(str(root)).execute(arguments)
    )
    _tool_call(
        calls,
        facade="index",
        action="full",
        arguments=arguments,
        result=result,
        evidence={
            "published": result.get("published"),
            "scope_complete": result.get("scope_complete"),
            "total_files": result.get("total_files"),
            "total_symbols": result.get("total_symbols"),
        },
    )


async def _record_discovery(
    root: Path,
    spec: ReferenceEditSpec,
    calls: list[dict[str, Any]],
) -> None:
    """定位唯一的新鲜符号，并取得编辑前结构。"""
    search_args = {
        "action": "symbol",
        "query": spec.search_symbol,
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
        if item.get("name") == spec.search_symbol
        and item.get("file") == spec.search_path
    ]
    freshness = (search_result.get("source_evidence") or {}).get("freshness")
    if len(matches) != 1 or freshness != "fresh":
        raise ReferenceTranscriptError("symbol lookup did not produce one fresh target")
    target = matches[0]
    _tool_call(
        calls,
        facade="search",
        action="symbol",
        arguments=search_args,
        result=search_result,
        evidence={
            "freshness": freshness,
            "target": {
                "file": target["file"],
                "name": target["name"],
                "kind": target["kind"],
                "line": target["line"],
            },
        },
    )

    outline_args = {
        "action": "outline",
        "file_path": spec.search_path,
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


async def _record_edit_safety(
    edit_facade: Any,
    spec: ReferenceEditSpec,
    calls: list[dict[str, Any]],
) -> None:
    """在宿主写入前记录 TSA 的编辑风险判断。"""
    arguments = {
        "action": "safe",
        "file_path": spec.search_path,
        "edit_type": spec.edit_type,
        "output_format": "json",
    }
    result = _require_tool_success("edit.safe", await edit_facade.execute(arguments))
    _tool_call(
        calls,
        facade="edit",
        action="safe",
        arguments=arguments,
        result=result,
        evidence={
            "risk_level": result.get("risk_level"),
            "verification_command": (result.get("agent_summary") or {}).get(
                "verification_command"
            ),
        },
    )


def _apply_and_validate_patch(
    root: Path,
    record: BenchmarkRecord,
    spec: ReferenceEditSpec,
    calls: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """应用固定编辑，并以完整 Git 补丁执行边界校验。"""
    receipt = _apply_reference_edit(root, spec)
    _host_call(
        calls,
        "edit",
        {"paths": list(spec.changed_paths), "replacement": spec.summary},
        receipt,
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
    if changed_paths != list(spec.changed_paths):
        raise ReferenceTranscriptError(f"unexpected changed paths: {changed_paths}")
    return patch, changed_paths


def _test_selection_evidence(
    record: BenchmarkRecord,
    verification_command: Any,
) -> dict[str, Any] | None:
    """要求选测任务精确报告预注册的 pytest 文件。"""
    if not record.selected_tests:
        return None
    expected = list(record.selected_tests)
    reported = _reported_test_paths(verification_command)
    if reported != expected:
        raise ReferenceTranscriptError(
            "impact did not report the registered selected tests"
        )
    return {"expected": expected, "reported": reported, "matched": True}


async def _record_impact(
    edit_facade: Any,
    record: BenchmarkRecord,
    calls: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    """记录改后影响，并取得绑定当前差分的验证请求。"""
    arguments = {
        "action": "impact",
        "mode": "diff",
        "resource_profile": "default",
        "output_format": "json",
    }
    result = _require_tool_success("edit.impact", await edit_facade.execute(arguments))
    request = result.get("verification_request")
    if not isinstance(request, str):
        raise ReferenceTranscriptError("impact did not issue a verification request")
    command = result.get("verification_command")
    _tool_call(
        calls,
        facade="edit",
        action="impact",
        arguments=arguments,
        result=result,
        evidence={
            "changed_files": result.get("changed_files"),
            "verification_command": command,
            "verification_request_sha256": _sha256_bytes(request.encode()),
        },
    )
    return request, _test_selection_evidence(record, command)


async def _record_bound_verification(
    edit_facade: Any,
    request: str,
    expects_failure: bool,
    calls: list[dict[str, Any]],
) -> bool:
    """运行绑定验证，并要求状态与预注册终态一致。"""
    arguments = {
        "action": "verify",
        "request": request,
        "output_format": "json",
    }
    result = await edit_facade.execute(arguments)
    if not isinstance(result, dict):
        raise ReferenceTranscriptError(f"edit.verify failed: {result!r}")
    expected_status = "failed" if expects_failure else "passed"
    if result.get("status") != expected_status:
        if expected_status == "passed":
            raise ReferenceTranscriptError("edit.verify did not pass")
        raise ReferenceTranscriptError(
            "edit.verify did not preserve the expected failure"
        )
    expected_success: bool = not expects_failure
    if result.get("success") is not expected_success:
        raise ReferenceTranscriptError(
            "edit.verify success flag contradicts its status"
        )
    steps = [
        {
            "role": step.get("role"),
            "status": step.get("status"),
            "exit_code": step.get("exit_code"),
        }
        for step in result.get("executed_steps", [])
    ]
    _tool_call(
        calls,
        facade="edit",
        action="verify",
        arguments=arguments,
        result=result,
        evidence={
            "status": result.get("status"),
            "total_steps": result.get("total_steps"),
            "executed_steps": steps,
        },
    )
    return not expects_failure


def _record_terminal_evidence(
    root: Path,
    record: BenchmarkRecord,
    oracle_path: Path,
    expected_success: bool,
    calls: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """运行完整注册验证与行为 oracle，并保留预期失败。"""
    verification = _run_registered_verification(root, record.verification_argv)
    _host_call(
        calls,
        "registered_verification",
        {"argv": list(record.verification_argv)},
        verification,
    )
    if verification["passed"] is not expected_success:
        if not expected_success:
            raise ReferenceTranscriptError(
                "registered verification did not preserve the expected failure"
            )
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
    return verification, oracle


def _build_transcript(
    root: Path,
    record: BenchmarkRecord,
    calls: list[dict[str, Any]],
    patch: str,
    changed_paths: list[str],
    verification: dict[str, Any],
    test_selection: dict[str, Any] | None,
    oracle: dict[str, Any],
    non_allowed_before: str,
) -> dict[str, Any]:
    """组装固定 schema，并最后确认非 allowed 树未变化。"""
    non_allowed_after = _tree_digest(root, record.allowed_paths)
    if non_allowed_before != non_allowed_after:
        raise ReferenceTranscriptError("non-allowed tree digest changed")
    return {
        "schema": "no1-010b/transcript/1",
        "evidence_level": "E0",
        "qualification": "REFERENCE_ONLY",
        "task_id": record.id,
        "task_class": record.task_class,
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
        "test_selection": test_selection,
        "oracle": oracle,
        "non_allowed_tree": {
            "before_sha256": non_allowed_before,
            "after_sha256": non_allowed_after,
            "unchanged": True,
        },
        "terminal": {
            "verdict": record.expected_terminal.verdict,
            "reason_code": record.expected_terminal.reason_code,
        },
        "limitations": [
            "repository-owned reference edit; no model was executed",
            "candidate execution is not protected by the RFC-0026 B1 sandbox",
            "result cannot support a public VCSR or default-tool claim",
        ],
    }


async def run_reference_transcript(
    record: BenchmarkRecord,
    corpus_root: Path,
    *,
    workspace_parent: Path | None = None,
) -> dict[str, Any]:
    """在临时副本运行预注册的 TSA→宿主编辑→验证→oracle 链路。"""
    spec = _reference_spec(record)

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
        await _record_index(root, calls)
        await _record_discovery(root, spec, calls)
        edit_facade = build_edit_facade(str(root))
        await _record_edit_safety(edit_facade, spec, calls)
        patch, changed_paths = _apply_and_validate_patch(root, record, spec, calls)
        request, test_selection = await _record_impact(edit_facade, record, calls)
        expects_verification_failure = spec.terminal == (
            "FAIL",
            "VERIFICATION_FAILED",
        )
        expected_success = await _record_bound_verification(
            edit_facade, request, expects_verification_failure, calls
        )
        verification, oracle = _record_terminal_evidence(
            root, record, oracle_path, expected_success, calls
        )
        transcript = _build_transcript(
            root,
            record,
            calls,
            patch,
            changed_paths,
            verification,
            test_selection,
            oracle,
            non_allowed_before,
        )
        return transcript
