#!/usr/bin/env python3
"""N7 (round-28): file_health smell parity + ``security:`` prefix normalization.

Reproduces the round-28 dogfood bugs:

* ``file_health.code_smells`` was missing ``mutable_default_argument``
  (and other anti-pattern findings) that ``code_patterns.results``
  surfaced on the same file.
* ``file_health`` emitted ``type='security:eval_usage'`` while
  ``code_patterns`` emitted ``type='eval_usage'`` — same rule, different
  string, forcing agents to branch on both.

The fix:

* ``detect_code_smells`` now invokes the shared ``detect_anti_patterns``
  helper, so file_health sees ``mutable_default_argument`` /
  ``bare_except`` / ``print_in_production`` like code_patterns does.
* Security smells are emitted with the bare type name. The legacy
  ``security:`` prefix is stripped via ``canonical_smell_type`` whenever
  ``type`` is projected.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.code_patterns_tool import CodePatternsTool
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool


def _run(coro: Any) -> Any:
    """Run an async coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def smelly_python_file(tmp_path: Path) -> Path:
    """Python file mixing security + anti-pattern + smell signals.

    Mirrors the round-28 reproducer file shape:

    * eval_usage (security)
    * mutable_default_argument (anti-pattern)
    * bare_except (anti-pattern AND security)
    """
    src = tmp_path / "smelly.py"
    src.write_text(
        "def f(x=[]):  # mutable default — anti-pattern\n"
        "    try:\n"
        "        result = eval(x)  # security: eval_usage\n"
        "    except:  # bare_except — both anti-pattern and security\n"
        "        result = None\n"
        "    return result\n",
        encoding="utf-8",
    )
    return src


class TestN7FileHealthSmellParity:
    """file_health.code_smells matches code_patterns.results."""

    def test_file_health_includes_mutable_default(
        self, tmp_path: Path, smelly_python_file: Path
    ) -> None:
        """file_health should now surface the mutable_default_argument
        finding that code_patterns has been catching all along."""
        tool = FileHealthTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "file_path": smelly_python_file.name,
                    "language": "python",
                    "output_format": "json",
                }
            )
        )
        smell_types = {smell["type"] for smell in result["code_smells"]}
        assert "mutable_default_argument" in smell_types, (
            f"N7: file_health.code_smells must include mutable_default_argument "
            f"— got types={sorted(smell_types)!r}"
        )

    def test_smell_type_no_security_prefix(
        self, tmp_path: Path, smelly_python_file: Path
    ) -> None:
        """No code_smells[].type should carry the legacy ``security:`` prefix."""
        tool = FileHealthTool(str(tmp_path))
        result = _run(
            tool.execute(
                {
                    "file_path": smelly_python_file.name,
                    "language": "python",
                    "output_format": "json",
                }
            )
        )
        smell_types = {smell["type"] for smell in result["code_smells"]}
        prefixed = {
            t for t in smell_types if isinstance(t, str) and t.startswith("security:")
        }
        assert not prefixed, (
            f"N7: file_health.code_smells[].type must not carry the legacy "
            f"``security:`` prefix — got {sorted(prefixed)!r}"
        )
        # And specifically — the rule that exposed the bug:
        assert "bare_except" in smell_types, (
            f"N7: file_health must surface bare_except WITHOUT a prefix — "
            f"got types={sorted(smell_types)!r}"
        )
        assert "security:bare_except" not in smell_types

    def test_file_health_and_code_patterns_smell_types_agree(
        self, tmp_path: Path, smelly_python_file: Path
    ) -> None:
        """The N7 contract: both tools see the same smell type strings.

        Set comparison (not order or count) — file_health groups some
        findings under one category while code_patterns spreads them
        across smells / security / anti_patterns. What matters is the
        canonical type *names* match on the same input.
        """
        fh_tool = FileHealthTool(str(tmp_path))
        fh_result = _run(
            fh_tool.execute(
                {
                    "file_path": smelly_python_file.name,
                    "language": "python",
                    "output_format": "json",
                }
            )
        )
        cp_tool = CodePatternsTool(str(tmp_path))
        cp_result = _run(
            cp_tool.execute(
                {
                    "file_path": smelly_python_file.name,
                    "output_format": "json",
                }
            )
        )
        fh_types = {smell["type"] for smell in fh_result["code_smells"]}
        cp_types = {r["type"] for r in cp_result["results"]}
        # Anti-patterns + security must overlap.
        shared_expected = {
            "mutable_default_argument",
            "eval_usage",
            "bare_except",
        }
        assert shared_expected <= fh_types, (
            f"N7: file_health missing canonical smell names — "
            f"expected ⊇ {shared_expected}, got {fh_types!r}"
        )
        assert shared_expected <= cp_types, (
            f"N7: code_patterns missing canonical smell names — "
            f"expected ⊇ {shared_expected}, got {cp_types!r}"
        )
        # The two surfaces agree on each of these names.
        for name in shared_expected:
            assert name in fh_types and name in cp_types, (
                f"N7: smell '{name}' must appear in BOTH tools — "
                f"file_health={fh_types!r}, code_patterns={cp_types!r}"
            )


class TestN7CanonicalSmellTypeHelper:
    """Unit-level checks for the shared normalization helper."""

    def test_strips_security_prefix(self) -> None:
        from tree_sitter_analyzer.mcp.tools.utils.file_health_smells import (
            canonical_smell_type,
        )

        assert canonical_smell_type({"smell": "security:eval_usage"}) == "eval_usage"
        assert canonical_smell_type({"type": "security:bare_except"}) == "bare_except"

    def test_passthrough_for_bare_names(self) -> None:
        from tree_sitter_analyzer.mcp.tools.utils.file_health_smells import (
            canonical_smell_type,
        )

        assert canonical_smell_type({"smell": "long_method"}) == "long_method"
        assert canonical_smell_type({"smell": "mutable_default_argument"}) == (
            "mutable_default_argument"
        )

    def test_unknown_smell_returns_string(self) -> None:
        from tree_sitter_analyzer.mcp.tools.utils.file_health_smells import (
            canonical_smell_type,
        )

        assert canonical_smell_type({}) == "unknown"
