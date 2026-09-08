"""Unit tests for pure utility functions in rename_symbol.py.

These tests exercise the stateless, file-IO-free helpers directly,
proving the rename engine's core logic without any ASTCache instance.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.rename_symbol import (
    RenameResult,
    RenameSite,
    _apply_rename_to_file,
    _group_sites_by_file,
    rename_symbol,
)

# ---------------------------------------------------------------------------
# RenameSite.to_dict
# ---------------------------------------------------------------------------


class TestRenameSiteToDict:
    def test_to_dict_returns_all_fields(self):
        site = RenameSite(
            file="a.py", line=10, column=5, old_text="foo", site_type="definition"
        )
        d = site.to_dict()
        assert d["file"] == "a.py"
        assert d["line"] == 10
        assert d["column"] == 5
        assert d["old_text"] == "foo"
        assert d["site_type"] == "definition"


# ---------------------------------------------------------------------------
# RenameResult.to_dict
# ---------------------------------------------------------------------------


class TestRenameResultToDict:
    def test_to_dict_includes_sites(self):
        site = RenameSite(
            file="b.py", line=1, column=0, old_text="bar", site_type="reference"
        )
        result = RenameResult(symbol="bar", new_name="baz", dry_run=True, sites=[site])
        d = result.to_dict()
        assert d["symbol"] == "bar"
        assert d["new_name"] == "baz"
        assert d["dry_run"] is True
        assert len(d["sites"]) == 1
        assert d["sites"][0]["old_text"] == "bar"

    def test_to_dict_empty_sites(self):
        result = RenameResult(symbol="x", new_name="y", dry_run=False)
        d = result.to_dict()
        assert d["sites"] == []
        assert d["errors"] == []
        assert d["files_changed"] == 0
        assert d["sites_renamed"] == 0


# ---------------------------------------------------------------------------
# _group_sites_by_file
# ---------------------------------------------------------------------------


class TestGroupSitesByFile:
    def _make_site(self, file: str) -> RenameSite:
        return RenameSite(file=file, line=1, column=0, old_text="x", site_type="ref")

    def test_single_file(self):
        sites = [self._make_site("a.py"), self._make_site("a.py")]
        groups = _group_sites_by_file(sites)
        assert list(groups.keys()) == ["a.py"]
        assert len(groups["a.py"]) == 2

    def test_multiple_files(self):
        sites = [
            self._make_site("a.py"),
            self._make_site("b.py"),
            self._make_site("a.py"),
        ]
        groups = _group_sites_by_file(sites)
        assert len(groups["a.py"]) == 2
        assert len(groups["b.py"]) == 1

    def test_empty(self):
        assert _group_sites_by_file([]) == {}


# ---------------------------------------------------------------------------
# _apply_rename_to_file  (requires real temp file)
# ---------------------------------------------------------------------------


class TestApplyRenameToFile:
    def test_simple_rename(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return foo()\n")
        site1 = RenameSite(
            file=str(f), line=1, column=4, old_text="foo", site_type="definition"
        )
        site2 = RenameSite(
            file=str(f), line=2, column=11, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site1, site2], "foo", "bar")
        assert ok is True
        content = f.read_text()
        assert "bar" in content
        assert "foo" not in content

    def test_missing_file_returns_false(self, tmp_path):
        missing = str(tmp_path / "nonexistent.py")
        site = RenameSite(file=missing, line=1, column=0, old_text="x", site_type="ref")
        ok = _apply_rename_to_file(missing, [site], "x", "y")
        assert ok is False

    def test_no_sites_leaves_file_unchanged(self, tmp_path):
        f = tmp_path / "unchanged.py"
        f.write_text("x = 1\n")
        ok = _apply_rename_to_file(str(f), [], "x", "y")
        assert ok is True
        assert f.read_text() == "x = 1\n"

    def test_word_boundary_respected(self, tmp_path):
        # "foobar" should not be renamed when target is "foo"
        f = tmp_path / "boundary.py"
        f.write_text("foobar = foo\n")
        site = RenameSite(
            file=str(f), line=1, column=9, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site], "foo", "baz")
        assert ok is True
        content = f.read_text()
        # foobar should remain unchanged, only standalone foo renamed
        assert "foobar" in content
        assert "baz" in content

    def test_unknown_positions_are_rejected(self, tmp_path):
        """未知坐标不能触发文本扫描替换。"""
        f = tmp_path / "unknown.py"
        original = b"foo = 1\n"
        f.write_bytes(original)
        for line, column in [(0, -1), (1, -1), (999, 0), (1, 50), (1, 1)]:
            site = RenameSite(str(f), line, column, "foo", "reference")
            assert _apply_rename_to_file(str(f), [site], "foo", "bar") is False
            assert f.read_bytes() == original

    def test_write_failure_returns_false(self, tmp_path):
        """写入异常必须上报失败。"""
        f = tmp_path / "read_only.py"
        f.write_bytes(b"foo = 1\n")
        site = RenameSite(str(f), 1, 0, "foo", "definition")
        with patch("pathlib.Path.write_bytes", side_effect=OSError("disk full")):
            assert _apply_rename_to_file(str(f), [site], "foo", "bar") is False


# ---------------------------------------------------------------------------
# rename_symbol  (integration: mock SymbolResolver)
# ---------------------------------------------------------------------------


def _make_mock_cache(project_root: str) -> MagicMock:
    cache = MagicMock()
    cache.project_root = project_root
    return cache


def _make_mock_resolver(definitions=(), references=()):
    resolve_result = SimpleNamespace(
        definitions=list(definitions), references=list(references)
    )
    resolver = MagicMock()
    resolver.find_references.return_value = resolve_result
    return resolver


class TestRenameSymbol:
    def test_dry_run_no_sites_returns_empty_result(self, tmp_path):
        cache = _make_mock_cache(str(tmp_path))
        resolver = _make_mock_resolver()
        with patch(
            "tree_sitter_analyzer.symbol_resolver.SymbolResolver", return_value=resolver
        ):
            result = rename_symbol(cache, "foo", "bar", dry_run=True)
        assert result.symbol == "foo"
        assert result.new_name == "bar"
        assert result.dry_run is True
        assert result.sites == []
        assert result.files_changed == 0

    def test_dry_run_with_sites_does_not_write(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo(): pass\n")
        cache = _make_mock_cache(str(tmp_path))
        defn = SimpleNamespace(file=str(f), line=1)
        resolver = _make_mock_resolver(definitions=[defn])
        with patch(
            "tree_sitter_analyzer.symbol_resolver.SymbolResolver", return_value=resolver
        ):
            result = rename_symbol(cache, "foo", "bar", dry_run=True)
        # File unchanged
        assert "foo" in f.read_text()
        assert result.sites
        assert result.files_changed == 0

    def test_live_rename_writes_file(self, tmp_path):
        f = tmp_path / "target.py"
        f.write_text("def foo(): pass\n")
        cache = _make_mock_cache(str(tmp_path))
        defn = SimpleNamespace(file=str(f), line=1)
        resolver = _make_mock_resolver(definitions=[defn])
        with patch(
            "tree_sitter_analyzer.symbol_resolver.SymbolResolver", return_value=resolver
        ):
            result = rename_symbol(cache, "foo", "bar", dry_run=False)
        assert result.files_changed == 1
        assert "bar" in f.read_text()

    def test_live_rename_rollback_on_write_error(self, tmp_path):
        f = tmp_path / "rollback.py"
        original = "def foo(): pass\n"
        f.write_text(original)
        cache = _make_mock_cache(str(tmp_path))
        defn = SimpleNamespace(file=str(f), line=1)
        resolver = _make_mock_resolver(definitions=[defn])
        with patch(
            "tree_sitter_analyzer.symbol_resolver.SymbolResolver", return_value=resolver
        ):
            with patch(
                "tree_sitter_analyzer.rename_symbol._apply_rename_to_file",
                return_value=False,
            ):
                result = rename_symbol(cache, "foo", "bar", dry_run=False)
        assert result.errors
        # Rollback should restore original content
        assert f.read_text() == original


@pytest.mark.parametrize(
    "source, new_name, error",
    [
        ("def foo(): pass\n", "class", "identifiers"),
        ("foo = 1\n", "bar", "module-level"),
        ("def foo(): pass\ndef foo(): pass\n", "bar", "multiple definitions"),
        (
            "def foo[T](): pass\n",
            "bar",
            "Generic type parameter bindings are unsupported"
            if sys.version_info >= (3, 12)
            else "invalid syntax",
        ),
        ("def foo(): pass\nmatch {}:\n    case {**bar}: pass\n", "bar", "Pattern"),
        ("def foo(): pass\nfrom a import foo\n", "bar", "Ambiguous import binding"),
        ("def foo(): pass\ndef other():\n    global foo\n", "bar", "Global/nonlocal"),
        (
            "def foo(): pass\ndef other():\n    def foo(): pass\n",
            "bar",
            "shadowed definition",
        ),
        ("def foo(): pass\nimport bar\n", "bar", "import binding"),
        (
            "def foo(): pass\ntry: pass\nexcept Exception as bar: pass\n",
            "bar",
            "exception binding",
        ),
        ("def \uff46\uff4f\uff4f(): pass\n", "bar", "exact identifier"),
    ],
)
def test_unsupported_engine_bindings_preserve_bytes(tmp_path, source, new_name, error):
    path = tmp_path / "a.py"
    original = source.encode()
    path.write_bytes(original)
    result = rename_symbol(
        _make_mock_cache(str(tmp_path)), "foo", new_name, dry_run=False
    )
    assert len(result.errors) == 1
    if error:
        assert error in result.errors[0]
    assert result.files_changed == 0
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "other_source, succeeds", [(b"foo();", False), (b"other();", True)]
)
def test_other_language_possible_reference_is_checked(tmp_path, other_source, succeeds):
    source = tmp_path / "a.py"
    source.write_bytes(b"def foo(): pass\n")
    other = tmp_path / "b.js"
    other.write_bytes(other_source)
    result = rename_symbol(_make_mock_cache(str(tmp_path)), "foo", "bar", dry_run=False)
    assert (result.errors == []) is succeeds
    assert source.read_bytes() == (
        b"def bar(): pass\n" if succeeds else b"def foo(): pass\n"
    )
    assert other.read_bytes() == other_source


def test_outside_root_source_is_rejected(tmp_path):
    source = tmp_path / "outside.py"
    original = b"def foo(): pass\n"
    source.write_bytes(original)
    root = tmp_path / "project"
    root.mkdir()
    with patch(
        "tree_sitter_analyzer.ast_cache._walk_source_files",
        return_value=iter([str(source)]),
    ):
        result = rename_symbol(_make_mock_cache(str(root)), "foo", "bar", dry_run=False)
    assert result.errors == ["Source path is outside project root"]
    assert source.read_bytes() == original


def test_changed_source_is_not_overwritten(tmp_path):
    from tree_sitter_analyzer.rename_symbol import _render_rename

    source = tmp_path / "a.py"
    source.write_bytes(b"def foo(): pass\n")
    changed = b"def foo(): return 42\n"

    def edit_after_plan(*args):
        rendered = _render_rename(*args)
        source.write_bytes(changed)
        return rendered

    with patch(
        "tree_sitter_analyzer.rename_symbol._render_rename", side_effect=edit_after_plan
    ):
        result = rename_symbol(
            _make_mock_cache(str(tmp_path)), "foo", "bar", dry_run=False
        )
    assert len(result.errors) == 1
    assert "Source changed during rename" in result.errors[0]
    assert source.read_bytes() == changed


def test_rollback_failure_is_reported(tmp_path):
    source = tmp_path / "a.py"
    original = b"def foo(): pass\n"
    source.write_bytes(original)
    with patch("pathlib.Path.write_bytes", side_effect=OSError("access denied")):
        result = rename_symbol(
            _make_mock_cache(str(tmp_path)), "foo", "bar", dry_run=False
        )
    assert len(result.errors) == 2
    assert "Failed to write" in result.errors[0]
    assert "Rollback failed" in result.errors[1]
    assert source.read_bytes() == original


def test_unrelated_import_and_annotation_remain_unchanged(tmp_path):
    source = tmp_path / "a.py"
    original = b'from typing import Any\ndef foo(x: Any) -> str: return "foo"\n'
    source.write_bytes(original)
    result = rename_symbol(_make_mock_cache(str(tmp_path)), "foo", "bar", dry_run=False)
    assert result.errors == []
    assert source.read_bytes() == original.replace(b"def foo", b"def bar")


def test_unicode_line_separator_in_literal_is_not_a_source_line(tmp_path):
    # 2026-09-08：字符串里的 Unicode 分隔符不能改变调用坐标。
    source = tmp_path / "a.py"
    original = 'def foo(x="a\u0085foo"): return x\nfoo()\n'.encode()
    source.write_bytes(original)
    result = rename_symbol(_make_mock_cache(str(tmp_path)), "foo", "bar", dry_run=False)
    assert result.errors == []
    assert source.read_bytes() == 'def bar(x="a\u0085foo"): return x\nbar()\n'.encode()
