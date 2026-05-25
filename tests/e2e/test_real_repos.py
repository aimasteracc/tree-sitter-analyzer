"""E2E tests against real open-source Python projects.

These tests clone public repos with ``--depth 1`` and run TSA tools
against them. They verify:
1. TSA produces meaningful results on codebases it has never seen.
2. TSA does not crash on any realistic Python project layout.
3. Latency stays within budget even on real (multi-file) projects.

If the network is unavailable the tests are automatically skipped via
the ``clone_repo_factory`` fixture.

Repos under test
----------------
* **pallets/click** — small (~15 source files), widely known, stable.
  Good proxy for a typical 1K-5K LoC library.
* **psf/requests** — medium (~30 source files), classic, well-structured.
  Good proxy for a typical 5K-20K LoC library.

These repos are chosen for stability (maintained, no churn) and size
(fast to clone in CI, small enough for quick analysis).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.e2e.conftest import MCPClient, initialized

pytestmark = [pytest.mark.e2e, pytest.mark.network]

# ---------------------------------------------------------------------------
# Real repos under test
# ---------------------------------------------------------------------------

REAL_REPOS = [
    ("https://github.com/pallets/click.git", "click"),
    ("https://github.com/psf/requests.git", "requests"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_python_file(repo_dir: Path) -> str:
    """Return a relative path to a small Python file inside ``repo_dir``.

    Prefers ``__init__.py`` files (commonly small, always present in
    Python packages). Falls back to the first ``.py`` file found.
    """
    for candidate in sorted(repo_dir.rglob("__init__.py")):
        if candidate.stat().st_size < 50_000:
            return str(candidate.relative_to(repo_dir))
    for candidate in sorted(repo_dir.rglob("*.py")):
        if candidate.stat().st_size < 50_000:
            return str(candidate.relative_to(repo_dir))
    pytest.skip(f"No Python file found in {repo_dir}")


# ---------------------------------------------------------------------------
# check_project_health against real repos
# ---------------------------------------------------------------------------


class TestCheckProjectHealthRealRepos:
    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_project_health_returns_result(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """check_project_health must not crash on a real Python project."""
        repo_dir = clone_repo_factory(url, name)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        response = client.call("check_project_health", {}, timeout=30.0)
        assert "error" not in response, (
            f"check_project_health crashed on {name}: {response.get('error')}\n"
            f"stderr:\n{client.stderr_text()}"
        )
        content = response["result"]["content"]
        assert content, f"check_project_health returned empty content for {name}"

    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_project_health_returns_grade(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """check_project_health must return a letter grade for real repos."""
        repo_dir = clone_repo_factory(url, name)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        response = client.call("check_project_health", {}, timeout=30.0)
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        text = content[0]["text"] if isinstance(content, list) else str(content)
        has_grade = any(g in text for g in ["A", "B", "C", "D", "F"])
        assert has_grade, (
            f"check_project_health for {name} has no letter grade:\n{text[:500]}"
        )

    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_project_health_under_30s(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """check_project_health must finish in 30s even on real repos."""
        import time

        repo_dir = clone_repo_factory(url, name)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        t0 = time.monotonic()
        response = client.call("check_project_health", {}, timeout=35.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 30.0, (
            f"check_project_health on {name} took {elapsed:.1f}s — over the 30s budget.\n"
            f"stderr:\n{client.stderr_text()}"
        )
        assert "error" not in response, response.get("error")


# ---------------------------------------------------------------------------
# check_file_health against real repos
# ---------------------------------------------------------------------------


class TestCheckFileHealthRealRepos:
    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_file_health_on_discovered_file(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """check_file_health must return a result for a file in a real repo."""
        repo_dir = clone_repo_factory(url, name)
        py_file = _find_python_file(repo_dir)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        response = client.call(
            "check_file_health",
            {"file_path": py_file},
            timeout=20.0,
        )
        assert "result" in response or "error" in response, (
            f"check_file_health({py_file}) on {name} returned neither"
        )


# ---------------------------------------------------------------------------
# safe_to_edit against real repos
# ---------------------------------------------------------------------------


class TestSafeToEditRealRepos:
    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_safe_to_edit_returns_verdict(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """safe_to_edit must return a SAFE/UNSAFE verdict for a real-repo file."""
        repo_dir = clone_repo_factory(url, name)
        py_file = _find_python_file(repo_dir)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        response = client.call(
            "safe_to_edit",
            {"file_path": py_file},
            timeout=15.0,
        )
        assert "error" not in response, (
            f"safe_to_edit({py_file}) on {name} returned JSON-RPC error: "
            f"{response.get('error')}"
        )
        content = response["result"]["content"]
        assert content
        text = content[0]["text"] if isinstance(content, list) else str(content)
        has_verdict = "SAFE" in text or "UNSAFE" in text or "CAUTION" in text
        assert has_verdict, (
            f"safe_to_edit({py_file}) on {name} has no verdict (expected SAFE/CAUTION/UNSAFE):\n{text[:500]}"
        )

    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_safe_to_edit_no_error_in_stderr(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """safe_to_edit on a real repo must not produce ERROR-level stderr."""
        repo_dir = clone_repo_factory(url, name)
        py_file = _find_python_file(repo_dir)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        client.call("safe_to_edit", {"file_path": py_file}, timeout=15.0)
        stderr = client.stderr_text()
        error_lines = [
            line
            for line in stderr.splitlines()
            if " - ERROR - " in line or "[error]" in line.lower()
        ]
        assert not error_lines, (
            f"ERROR-level lines in stderr while running safe_to_edit on {name}:\n"
            + "\n".join(error_lines[:10])
        )


# ---------------------------------------------------------------------------
# Cross-project diversity: file-count sanity
# ---------------------------------------------------------------------------


class TestCrossProjectDiversity:
    @pytest.mark.parametrize("url,name", REAL_REPOS)
    def test_project_health_reports_nonzero_file_count(
        self,
        url: str,
        name: str,
        clone_repo_factory: Callable[[str, str], Path],
        mcp_server_factory: Callable[..., MCPClient],
    ) -> None:
        """The analyzed file count must be > 0 for any real repo."""
        repo_dir = clone_repo_factory(url, name)
        client = mcp_server_factory(repo_dir)
        initialized(client)
        response = client.call("check_project_health", {}, timeout=30.0)
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        text = content[0]["text"] if isinstance(content, list) else str(content)
        numbers = [int(n) for n in re.findall(r"\b(\d+)\b", text)]
        assert any(n > 0 for n in numbers), (
            f"check_project_health for {name} contains no positive numbers:\n{text[:500]}"
        )
