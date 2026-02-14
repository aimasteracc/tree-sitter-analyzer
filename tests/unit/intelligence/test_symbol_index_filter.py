"""Tests for SymbolIndex.lookup_references file_filter parameter."""

from __future__ import annotations

from tree_sitter_analyzer.intelligence.models import SymbolReference
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex


class TestLookupReferencesFileFilter:
    """lookup_references must support an optional file_filter callable."""

    def _make_index(self) -> SymbolIndex:
        si = SymbolIndex()
        si.add_reference(SymbolReference("foo", "src/core.py", 10, "call"))
        si.add_reference(SymbolReference("foo", "tests/test_core.py", 20, "call"))
        si.add_reference(SymbolReference("foo", "tests/test_utils.py", 30, "import"))
        si.add_reference(SymbolReference("bar", "src/utils.py", 5, "call"))
        return si

    def test_no_filter_returns_all(self):
        si = self._make_index()
        refs = si.lookup_references("foo")
        assert len(refs) == 3

    def test_filter_to_test_files(self):
        si = self._make_index()
        refs = si.lookup_references("foo", file_filter=lambda f: f.startswith("tests/"))
        assert len(refs) == 2
        assert all(r.file_path.startswith("tests/") for r in refs)

    def test_filter_to_source_files(self):
        si = self._make_index()
        refs = si.lookup_references("foo", file_filter=lambda f: f.startswith("src/"))
        assert len(refs) == 1
        assert refs[0].file_path == "src/core.py"

    def test_filter_combined_with_ref_type(self):
        si = self._make_index()
        refs = si.lookup_references(
            "foo", ref_type="call", file_filter=lambda f: f.startswith("tests/")
        )
        assert len(refs) == 1
        assert refs[0].file_path == "tests/test_core.py"

    def test_filter_no_matches(self):
        si = self._make_index()
        refs = si.lookup_references("bar", file_filter=lambda f: f.startswith("tests/"))
        assert len(refs) == 0
