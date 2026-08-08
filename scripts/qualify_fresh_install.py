#!/usr/bin/env python3
"""Exercise offline installer boundaries without granting qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

AXES = ("macos", "linux", "windows")
SCENARIOS = (
    "disable_unverified_bootstrap",
    "missing_uv_bootstraps",
    "outdated_uv_bootstraps",
    "installer_body_failure",
    "curl_missing",
    "download_tls_failure",
    "post_bootstrap_uv_missing",
    "post_bootstrap_uv_non_executable",
    "post_bootstrap_uv_too_old",
    "post_bootstrap_uv_malformed",
    "post_bootstrap_path_prefers_new_uv",
    "json_parse_error_skips_and_continues",
    "python3_missing_fails_closed",
    "config_root_non_object_fails_closed",
    "mcp_servers_non_object_fails_closed",
    "tsa_entry_non_object_fails_closed",
    "no_agent_config_skips_cleanly",
    "merge_write_permission_failure_fails_closed",
)
CONFIG_TEXT = {
    "valid": "{}\n",
    "parse_error": "{ invalid json }\n",
    "root_list": "[]\n",
    "mcp_list": '{"mcpServers": []}\n',
    "entry_list": '{"mcpServers": {"tree-sitter-analyzer": []}}\n',
    "permission": "{}\n",
}


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _host_axis() -> str:
    return {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(
        platform.system(), "unsupported"
    )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _restricted_tools(root: Path, *, include_python3: bool = True) -> Path:
    """Build a hermetic PATH containing tools the installer contract requires."""
    tool_bin = root / "tool-bin"
    tool_bin.mkdir()
    commands = (
        "awk",
        "cat",
        "chmod",
        "grep",
        "mkdir",
        "mktemp",
        "realpath",
        "rm",
        "sh",
        "sleep",
        "uname",
    )
    for command in commands:
        resolved = shutil.which(command)
        if resolved:
            (tool_bin / command).symlink_to(resolved)
    if include_python3:
        (tool_bin / "python3").symlink_to(Path(sys.executable).resolve())
    return tool_bin


def _prepare_fixture(
    root: Path,
    initial_uv: str | None,
    bootstrap_mode: str,
    *,
    config_mode: str = "valid",
    curl_mode: str = "success",
    restricted_path: bool = False,
    initial_uv_location: str = "mock-bin",
) -> dict[str, str]:
    mock_bin, home, claude = root / "mock-bin", root / "home", root / ".claude"
    mock_bin.mkdir()
    home.mkdir()
    claude.mkdir()
    if config_mode != "none":
        (claude / ".mcp.json").write_text(CONFIG_TEXT[config_mode], encoding="utf-8")
    if config_mode == "permission":
        claude.chmod(0o555)
    initial_bin = mock_bin
    if initial_uv_location == "legacy-bin":
        initial_bin = root / "legacy-bin"
        initial_bin.mkdir()
    if initial_uv is not None:
        _write_executable(initial_bin / "uv", f'#!/bin/sh\nprintf "{initial_uv}\\n"\n')
    if curl_mode != "missing":
        if curl_mode == "failure":
            curl = '#!/bin/sh\nprintf "%s\\n" "$*" > "$CURL_LOG"\nexit 60\n'
        else:
            curl = r"""#!/bin/sh
printf '%s\n' "$*" > "$CURL_LOG"
out=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = '-o' ]; then out=$2; shift 2; else shift; fi
done
[ -n "$out" ] || exit 64
cat > "$out" <<'INSTALLER'
#!/bin/sh
case "$BOOTSTRAP_MODE" in
  body_failure) exit 9 ;;
  missing) exit 0 ;;
  nonexec)
    mkdir -p "$HOME/.local/bin"
    printf '#!/bin/sh\nprintf "uv 0.11.0\\n"\n' > "$HOME/.local/bin/uv"
    chmod 644 "$HOME/.local/bin/uv" ;;
  old) version='uv 0.10.9' ;;
  malformed) version='not-uv 0.11.0' ;;
  valid) version='uv 0.11.0' ;;
  *) exit 65 ;;
esac
if [ -n "${version:-}" ]; then
  mkdir -p "$HOME/.local/bin"
  printf '#!/bin/sh\nprintf "%%s\\n" "%s"\n' "$version" > "$HOME/.local/bin/uv"
  chmod 755 "$HOME/.local/bin/uv"
fi
INSTALLER
"""
        _write_executable(mock_bin / "curl", curl)
    path = [str(mock_bin)]
    if initial_uv_location == "legacy-bin":
        path.append(str(initial_bin))
    # Never expose the host PATH: initial_uv=None must mean uv is genuinely
    # absent even on machines that install it in /usr/bin or /bin.
    path.append(str(_restricted_tools(root, include_python3=not restricted_path)))
    return {
        "HOME": str(home),
        "PATH": os.pathsep.join(path),
        "BOOTSTRAP_MODE": bootstrap_mode,
        "CURL_LOG": str(root / "curl.log"),
    }


def _fixture_fingerprint(root: Path, fixture: dict[str, str]) -> str:
    def file_record(path: Path) -> dict[str, object]:
        if not path.exists():
            return {"present": False}
        return {
            "present": True,
            "mode": path.stat().st_mode & 0o777,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    normalized_path = [
        str(Path(item).relative_to(root))
        if item.startswith(f"{root}{os.sep}")
        else item
        for item in fixture["PATH"].split(os.pathsep)
    ]
    manifest = {
        "path": normalized_path,
        "bootstrap_mode": fixture["BOOTSTRAP_MODE"],
        "bootstrap_disabled": fixture.get("TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"),
        "bootstrap_install_location": "home/.local/bin/uv",
        "mock_uv": file_record(root / "mock-bin" / "uv"),
        "legacy_uv": file_record(root / "legacy-bin" / "uv"),
        "curl": file_record(root / "mock-bin" / "curl"),
        "python3_present": (root / "tool-bin" / "python3").exists(),
        "config": file_record(root / ".claude" / ".mcp.json"),
    }
    return _fingerprint(manifest)


def _remove_fixture(root: Path) -> None:
    if not root.exists():
        return
    claude = root / ".claude"
    if claude.exists():
        claude.chmod(0o755)
    shutil.rmtree(root)


def _run(
    repo: Path, initial_uv: str | None, bootstrap_mode: str, **options: Any
) -> tuple[subprocess.CompletedProcess[str], Path, str]:
    root = Path(tempfile.mkdtemp(prefix="tsa-installer-contract-"))
    try:
        disable = options.pop("disable_bootstrap", False)
        fixture = _prepare_fixture(root, initial_uv, bootstrap_mode, **options)
        if disable:
            fixture["TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"] = "1"
        execution_fingerprint = _fixture_fingerprint(root, fixture)
        execution_env = os.environ.copy()
        execution_env.pop("TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP", None)
        execution_env.update(fixture)
        completed = subprocess.run(
            ["/bin/bash", str(repo / "install.sh")],
            cwd=root,
            env=execution_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except BaseException:
        _remove_fixture(root)
        raise
    return completed, root, execution_fingerprint


def _settings(scenario_id: str) -> tuple[str | None, str, dict[str, Any]]:
    initial: str | None = None
    bootstrap = "valid"
    options: dict[str, Any] = {}
    if scenario_id == "disable_unverified_bootstrap":
        options["disable_bootstrap"] = True
    elif scenario_id == "outdated_uv_bootstraps":
        initial = "uv 0.10.9"
    elif scenario_id == "post_bootstrap_path_prefers_new_uv":
        initial = "uv 0.10.9"
        options["initial_uv_location"] = "legacy-bin"
    elif scenario_id == "installer_body_failure":
        bootstrap = "body_failure"
    elif scenario_id == "curl_missing":
        options.update(curl_mode="missing", restricted_path=True)
    elif scenario_id == "download_tls_failure":
        options["curl_mode"] = "failure"
    elif scenario_id.startswith("post_bootstrap_uv_"):
        bootstrap = {
            "post_bootstrap_uv_missing": "missing",
            "post_bootstrap_uv_non_executable": "nonexec",
            "post_bootstrap_uv_too_old": "old",
            "post_bootstrap_uv_malformed": "malformed",
        }[scenario_id]
    elif scenario_id == "json_parse_error_skips_and_continues":
        initial, options["config_mode"] = "uv 0.11.0", "parse_error"
    elif scenario_id == "python3_missing_fails_closed":
        initial, options["restricted_path"] = "uv 0.11.0", True
    elif scenario_id == "config_root_non_object_fails_closed":
        initial, options["config_mode"] = "uv 0.11.0", "root_list"
    elif scenario_id == "mcp_servers_non_object_fails_closed":
        initial, options["config_mode"] = "uv 0.11.0", "mcp_list"
    elif scenario_id == "tsa_entry_non_object_fails_closed":
        initial, options["config_mode"] = "uv 0.11.0", "entry_list"
    elif scenario_id == "no_agent_config_skips_cleanly":
        initial, options["config_mode"] = "uv 0.11.0", "none"
    elif scenario_id == "merge_write_permission_failure_fails_closed":
        initial, options["config_mode"] = "uv 0.11.0", "permission"
    return initial, bootstrap, options


def _scenario(repo: Path, scenario_id: str) -> dict[str, Any]:
    root: Path | None = None
    try:
        initial, bootstrap, options = _settings(scenario_id)
        settings_fingerprint = _fingerprint(
            {
                "initial_uv": initial,
                "bootstrap_mode": bootstrap,
                "options": options,
            }
        )
        completed, root, execution_fingerprint = _run(
            repo, initial, bootstrap, **options
        )
        output, config_path = (
            completed.stdout + completed.stderr,
            root / ".claude" / ".mcp.json",
        )
        if scenario_id == "disable_unverified_bootstrap":
            passed = completed.returncode == 1 and not (root / "curl.log").exists()
        elif scenario_id in {"missing_uv_bootstraps", "outdated_uv_bootstraps"}:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            passed = (
                completed.returncode == 0
                and config["mcpServers"]["tree-sitter-analyzer"]["command"] == "uvx"
                and "UNVERIFIED and mutable" in output
            )
        elif scenario_id == "post_bootstrap_path_prefers_new_uv":
            passed = (
                completed.returncode == 0 and str(root / "home/.local/bin/uv") in output
            )
        elif scenario_id == "installer_body_failure":
            passed = (
                completed.returncode == 1 and "Recovery: install uv >= 0.11.0" in output
            )
        elif scenario_id == "curl_missing":
            passed = completed.returncode == 1 and "curl not found" in output
        elif scenario_id == "download_tls_failure":
            passed = (
                completed.returncode == 1 and "Automatic uv bootstrap failed" in output
            )
        elif scenario_id.startswith("post_bootstrap_uv_"):
            passed = (
                completed.returncode == 1 and "did not provide required uv" in output
            )
        elif scenario_id == "json_parse_error_skips_and_continues":
            passed = (
                completed.returncode == 0
                and config_path.read_text(encoding="utf-8")
                == CONFIG_TEXT["parse_error"]
                and "JSON parse error — skipping" in output
            )
        elif scenario_id == "python3_missing_fails_closed":
            passed = (
                completed.returncode == 1
                and config_path.read_text(encoding="utf-8") == CONFIG_TEXT["valid"]
                and "python3 not found — skipping" in output
            )
        elif scenario_id == "no_agent_config_skips_cleanly":
            passed = completed.returncode == 0 and not config_path.exists()
        elif scenario_id == "merge_write_permission_failure_fails_closed":
            passed = (
                completed.returncode == 1
                and config_path.read_text(encoding="utf-8") == CONFIG_TEXT["permission"]
                and "unexpected error (exit 1) — skipping" in output
            )
        else:
            mode = options["config_mode"]
            passed = (
                completed.returncode == 1
                and config_path.read_text(encoding="utf-8") == CONFIG_TEXT[mode]
                and "unexpected error (exit 3) — skipping" in output
            )
        return {
            "id": scenario_id,
            "status": "passed" if passed else "failed",
            "installer_exit": completed.returncode,
            "settings_fingerprint": settings_fingerprint,
            "execution_fingerprint": execution_fingerprint,
        }
    except Exception as exc:  # noqa: BLE001
        return {"id": scenario_id, "status": "failed", "error_type": type(exc).__name__}
    finally:
        if root is not None:
            _remove_fixture(root)


def _git_provenance(repo: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    return {"commit": commit, "dirty": dirty}


def qualify(repo: Path, requested_axes: tuple[str, ...]) -> dict[str, Any]:
    host, axes = _host_axis(), []
    for axis in requested_axes:
        base = {
            "axis": axis,
            "qualification": "not_performed",
            "qualified": False,
            "native_evidence": False,
        }
        if axis != host:
            axes.append(
                base
                | {
                    "status": "not_run",
                    "reason": f"requires {axis} host; current host is {host}",
                    "scenarios": [],
                }
            )
        elif axis == "windows":
            axes.append(
                base
                | {
                    "status": "failed",
                    "reason": "install.sh is POSIX-only",
                    "scenarios": [],
                }
            )
        else:
            scenarios = [_scenario(repo, item) for item in SCENARIOS]
            passed = all(item["status"] == "passed" for item in scenarios)
            axes.append(
                base
                | {
                    "status": "passed" if passed else "failed",
                    "scenario_type": "offline_installer_contract",
                    "scenarios": scenarios,
                }
            )
    return {
        "schema_version": 2,
        "qualification_id": "NO1-006A",
        "evidence_scope": "offline_installer_contract",
        "evidence_trust": "UNTRUSTED_SELF_REPORTED",
        "qualification_performed": False,
        "native_axes_qualified": False,
        "host": {
            "axis": host,
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "python_runtime": sys.implementation.name,
        },
        "source": {
            "git": _git_provenance(repo),
            "install_sh_sha256": hashlib.sha256(
                (repo / "install.sh").read_bytes()
            ).hexdigest(),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "bootstrap": {
            "url": "https://astral.sh/uv/install.sh",
            "integrity": "none",
            "attestation": "none",
            "trust": "UNVERIFIED",
            "execution": "default_unverified_with_secure_opt_out",
        },
        "package_evidence": "none",
        "mcp_protocol_evidence": "none",
        "axes": axes,
        "pending_axes": [item["axis"] for item in axes if item["status"] == "not_run"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis", choices=(*AXES, "all"))
    parser.add_argument(
        "--local-contract-only",
        action="store_true",
        help="run current-host offline contract; never grants qualification",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.local_contract_only and args.axis is not None:
        parser.error(
            "--local-contract-only cannot be combined with --axis; it always runs only the current host"
        )
    repo = Path(__file__).resolve().parents[1]
    requested = (
        (_host_axis(),)
        if args.local_contract_only
        else AXES
        if args.axis in {None, "all"}
        else (args.axis,)
    )
    report = qualify(repo, requested)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not args.local_contract_only:
        return 1
    executed = [item for item in report["axes"] if item["status"] != "not_run"]
    return 0 if executed and all(item["status"] == "passed" for item in executed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
