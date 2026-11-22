#!/usr/bin/env python
"""生成 envelope / CLI 的真实 v3.1.2 固定输出(fixture)。

用法(必须在仓库根目录执行):
    /tmp/tsa-v312-venv/bin/python rust/fixtures/tools/gen_envelope_cli.py

所有 JSON 均为对已安装的 tree_sitter_analyzer 3.1.2 的**真实调用结果**,
禁止手工编纂。输出只写入 rust/fixtures/ 之下:
  - envelope/response_builder_valid.json
  - envelope/response_builder_invalid.json
  - envelope/envelope_validation.json
  - envelope/error_recovery.json
  - cli/cli_outputs.json
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tree_sitter_analyzer
from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
    _classify,
    _normalize_path_string,
    build_agent_friendly_error,
    ensure_canonical_error_envelope,
    ensure_canonical_success_envelope,
)
from tree_sitter_analyzer.mcp.tools import tool_response
from tree_sitter_analyzer.mcp.tools._response_builder import (
    CANONICAL_VERDICTS,
    InvalidVerdictError,
    build_agent_summary,
    build_error,
    build_error_response,
    build_response,
    build_success_response,
)
from tree_sitter_analyzer.mcp.utils.error_sanitizer import (
    project_root_from_env,
    safe_error_message,
)

# ---------------------------------------------------------------- 路径与守卫

SCRIPT_PATH = Path(__file__).resolve()
FIXTURES_ROOT = SCRIPT_PATH.parents[1]  # rust/fixtures/
REPO_ROOT = SCRIPT_PATH.parents[3]  # 仓库根,CLI 子进程的工作目录
ENVELOPE_DIR = FIXTURES_ROOT / "envelope"
CLI_DIR = FIXTURES_ROOT / "cli"

CLI_BIN = "/tmp/tsa-v312-venv/bin/tree-sitter-analyzer"

# 必须命中 v3.1.2 虚拟环境里的安装副本,防止误用仓库内源码
assert (
    "tsa-v312-venv" in str(Path(tree_sitter_analyzer.__file__).resolve())
    and tree_sitter_analyzer.__version__ == "3.1.2"
), f"unexpected tsa install: {tree_sitter_analyzer.__file__} {tree_sitter_analyzer.__version__}"

META: dict[str, Any] = {
    "generator": "rust/fixtures/tools/gen_envelope_cli.py",
    "tsa_version": tree_sitter_analyzer.__version__,
    "tsa_module": str(Path(tree_sitter_analyzer.__file__).resolve()),
    "python_version": platform.python_version(),
    "python_executable": sys.executable,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "provenance": "captured from real tree_sitter_analyzer calls; never hand-edited",
}


def write_json(name: str, payload: Any, *subdirs: str) -> Path:
    """把 payload 写入 FIXTURES_ROOT 之下,拒绝越界写。"""
    target_dir = FIXTURES_ROOT.joinpath(*subdirs)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / name
    resolved = path.resolve()
    assert str(resolved).startswith(
        str(FIXTURES_ROOT.resolve())
    ), f"refusing to write outside fixtures: {resolved}"
    with open(resolved, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return resolved


# --------------------------------------------- 1. response_builder 有效输入

def gen_response_builder_valid() -> dict[str, Any]:
    doc: dict[str, Any] = {"meta": dict(META), "canonical_verdicts": sorted(CANONICAL_VERDICTS)}

    # 8 个合法 verdict 逐个构造
    verdicts = []
    for verdict in sorted(CANONICAL_VERDICTS):
        verdicts.append(
            {
                "verdict": verdict,
                "call": "build_response(verdict=verdict, mode='fixture', total_count=1)",
                "result": build_response(verdict=verdict, mode="fixture", total_count=1),
            }
        )
    assert len(verdicts) == 8
    doc["build_response_all_verdicts"] = verdicts

    # warnings 三种形态:None / 空列表 / 非空列表
    warnings_cases = []
    for label, warnings in (
        ("none", None),
        ("empty_list", []),
        ("nonempty_list", ["stale cache"]),
    ):
        result = build_response(verdict="INFO", mode="warnings_probe", warnings=warnings)
        warnings_cases.append(
            {
                "label": label,
                "warnings_argument": warnings,
                "result": result,
                "warnings_key_present": "warnings" in result,
            }
        )
    doc["build_response_warnings_variants"] = warnings_cases

    # build_error:默认 verdict 与显式 NOT_FOUND
    doc["build_error"] = [
        {"call": "build_error(error='boom')", "result": build_error(error="boom")},
        {
            "call": "build_error(error='no such symbol', verdict='NOT_FOUND', mode='lookup')",
            "result": build_error(error="no such symbol", verdict="NOT_FOUND", mode="lookup"),
        },
    ]

    # build_error_response:附带 tool 名
    doc["build_error_response"] = [
        {
            "call": "build_error_response('query', 'bad symbol')",
            "result": build_error_response("query", "bad symbol"),
        },
        {
            "call": "build_error_response('read_partial', 'key missing', verdict='NOT_FOUND', available_keys=['a', 'b'])",
            "result": build_error_response(
                "read_partial", "key missing", verdict="NOT_FOUND", available_keys=["a", "b"]
            ),
        },
    ]

    # build_success_response:duration_ms 传 None(键缺席)与传值(键在场)两种,
    # 同时记录原始在场性,便于消费端做确定性断言
    success_cases = []
    for duration_ms in (None, 12.5):
        result = build_success_response(
            "query", {"total": 3}, verdict="INFO", duration_ms=duration_ms, page=1
        )
        success_cases.append(
            {
                "call": "build_success_response('query', {'total': 3}, verdict='INFO', duration_ms=<see field>, page=1)",
                "duration_ms_passed": duration_ms,
                "duration_ms_present_in_result": "duration_ms" in result,
                "result": result,
            }
        )
    doc["build_success_response"] = success_cases

    # build_agent_summary:带/不带 recommendations
    doc["build_agent_summary"] = [
        {
            "call": "build_agent_summary('WARN', 'index is stale')",
            "result": build_agent_summary("WARN", "index is stale"),
        },
        {
            "call": "build_agent_summary('CAUTION', 'coverage limited', ['narrow the query'])",
            "result": build_agent_summary(
                "CAUTION", "coverage limited", ["narrow the query"]
            ),
        },
    ]
    return doc


# --------------------------------------------- 2. response_builder 非法 verdict

BAD_VERDICTS = ["OK", "safe", "Safe", "CLEAN", "NEEDS_REVIEW", "LOOKS_GOOD", "READY", "", "info"]


def gen_response_builder_invalid() -> dict[str, Any]:
    cases = []
    for bad in BAD_VERDICTS:
        try:
            result = build_response(verdict=bad)
            cases.append(
                {
                    "input": bad,
                    "exc_type": None,
                    "is_value_error": None,
                    "message": None,
                    "unexpected_result": result,
                }
            )
        except InvalidVerdictError as exc:
            cases.append(
                {
                    "input": bad,
                    "exc_type": type(exc).__name__,
                    "is_value_error": isinstance(exc, ValueError),
                    "message": str(exc),
                }
            )
    assert all(c["exc_type"] == "InvalidVerdictError" for c in cases)
    return {"meta": dict(META), "invalid_verdicts": cases}


# --------------------------------------------- 3. envelope 校验规则全覆盖

def _validate_outcome(payload: Any, tool_name: str) -> dict[str, Any]:
    try:
        tool_response.validate_tool_response(payload, tool_name)
        return {"raised": False, "assertion_error": None}
    except AssertionError as exc:
        return {"raised": True, "assertion_error": str(exc)}


def gen_envelope_validation() -> dict[str, Any]:
    valid_cases: list[dict[str, Any]] = []
    invalid_cases: list[dict[str, Any]] = []

    def add_valid(name: str, envelope: Any) -> None:
        valid_cases.append(
            {
                "name": name,
                "envelope": envelope,
                "validate_tool_response": _validate_outcome(envelope, name),
                "envelope_violations": [
                    list(pair) for pair in tool_response.envelope_violations(envelope, name)
                ],
            }
        )

    def add_invalid(name: str, target_rule: str, envelope: Any) -> None:
        violations = [
            list(pair) for pair in tool_response.envelope_violations(envelope, name)
        ]
        invalid_cases.append(
            {
                "name": name,
                "target_rule": target_rule,
                "envelope": envelope,
                "validate_tool_response": _validate_outcome(envelope, name),
                "envelope_violations": violations,
                "rules_fired": sorted({rule for rule, _ in violations}),
            }
        )

    known_reason = sorted(tool_response.known_completeness_reasons())[0]  # 'ACCESSOR_NOT_CALL_EDGES'

    # ---- 合法信封 ----
    add_valid("success_info_payload", build_response(verdict="INFO", mode="fixture", total_count=2))
    add_valid(
        "failure_error_full",
        build_error_response("query", "bad symbol", error_code="BAD_SYMBOL"),
    )
    add_valid(
        "failure_not_found",
        {"success": False, "error": "gone", "error_type": "file_not_found", "verdict": "NOT_FOUND"},
    )
    add_valid(
        "warn_with_summary_completeness_truncation",
        {
            "success": True,
            "verdict": "WARN",
            "agent_summary": {"summary_line": "q: partial", "verdict": "WARN"},
            "completeness": "incomplete",
            "completeness_reasons": [known_reason],
            "truncated": True,
            "total_count": 5,
            "returned_count": 3,
        },
    )
    add_valid("agent_summary_only", build_agent_summary("SAFE", "no findings"))

    # ---- 逐条覆盖 11 条 ENVELOPE_RULES ----
    add_invalid("not_a_dict", "base", ["success"])
    add_invalid("missing_success_key", "base", {"verdict": "INFO"})
    add_invalid("success_not_bool", "base", {"success": "yes"})
    add_invalid("failure_without_error", "base", {"success": False})
    add_invalid("agent_summary_not_dict", "agent-summary-shape", {"success": True, "agent_summary": "broken"})
    add_invalid(
        "agent_summary_verdict_noncanonical",
        "verdict-canonical",
        {"success": True, "agent_summary": {"verdict": "CLEAN"}},
    )
    add_invalid(
        "verdict_mirror_mismatch",
        "verdict-mirror",
        {"success": True, "verdict": "WARN", "agent_summary": {"verdict": "INFO"}},
    )
    add_invalid(
        "failure_with_success_verdict",
        "failure-verdict",
        {"success": False, "error": "x", "error_type": "internal", "verdict": "WARN"},
    )
    add_invalid("success_with_error_verdict", "success-verdict", {"success": True, "verdict": "ERROR"})
    add_invalid("failure_without_machine_code", "error-code", {"success": False, "error": "boom"})
    add_invalid("completeness_bad_status", "completeness-status", {"success": True, "completeness": "partial"})
    add_invalid(
        "incomplete_without_reasons",
        "completeness-reasons",
        {"success": True, "completeness": "incomplete"},
    )
    add_invalid(
        "complete_with_reasons",
        "completeness-reasons",
        {"success": True, "completeness": "complete", "completeness_reasons": [known_reason]},
    )
    add_invalid(
        "unknown_reason_code",
        "completeness-reason-code",
        {"success": True, "completeness": "incomplete", "completeness_reasons": ["TOTALLY_UNKNOWN_CODE"]},
    )
    add_invalid(
        "truncated_false_but_counts_disagree",
        "truncation",
        {"success": True, "total_count": 10, "returned_count": 3, "truncated": False},
    )
    add_invalid("truncated_not_bool", "truncation", {"success": True, "truncated": "no"})
    add_invalid(
        "listed_exceeds_total",
        "truncation",
        {"success": True, "total_matches": 2, "returned_matches": 7},
    )

    # 自检:11 条规则必须全部被真实触发
    fired = {rule for case in invalid_cases for rule in case["rules_fired"]}
    assert fired == set(tool_response.ENVELOPE_RULES), (
        f"rule coverage gap: missing {sorted(set(tool_response.ENVELOPE_RULES) - fired)}"
    )
    assert all(not c["envelope_violations"] for c in valid_cases)

    return {
        "meta": dict(META),
        "canonical_verdicts": sorted(tool_response.CANONICAL_VERDICTS),
        "envelope_rules": sorted(tool_response.ENVELOPE_RULES),
        "rules_actually_fired": sorted(fired),
        "known_completeness_reasons_count": len(tool_response.known_completeness_reasons()),
        "known_completeness_reasons_sample": sorted(tool_response.known_completeness_reasons())[:10],
        "valid": valid_cases,
        "invalid": invalid_cases,
    }


# --------------------------------------------- 4. 错误恢复信封

# (名称, 异常工厂, 传给 build_agent_friendly_error 的 arguments)
ERROR_CASES: list[tuple[str, Any, dict[str, Any] | None]] = [
    ("file_not_found", FileNotFoundError("File not found: tests/golden/missing_xyz.py"), {"file_path": "tests/golden/missing_xyz.py"}),
    ("language_unsupported", ValueError("Unsupported language: .xyz extension not recognized"), {"file_path": "config.xyz"}),
    ("project_not_set", RuntimeError("Project root has not been set"), None),
    ("security_violation", ValueError("The file is outside project boundary"), {"file_path": "../secrets.py"}),
    ("validation_blast_radius_mode", ValueError("blast_radius mode requires function_names to be provided"), {"mode": "blast_radius"}),
    ("validation_required", ValueError("function_names is required for this action"), None),
    ("resource_exhausted", MemoryError("The operation ran out of memory"), None),
    ("timeout", TimeoutError("The operation timed out after 30 seconds"), None),
    ("subprocess", ValueError("Regex parse error: unmatched parenthesis"), {"query": "(["}),
    ("index_not_ready", RuntimeError("AST cache is empty; build the index first"), None),
    ("permission_denied", PermissionError("Permission denied: tests/golden/corpus_python.py"), {"file_path": "tests/golden/corpus_python.py"}),
    ("internal", RuntimeError("Unexpected internal state reached"), None),
]


def gen_error_recovery() -> dict[str, Any]:
    doc: dict[str, Any] = {"meta": dict(META)}

    cases = []
    for name, exc_factory, arguments in ERROR_CASES:
        exc = exc_factory  # 异常实例已在上表构造
        sanitized = safe_error_message(exc, project_root_from_env())
        error_type, recovery_hint, suggested_tool = _classify(sanitized, type(exc).__name__)
        cases.append(
            {
                "name": name,
                "exception_class": type(exc).__name__,
                "sanitized_message": sanitized,
                "classify": {
                    "error_type": error_type,
                    "recovery_hint": recovery_hint,
                    "suggested_tool": suggested_tool,
                },
                "build_agent_friendly_error": build_agent_friendly_error(
                    "fixture_probe", exc, arguments=arguments
                ),
                "ensure_canonical_error_envelope_from_minimal": ensure_canonical_error_envelope(
                    "fixture_probe", {"success": False, "error": str(exc)}, arguments=arguments
                ),
            }
        )
    # 自检:分类名与用例名对应(validation 的两个变体同归 validation)
    expected = {name: ("validation" if name.startswith("validation") else name) for name, _, _ in ERROR_CASES}
    assert all(c["classify"]["error_type"] == expected[c["name"]] for c in cases), [
        (c["name"], c["classify"]["error_type"]) for c in cases
    ]
    doc["error_cases"] = cases

    # 预置字段的错误信封:error_type / next_step 必须被保留而不被通用提示覆盖
    doc["error_envelope_preserves_preset_fields"] = ensure_canonical_error_envelope(
        "fixture_probe",
        {
            "success": False,
            "error": "AST cache is empty; build the index first",
            "error_type": "index_not_ready",
            "next_step": "custom: run index action=auto then retry",
        },
    )
    # 缺 error 的失败响应:从 errors 列表推导 error,并从消息前导码推导 error_code
    doc["error_envelope_derives_identity"] = ensure_canonical_error_envelope(
        "fixture_probe",
        {"success": False, "errors": [{"error": "COMBINED_SCORE_UNAVAILABLE: score missing"}]},
    )

    # K12:file_path 回显归一化('./a\b.py' -> 'a/b.py')
    k12_input = "./a\\b.py"
    k12_envelope = {
        "success": True,
        "verdict": "INFO",
        "file_path": k12_input,
        "entries": 2,
    }
    k12_output = ensure_canonical_success_envelope("k12_probe", dict(k12_envelope))
    doc["k12_path_normalization"] = {
        "note": "ensure_canonical_success_envelope normalizes echoed file_path ('./a\\b.py' -> 'a/b.py')",
        "input_envelope": k12_envelope,
        "output_envelope": k12_output,
        "normalize_path_string_direct": {
            "input": k12_input,
            "output": _normalize_path_string(k12_input),
        },
    }

    # M14:单文件成功信封自动回显 language(Python 语料 → 'python')
    m14_envelope = {"success": True, "file_path": "tests/golden/corpus_python.py", "total_lines": 257}
    doc["m14_language_echo"] = {
        "note": "ensure_canonical_success_envelope detects and echoes language for single-file responses",
        "input_envelope": m14_envelope,
        "output_envelope": ensure_canonical_success_envelope("m14_probe", dict(m14_envelope)),
    }
    assert doc["m14_language_echo"]["output_envelope"].get("language") == "python"
    assert k12_output["file_path"] == "a/b.py"
    return doc


# --------------------------------------------- 5. CLI 子进程输出

TIMING_KEYS = {"analysis_time", "duration_ms", "elapsed_ms", "elapsed_time"}


def _normalize_strings(value: Any) -> Any:
    """把绝对仓库路径折算为相对路径(仅字符串替换,不改变结构)。"""
    if isinstance(value, dict):
        return {k: _normalize_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_strings(v) for v in value]
    if isinstance(value, str):
        s = value
        prefix = str(REPO_ROOT) + "/"
        if prefix in s:
            s = s.replace(prefix, "")
        elif s == str(REPO_ROOT):
            s = "."
        elif str(REPO_ROOT) in s:
            s = s.replace(str(REPO_ROOT), ".")
        return s
    return value


def _null_timing(value: Any) -> tuple[Any, list[str]]:
    """把计时键置空并返回被置空的键名列表。"""
    nulled: list[str] = []
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in TIMING_KEYS and isinstance(v, (int, float)):
                out[k] = None
                nulled.append(k)
            else:
                child, child_nulled = _null_timing(v)
                out[k] = child
                nulled.extend(child_nulled)
        return out, nulled
    if isinstance(value, list):
        out = []
        for v in value:
            child, child_nulled = _null_timing(v)
            out.append(child)
            nulled.extend(child_nulled)
        return out, nulled
    return value, nulled


def gen_cli_outputs() -> dict[str, Any]:
    argv_cases = [
        ("structure", ["tests/golden/corpus_python.py", "--structure", "--output-format", "json"]),
        ("table_full", ["tests/golden/corpus_python.py", "--table", "full", "--output-format", "json"]),
        ("outline", ["tests/golden/corpus_python.py", "--outline", "--output-format", "json"]),
        ("missing_file", ["tests/golden/does_not_exist_xyz.py", "--structure", "--output-format", "json"]),
    ]
    cases = []
    for name, argv in argv_cases:
        proc = subprocess.run(
            [CLI_BIN, *argv],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        stdout_text = proc.stdout
        parsed: Any = None
        stdout_parse_ok = False
        if stdout_text.strip():
            try:
                parsed = json.loads(stdout_text)
                stdout_parse_ok = True
            except json.JSONDecodeError:
                parsed = None
        normalized, nulled_keys = _null_timing(_normalize_strings(parsed))
        cases.append(
            {
                "name": name,
                "argv": argv,
                "cwd": ". (repository root)",
                "exit_code": proc.returncode,
                "stdout_parse_ok": stdout_parse_ok,
                "stdout_json": normalized,
                "timing_keys_nulled": sorted(set(nulled_keys)),
                "stderr": _normalize_strings(proc.stderr),
                "stdout_raw_if_unparseable": None if stdout_parse_ok else stdout_text,
            }
        )
    # 前三个用例必须成功且 stdout 可解析;缺文件用例必须失败且 stdout 为空
    assert all(c["exit_code"] == 0 and c["stdout_parse_ok"] for c in cases[:3]), [
        {"name": c["name"], "exit": c["exit_code"], "parse": c["stdout_parse_ok"], "stderr": c["stderr"][:300]}
        for c in cases[:3]
    ]
    assert cases[3]["exit_code"] != 0 and cases[3]["stdout_parse_ok"] is False, cases[3][
        "stderr"
    ][:300]
    return {
        "meta": dict(META, cli_binary=CLI_BIN),
        "cases": cases,
    }


# --------------------------------------------- 入口

def main() -> int:
    outputs = [
        ("response_builder_valid.json", gen_response_builder_valid(), "envelope"),
        ("response_builder_invalid.json", gen_response_builder_invalid(), "envelope"),
        ("envelope_validation.json", gen_envelope_validation(), "envelope"),
        ("error_recovery.json", gen_error_recovery(), "envelope"),
        ("cli_outputs.json", gen_cli_outputs(), "cli"),
    ]
    written = []
    for name, payload, subdir in outputs:
        path = write_json(name, payload, subdir)
        # 立即回读校验,确保写出的文件可被 json.load 解析
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
        written.append(path)
        print(f"OK  {path} ({path.stat().st_size} bytes)")
    print(f"\nAll {len(written)} fixtures written and verified parseable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
