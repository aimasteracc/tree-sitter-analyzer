"""Analysis modules for tree-sitter-analyzer."""

from tree_sitter_analyzer.analysis.llm_benchmark import (
    BenchmarkResult,
    Question,
    analyze_fidelity_vs_compression,
    format_benchmark_report,
    generate_questions_from_code,
    run_benchmark,
)

__all__ = [
    "BenchmarkResult",
    "Question",
    "analyze_fidelity_vs_compression",
    "format_benchmark_report",
    "generate_questions_from_code",
    "run_benchmark",
]
