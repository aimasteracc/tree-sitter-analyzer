"""Mechanical transcript-policy audit for the NO1-001B Gin Smoke."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

_ARM_SERVER = {
    "native-only": None,
    "tsa-warm": "tree-sitter-analyzer",
    "codegraph-warm": "codegraph",
}
_FORBIDDEN_ORACLE_TERMS = (
    "expected_key_points",
    "anti_hallucination_checks",
    "oracle_hash",
)
_WRITE_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)"
    r"(?:rm|mv|cp|install|tee|touch|mkdir|chmod|chown)\b"
    r"|\bgit\s+(?:add|commit|checkout|switch|reset|clean|restore)\b"
    r"|\bsed\s+-i\b|(?:^|[^<])>{1,2}(?!=)",
    re.IGNORECASE,
)
_INDEX_COMMAND = re.compile(
    r"\b(?:codegraph|tree[-_]sitter[-_]analyzer)\b",
    re.IGNORECASE,
)
_INDEX_NAMESPACE = re.compile(
    r"(?:^|[\s/\\])(?:\.ast-cache|\.codegraph)(?:[/\\]|$)"
)
_BOUNDARY_ESCAPE = re.compile(
    r"(?:^|[\s'\"=])(?:/|~|\.\.(?:[/\\]|\s|$)|\$HOME\b|\$\{HOME\}|[A-Za-z]:[/\\])"
)
_PROCESS_INSPECTION = re.compile(
    r"(?:^|[;&|]\s*|\s)(?:ps|pgrep|lsof|env|printenv|mount)\b",
    re.IGNORECASE,
)
_NETWORK_COMMAND = re.compile(
    r"(?:^|[;&|]\s*|\s)"
    r"(?:curl|wget|ssh|scp|sftp|nc|netcat|telnet|python|python3|node|ruby|perl|php)"
    r"\b|\bgit\s+(?:clone|fetch|pull|push|ls-remote)\b",
    re.IGNORECASE,
)
_READ_COMMANDS = frozenset(
    {
        "cat",
        "cd",
        "cut",
        "grep",
        "head",
        "ls",
        "pwd",
        "sort",
        "tail",
        "tr",
        "uniq",
        "wc",
    }
)


@dataclass(frozen=True)
class PolicyAudit:
    """Mechanical transcript-policy decision for one physical attempt."""

    arm: str
    transcript_path: str
    observed_mcp_servers: tuple[str, ...]
    observed_mcp_tools: tuple[str, ...]
    violations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations


def audit_codex_transcript(transcript_path: Path, arm: str) -> PolicyAudit:
    """Fail closed on malformed, cross-arm, mutating, or oracle-bearing events."""

    if arm not in _ARM_SERVER:
        raise ValueError(f"Unsupported Smoke arm: {arm}")
    violations: list[str] = []
    servers: list[str] = []
    tools: list[str] = []
    if not transcript_path.is_file():
        violations.append("TRANSCRIPT_MISSING")
        return PolicyAudit(arm, str(transcript_path), (), (), tuple(violations))

    expected_server = _ARM_SERVER[arm]
    for line_number, line in enumerate(
        transcript_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            violations.append(f"MALFORMED_JSON:{line_number}")
            continue
        if not isinstance(event, dict):
            violations.append(f"NON_OBJECT_EVENT:{line_number}")
            continue
        if any(term in line.lower() for term in _FORBIDDEN_ORACLE_TERMS):
            violations.append(f"ORACLE_EXPOSURE:{line_number}")
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "file_change":
            violations.append(f"FILE_CHANGE:{line_number}")
        elif item_type == "web_search":
            violations.append(f"NETWORK_TOOL:{line_number}")
        elif item_type == "command_execution":
            _audit_command(str(item.get("command") or ""), line_number, violations)
        elif item_type == "mcp_tool_call":
            server = str(item.get("server") or item.get("server_name") or "")
            tool = str(item.get("tool") or item.get("tool_name") or "")
            servers.append(server)
            tools.append(tool)
            if not server or server != expected_server:
                violations.append(f"CROSS_ARM_MCP:{line_number}")

    if expected_server is not None and expected_server not in servers:
        violations.append("MISSING_INDEX_QUERY")
    return PolicyAudit(
        arm,
        str(transcript_path),
        tuple(servers),
        tuple(tools),
        tuple(dict.fromkeys(violations)),
    )


def _audit_command(
    command: str, line_number: int, violations: list[str]
) -> None:
    violation_count = len(violations)
    checks = (
        (_WRITE_COMMAND, "MUTATING_COMMAND"),
        (_INDEX_COMMAND, "INDEX_COMMAND_OUTSIDE_MCP"),
        (_INDEX_NAMESPACE, "INDEX_NAMESPACE_OUTSIDE_MCP"),
    )
    for pattern, code in checks:
        if pattern.search(command):
            violations.append(f"{code}:{line_number}")
    if _BOUNDARY_ESCAPE.search(command) or _PROCESS_INSPECTION.search(command):
        violations.append(f"FILESYSTEM_BOUNDARY_ESCAPE:{line_number}")
    if _NETWORK_COMMAND.search(command):
        violations.append(f"NETWORK_COMMAND:{line_number}")
    if len(violations) == violation_count and not _command_is_allowlisted(command):
        violations.append(f"UNDECLARED_SHELL_COMMAND:{line_number}")


def _command_is_allowlisted(command: str) -> bool:
    if "$(" in command or "`" in command:
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= {";", "&", "|"}:
            segments.append([])
        else:
            segments[-1].append(token)
    for segment in segments:
        if not segment:
            continue
        executable = Path(segment[0]).name
        if executable not in _READ_COMMANDS:
            return False
    return True
