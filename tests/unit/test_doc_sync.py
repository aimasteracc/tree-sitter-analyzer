"""Tests for doc_sync — documentation-code synchronization checker."""

import textwrap

from tree_sitter_analyzer.doc_sync import (
    DocRef,
    extract_file_refs,
    run_doc_sync,
    validate_file_refs,
)

# ---------------------------------------------------------------------------
# extract_file_refs
# ---------------------------------------------------------------------------


class TestExtractFileRefs:
    def test_backtick_py_file(self):
        content = "See `tree_sitter_analyzer/ast_cache.py` for details."
        refs = extract_file_refs(content, "docs/README.md")
        assert len(refs) == 1
        assert refs[0].path == "tree_sitter_analyzer/ast_cache.py"
        assert refs[0].line == 1
        assert refs[0].doc_file == "docs/README.md"

    def test_backtick_md_file(self):
        content = "See `docs/architecture.md` for the overview."
        refs = extract_file_refs(content, "docs/guide.md")
        assert len(refs) == 1
        assert refs[0].path == "docs/architecture.md"

    def test_markdown_link_target(self):
        content = "Read [ast cache](tree_sitter_analyzer/ast_cache.py) for details."
        refs = extract_file_refs(content, "docs/README.md")
        assert len(refs) == 1
        assert refs[0].path == "tree_sitter_analyzer/ast_cache.py"

    def test_skips_glob_patterns(self):
        content = "All formatters: `formatters/*.py`"
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []

    def test_skips_http_links(self):
        content = "See [docs](https://github.com/foo/bar.py) for more."
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []

    def test_skips_anchor_links(self):
        content = "Go to [section](#some-section)"
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []

    def test_skips_plain_words(self):
        content = "The `json` format is supported."
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []

    def test_multiple_refs_on_same_line(self):
        content = "Files: `foo.py` and `bar.md` are important."
        refs = extract_file_refs(content, "docs/README.md")
        assert len(refs) == 2
        paths = {r.path for r in refs}
        assert paths == {"foo.py", "bar.md"}

    def test_line_numbers_are_accurate(self):
        content = "line one\nSee `path/to/file.py` here.\nline three"
        refs = extract_file_refs(content, "docs/README.md")
        assert len(refs) == 1
        assert refs[0].line == 2

    def test_shell_script_ref(self):
        content = "Run `scripts/codemap-sync-check.sh` first."
        refs = extract_file_refs(content, "docs/README.md")
        assert len(refs) == 1
        assert refs[0].path == "scripts/codemap-sync-check.sh"

    def test_skips_code_blocks(self):
        content = textwrap.dedent("""\
            Normal text.
            ```python
            import some/fake/path.py
            ```
            More text.
        """)
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []

    def test_path_without_extension_skipped(self):
        content = "Module `tree_sitter_analyzer` is the main package."
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []

    def test_path_with_slash_and_no_ext_skipped(self):
        content = "Directory `tree_sitter_analyzer/formatters/`"
        refs = extract_file_refs(content, "docs/README.md")
        assert refs == []


# ---------------------------------------------------------------------------
# validate_file_refs
# ---------------------------------------------------------------------------


class TestValidateFileRefs:
    def test_existing_file_no_stale(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main")
        refs = [DocRef("src/main.py", "docs/README.md", 1)]
        stale = validate_file_refs(refs, str(tmp_path))
        assert stale == []

    def test_missing_file_reported(self, tmp_path):
        refs = [DocRef("src/missing.py", "docs/README.md", 5)]
        stale = validate_file_refs(refs, str(tmp_path))
        assert len(stale) == 1
        assert stale[0].ref.path == "src/missing.py"
        assert stale[0].ref.line == 5
        assert stale[0].reason == "file_missing"

    def test_multiple_some_stale(self, tmp_path):
        (tmp_path / "exists.py").write_text("# ok")
        refs = [
            DocRef("exists.py", "docs/README.md", 1),
            DocRef("missing.py", "docs/README.md", 2),
        ]
        stale = validate_file_refs(refs, str(tmp_path))
        assert len(stale) == 1
        assert stale[0].ref.path == "missing.py"

    def test_empty_refs_returns_empty(self, tmp_path):
        assert validate_file_refs([], str(tmp_path)) == []


# ---------------------------------------------------------------------------
# run_doc_sync (integration)
# ---------------------------------------------------------------------------


class TestRunDocSync:
    def test_finds_stale_ref_in_doc(self, tmp_path):
        (tmp_path / "docs").mkdir()
        doc = tmp_path / "docs" / "guide.md"
        doc.write_text("See `src/real.py` and `src/ghost.py` for details.")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "real.py").write_text("# exists")

        result = run_doc_sync(str(tmp_path), doc_patterns=["docs/*.md"])

        assert result["success"] is True
        stale = result["stale_refs"]
        assert len(stale) == 1
        assert stale[0]["path"] == "src/ghost.py"
        assert stale[0]["reason"] == "file_missing"

    def test_all_clean_returns_zero_stale(self, tmp_path):
        (tmp_path / "docs").mkdir()
        doc = tmp_path / "docs" / "guide.md"
        doc.write_text("See `src/real.py` for details.")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "real.py").write_text("# exists")

        result = run_doc_sync(str(tmp_path), doc_patterns=["docs/*.md"])

        assert result["success"] is True
        assert result["stale_refs"] == []
        assert result["total_refs_checked"] == 1
        assert result["stale_count"] == 0

    def test_summary_fields_present(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("No file refs here.")

        result = run_doc_sync(str(tmp_path), doc_patterns=["docs/*.md"])

        assert "success" in result
        assert "stale_count" in result
        assert "total_refs_checked" in result
        assert "docs_scanned" in result
        assert "stale_refs" in result

    def test_default_pattern_scans_docs_folder(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "a.md").write_text("See `missing.py`.")

        result = run_doc_sync(str(tmp_path))

        assert result["stale_count"] == 1

    def test_no_docs_folder_returns_success(self, tmp_path):
        result = run_doc_sync(str(tmp_path))
        assert result["success"] is True
        assert result["stale_count"] == 0

    def test_stale_ref_includes_doc_file_and_line(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "line one\n`missing.py` is gone.\nline three"
        )

        result = run_doc_sync(str(tmp_path), doc_patterns=["docs/*.md"])

        assert result["stale_count"] == 1
        stale = result["stale_refs"][0]
        assert "docs/guide.md" in stale["doc_file"]
        assert stale["line"] == 2
