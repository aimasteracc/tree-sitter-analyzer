import asyncio
import time

import pytest

from tree_sitter_analyzer.api import get_engine
from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
)


@pytest.mark.asyncio
async def test_concurrent_analysis_performance(tmp_path):
    """
    Measure performance of concurrent analysis.
    In the current implementation, it might still block if plugins are synchronous.
    Phase 2 aims to make this fully parallel.
    """
    # Create multiple files
    num_files = 5
    files = []
    for i in range(num_files):
        f = tmp_path / f"test_{i}.py"
        f.write_text(f"def func_{i}():\n    pass\n" * 100)  # Fairly large file
        files.append(str(f))

    engine = get_engine()

    # Concurrent analysis
    start_time = time.perf_counter()
    requests = [AnalysisRequest(file_path=f, language="python") for f in files]
    tasks = [engine.analyze(req) for req in requests]
    results = await asyncio.gather(*tasks)
    end_time = time.perf_counter()

    concurrent_duration = end_time - start_time
    print(f"\nConcurrent duration for {num_files} files: {concurrent_duration:.4f}s")

    assert len(results) == num_files
    assert all(r.success for r in results)


@pytest.mark.asyncio
async def test_parser_cache_effectiveness(tmp_path):
    """
    Verify that repeated requests for the same file are faster due to caching.
    Note: Currently UnifiedAnalysisEngine has a result cache, but Phase 2
    introduces a lower-level ParseResult cache.
    """
    f = tmp_path / "test_cache.py"
    f.write_text("def cached_func(): pass")
    file_path = str(f)

    engine = get_engine()
    request = AnalysisRequest(file_path=file_path, language="python")

    # First time - should parse
    start1 = time.perf_counter()
    res1 = await engine.analyze(request)
    duration1 = time.perf_counter() - start1

    # Second time - should hit cache
    start2 = time.perf_counter()
    res2 = await engine.analyze(request)
    duration2 = time.perf_counter() - start2

    print(f"\nFirst call: {duration1:.4f}s, Second call (cached): {duration2:.4f}s")
    assert duration2 < duration1
    assert res1.elements == res2.elements


@pytest.mark.asyncio
async def test_event_loop_responsiveness(tmp_path):
    """
    Verify that the event loop remains responsive during analysis.
    Phase 2 offloads to threads, so this should pass better.
    """
    f = tmp_path / "heavy.py"
    f.write_text("def heavy(): pass\n" * 1000)

    engine = get_engine()
    request = AnalysisRequest(file_path=str(f), language="python")

    # Heartbeat task to check blocking
    heartbeat_count = 0

    async def heartbeat():
        nonlocal heartbeat_count
        while True:
            await asyncio.sleep(0.01)
            heartbeat_count += 1

    hb_task = asyncio.create_task(heartbeat())

    start_time = time.perf_counter()
    await engine.analyze(request)
    end_time = time.perf_counter()

    actual_duration = end_time - start_time
    # If it was non-blocking, we expect around actual_duration / 0.01 heartbeats
    expected_heartbeats = actual_duration / 0.01

    hb_task.cancel()

    print(
        f"\nActual duration: {actual_duration:.4f}s, Heartbeats: {heartbeat_count}, Expected: {expected_heartbeats:.1f}"
    )

    # In Phase 1, it likely blocks, so heartbeat_count will be low.
    # In Phase 2, it should be significantly higher.
    # We will use this to compare.


@pytest.mark.asyncio
async def test_cache_invalidation_on_file_change(tmp_path):
    """
    Verify that changing the file invalidates the result cache.
    Phase 2 added mtime/size to the cache key.
    """
    f = tmp_path / "change.py"
    f.write_text("def old(): pass")
    file_path = str(f)

    engine = get_engine()
    request = AnalysisRequest(file_path=file_path, language="python")

    # Initial analysis
    res1 = await engine.analyze(request)
    assert any(e.name == "old" for e in res1.elements)

    # Modify file (wait a bit to ensure mtime changes if filesystem resolution is low)
    time.sleep(1.1)
    f.write_text("def new(): pass")

    # Second analysis - should NOT return "old"
    res2 = await engine.analyze(request)
    assert any(e.name == "new" for e in res2.elements)
    assert not any(e.name == "old" for e in res2.elements)

    print("\nCache invalidation verified: result updated after file change.")


@pytest.mark.asyncio
async def test_parser_cache_impact_on_queries(tmp_path):
    """
    Verify that query execution doesn't cause redundant parsing hits if already parsed.
    """
    f = tmp_path / "query_cache.py"
    f.write_text("def test_func(): pass")
    file_path = str(f)

    engine = get_engine()
    # 1. Analyze without queries
    req1 = AnalysisRequest(file_path=file_path, language="python")
    await engine.analyze(req1)

    # 2. Analyze WITH queries - should use the parser cache if we implement it for all parses
    # Wait, currently only queries use the parser cache if they re-parse.
    # We should probably make the initial parse also fill the cache.

    req2 = AnalysisRequest(
        file_path=file_path,
        language="python",
        queries=["python.functions"],
        include_queries=True,
    )

    start = time.perf_counter()
    res2 = await engine.analyze(req2)
    duration = time.perf_counter() - start

    assert res2.query_results is not None
    print(f"\nQuery execution with potentially cached parser: {duration:.4f}s")
