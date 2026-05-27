#!/usr/bin/env python3
"""Route CI jobs from changed files.

The parser deliberately supports only the tiny YAML subset used by
config/ci-routing.yml so GitHub can run this before project dependencies
are installed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_OUTPUTS = {
    "run_quality": True,
    "run_test_matrix": True,
    "run_build": True,
    "run_e2e_smoke": False,
    "run_regression": False,
    "run_sql_platform_compat": False,
    "run_benchmarks": False,
    "run_grammar_coverage": False,
    "upload_coverage": True,
    "full_language_once": True,
    "full_suite_required": False,
    "regression_scope": "all",
    "benchmark_scope": "all",
}


def _parse_scalar(value: str) -> Any:
    if value == "true":
        return True
    if value == "false":
        return False
    return value.strip('"')


def load_routing_config(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line_without_comment = raw_line.split("#", 1)[0].rstrip()
        if not line_without_comment.strip():
            continue
        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        text = line_without_comment.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if text.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"List item without list parent: {raw_line}")
            parent.append(_parse_scalar(text[2:].strip()))
            continue

        key, sep, value = text.partition(":")
        if not sep:
            raise ValueError(f"Unsupported config line: {raw_line}")

        key = key.strip()
        value = value.strip()
        if value:
            parent[key] = _parse_scalar(value)
            continue

        next_container: Any = (
            [] if _next_meaningful_line_is_list(path, raw_line) else {}
        )
        parent[key] = next_container
        stack.append((indent, next_container))

    return root


def _next_meaningful_line_is_list(path: Path, current_line: str) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(current_line) + 1
    except ValueError:
        return False
    current_indent = len(current_line) - len(current_line.lstrip(" "))
    for line in lines[start:]:
        stripped = line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        if indent <= current_indent:
            return False
        return stripped.strip().startswith("- ")
    return False


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def route_changed_files(
    changed_files: list[str], config: dict[str, Any]
) -> dict[str, Any]:
    outputs = dict(DEFAULT_OUTPUTS)
    outputs.update(config.get("always", {}))
    reason_codes: list[str] = []

    full_suite_patterns = config.get("full_suite", [])
    if any(matches_any(path, full_suite_patterns) for path in changed_files):
        outputs["full_suite_required"] = True
        reason_codes.append("full-suite-path")

    for output_name, patterns in config.get("routes", {}).items():
        if any(matches_any(path, patterns) for path in changed_files):
            outputs[output_name] = True
            reason_codes.append(output_name)

    for scope_name, scope_config in config.get("scopes", {}).items():
        matched_scopes = [
            value
            for value, patterns in scope_config.get("values", {}).items()
            if any(matches_any(path, patterns) for path in changed_files)
        ]
        if len(matched_scopes) == 1:
            outputs[scope_name] = matched_scopes[0]
        elif len(matched_scopes) > 1:
            outputs[scope_name] = scope_config.get("default", "all")
            reason_codes.append(f"{scope_name}-multiple")

    if outputs["full_suite_required"]:
        for key in list(outputs):
            if key.startswith("run_"):
                outputs[key] = True
        reason_codes.append("force-all-routes")

    outputs["changed_count"] = len(changed_files)
    outputs["changed_files"] = changed_files
    outputs["reason_codes"] = sorted(set(reason_codes))
    return outputs


def _read_changed_files(args: argparse.Namespace) -> list[str]:
    paths: list[str] = []
    for file_list in args.files:
        paths.extend(Path(file_list).read_text(encoding="utf-8").splitlines())
    paths.extend(args.paths)
    if not paths and not sys.stdin.isatty():
        paths.extend(sys.stdin.read().splitlines())
    return sorted({path.strip() for path in paths if path.strip()})


def _write_github_outputs(outputs: dict[str, Any], github_output: str) -> None:
    with Path(github_output).open("a", encoding="utf-8") as fh:
        for key, value in outputs.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (list, dict)):
                rendered = json.dumps(value, sort_keys=True)
            else:
                rendered = str(value)
            fh.write(f"{key}={rendered}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--config", default="config/ci-routing.yml")
    parser.add_argument("--files", action="append", default=[])
    parser.add_argument("--github-output")
    args = parser.parse_args(argv)

    config = load_routing_config(Path(args.config))
    outputs = route_changed_files(_read_changed_files(args), config)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    if args.github_output:
        _write_github_outputs(outputs, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
