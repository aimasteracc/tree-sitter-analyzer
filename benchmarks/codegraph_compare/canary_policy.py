"""Fail-closed transcript qualification for indexed MCP canary cells."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from benchmarks.codegraph_compare.smoke_policy import (
    _ARM_SERVER,
    PolicyAudit,
    _is_source_discovery_command,
    _mcp_call_failed,
    audit_codex_transcript,
)


@dataclass(frozen=True)
class CanaryReceipt:
    call_id: str
    server: str
    tool: str
    repository_relative_path: str
    symbol_identity: str
    symbol_kind: str
    transcript_line: int


@dataclass(frozen=True)
class CanaryAudit:
    policy: PolicyAudit
    receipt: CanaryReceipt | None
    violations: tuple[str, ...]


def audit_canary_transcript(
    transcript_path: Path,
    arm: str,
    *,
    expected_tool: str,
    expected_path: str,
    expected_symbol: str,
    expected_kind: str,
    expected_arguments: dict[str, object] | None = None,
) -> CanaryAudit:
    """Bind one qualification to exact MCP order, identity, and evidence."""

    policy = audit_codex_transcript(transcript_path, arm)
    violations = list(policy.violations)
    expected_server = _ARM_SERVER.get(arm)
    if expected_arguments is None:
        expected_arguments = (
            {
                "action": "navigate",
                "symbol": expected_symbol,
                "file_path": expected_path,
                "output_format": "json",
            }
            if expected_server == "tree-sitter-analyzer"
            else {
                "query": expected_symbol,
                "kind": expected_kind,
                "limit": 10,
            }
        )
    receipts: list[CanaryReceipt] = []
    receipt_seen = False
    if expected_server is None:
        violations.append("CANARY_INDEXED_ARM_REQUIRED")
    elif transcript_path.is_file():
        for line_number, line in enumerate(
            transcript_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            receipt, violation = _canary_receipt(
                line,
                line_number,
                expected_server=expected_server,
                expected_tool=expected_tool,
                expected_path=expected_path,
                expected_symbol=expected_symbol,
                expected_kind=expected_kind,
                expected_arguments=expected_arguments,
            )
            if violation:
                violations.append(violation)
            if receipt is not None:
                receipts.append(receipt)
                receipt_seen = True
            elif not receipt_seen and _canary_source_discovery(line):
                violations.append(
                    f"CANARY_SOURCE_DISCOVERY_BEFORE_RECEIPT:{line_number}"
                )
    if len(receipts) != 1:
        code = "CANARY_RECEIPT_MISSING" if not receipts else "CANARY_RECEIPT_AMBIGUOUS"
        violations.append(code)
    return CanaryAudit(
        policy,
        receipts[0] if len(receipts) == 1 else None,
        tuple(dict.fromkeys(violations)),
    )


def _canary_source_discovery(line: str) -> bool:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(event, dict) or event.get("type") != "item.completed":
        return False
    item = event.get("item")
    return (
        isinstance(item, dict)
        and item.get("type") == "command_execution"
        and _is_source_discovery_command(str(item.get("command") or ""))
    )


def _canary_receipt(
    line: str,
    line_number: int,
    *,
    expected_server: str,
    expected_tool: str,
    expected_path: str,
    expected_symbol: str,
    expected_kind: str,
    expected_arguments: dict[str, object] | None,
) -> tuple[CanaryReceipt | None, str | None]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(event, dict) or event.get("type") != "item.completed":
        return None, None
    item = event.get("item")
    if (
        not isinstance(item, dict)
        or item.get("type") != "mcp_tool_call"
        or item.get("server") != expected_server
        or _mcp_call_failed(item)
    ):
        return None, None
    if item.get("tool") != expected_tool:
        return None, f"CANARY_TOOL_MISMATCH:{line_number}"
    call_id = item.get("id")
    result = item.get("result")
    if (
        not isinstance(call_id, str)
        or not call_id
        or item.get("status") != "completed"
        or not isinstance(result, dict)
    ):
        return None, f"CANARY_RECEIPT_INVALID:{line_number}"
    if expected_arguments is None or item.get("arguments") != expected_arguments:
        return None, f"CANARY_ARGUMENTS_MISMATCH:{line_number}"
    evidence = (
        _codegraph_evidence(item, result, expected_path, expected_symbol, expected_kind)
        if expected_server == "codegraph"
        else _tsa_evidence(result)
    )
    if evidence is None:
        return None, f"CANARY_RECEIPT_INVALID:{line_number}"
    if evidence != (expected_path, expected_symbol, expected_kind):
        return None, f"CANARY_EVIDENCE_MISMATCH:{line_number}"
    return (
        CanaryReceipt(
            call_id,
            expected_server,
            expected_tool,
            expected_path,
            expected_symbol,
            expected_kind,
            line_number,
        ),
        None,
    )


def _codegraph_evidence(
    item: dict[str, object],
    result: dict[str, object],
    expected_path: str,
    expected_symbol: str,
    expected_kind: str,
) -> tuple[str, str, str] | None:
    text = _single_text_content(result)
    if text is None:
        return None
    short_name = expected_symbol.rsplit(".", 1)[-1]
    receiver = expected_symbol.rsplit(".", 1)[0]
    header = re.compile(
        rf"(?m)^\*\*{re.escape(short_name)}\*\* \({re.escape(expected_kind)}\)$"
    )
    if len(tuple(header.finditer(text))) != 1:
        return None
    pattern = re.compile(
        rf"(?m)^\*\*{re.escape(short_name)}\*\* \({re.escape(expected_kind)}\)\n"
        rf"func \(\s*[A-Za-z_]\w*\s+\*?{re.escape(receiver)}\s*\) "
        rf"{re.escape(short_name)}\([^\n]*\)\n"
        rf"{re.escape(expected_path)}:(?P<line>[1-9]\d*)$"
    )
    if len(tuple(pattern.finditer(text))) != 1:
        return None
    return expected_path, expected_symbol, expected_kind


def _tsa_evidence(result: dict[str, object]) -> tuple[str, str, str] | None:
    text = _single_text_content(result)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("symbol"), str):
        return None
    definition = payload.get("definition")
    definitions = (
        definition.get("definitions") if isinstance(definition, dict) else None
    )
    if not isinstance(definitions, list) or len(definitions) != 1:
        return None
    entry = definitions[0]
    if not isinstance(entry, dict):
        return None
    evidence = entry.get("file"), entry.get("name"), entry.get("kind")
    if not all(isinstance(value, str) and value for value in evidence):
        return None
    if payload["symbol"] != evidence[1]:
        return None
    return evidence


def _single_text_content(result: dict[str, object]) -> str | None:
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return None
    block = content[0]
    if not isinstance(block, dict) or block.get("type") != "text":
        return None
    text = block.get("text")
    return text if isinstance(text, str) else None
