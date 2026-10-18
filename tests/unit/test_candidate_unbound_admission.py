"""RFC-0032 follow-up (#1664 item 3): ``INDEX_CANDIDATE_UNBOUND`` is emitted.

RFC-0032 "Operation lease and candidate binding": an unbound candidate cannot
authorize mutation and gets ``INDEX_CANDIDATE_UNBOUND`` without writes. On the
default locator every candidate from ``build_index_candidate_snapshot`` is bound
to the publication selector it saw (``publication_bound``). A candidate without
that binding (built by hand, or from an older develop interface) was refused as
``INDEX_CANDIDATE_SUPERSEDED``, whose ``recapture`` advice repeats the failure
when the caller builds the candidate the same way again.

Custom ``db_path`` caches still accept unbound candidates (owner decision of
2026-10-14, until a major version); that stays pinned by
``test_unbound_candidate_stays_accepted_on_custom_path``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.admission import (
    ADMISSION_CODES,
    IndexWriteAdmissionError,
    admission_failure_of,
)
from tree_sitter_analyzer.cache.generation_routing import generation_storage_path
from tree_sitter_analyzer.constants import EXCLUDE_DIRS
from tree_sitter_analyzer.incremental_sync import IncrementalSync
from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
    walk_index_candidate_entries,
)
from tree_sitter_analyzer.project_graph import _language_from_ext

# Spelled out so the module imports on develop and the tests fail on behaviour.
INDEX_CANDIDATE_UNBOUND = "INDEX_CANDIDATE_UNBOUND"


def _published(root: Path) -> Path:
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(root))
    try:
        cache.index_project()
    finally:
        cache.close()
    selector = generation_storage_path(str(root)) / "active.json"
    assert selector.is_file()
    return selector


def _unbound(root: Path):
    scope = make_source_scope_descriptor()
    bound = build_index_candidate_snapshot(
        str(root),
        max_files=scope.certification_max_files,
        exclude_patterns=scope.effective_excludes,
        walk_fn=lambda path: walk_index_candidate_entries(
            path, excluded_dir_names=frozenset(EXCLUDE_DIRS)
        ),
        language_fn=_language_from_ext,
    )
    assert bound.publication_bound is True
    return replace(bound, publication_bound=False, publication_parent=None)


def _generations(root: Path) -> set[str]:
    return {
        path.name
        for path in (generation_storage_path(str(root)) / "generations").iterdir()
    }


def _assert_unbound(exc: BaseException) -> None:
    assert isinstance(exc, IndexWriteAdmissionError)
    assert (exc.code, exc.cause_code) == (
        INDEX_CANDIDATE_UNBOUND,
        INDEX_CANDIDATE_UNBOUND,
    )
    assert (exc.retryable, exc.retry_after_ms, exc.next_action) == (
        False,
        0,
        "obtain_bound_candidate",
    )


def test_unbound_contract_matches_rfc_table():
    contract = ADMISSION_CODES[INDEX_CANDIDATE_UNBOUND]
    assert (contract.retryable, contract.retry_after_ms, contract.next_action) == (
        False,
        0,
        "obtain_bound_candidate",
    )
    assert "build_index_candidate_snapshot" in contract.next_step


def _sync(cache: ASTCache, candidate) -> None:
    scope = make_source_scope_descriptor()
    IncrementalSync(cache).sync(
        max_files=scope.certification_max_files,
        exclude_patterns=scope.effective_excludes,
        candidate_snapshot=candidate,
        source_scope=scope,
    )


def _index_project(cache: ASTCache, candidate) -> None:
    cache.index_project(candidate_snapshot=candidate)


@pytest.mark.parametrize("route", [_sync, _index_project], ids=["sync", "index"])
def test_unbound_candidate_on_default_locator_is_refused_without_writes(
    tmp_path, route
):
    selector = _published(tmp_path)
    (tmp_path / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    candidate = _unbound(tmp_path)
    before = (selector.read_bytes(), _generations(tmp_path))
    cache = ASTCache(str(tmp_path))
    try:
        with pytest.raises(IndexWriteAdmissionError) as raised:
            route(cache, candidate)
        assert cache.get_stats()["total_files"] == 1
    finally:
        cache.close()
    _assert_unbound(raised.value)
    # No private build was started and nothing was published.
    assert (selector.read_bytes(), _generations(tmp_path)) == before


def test_watcher_does_not_replay_an_unbound_candidate(tmp_path):
    # RFC-0032: an unbound candidate does not cause an automatic replay loop.
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    _published(tmp_path)
    cache = ASTCache(str(tmp_path))
    watcher = FileWatcherDaemon(cache, poll_interval=1, debounce=0)
    unbound = IndexWriteAdmissionError(INDEX_CANDIDATE_UNBOUND)
    try:
        with (
            patch.object(watcher._sync, "sync", side_effect=unbound),
            patch.object(watcher, "_request_sync") as request_sync,
        ):
            result = watcher.trigger_sync()
        request_sync.assert_not_called()
        assert (result["error_code"], result["retryable"], result["next_action"]) == (
            INDEX_CANDIDATE_UNBOUND,
            False,
            "obtain_bound_candidate",
        )
        assert admission_failure_of(unbound).code == INDEX_CANDIDATE_UNBOUND
        assert watcher.get_stats()["last_admission_error"] == result
    finally:
        watcher.stop()
        cache.close()
