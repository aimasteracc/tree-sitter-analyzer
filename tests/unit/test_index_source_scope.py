"""Certified full-index source-scope replay tests."""

from __future__ import annotations

import os

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_default_scope_excludes_golden_corpus_and_stays_complete(tmp_path):
    # PR #1253: status must replay the exact scope certified by full-index.
    golden = tmp_path / "tests" / "golden"
    golden.mkdir(parents=True)
    (golden / "corpus_generated.py").write_text("ignored = True\n")
    (tmp_path / "sample.py").write_text("included = True\n")
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "output_format": "json"}
    )
    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["total_files"]) == ("complete", 1)


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_no_default_excludes_scope_includes_golden_corpus(tmp_path):
    # PR #1253: no_default_excludes is persisted rather than hard-coded away.
    golden = tmp_path / "tests" / "golden"
    golden.mkdir(parents=True)
    (golden / "corpus_generated.py").write_text("included = True\n")
    (tmp_path / "sample.py").write_text("also_included = True\n")
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {
            "mode": "full",
            "no_default_excludes": True,
            "output_format": "json",
        }
    )
    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["total_files"]) == ("complete", 2)


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_new_file_inside_certified_scope_is_detected(tmp_path):
    # PR #1253: replaying a descriptor must detect later in-scope additions.
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "sample.py").write_text("value = 1\n")
    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "output_format": "json"}
    )
    (tmp_path / "new.py").write_text("value = 2\n")
    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "SOURCE_INDEX_MISMATCH",
    )


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_excluded_supported_file_beyond_certified_max_is_bounded(tmp_path):
    # PR #1253: max_files is charged before persisted exclusions during replay.
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "a.py").write_text("value = 1\n")
    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {
            "mode": "full",
            "max_files": 1,
            "exclude_patterns": ["z_excluded.py"],
            "output_format": "json",
        }
    )
    (tmp_path / "z_excluded.py").write_text("value = 2\n")

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "unknown",
        "SOURCE_SCOPE_UNBOUNDED",
    )


@requires_posix_snapshot
@pytest.mark.asyncio
async def test_invalid_persisted_scope_cannot_certify_complete(tmp_path):
    # PR #1253: malformed discovery policy is not trusted by status.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.get_conn().execute(
        "UPDATE ast_index_snapshot_manifest SET source_scope_descriptor = ?",
        ('{"roots":["."]}',),
    )
    cache.get_conn().commit()
    cache.close()

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "SOURCE_SCOPE_DESCRIPTOR_INVALID",
    )


@requires_posix_snapshot
@pytest.mark.asyncio
async def test_missing_scope_manifest_cannot_certify_complete(tmp_path):
    # PR #1253: absent descriptor evidence degrades to partial.
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    cache.close()

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "SOURCE_SCOPE_DESCRIPTOR_MISSING",
    )


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        '{"certification_max_files":20000,"discovery_policy":"wrong","discovery_policy_version":2,"exclude_patterns":[],"no_default_excludes":false,"roots":["."]}',
        '{"certification_max_files":20000,"discovery_policy":"tsa-full-index-walk","discovery_policy_version":2,"exclude_patterns":[],"no_default_excludes":false,"roots":["../escape"]}',
        '{ "certification_max_files":20000,"discovery_policy":"tsa-full-index-walk","discovery_policy_version":2,"exclude_patterns":[],"no_default_excludes":false,"roots":["."]}',
    ],
)
def test_source_scope_descriptor_rejects_noncanonical_policy(raw):
    # PR #1253: status only replays the exact known canonical policy.
    from tree_sitter_analyzer.index_source_snapshot import parse_source_scope_descriptor

    with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_INVALID"):
        parse_source_scope_descriptor(raw)


def test_full_index_scope_validation_rejects_mismatched_effective_excludes():
    # PR #1253: writers cannot certify a descriptor different from their walk.
    from tree_sitter_analyzer.index_source_snapshot import (
        make_source_scope_descriptor,
        validate_full_index_source_scope,
    )

    scope = make_source_scope_descriptor(certification_max_files=40_000)
    assert scope.certification_max_files == 40_000
    with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_MISMATCH"):
        validate_full_index_source_scope(scope, frozenset(), 20_000)


@requires_posix_snapshot
def test_writer_ignores_unsupported_suffix_directory_symlink(tmp_path):
    from tree_sitter_analyzer.cache.indexer import _walk_source_files

    target = tmp_path / "source_dir"
    target.mkdir()
    (target / "hidden.py").write_text("value = 1\n")
    (tmp_path / "alias.data").symlink_to(target, target_is_directory=True)

    assert list(_walk_source_files(str(tmp_path))) == [str(target / "hidden.py")]


@requires_posix_snapshot
def test_source_inventory_charges_actual_growth_chunks(tmp_path, monkeypatch):
    # PR #1253: a post-stat growth race cannot allocate beyond the source budget.
    import tree_sitter_analyzer.index_source_snapshot as source_owner

    (tmp_path / "sample.py").write_bytes(b"x")
    chunks = iter((b"1234", b"56"))
    monkeypatch.setattr(source_owner, "_SOURCE_BYTE_BUDGET", 5)
    monkeypatch.setattr(source_owner.os, "read", lambda _fd, _size: next(chunks))

    with pytest.raises(OverflowError):
        source_owner._inventory(str(tmp_path), float("inf"), with_content=True)
