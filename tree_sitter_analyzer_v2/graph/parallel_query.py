"""Parallel query execution for high throughput"""

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
from typing import Any

from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage
from tree_sitter_analyzer_v2.graph.query_optimizer import QueryOptimizer


@dataclass
class QueryBatch:
    """Represents a batch of queries to execute"""

    queries: list[str]
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ParallelQueryExecutor:
    """Executes queries in parallel for high throughput"""

    def __init__(self, storage: CodeGraphStorage, max_workers: int = 4):
        """
        Initialize parallel executor

        Args:
            storage: CodeGraphStorage instance
            max_workers: Maximum number of worker threads
        """
        self.storage = storage
        self.max_workers = max_workers
        self.optimizer = QueryOptimizer(storage)

    def execute_single(self, query: str) -> list[dict[str, Any]]:
        """
        Execute a single query

        Args:
            query: CQL query string

        Returns:
            Query results
        """
        plan = self.optimizer.optimize(query)
        return plan.execute()

    def execute_batch(
        self,
        queries: list[str],
        continue_on_error: bool = False,
        timeout: float = None
    ) -> list[list[dict[str, Any]] | None]:
        """
        Execute multiple queries in parallel

        Args:
            queries: List of CQL query strings
            continue_on_error: Continue if a query fails
            timeout: Maximum time to wait for all queries (seconds)

        Returns:
            List of query results (None for failed queries if continue_on_error)
        """
        results = [None] * len(queries)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all queries
            future_to_idx = {
                executor.submit(self._execute_query_safe, q, continue_on_error): i
                for i, q in enumerate(queries)
            }

            # Collect results
            try:
                for future in as_completed(future_to_idx.keys(), timeout=timeout):
                    idx = future_to_idx[future]
                    try:
                        results[idx] = future.result()
                    except Exception:
                        if not continue_on_error:
                            raise
                        results[idx] = []
            except TimeoutError:
                # Return partial results on timeout
                pass

        return results

    def execute_batch_with_metadata(
        self,
        batch: QueryBatch
    ) -> list[dict[str, Any]]:
        """
        Execute batch with detailed metadata

        Args:
            batch: QueryBatch with queries and metadata

        Returns:
            List of results with metadata
        """
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all queries with timing
            future_to_query = {
                executor.submit(self._execute_with_timing, q): q
                for q in batch.queries
            }

            # Collect results with metadata
            for future in as_completed(future_to_query.keys()):
                query = future_to_query[future]
                try:
                    result, exec_time = future.result()
                    results.append({
                        'query': query,
                        'results': result,
                        'count': len(result),
                        'execution_time': exec_time,
                        'success': True
                    })
                except Exception as e:
                    results.append({
                        'query': query,
                        'results': [],
                        'count': 0,
                        'execution_time': 0,
                        'success': False,
                        'error': str(e)
                    })

        return results

    def execute_stream(
        self,
        queries: list[str]
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Execute queries and stream results as they complete

        Args:
            queries: List of CQL query strings

        Yields:
            Query results as they complete
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all queries
            futures = [
                executor.submit(self._execute_query_safe, q, True)
                for q in queries
            ]

            # Yield results as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        yield result
                except Exception:
                    yield []

    def _execute_query_safe(
        self,
        query: str,
        continue_on_error: bool
    ) -> list[dict[str, Any]] | None:
        """
        Execute query with error handling

        Args:
            query: CQL query string
            continue_on_error: Return empty list on error

        Returns:
            Query results or None on error
        """
        try:
            plan = self.optimizer.optimize(query)
            return plan.execute()
        except Exception:
            if continue_on_error:
                return []
            raise

    def _execute_with_timing(
        self,
        query: str
    ) -> tuple[list[dict[str, Any]], float]:
        """
        Execute query and measure execution time

        Args:
            query: CQL query string

        Returns:
            Tuple of (results, execution_time)
        """
        start = time.time()
        plan = self.optimizer.optimize(query)
        results = plan.execute()
        exec_time = time.time() - start
        return results, exec_time


class ParallelBatchProcessor:
    """Process large batches of queries efficiently"""

    def __init__(
        self,
        storage: CodeGraphStorage,
        max_workers: int = 4,
        batch_size: int = 100
    ):
        """
        Initialize batch processor

        Args:
            storage: CodeGraphStorage instance
            max_workers: Maximum worker threads
            batch_size: Number of queries per batch
        """
        self.executor = ParallelQueryExecutor(storage, max_workers)
        self.batch_size = batch_size

    def process_large_batch(
        self,
        queries: list[str],
        progress_callback: callable = None
    ) -> list[list[dict[str, Any]]]:
        """
        Process very large batches with progress tracking

        Args:
            queries: List of queries
            progress_callback: Optional callback(completed, total)

        Returns:
            All query results
        """
        results = []
        total = len(queries)

        # Process in chunks
        for i in range(0, total, self.batch_size):
            chunk = queries[i:i + self.batch_size]
            chunk_results = self.executor.execute_batch(chunk)
            results.extend(chunk_results)

            if progress_callback:
                progress_callback(min(i + self.batch_size, total), total)

        return results

    def process_with_aggregation(
        self,
        queries: list[str],
        aggregator: callable
    ) -> Any:
        """
        Process queries and aggregate results

        Args:
            queries: List of queries
            aggregator: Function to aggregate results

        Returns:
            Aggregated result
        """
        all_results = []

        for i in range(0, len(queries), self.batch_size):
            chunk = queries[i:i + self.batch_size]
            chunk_results = self.executor.execute_batch(chunk)
            all_results.extend(chunk_results)

        return aggregator(all_results)
