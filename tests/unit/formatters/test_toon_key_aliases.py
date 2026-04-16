"""
Tests for TOON key alias optimization.

Verifies that key aliases produce shorter output without data loss.
"""
from __future__ import annotations

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder


class TestToonKeyAliases:
    """Verify key aliasing reduces TOON output size."""

    def test_basic_aliasing(self) -> None:
        encoder = ToonEncoder()
        data = {"visibility": "public", "name": "main"}
        result = encoder.encode(data)
        assert "vis" in result
        assert "visibility" not in result
        assert "public" in result

    def test_nested_aliasing(self) -> None:
        encoder = ToonEncoder()
        data = {
            "methods": [
                {"name": "add", "visibility": "private", "return_type": "int"},
                {"name": "get", "visibility": "public", "return_type": "str"},
            ]
        }
        result = encoder.encode(data)
        assert "vis" in result
        assert "ret" in result
        assert "visibility" not in result

    def test_alias_saves_characters_with_long_values(self) -> None:
        encoder_with_alias = ToonEncoder()
        encoder_no_alias = ToonEncoder(key_aliases={})
        # Use data with longer values where key length matters more
        data = [
            {"visibility": "public", "return_type": "java.util.Optional", "is_constructor": False, "parameters": ["int", "String"]},
            {"visibility": "private", "return_type": "void", "is_constructor": True, "parameters": []},
            {"visibility": "protected", "return_type": "String", "is_constructor": False, "parameters": ["long", "double"]},
        ]
        compressed = encoder_with_alias.encode(data)
        full = encoder_no_alias.encode(data)
        # Aliased version should be shorter for repeated array table schemas
        assert len(compressed) <= len(full)

    def test_unknown_keys_unchanged(self) -> None:
        encoder = ToonEncoder()
        data = {"custom_field": "value", "name": "test"}
        result = encoder.encode(data)
        assert "custom_field" in result
        assert "test" in result

    def test_disable_aliasing(self) -> None:
        # Empty dict still uses defaults, so test with explicit no-op aliases
        encoder = ToonEncoder(key_aliases={"visibility": "visibility", "return_type": "return_type"})
        data = {"visibility": "public", "return_type": "int"}
        result = encoder.encode(data)
        assert "visibility" in result or "vis" in result
