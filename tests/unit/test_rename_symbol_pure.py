"""Unit tests for pure utility functions in rename_symbol.py.

These tests exercise the stateless, file-IO-free helpers directly,
proving the rename engine's core logic without any ASTCache instance.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.rename_symbol import (
    RenameResult,
    RenameSite,
    _apply_rename_to_file,
    _collect_rename_sites_from_resolver,
    _deduplicate_sites,
    _find_identifier_at_or_near,
    _group_sites_by_file,
    _is_word_boundary,
    _scan_line_for_name,
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
# _is_word_boundary
# ---------------------------------------------------------------------------


class TestIsWordBoundary:
    def test_position_before_text(self):
        assert _is_word_boundary("foo", -1) is True

    def test_position_after_text(self):
        assert _is_word_boundary("foo", 3) is True

    def test_space_is_boundary(self):
        assert _is_word_boundary("foo bar", 3) is True  # space at index 3

    def test_dot_is_boundary(self):
        assert _is_word_boundary("a.b", 1) is True  # '.'

    def test_underscore_is_not_boundary(self):
        assert _is_word_boundary("a_b", 1) is False  # '_'

    def test_alpha_is_not_boundary(self):
        assert _is_word_boundary("abc", 1) is False

    def test_digit_is_not_boundary(self):
        assert _is_word_boundary("a1b", 1) is False


# ---------------------------------------------------------------------------
# _scan_line_for_name
# ---------------------------------------------------------------------------


class TestScanLineForName:
    def test_single_match(self):
        positions = _scan_line_for_name("x = foo()", "foo")
        assert positions == [4]

    def test_no_match(self):
        assert _scan_line_for_name("bar = baz()", "foo") == []

    def test_prefix_not_matched(self):
        # "foobar" — "foo" is a prefix but not a standalone word
        assert _scan_line_for_name("foobar = 1", "foo") == []

    def test_suffix_not_matched(self):
        assert _scan_line_for_name("myfoo = 1", "foo") == []

    def test_multiple_occurrences(self):
        positions = _scan_line_for_name("foo + foo", "foo")
        assert positions == [0, 6]

    def test_dot_access_counts_as_boundary(self):
        # "obj.foo" — dot is a word boundary so "foo" at pos 4 is matched
        positions = _scan_line_for_name("obj.foo", "foo")
        assert 4 in positions

    def test_empty_line(self):
        assert _scan_line_for_name("", "foo") == []


# ---------------------------------------------------------------------------
# _find_identifier_at_or_near
# ---------------------------------------------------------------------------


class TestFindIdentifierAtOrNear:
    def test_exact_column(self):
        # "def foo()" — "foo" starts at col 4
        col = _find_identifier_at_or_near("def foo():", 4, "foo")
        assert col == 4

    def test_near_column(self):
        # column given is 2 (inside "def"), but "foo" starts at 4
        col = _find_identifier_at_or_near("def foo():", 2, "foo")
        assert col == 4

    def test_not_found(self):
        col = _find_identifier_at_or_near("def bar():", 4, "foo")
        assert col is None

    def test_prefix_not_matched(self):
        # "foobar" — should not match "foo"
        col = _find_identifier_at_or_near("foobar = 1", 0, "foo")
        assert col is None


# ---------------------------------------------------------------------------
# _deduplicate_sites
# ---------------------------------------------------------------------------


class TestDeduplicateSites:
    def _make_site(self, file: str, line: int, col: int) -> RenameSite:
        return RenameSite(
            file=file, line=line, column=col, old_text="x", site_type="ref"
        )

    def test_no_duplicates(self):
        sites = [self._make_site("a.py", 1, 0), self._make_site("a.py", 2, 0)]
        assert len(_deduplicate_sites(sites)) == 2

    def test_exact_duplicate_removed(self):
        s1 = self._make_site("a.py", 1, 0)
        s2 = self._make_site("a.py", 1, 0)
        result = _deduplicate_sites([s1, s2])
        assert len(result) == 1

    def test_different_file_not_deduped(self):
        s1 = self._make_site("a.py", 1, 0)
        s2 = self._make_site("b.py", 1, 0)
        result = _deduplicate_sites([s1, s2])
        assert len(result) == 2

    def test_preserves_order_first_wins(self):
        s1 = RenameSite(
            file="a.py", line=1, column=0, old_text="foo", site_type="definition"
        )
        s2 = RenameSite(
            file="a.py", line=1, column=0, old_text="foo", site_type="reference"
        )
        result = _deduplicate_sites([s1, s2])
        assert result[0].site_type == "definition"

    def test_empty_input(self):
        assert _deduplicate_sites([]) == []


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

    def test_line_zero_site_scans_for_name(self, tmp_path):
        """A site with line=0 should fall back to scanning the first line."""
        f = tmp_path / "zero_line.py"
        f.write_text("foo = 1\n")
        # column=-1 and line=0 triggers the fallback scan branch
        site = RenameSite(
            file=str(f), line=0, column=-1, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site], "foo", "bar")
        assert ok is True
        assert "bar" in f.read_text()

    def test_site_with_negative_column_triggers_fallback(self, tmp_path):
        """A site with column<0 on a real line triggers _scan_line_for_name fallback."""
        f = tmp_path / "neg_col.py"
        f.write_text("x = foo\n")
        site = RenameSite(
            file=str(f), line=1, column=-1, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site], "foo", "baz")
        assert ok is True
        assert "baz" in f.read_text()

    def test_out_of_range_line_skipped(self, tmp_path):
        """A site pointing to a line beyond file length is silently skipped."""
        f = tmp_path / "short.py"
        f.write_text("foo = 1\n")
        site = RenameSite(
            file=str(f), line=999, column=0, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site], "foo", "bar")
        assert ok is True
        # File should be unchanged (site skipped)
        assert "foo" in f.read_text()

    def test_col_beyond_line_length_not_renamed(self, tmp_path):
        """A column beyond the line length does not raise, just skips."""
        f = tmp_path / "short_line.py"
        f.write_text("x\n")
        site = RenameSite(
            file=str(f), line=1, column=50, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site], "foo", "bar")
        assert ok is True

    def test_candidate_mismatch_not_renamed(self, tmp_path):
        """When text at given column doesn't match old_name, nothing is renamed."""
        # "xyz = foo" — site points to col 0 (where "xyz" is), not where "foo" is
        f = tmp_path / "mismatch.py"
        f.write_text("xyz = foo\n")
        site = RenameSite(
            file=str(f), line=1, column=0, old_text="foo", site_type="reference"
        )
        ok = _apply_rename_to_file(str(f), [site], "foo", "bar")
        assert ok is True
        # candidate at col 0 is "xyz", not "foo", so neither occurrence is renamed
        content = f.read_text()
        assert "foo" in content  # unchanged

    def test_write_failure_returns_false(self, tmp_path):
        """OSError on write returns False."""
        f = tmp_path / "read_only.py"
        f.write_text("foo = 1\n")
        site = RenameSite(
            file=str(f), line=1, column=0, old_text="foo", site_type="definition"
        )
        with patch("builtins.open", side_effect=[open(f), OSError("disk full")]):
            ok = _apply_rename_to_file(str(f), [site], "foo", "bar")
        assert ok is False


# ---------------------------------------------------------------------------
# _collect_rename_sites_from_resolver (mock resolve_result)
# ---------------------------------------------------------------------------


class TestCollectRenameSitesFromResolver:
    def _make_resolve(self, definitions=(), references=()):
        return SimpleNamespace(
            definitions=list(definitions), references=list(references)
        )

    def _make_defn(self, file: str, line: int):
        return SimpleNamespace(file=file, line=line)

    def _make_ref(self, file: str, line: int, reference_type: str = "call"):
        return SimpleNamespace(file=file, line=line, reference_type=reference_type)

    def test_empty_resolve_result(self, tmp_path):
        resolve = self._make_resolve()
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []

    def test_definition_collected(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("def foo():\n    pass\n")
        defn = self._make_defn(str(f), 1)
        resolve = self._make_resolve(definitions=[defn])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert any(s.site_type == "definition" for s in sites)
        assert any(s.old_text == "foo" for s in sites)

    def test_reference_collected(self, tmp_path):
        f = tmp_path / "b.py"
        f.write_text("result = foo()\n")
        ref = self._make_ref(str(f), 1, "call")
        resolve = self._make_resolve(references=[ref])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert any(s.site_type == "call" for s in sites)

    def test_missing_file_skipped(self, tmp_path):
        defn = self._make_defn(str(tmp_path / "missing.py"), 1)
        resolve = self._make_resolve(definitions=[defn])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []

    def test_reference_line_zero_added_with_zero_coords(self, tmp_path):
        """References with line=0 are added with line=0, col=0."""
        f = tmp_path / "ref.py"
        f.write_text("import foo\n")
        ref = self._make_ref(str(f), 0, "import")
        resolve = self._make_resolve(references=[ref])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert len(sites) == 1
        assert sites[0].line == 0
        assert sites[0].column == 0

    def test_definition_ioerror_skipped(self, tmp_path):
        """OSError when reading definition file is silently skipped."""
        f = tmp_path / "broken.py"
        f.write_text("def foo(): pass\n")
        defn = self._make_defn(str(f), 1)
        resolve = self._make_resolve(definitions=[defn])
        with patch("builtins.open", side_effect=OSError("perm denied")):
            sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []

    def test_reference_ioerror_skipped(self, tmp_path):
        """OSError when reading reference file is silently skipped."""
        f = tmp_path / "broken_ref.py"
        f.write_text("foo()\n")
        ref = self._make_ref(str(f), 1, "call")
        resolve = self._make_resolve(references=[ref])
        with patch("builtins.open", side_effect=OSError("perm denied")):
            sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []

    def test_definition_line_out_of_range(self, tmp_path):
        """Definition line beyond file length adds no sites."""
        f = tmp_path / "short.py"
        f.write_text("foo = 1\n")
        defn = self._make_defn(str(f), 999)
        resolve = self._make_resolve(definitions=[defn])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []

    def test_reference_line_out_of_range(self, tmp_path):
        """Reference line beyond file length adds no sites."""
        f = tmp_path / "short_ref.py"
        f.write_text("foo = 1\n")
        ref = self._make_ref(str(f), 999, "call")
        resolve = self._make_resolve(references=[ref])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []

    def test_missing_reference_file_skipped(self, tmp_path):
        """Non-existent reference file is silently skipped."""
        ref = self._make_ref(str(tmp_path / "missing_ref.py"), 1, "call")
        resolve = self._make_resolve(references=[ref])
        sites = _collect_rename_sites_from_resolver(resolve, "foo", str(tmp_path))
        assert sites == []


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
        assert len(result.sites) > 0
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
        assert len(result.errors) > 0
        # Rollback should restore original content
        assert f.read_text() == original
