"""
Performance and Scalability Tests

Comprehensive performance testing framework for format output validation.
Tests performance characteristics, scalability limits, and regression detection.
"""

import gc
import json
import statistics
import time
import tracemalloc
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil


@dataclass
class PerformanceMetrics:
    """Performance measurement results"""

    test_name: str
    execution_time_ms: float
    memory_usage_mb: float
    peak_memory_mb: float
    cpu_usage_percent: float
    throughput_ops_per_sec: float
    file_size_bytes: int
    element_count: int
    format_type: str
    timestamp: str
    success: bool
    error_message: str | None = None


@dataclass
class ScalabilityTestResult:
    """Scalability test results"""

    test_name: str
    input_sizes: list[int]
    execution_times: list[float]
    memory_usages: list[float]
    throughput_rates: list[float]
    scalability_factor: float  # How performance scales with input size
    performance_threshold_exceeded: bool
    timestamp: str


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression detection"""

    test_name: str
    baseline_time_ms: float
    baseline_memory_mb: float
    acceptable_variance_percent: float
    created_timestamp: str
    last_updated: str


class PerformanceProfiler:
    """Profiles performance of format operations"""

    def __init__(self):
        self.process = psutil.Process()
        self.baseline_memory = None
        self.start_time = None
        self.tracemalloc_started = False

    def start_profiling(self):
        """Start performance profiling"""
        gc.collect()  # Clean up before measurement

        self.baseline_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_time = time.perf_counter()

        # Start memory tracing
        if not self.tracemalloc_started:
            tracemalloc.start()
            self.tracemalloc_started = True

    def stop_profiling(self) -> dict[str, float]:
        """Stop profiling and return metrics"""
        if not self.start_time:
            raise RuntimeError("Profiling not started")

        end_time = time.perf_counter()
        execution_time = (end_time - self.start_time) * 1000  # Convert to ms

        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = current_memory - self.baseline_memory

        # Get peak memory usage
        if self.tracemalloc_started:
            current, peak = tracemalloc.get_traced_memory()
            peak_memory = peak / 1024 / 1024  # Convert to MB
            tracemalloc.stop()
            self.tracemalloc_started = False
        else:
            peak_memory = current_memory

        # Get CPU usage (approximate)
        cpu_usage = self.process.cpu_percent()

        return {
            "execution_time_ms": execution_time,
            "memory_usage_mb": memory_usage,
            "peak_memory_mb": peak_memory,
            "cpu_usage_percent": cpu_usage,
        }


class PerformanceTester:
    """Main performance testing framework"""

    def __init__(self, results_dir: str = "performance_results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)

        self.profiler = PerformanceProfiler()
        self.baselines: dict[str, PerformanceBaseline] = {}
        self.load_baselines()

    def run_performance_test(
        self,
        test_name: str,
        test_function: Callable,
        test_data: Any,
        format_type: str = "full",
        iterations: int = 5,
    ) -> PerformanceMetrics:
        """Run performance test with multiple iterations"""

        results = []

        for i in range(iterations):
            try:
                self.profiler.start_profiling()

                # Execute test function
                test_function(test_data)

                # Get performance metrics
                metrics = self.profiler.stop_profiling()

                # Calculate throughput (operations per second)
                throughput = (
                    1000 / metrics["execution_time_ms"]
                    if metrics["execution_time_ms"] > 0
                    else 0
                )

                # Get data characteristics
                file_size = (
                    len(str(test_data).encode()) if hasattr(test_data, "__str__") else 0
                )
                element_count = self._estimate_element_count(test_data)

                result_metrics = PerformanceMetrics(
                    test_name=f"{test_name}_iteration_{i+1}",
                    execution_time_ms=metrics["execution_time_ms"],
                    memory_usage_mb=metrics["memory_usage_mb"],
                    peak_memory_mb=metrics["peak_memory_mb"],
                    cpu_usage_percent=metrics["cpu_usage_percent"],
                    throughput_ops_per_sec=throughput,
                    file_size_bytes=file_size,
                    element_count=element_count,
                    format_type=format_type,
                    timestamp=datetime.utcnow().isoformat(),
                    success=True,
                )

                results.append(result_metrics)

            except Exception as e:
                error_metrics = PerformanceMetrics(
                    test_name=f"{test_name}_iteration_{i+1}",
                    execution_time_ms=0,
                    memory_usage_mb=0,
                    peak_memory_mb=0,
                    cpu_usage_percent=0,
                    throughput_ops_per_sec=0,
                    file_size_bytes=0,
                    element_count=0,
                    format_type=format_type,
                    timestamp=datetime.utcnow().isoformat(),
                    success=False,
                    error_message=str(e),
                )
                results.append(error_metrics)

        # Calculate aggregate metrics
        successful_results = [r for r in results if r.success]

        if not successful_results:
            return results[0]  # Return first error

        aggregate_metrics = PerformanceMetrics(
            test_name=test_name,
            execution_time_ms=statistics.mean(
                [r.execution_time_ms for r in successful_results]
            ),
            memory_usage_mb=statistics.mean(
                [r.memory_usage_mb for r in successful_results]
            ),
            peak_memory_mb=max([r.peak_memory_mb for r in successful_results]),
            cpu_usage_percent=statistics.mean(
                [r.cpu_usage_percent for r in successful_results]
            ),
            throughput_ops_per_sec=statistics.mean(
                [r.throughput_ops_per_sec for r in successful_results]
            ),
            file_size_bytes=successful_results[0].file_size_bytes,
            element_count=successful_results[0].element_count,
            format_type=format_type,
            timestamp=datetime.utcnow().isoformat(),
            success=True,
        )

        # Save results
        self._save_performance_results(test_name, aggregate_metrics, results)

        return aggregate_metrics

    def run_scalability_test(
        self,
        test_name: str,
        test_function: Callable,
        data_generator: Callable[[int], Any],
        size_range: list[int],
        format_type: str = "full",
    ) -> ScalabilityTestResult:
        """Run scalability test across different input sizes"""

        execution_times = []
        memory_usages = []
        throughput_rates = []

        for size in size_range:
            print(f"Testing scalability with size: {size}")

            # Generate test data of specified size
            test_data = data_generator(size)

            # Run performance test
            metrics = self.run_performance_test(
                f"{test_name}_size_{size}",
                test_function,
                test_data,
                format_type,
                iterations=3,  # Fewer iterations for scalability tests
            )

            execution_times.append(metrics.execution_time_ms)
            memory_usages.append(metrics.memory_usage_mb)
            throughput_rates.append(metrics.throughput_ops_per_sec)

        # Calculate scalability factor (how performance degrades with size)
        scalability_factor = self._calculate_scalability_factor(
            size_range, execution_times
        )

        # Check if performance thresholds are exceeded
        performance_threshold_exceeded = any(
            time_ms > 10000 for time_ms in execution_times  # 10 second threshold
        )

        result = ScalabilityTestResult(
            test_name=test_name,
            input_sizes=size_range,
            execution_times=execution_times,
            memory_usages=memory_usages,
            throughput_rates=throughput_rates,
            scalability_factor=scalability_factor,
            performance_threshold_exceeded=performance_threshold_exceeded,
            timestamp=datetime.utcnow().isoformat(),
        )

        # Save scalability results
        self._save_scalability_results(result)

        return result

    def run_concurrent_performance_test(
        self,
        test_name: str,
        test_function: Callable,
        test_data_list: list[Any],
        max_workers: int = 4,
        format_type: str = "full",
    ) -> list[PerformanceMetrics]:
        """Run concurrent performance tests"""

        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = []
            for i, test_data in enumerate(test_data_list):
                future = executor.submit(
                    self.run_performance_test,
                    f"{test_name}_concurrent_{i}",
                    test_function,
                    test_data,
                    format_type,
                    iterations=1,  # Single iteration for concurrent tests
                )
                futures.append(future)

            # Collect results
            for future in futures:
                try:
                    result = future.result(timeout=60)  # 60 second timeout
                    results.append(result)
                except Exception as e:
                    error_result = PerformanceMetrics(
                        test_name=f"{test_name}_concurrent_error",
                        execution_time_ms=0,
                        memory_usage_mb=0,
                        peak_memory_mb=0,
                        cpu_usage_percent=0,
                        throughput_ops_per_sec=0,
                        file_size_bytes=0,
                        element_count=0,
                        format_type=format_type,
                        timestamp=datetime.utcnow().isoformat(),
                        success=False,
                        error_message=str(e),
                    )
                    results.append(error_result)

        return results

    def check_performance_regression(
        self, test_name: str, current_metrics: PerformanceMetrics
    ) -> dict[str, Any]:
        """Check for performance regression against baseline"""

        if test_name not in self.baselines:
            # No baseline exists, create one
            self.create_baseline(test_name, current_metrics)
            return {
                "regression_detected": False,
                "message": "Baseline created",
                "baseline_created": True,
            }

        baseline = self.baselines[test_name]

        # Calculate performance changes
        time_change_percent = (
            (current_metrics.execution_time_ms - baseline.baseline_time_ms)
            / baseline.baseline_time_ms
            * 100
        )

        memory_change_percent = (
            (
                (current_metrics.memory_usage_mb - baseline.baseline_memory_mb)
                / baseline.baseline_memory_mb
                * 100
            )
            if baseline.baseline_memory_mb > 0
            else 0
        )

        # Check for regression
        time_regression = time_change_percent > baseline.acceptable_variance_percent
        memory_regression = memory_change_percent > baseline.acceptable_variance_percent

        regression_detected = time_regression or memory_regression

        return {
            "regression_detected": regression_detected,
            "time_change_percent": time_change_percent,
            "memory_change_percent": memory_change_percent,
            "time_regression": time_regression,
            "memory_regression": memory_regression,
            "baseline_time_ms": baseline.baseline_time_ms,
            "baseline_memory_mb": baseline.baseline_memory_mb,
            "current_time_ms": current_metrics.execution_time_ms,
            "current_memory_mb": current_metrics.memory_usage_mb,
            "acceptable_variance_percent": baseline.acceptable_variance_percent,
        }

    def create_baseline(
        self,
        test_name: str,
        metrics: PerformanceMetrics,
        acceptable_variance_percent: float = 20.0,
    ):
        """Create performance baseline"""

        baseline = PerformanceBaseline(
            test_name=test_name,
            baseline_time_ms=metrics.execution_time_ms,
            baseline_memory_mb=metrics.memory_usage_mb,
            acceptable_variance_percent=acceptable_variance_percent,
            created_timestamp=datetime.utcnow().isoformat(),
            last_updated=datetime.utcnow().isoformat(),
        )

        self.baselines[test_name] = baseline
        self.save_baselines()

    def update_baseline(self, test_name: str, metrics: PerformanceMetrics):
        """Update existing baseline"""

        if test_name in self.baselines:
            baseline = self.baselines[test_name]
            baseline.baseline_time_ms = metrics.execution_time_ms
            baseline.baseline_memory_mb = metrics.memory_usage_mb
            baseline.last_updated = datetime.utcnow().isoformat()

            self.save_baselines()

    def load_baselines(self):
        """Load performance baselines from file"""
        baselines_file = self.results_dir / "performance_baselines.json"

        if baselines_file.exists():
            with open(baselines_file) as f:
                data = json.load(f)

                for test_name, baseline_data in data.items():
                    self.baselines[test_name] = PerformanceBaseline(**baseline_data)

    def save_baselines(self):
        """Save performance baselines to file"""
        baselines_file = self.results_dir / "performance_baselines.json"

        data = {}
        for test_name, baseline in self.baselines.items():
            data[test_name] = asdict(baseline)

        with open(baselines_file, "w") as f:
            json.dump(data, f, indent=2)

    def generate_performance_report(self) -> str:
        """Generate comprehensive performance report"""

        # Load all performance results
        all_results = self._load_all_performance_results()

        report_lines = [
            "# Performance Test Report",
            f"Generated: {datetime.utcnow().isoformat()}",
            "",
            "## Summary",
            f"Total tests: {len(all_results)}",
            f"Successful tests: {sum(1 for r in all_results if r.success)}",
            f"Failed tests: {sum(1 for r in all_results if not r.success)}",
            "",
        ]

        # Performance by format type
        by_format = {}
        for result in all_results:
            if result.success:
                if result.format_type not in by_format:
                    by_format[result.format_type] = []
                by_format[result.format_type].append(result)

        report_lines.append("## Performance by Format Type")
        for format_type, results in by_format.items():
            avg_time = statistics.mean([r.execution_time_ms for r in results])
            avg_memory = statistics.mean([r.memory_usage_mb for r in results])
            avg_throughput = statistics.mean(
                [r.throughput_ops_per_sec for r in results]
            )

            report_lines.extend(
                [
                    f"### {format_type.title()} Format",
                    f"- Average execution time: {avg_time:.2f} ms",
                    f"- Average memory usage: {avg_memory:.2f} MB",
                    f"- Average throughput: {avg_throughput:.2f} ops/sec",
                    "",
                ]
            )

        # Regression analysis
        report_lines.append("## Regression Analysis")
        for test_name in self.baselines:
            # Find latest result for this test
            test_results = [
                r
                for r in all_results
                if r.test_name.startswith(test_name) and r.success
            ]
            if test_results:
                latest_result = max(test_results, key=lambda x: x.timestamp)
                regression_info = self.check_performance_regression(
                    test_name, latest_result
                )

                if regression_info["regression_detected"]:
                    report_lines.extend(
                        [
                            f"⚠️ **Regression detected in {test_name}**",
                            f"- Time change: {regression_info['time_change_percent']:.1f}%",
                            f"- Memory change: {regression_info['memory_change_percent']:.1f}%",
                            "",
                        ]
                    )
                else:
                    report_lines.extend([f"✅ {test_name}: No regression detected", ""])

        report_content = "\n".join(report_lines)

        # Save report
        report_file = (
            self.results_dir
            / f"performance_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
        )
        with open(report_file, "w") as f:
            f.write(report_content)

        return str(report_file)

    def _estimate_element_count(self, test_data: Any) -> int:
        """Estimate number of elements in test data"""
        if hasattr(test_data, "__len__"):
            return len(test_data)
        elif isinstance(test_data, str):
            # Rough estimate based on lines
            return len(test_data.split("\n"))
        else:
            return 1

    def _calculate_scalability_factor(
        self, sizes: list[int], times: list[float]
    ) -> float:
        """Calculate how performance scales with input size"""
        if len(sizes) < 2 or len(times) < 2:
            return 1.0

        # Calculate the ratio of time increase to size increase
        size_ratios = []
        time_ratios = []

        for i in range(1, len(sizes)):
            size_ratio = sizes[i] / sizes[i - 1]
            time_ratio = times[i] / times[i - 1] if times[i - 1] > 0 else 1.0

            size_ratios.append(size_ratio)
            time_ratios.append(time_ratio)

        # Average scalability factor
        if size_ratios:
            avg_size_ratio = statistics.mean(size_ratios)
            avg_time_ratio = statistics.mean(time_ratios)
            return avg_time_ratio / avg_size_ratio if avg_size_ratio > 0 else 1.0

        return 1.0

    def _save_performance_results(
        self,
        test_name: str,
        aggregate_metrics: PerformanceMetrics,
        individual_results: list[PerformanceMetrics],
    ):
        """Save performance test results"""
        results_file = (
            self.results_dir
            / f"{test_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )

        data = {
            "aggregate_metrics": asdict(aggregate_metrics),
            "individual_results": [asdict(r) for r in individual_results],
        }

        with open(results_file, "w") as f:
            json.dump(data, f, indent=2)

    def _save_scalability_results(self, result: ScalabilityTestResult):
        """Save scalability test results"""
        results_file = (
            self.results_dir
            / f"scalability_{result.test_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(results_file, "w") as f:
            json.dump(asdict(result), f, indent=2)

    def _load_all_performance_results(self) -> list[PerformanceMetrics]:
        """Load all performance results from files"""
        results = []

        for results_file in self.results_dir.glob("*.json"):
            if "scalability" in results_file.name or "baselines" in results_file.name:
                continue

            try:
                with open(results_file) as f:
                    data = json.load(f)

                    if "aggregate_metrics" in data:
                        metrics = PerformanceMetrics(**data["aggregate_metrics"])
                        results.append(metrics)

                    if "individual_results" in data:
                        for result_data in data["individual_results"]:
                            metrics = PerformanceMetrics(**result_data)
                            results.append(metrics)

            except Exception as e:
                print(f"Error loading results from {results_file}: {e}")

        return results


class FormatPerformanceTester:
    """Specialized performance tester for format operations"""

    def __init__(self, results_dir: str = "format_performance_results"):
        self.performance_tester = PerformanceTester(results_dir)

    def test_format_performance(
        self,
        analyzer_function: Callable,
        test_data: str,
        language: str,
        format_types: list[str] = None,
    ) -> dict[str, PerformanceMetrics]:
        """Test performance across different format types"""

        if format_types is None:
            format_types = ["full", "compact", "csv"]

        results = {}

        for format_type in format_types:
            test_name = f"format_{language}_{format_type}"

            def test_function(data, format_type=format_type):
                return analyzer_function(data, format_type=format_type)

            metrics = self.performance_tester.run_performance_test(
                test_name, test_function, test_data, format_type
            )

            results[format_type] = metrics

        return results

    def test_format_scalability(
        self,
        analyzer_function: Callable,
        data_generator: Callable[[int], str],
        language: str,
        format_type: str = "full",
        size_range: list[int] = None,
    ) -> ScalabilityTestResult:
        """Test format scalability with increasing data sizes"""

        if size_range is None:
            size_range = [100, 500, 1000, 5000, 10000]  # Lines of code

        test_name = f"scalability_{language}_{format_type}"

        def test_function(data):
            return analyzer_function(data, format_type=format_type)

        return self.performance_tester.run_scalability_test(
            test_name, test_function, data_generator, size_range, format_type
        )

    def benchmark_format_comparison(
        self, analyzer_function: Callable, test_data: str, language: str
    ) -> dict[str, Any]:
        """Benchmark and compare all format types"""

        format_results = self.test_format_performance(
            analyzer_function, test_data, language
        )

        # Calculate relative performance
        baseline_time = format_results["full"].execution_time_ms

        comparison = {
            "absolute_performance": format_results,
            "relative_performance": {},
            "fastest_format": None,
            "most_memory_efficient": None,
        }

        fastest_time = float("inf")
        lowest_memory = float("inf")

        for format_type, metrics in format_results.items():
            if metrics.success:
                relative_time = metrics.execution_time_ms / baseline_time
                comparison["relative_performance"][format_type] = {
                    "time_ratio": relative_time,
                    "memory_ratio": metrics.memory_usage_mb
                    / format_results["full"].memory_usage_mb,
                    "throughput_ratio": metrics.throughput_ops_per_sec
                    / format_results["full"].throughput_ops_per_sec,
                }

                if metrics.execution_time_ms < fastest_time:
                    fastest_time = metrics.execution_time_ms
                    comparison["fastest_format"] = format_type

                if metrics.memory_usage_mb < lowest_memory:
                    lowest_memory = metrics.memory_usage_mb
                    comparison["most_memory_efficient"] = format_type

        return comparison
