import asyncio
import os
import time

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    UnifiedAnalysisEngine,
)


async def profile_analysis():
    engine = UnifiedAnalysisEngine()

    # Large file to analyze
    target_file = "examples/BigService.java"
    if not os.path.exists(target_file):
        print(
            f"Target file {target_file} not found, using a sample python file instead."
        )
        target_file = "tree_sitter_analyzer/core/analysis_engine.py"

    print(f"Analyzing {target_file}...")

    request = AnalysisRequest(
        file_path=target_file, include_complexity=True, include_details=True
    )

    # Measure multiple times to see cache effect
    for i in range(3):
        start_time = time.perf_counter()
        result = await engine.analyze(request)
        end_time = time.perf_counter()
        print(
            f"Analysis {i + 1} took {end_time - start_time:.4f} seconds (Success: {result.success})"
        )

    # Get stats
    stats = engine.get_cache_stats()
    print(f"Cache stats: {stats}")


if __name__ == "__main__":
    asyncio.run(profile_analysis())
