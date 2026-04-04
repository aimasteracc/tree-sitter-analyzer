#!/usr/bin/env python3
"""Phase 3 Auto-Discovery CLI.

用法:
  # 分析单种语言
  python scripts/auto_discover.py python

  # 分析所有语言
  python scripts/auto_discover.py --all

  # 输出报告到文件
  python scripts/auto_discover.py --all --output report.md

  # 只显示 wrapper 节点
  python scripts/auto_discover.py typescript --show-wrappers

  # 只显示缺失节点
  python scripts/auto_discover.py java --show-missing
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tree_sitter_analyzer.grammar_coverage.auto_discovery import (  # noqa: E402
    AutoDiscoveryEngine,
)
from tree_sitter_analyzer.grammar_coverage.discovery_corpus import (  # noqa: E402
    TARGET_LANGUAGES,
)


def print_language_report(engine: AutoDiscoveryEngine, language: str, args: argparse.Namespace) -> int:
    """分析单个语言并打印结果，返回退出码（0=成功）."""
    report = engine.analyze_coverage_gap(language)

    if not report.is_ok:
        print(f"❌  {language}: {report.error}", file=sys.stderr)
        return 1

    print(f"\n{'=' * 60}")
    print(f"Language: {language}")
    print(f"{'=' * 60}")
    print(f"  Grammar node types : {report.total_node_types}")
    print(f"  Discovered in corpus: {len(report.discovered_node_types)}")
    discovered_in_grammar = len(
        set(report.discovered_node_types)
        & set(engine.get_all_node_types(language))
    )
    print(f"  In-grammar discovered: {discovered_in_grammar}")
    print(f"  Coverage rate       : {report.coverage_rate:.1f}%")
    print(f"  Missing types       : {len(report.missing_node_types)}")
    print(f"  Wrapper candidates  : {len(report.wrapper_candidates)}")
    print(f"  Analysis time       : {report.elapsed_ms:.1f}ms")

    if args.show_wrappers and report.wrapper_candidates:
        print(f"\n  Wrapper nodes (score >= {engine.wrapper_threshold:.0f}):")
        for wc in report.wrapper_candidates:
            print(
                f"    [{wc.score:3.0f}] {wc.node_type}"
                f"  ({', '.join(wc.reasons)})"
            )

    if args.show_missing and report.missing_node_types:
        print(f"\n  Missing from corpus ({len(report.missing_node_types)}):")
        for nt in report.missing_node_types[:20]:
            print(f"    - {nt}")
        if len(report.missing_node_types) > 20:
            print(f"    ... and {len(report.missing_node_types) - 20} more")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 3 Auto-Discovery: analyze grammar coverage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "language",
        nargs="?",
        help="Language to analyze (e.g. python, typescript)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyze all supported languages",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write Markdown report to FILE",
    )
    parser.add_argument(
        "--show-wrappers",
        action="store_true",
        help="Print wrapper node candidates",
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Print missing node types",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=30.0,
        help="Wrapper detection score threshold (default: 30)",
    )
    args = parser.parse_args()

    if not args.language and not args.all:
        parser.print_help()
        return 1

    engine = AutoDiscoveryEngine(wrapper_threshold=args.threshold)

    if args.all:
        print(f"Analyzing {len(TARGET_LANGUAGES)} languages...")
        results = engine.analyze_all_languages()

        for lang in sorted(results):
            print_language_report(engine, lang, args)

        if args.output:
            report_md = engine.generate_report(results)
            Path(args.output).write_text(report_md, encoding="utf-8")
            print(f"\nReport written to: {args.output}")

        ok_count = sum(1 for r in results.values() if r.is_ok)
        print(f"\n✅  {ok_count}/{len(results)} languages analyzed successfully")
        return 0 if ok_count == len(results) else 1

    else:
        lang = args.language
        if lang not in TARGET_LANGUAGES:
            available = ", ".join(sorted(TARGET_LANGUAGES))
            print(f"Unknown language '{lang}'. Available: {available}", file=sys.stderr)
            return 1

        rc = print_language_report(engine, lang, args)

        if args.output:
            results = {lang: engine.analyze_coverage_gap(lang)}
            report_md = engine.generate_report(results)
            Path(args.output).write_text(report_md, encoding="utf-8")
            print(f"\nReport written to: {args.output}")

        return rc


if __name__ == "__main__":
    sys.exit(main())
