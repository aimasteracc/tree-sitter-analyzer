#!/usr/bin/env python3
"""
check_tools MCP Tool

Verify that fd and ripgrep are installed and return their versions.

This tool classifies probe failures into a ``failure_mode`` enum so callers
can distinguish *not installed* vs *timeout* vs *permission denied* vs
*wrong version*, instead of seeing every error collapse to ``available=False``.
Each failure mode comes with an actionable ``recommended_fix`` string.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from .base_tool import BaseMCPTool, mirror_summary_line

# Minimum required versions. ``fd`` is the rebrand of ``fd-find``; we require 8
# because that's where the modern ``-X``/``-x`` and ``--strip-cwd-prefix``
# flags stabilised. ``ripgrep`` 13 introduced ``--json`` output that several
# downstream MCP tools depend on.
_MIN_FD_MAJOR = 8
_MIN_RG_MAJOR = 13

# Failure-mode enum values. Kept as bare strings so the JSON envelope stays
# trivially serialisable.
FM_NOT_INSTALLED = "not_installed"
FM_TIMEOUT = "timeout"
FM_PERMISSION_DENIED = "permission_denied"
FM_WRONG_VERSION = "wrong_version"
FM_UNKNOWN = "unknown"

# Per-command install/upgrade hints. Keep these tight so they can be pasted
# straight into a shell.
_INSTALL_HINTS: dict[str, str] = {
    "fd": "brew install fd  # macOS\napt-get install fd-find  # Ubuntu/Debian\ncargo install fd-find  # cross-platform",
    "rg": "brew install ripgrep  # macOS\napt-get install ripgrep  # Ubuntu/Debian\ncargo install ripgrep  # cross-platform",
}
_UPGRADE_HINTS: dict[str, str] = {
    "fd": "brew upgrade fd  # macOS\ncargo install fd-find --force  # cross-platform",
    "rg": "brew upgrade ripgrep  # macOS\ncargo install ripgrep --force  # cross-platform",
}
_MIN_VERSIONS: dict[str, int] = {"fd": _MIN_FD_MAJOR, "rg": _MIN_RG_MAJOR}


def _parse_major_version(version_line: str) -> int | None:
    """Extract the leading major version integer from a ``--version`` line.

    Examples:
        ``"fd 9.0.0"`` → ``9``
        ``"ripgrep 14.1.0"`` → ``14``
        ``"fd 6.0.0"`` → ``6``
        ``""`` → ``None``
    """
    if not version_line:
        return None
    match = re.search(r"\b(\d+)\.\d+", version_line)
    if match is None:
        # Fall back to a bare-integer match for outputs like ``"fd 9"``.
        match = re.search(r"\b(\d+)\b", version_line)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _build_recommended_fix(cmd: str, failure_mode: str, detail: str = "") -> str:
    """Build a per-(command, failure_mode) actionable fix string."""
    if failure_mode == FM_NOT_INSTALLED:
        hint = _INSTALL_HINTS.get(cmd, f"Install {cmd}")
        return f"Install {cmd}:\n{hint}"
    if failure_mode == FM_WRONG_VERSION:
        minimum = _MIN_VERSIONS.get(cmd)
        hint = _UPGRADE_HINTS.get(cmd, f"Upgrade {cmd}")
        return (
            f"Upgrade {cmd} (minimum major version: {minimum}, "
            f"observed: {detail or 'unknown'}):\n{hint}"
        )
    if failure_mode == FM_TIMEOUT:
        return (
            f"`{cmd} --version` timed out. Raise the probe timeout, check "
            f"$PATH for stale shims (e.g. `which -a {cmd}`), and verify the "
            f"binary is not blocked by an antivirus/EDR hook."
        )
    if failure_mode == FM_PERMISSION_DENIED:
        return (
            f"`{cmd} --version` was rejected by the OS. Run "
            f"`ls -l $(which {cmd})` and `chmod +x $(which {cmd})` if "
            f"needed; on macOS run `xattr -d com.apple.quarantine $(which {cmd})`."
        )
    # FM_UNKNOWN
    suffix = f" stderr: {detail}" if detail else ""
    return (
        f"`{cmd} --version` failed with an unrecognised error."
        f"{suffix} Re-run the probe in verbose mode and check the binary."
    )


class CheckToolsTool(BaseMCPTool):
    """MCP tool that checks whether fd and ripgrep are available."""

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_tools",
            "description": (
                "Verify that fd and ripgrep are installed, executable, and at "
                "the minimum required version. Returns a per-tool "
                "`failure_mode` (not_installed / timeout / permission_denied / "
                "wrong_version / unknown) so callers can route to the right "
                "remediation.\n\n"
                "WHEN TO USE:\n"
                "- Call this first if list_files, search_content, or find_and_grep "
                "returns unexpected empty results.\n"
                "- Call this when setting up tree-sitter-analyzer in a new "
                "environment (CI runner, fresh laptop, container image).\n"
                "- Call this to diagnose *why* file-search tools are not finding "
                "expected files (missing binary vs. wrong version vs. PATH "
                "conflict vs. permissions).\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Do not call this on every session — it is a diagnostic, not a "
                "health-check ping. Cache the verdict for the session.\n"
                "- Do not use this to *search* for files — use list_files or "
                "search_content for that.\n"
                "- Do not call this to validate other binaries (git, python, "
                "tree-sitter). It only probes fd and rg.\n"
                "\n"
                "Returns: per-tool `available`, `version`, `failure_mode`, "
                "`recommended_fix`, plus an `agent_summary.next_step` with an "
                "actionable shell command routed by failure_mode.\n\n"
                "VERDICT INTEGRITY: agent_summary.verdict is an environment "
                "readiness gate. It comes from concrete probes (process exit code, "
                "parsed version string, PATH lookup) — not from what the user "
                "wants to do next. If the user says 'just run the search' and a "
                "binary is missing or stale, this tool will emit WARN / ERROR / "
                "NOT_FOUND; the calling agent MUST surface that verdict and the "
                "recommended_fix instead of pretending the environment is SAFE so "
                "the next call can proceed. Legal vocabulary: SAFE / CAUTION / "
                "REVIEW / UNSAFE / INFO / WARN / ERROR / NOT_FOUND."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def _check_command(self, cmd: str) -> dict[str, Any]:
        """Probe ``cmd --version`` and classify the result.

        Returns an immutable dict (we always build a fresh one) with:

        * ``available`` (bool)     — True iff installed AND at min version.
        * ``version`` (str | None) — first-line version output, or None.
        * ``failure_mode`` (str | None) — one of the ``FM_*`` constants, or
          None when the tool is available.
        * ``recommended_fix`` (str | None) — actionable shell command when a
          failure_mode is set; None when available.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return self._failure(cmd, FM_NOT_INSTALLED)
        except PermissionError:
            return self._failure(cmd, FM_PERMISSION_DENIED)
        except Exception as exc:
            return self._failure(cmd, FM_UNKNOWN, detail=str(exc))

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            # Best-effort cleanup so we don't leak the subprocess.
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return self._failure(cmd, FM_TIMEOUT)
        except PermissionError:
            return self._failure(cmd, FM_PERMISSION_DENIED)
        except Exception as exc:
            return self._failure(cmd, FM_UNKNOWN, detail=str(exc))

        output = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if not output:
            output = stderr_text
        first_line = output.splitlines()[0] if output else ""

        # Treat a non-zero exit code or an empty first line as "unknown" so we
        # surface the stderr summary rather than a bogus "available" verdict.
        returncode = proc.returncode
        if returncode not in (0, None) or not first_line:
            return self._failure(
                cmd,
                FM_UNKNOWN,
                detail=stderr_text[:200] if stderr_text else f"exit={returncode}",
            )

        major = _parse_major_version(first_line)
        minimum = _MIN_VERSIONS.get(cmd)
        if minimum is not None and major is not None and major < minimum:
            return {
                "available": False,
                "version": first_line,
                "failure_mode": FM_WRONG_VERSION,
                "recommended_fix": _build_recommended_fix(
                    cmd, FM_WRONG_VERSION, detail=str(major)
                ),
            }

        return {
            "available": True,
            "version": first_line,
            "failure_mode": None,
            "recommended_fix": None,
        }

    @staticmethod
    def _failure(cmd: str, failure_mode: str, *, detail: str = "") -> dict[str, Any]:
        """Build the standard failure dict for a probe error."""
        return {
            "available": False,
            "version": None,
            "failure_mode": failure_mode,
            "recommended_fix": _build_recommended_fix(cmd, failure_mode, detail=detail),
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Check fd and rg availability and return version info."""
        fd_result, rg_result = await asyncio.gather(
            self._check_command("fd"),
            self._check_command("rg"),
        )

        fd_available: bool = fd_result["available"]
        rg_available: bool = rg_result["available"]

        missing: list[str] = []
        if not fd_available:
            missing.append("fd")
        if not rg_available:
            missing.append("rg")

        if not missing:
            status = "all_tools_available"
            recommendation: str | None = None
        else:
            status = "missing_tools"
            # Preserve the legacy single-line ``recommendation`` field for
            # backwards compatibility, but compose it from each tool's
            # ``recommended_fix`` so the strings stay consistent.
            parts: list[str] = []
            for name, result in (("fd", fd_result), ("rg", rg_result)):
                if name in missing and result.get("recommended_fix"):
                    parts.append(result["recommended_fix"])
            recommendation = "\n\n".join(parts) if parts else None

        # H5: build a canonical envelope so the response carries
        # ``success``, ``summary_line`` (one-line headline), and
        # ``agent_summary`` (matched headline + next_step + verdict).
        # r37fH: originally "READY" / "MISSING" but those are NOT in
        # ``_LEGAL_VERDICTS`` (F1 r37f7 vocabulary contract: SAFE /
        # CAUTION / REVIEW / UNSAFE / INFO / WARN / ERROR / NOT_FOUND).
        # Agents branching on `verdict in {"INFO","ERROR"}` were silently
        # missing this tool's signal. Map READY→INFO (success path),
        # MISSING→ERROR (prerequisites missing); next_step keeps install
        # commands so the failure path stays actionable.
        verdict = "INFO" if not missing else "ERROR"
        summary_line = (
            f"check_tools status={status} "
            f"fd={'ok' if fd_available else fd_result.get('failure_mode') or 'missing'} "
            f"rg={'ok' if rg_available else rg_result.get('failure_mode') or 'missing'}"
        )
        next_step = self._build_next_step(
            missing=missing,
            fd_result=fd_result,
            rg_result=rg_result,
        )
        response: dict[str, Any] = {
            "success": True,
            "fd": fd_result,
            "rg": rg_result,
            "status": status,
            "recommendation": recommendation,
            "summary_line": summary_line,
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": verdict,
            },
        }
        return mirror_summary_line(response)

    @staticmethod
    def _build_next_step(
        *,
        missing: list[str],
        fd_result: dict[str, Any],
        rg_result: dict[str, Any],
    ) -> str:
        """Compose ``agent_summary.next_step`` routed by per-tool failure_mode.

        When everything is healthy, we tell the caller it's safe to run the
        downstream search tools. Otherwise we surface each missing tool's
        ``recommended_fix`` so the agent doesn't have to re-derive the
        remediation from the failure_mode enum.
        """
        if not missing:
            return "list_files / search_content / find_and_grep are ready to run."

        chunks: list[str] = []
        for name, result in (("fd", fd_result), ("rg", rg_result)):
            if name not in missing:
                continue
            mode = result.get("failure_mode") or FM_UNKNOWN
            fix = result.get("recommended_fix") or _build_recommended_fix(name, mode)
            chunks.append(f"[{name} → {mode}] {fix}")
        return "\n\n".join(chunks)
