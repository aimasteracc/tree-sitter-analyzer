"""Prove exact Codex model availability before freezing a Smoke manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from benchmarks.codegraph_compare.integrity import _sha256

SCHEMA_VERSION = 1
SENTINEL = "NO1_MODEL_PREFLIGHT_OK"


def _codex_identity() -> dict[str, str]:
    executable = shutil.which("codex")
    if executable is None:
        raise ValueError("Required executable is unavailable: codex")
    binary = Path(executable).resolve()
    version = subprocess.run(
        ["codex", "--version"], capture_output=True, text=True, check=True
    )
    return {
        "command": "codex --version",
        "version": (version.stdout or version.stderr).strip(),
        "executable": str(binary),
        "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }


def _account_surface() -> str:
    status = subprocess.run(
        ["codex", "login", "status"], capture_output=True, text=True, check=True
    )
    output = (status.stdout or status.stderr).strip()
    if output != "Logged in using ChatGPT":
        raise ValueError(f"Unsupported or ambiguous Codex account surface: {output}")
    return "ChatGPT"


def _agent_message(stdout: str) -> str:
    messages: list[str] = []
    for line in stdout.splitlines():
        event = json.loads(line)
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text")
            if not isinstance(text, str):
                raise ValueError("Model preflight agent message is not text")
            messages.append(text)
    if len(messages) != 1:
        raise ValueError("Model preflight did not return exactly one terminal message")
    try:
        payload = json.loads(messages[0])
    except json.JSONDecodeError as exc:
        raise ValueError("Model preflight terminal message is not JSON") from exc
    if payload != {"status": SENTINEL}:
        raise ValueError("Model preflight did not return the exact terminal sentinel")
    return SENTINEL


def run_model_preflight(
    *, model: str, output_path: Path, timeout_seconds: int = 120
) -> dict[str, Any]:
    """Call an exact model outside the benchmark tree and write immutable evidence."""

    identity = _codex_identity()
    account_surface = _account_surface()
    with tempfile.TemporaryDirectory(prefix="no1-model-preflight-") as directory:
        schema_path = Path(directory) / "output-schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "const": SENTINEL},
                    },
                    "required": ["status"],
                    "additionalProperties": False,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "codex",
                "exec",
                "--model",
                model,
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--json",
                "--output-schema",
                str(schema_path),
                "Return the required JSON object.",
            ],
            cwd=directory,
            env={**os.environ, "CODEX_NETWORK_DISABLED": "1"},
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    _agent_message(result.stdout)
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASSED",
        "provider": "OpenAI",
        "account_surface": account_surface,
        "model": model,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "agent_cli": identity,
        "agent_cli_fingerprint": _sha256(identity),
        "sentinel_sha256": hashlib.sha256(SENTINEL.encode()).hexdigest(),
    }
    with output_path.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return evidence


def validate_model_preflight(
    path: Path,
    *,
    expected_model: str,
    expected_cli_fingerprint: str,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    """Reject stale, failed, ambiguous, or differently bound preflight evidence."""

    evidence = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    required = {
        "schema_version",
        "status",
        "provider",
        "account_surface",
        "model",
        "checked_at",
        "agent_cli",
        "agent_cli_fingerprint",
        "sentinel_sha256",
    }
    if set(evidence) != required:
        raise ValueError("Model preflight evidence has an invalid field set")
    if evidence["schema_version"] != SCHEMA_VERSION or evidence["status"] != "PASSED":
        raise ValueError("Model preflight evidence is not a successful V1 record")
    if evidence["provider"] != "OpenAI" or evidence["account_surface"] != "ChatGPT":
        raise ValueError("Model preflight provider/account surface is not approved")
    if evidence["model"] != expected_model:
        raise ValueError("Model preflight does not match the requested model")
    if evidence["agent_cli_fingerprint"] != expected_cli_fingerprint:
        raise ValueError("Model preflight Codex CLI fingerprint is stale or mismatched")
    if evidence["sentinel_sha256"] != hashlib.sha256(SENTINEL.encode()).hexdigest():
        raise ValueError("Model preflight sentinel is invalid")
    checked_at = datetime.fromisoformat(evidence["checked_at"])
    if checked_at.tzinfo is None:
        raise ValueError("Model preflight timestamp must include a timezone")
    if max_age_seconds is not None:
        age = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise ValueError("Model preflight is stale or has a future timestamp")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        evidence = run_model_preflight(
            model=args.model,
            output_path=args.output,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        print(f"Model preflight failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
