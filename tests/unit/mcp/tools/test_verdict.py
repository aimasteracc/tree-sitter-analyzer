"""Tests for tree_sitter_analyzer.mcp.tools._verdict.

Pins the canonical verdict vocabulary, alias table, and the
_canonicalize_verdict normalisation function extracted from base_tool.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools._verdict import (
    _LEGAL_VERDICTS,
    _VERDICT_ALIASES,
    _canonicalize_verdict,
)


class TestLegalVerdicts:
    """The vocabulary itself is part of the public contract."""

    def test_is_frozenset(self) -> None:
        assert isinstance(_LEGAL_VERDICTS, frozenset)

    def test_exact_membership(self) -> None:
        assert _LEGAL_VERDICTS == {
            "SAFE",
            "CAUTION",
            "REVIEW",
            "UNSAFE",
            "INFO",
            "WARN",
            "ERROR",
            "NOT_FOUND",
        }

    def test_all_uppercase(self) -> None:
        for v in _LEGAL_VERDICTS:
            assert v == v.upper(), f"{v!r} must be UPPER_SNAKE"


class TestVerdictAliases:
    """Alias table maps historical drift values to canonical replacements."""

    def test_is_dict(self) -> None:
        assert isinstance(_VERDICT_ALIASES, dict)

    def test_all_values_are_canonical(self) -> None:
        for alias, canonical in _VERDICT_ALIASES.items():
            assert canonical in _LEGAL_VERDICTS, (
                f"alias {alias!r} maps to non-canonical {canonical!r}"
            )

    def test_known_aliases_present(self) -> None:
        assert _VERDICT_ALIASES.get("") == "INFO"
        assert _VERDICT_ALIASES.get("n/a") == "INFO"
        assert _VERDICT_ALIASES.get("na") == "INFO"
        assert _VERDICT_ALIASES.get("success") == "INFO"
        assert _VERDICT_ALIASES.get("clean") == "SAFE"
        assert _VERDICT_ALIASES.get("ok") == "SAFE"
        assert _VERDICT_ALIASES.get("warning") == "WARN"


class TestCanonicalize:
    """_canonicalize_verdict always returns a member of _LEGAL_VERDICTS."""

    @pytest.mark.parametrize("verdict", sorted(_LEGAL_VERDICTS))
    def test_legal_verdict_passes_through_unchanged(self, verdict: str) -> None:
        assert _canonicalize_verdict(verdict) == verdict

    def test_none_returns_info(self) -> None:
        assert _canonicalize_verdict(None) == "INFO"

    def test_empty_string_returns_info(self) -> None:
        assert _canonicalize_verdict("") == "INFO"

    def test_na_returns_info(self) -> None:
        assert _canonicalize_verdict("n/a") == "INFO"
        assert _canonicalize_verdict("na") == "INFO"

    def test_success_returns_info(self) -> None:
        assert _canonicalize_verdict("success") == "INFO"

    def test_clean_returns_safe(self) -> None:
        assert _canonicalize_verdict("clean") == "SAFE"
        assert _canonicalize_verdict("CLEAN") == "SAFE"

    def test_ok_returns_safe(self) -> None:
        assert _canonicalize_verdict("ok") == "SAFE"
        assert _canonicalize_verdict("OK") == "SAFE"

    def test_warning_returns_warn(self) -> None:
        assert _canonicalize_verdict("warning") == "WARN"

    def test_unknown_string_returns_info(self) -> None:
        assert _canonicalize_verdict("UNKNOWN_VERDICT_XYZ") == "INFO"

    def test_non_string_returns_info(self) -> None:
        # Defensive path: non-str types fall back to INFO without raising.
        assert _canonicalize_verdict(42) == "INFO"  # type: ignore[arg-type]
        assert _canonicalize_verdict(True) == "INFO"  # type: ignore[arg-type]

    def test_return_value_is_always_legal(self) -> None:
        """Fuzz over alias keys + garbage and verify every result is legal."""
        inputs = list(_VERDICT_ALIASES.keys()) + [
            None,
            "",
            "garbage",
            "GARBAGE",
            42,
            False,
        ]
        for inp in inputs:
            result = _canonicalize_verdict(inp)  # type: ignore[arg-type]
            assert result in _LEGAL_VERDICTS, (
                f"_canonicalize_verdict({inp!r}) = {result!r} is not legal"
            )
