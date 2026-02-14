#!/usr/bin/env python3
"""Output formatters for Code Intelligence Graph results."""
from __future__ import annotations

import json
from typing import Any


def format_trace_result(data: dict[str, Any], output_format: str = "summary") -> str:
    if output_format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    if output_format == "tree":
        return _format_trace_tree(data)
    return _format_trace_summary(data)


def _format_trace_summary(data: dict[str, Any]) -> str:
    lines = [f"=== Symbol Trace: {data.get('symbol', '?')} ===", ""]
    defs = data.get("definitions", [])
    if defs:
        lines.append("Definition(s):")
        for d in defs:
            params = ", ".join(d.get("parameters", []))
            lines.append(f"  {d.get('file_path', '?')}:{d.get('line', '?')}  {d.get('symbol_type', '?')} {d.get('name', '?')}({params})")
    usages = data.get("usages", [])
    if usages:
        lines.append(f"\nUsages ({len(usages)}):")
        for u in usages:
            lines.append(f"  {u.get('file_path', '?')}:{u.get('line', '?')}  [{u.get('ref_type', '?')}] {u.get('context_function', '?')}")
    cc = data.get("call_chain", {})
    callers = cc.get("callers", [])
    callees = cc.get("callees", [])
    if callers:
        lines.append(f"\nCallers ({len(callers)}):")
        for c in callers:
            lines.append(f"  {c.get('caller_file', '?')}:{c.get('line', '?')}  {c.get('caller_function', '?')}()")
    if callees:
        lines.append(f"\nCallees ({len(callees)}):")
        for c in callees:
            obj = f"{c.get('callee_object', '')}." if c.get('callee_object') else ""
            lines.append(f"  -> {obj}{c.get('callee_name', '?')}()")
    inheritance = data.get("inheritance", [])
    if inheritance:
        lines.append(f"\nInheritance: {' -> '.join(inheritance)}")
    return "\n".join(lines)


def _format_trace_tree(data: dict[str, Any]) -> str:
    lines = [f"sym:{data.get('symbol', '?')}"]
    for d in data.get("definitions", []):
        lines.append(f"def:{d.get('file_path', '?')}:{d.get('line', '?')}:{d.get('symbol_type', '?')}")
    for u in data.get("usages", []):
        lines.append(f"ref:{u.get('file_path', '?')}:{u.get('line', '?')}:{u.get('ref_type', '?')}")
    cc = data.get("call_chain", {})
    for c in cc.get("callers", []):
        lines.append(f"<-{c.get('caller_file', '?')}:{c.get('caller_function', '?')}")
    for c in cc.get("callees", []):
        lines.append(f"->{c.get('callee_name', '?')}")
    inh = data.get("inheritance", [])
    if inh:
        lines.append(f"inh:{'>'.join(inh)}")
    return "\n".join(lines)


def format_impact_result(data: dict[str, Any], output_format: str = "summary") -> str:
    if output_format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    return _format_impact_summary(data)


def _format_impact_summary(data: dict[str, Any]) -> str:
    lines = [
        f"=== Change Impact: {data.get('target', '?')} ===",
        f"Change Type: {data.get('change_type', '?')}",
        f"Risk Level: {data.get('risk_level', '?').upper()}",
        f"Total Affected Files: {data.get('total_affected_files', 0)}",
        "",
    ]
    direct = data.get("direct_impacts", [])
    if direct:
        lines.append(f"Direct Impacts ({len(direct)}):")
        for d in direct:
            lines.append(f"  {d.get('file_path', '?')}:{d.get('line', '?')}  {d.get('symbol_name', '?')} [{d.get('impact_type', '?')}]")
    trans = data.get("transitive_impacts", [])
    if trans:
        lines.append(f"\nTransitive Impacts ({len(trans)}):")
        for t in trans:
            lines.append(f"  {t.get('file_path', '?')}:{t.get('line', '?')}  {t.get('symbol_name', '?')} [depth={t.get('depth', '?')}]")
    tests = data.get("affected_tests", [])
    if tests:
        lines.append(f"\nAffected Tests ({len(tests)}):")
        for t in tests:
            lines.append(f"  {t}")
    return "\n".join(lines)


def format_architecture_report(data: dict[str, Any], output_format: str = "summary") -> str:
    if output_format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    return _format_arch_summary(data)


def _format_arch_summary(data: dict[str, Any]) -> str:
    lines = [
        f"=== Architecture Health: {data.get('path', '?')} ===",
        f"Score: {data.get('score', '?')}/100",
        "",
    ]
    cycles = data.get("cycles", [])
    if cycles:
        lines.append(f"Circular Dependencies ({len(cycles)}):")
        for c in cycles:
            lines.append(f"  [{c.get('severity', '?')}] {' -> '.join(c.get('files', []))}")
    violations = data.get("layer_violations", [])
    if violations:
        lines.append(f"\nLayer Violations ({len(violations)}):")
        for v in violations:
            lines.append(f"  {v.get('source_file', '?')} -> {v.get('target_file', '?')}: {v.get('description', '')}")
    gods = data.get("god_classes", [])
    if gods:
        lines.append(f"\nGod Classes ({len(gods)}):")
        for g in gods:
            lines.append(f"  {g.get('class_name', '?')} ({g.get('file_path', '?')}): {g.get('method_count', 0)} methods")
    dead = data.get("dead_symbols", [])
    if dead:
        lines.append(f"\nDead Symbols ({len(dead)}):")
        for d in dead:
            lines.append(f"  {d}")
    metrics = data.get("module_metrics", {})
    if metrics:
        lines.append(f"\nModule Metrics ({len(metrics)}):")
        for name, m in metrics.items():
            lines.append(f"  {name}: I={m.get('instability', 0):.2f} A={m.get('abstractness', 0):.2f} D={m.get('distance_from_main_sequence', 0):.2f}")

    tc = data.get("test_coverage")
    if tc:
        lines.append(f"\nTest Coverage (ratio={tc.get('coverage_ratio', 0):.1%}):")
        untested = tc.get("untested_symbols", [])
        if untested:
            lines.append(f"  Untested ({len(untested)}):")
            for s in untested[:20]:  # cap display
                lines.append(f"    {s.get('file_path', '?')}:{s.get('line', '?')} {s.get('symbol_type', '?')} {s.get('name', '?')}")
            if len(untested) > 20:
                lines.append(f"    ... and {len(untested) - 20} more")
        over = tc.get("overtested_symbols", [])
        if over:
            lines.append(f"  Over-tested ({len(over)}):")
            for s in over[:10]:
                lines.append(f"    {s.get('name', '?')} ({s.get('test_ref_count', 0)} test refs)")
        test_only = tc.get("test_only_symbols", [])
        if test_only:
            lines.append(f"  Test-only ({len(test_only)}):")
            for s in test_only[:10]:
                lines.append(f"    {s}")
            if len(test_only) > 10:
                lines.append(f"    ... and {len(test_only) - 10} more")
    return "\n".join(lines)
