"""Regression tests for Issue #768 — Ruby default-valued parameters mangled.

`permissions = []` was extracting as name='[]', type='permissions =' because
`_process_type_prefix_parameter` used rfind(" ") and treated the last
word as the name. Fix: add Ruby to TYPE_SUFFIX_LANGUAGES and strip `= default`
in `_process_type_suffix_parameter`.
"""

import pytest

from tree_sitter_analyzer.cli.commands.table_command_helpers import (
    TYPE_SUFFIX_LANGUAGES,
    _process_single_parameter,
)

pytestmark = pytest.mark.unit


class TestRubyInTypeSuffixLanguages:
    """Ruby must route through the suffix (name-first) path — tracked: #768."""

    def test_ruby_in_type_suffix_languages(self):
        assert "ruby" in TYPE_SUFFIX_LANGUAGES, (
            "'ruby' must be in TYPE_SUFFIX_LANGUAGES so default-valued "
            "params are not garbled by the type-prefix rfind path"
        )


class TestRubyDefaultValuedParameters:
    """Default-valued Ruby params must extract the name, not the default literal."""

    def test_array_default(self):
        """permissions = [] → name='permissions', not '[]'."""
        result = _process_single_parameter("permissions = []", "ruby")
        assert result["name"] == "permissions", (
            f"Expected name='permissions' but got name='{result['name']}' — "
            "the default literal [] must not be the name"
        )

    def test_hash_default(self):
        """opts = {} → name='opts'."""
        result = _process_single_parameter("opts = {}", "ruby")
        assert result["name"] == "opts"

    def test_string_default(self):
        """role = 'admin' → name='role'."""
        result = _process_single_parameter("role = 'admin'", "ruby")
        assert result["name"] == "role"

    def test_integer_default(self):
        """limit = 10 → name='limit'."""
        result = _process_single_parameter("limit = 10", "ruby")
        assert result["name"] == "limit"

    def test_nil_default(self):
        """options = nil → name='options'."""
        result = _process_single_parameter("options = nil", "ruby")
        assert result["name"] == "options"

    def test_no_default_unchanged(self):
        """Bare params without defaults must still extract correctly."""
        result = _process_single_parameter("username", "ruby")
        assert result["name"] == "username"
        assert result["type"] == "Any"

    def test_splat_param(self):
        """*args → name='*args', type='Any' (no mangling)."""
        result = _process_single_parameter("*args", "ruby")
        assert result["name"] == "*args"

    def test_double_splat_param(self):
        """**kwargs → name='**kwargs', type='Any'."""
        result = _process_single_parameter("**kwargs", "ruby")
        assert result["name"] == "**kwargs"

    def test_type_not_garbled(self):
        """Type must be 'Any' (Ruby has no type annotations)."""
        result = _process_single_parameter("permissions = []", "ruby")
        assert result["type"] == "Any", (
            f"Expected type='Any' but got type='{result['type']}' — "
            "the fragment 'permissions =' must not become the type"
        )
