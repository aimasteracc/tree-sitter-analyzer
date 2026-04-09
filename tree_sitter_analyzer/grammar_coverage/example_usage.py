#!/usr/bin/env python3
"""
Grammar Coverage Validator - Example Usage

演示如何使用 grammar coverage validator 验证语言插件的覆盖度。

Usage:
    python -m tree_sitter_analyzer.grammar_coverage.example_usage
"""

from tree_sitter_analyzer.grammar_coverage import (
    check_coverage_threshold,
    generate_coverage_report,
    validate_plugin_coverage_sync,
)


def main() -> None:
    """运行 grammar coverage 验证示例"""
    print("Grammar Coverage Validator - Example Usage\n")
    print("=" * 70)

    # 示例 1: 验证 Python 插件覆盖度
    print("\n1. Validating Python plugin coverage...")
    print("-" * 70)

    try:
        report = validate_plugin_coverage_sync("python")

        # 生成人类可读的报告
        report_text = generate_coverage_report(report)
        print(report_text)

        # 检查是否达到 100% 阈值
        print("\n" + "=" * 70)
        if check_coverage_threshold(report.coverage_percentage, threshold=100.0):
            print("✓ Coverage meets 100% threshold")
        else:
            print(
                f"✗ Coverage below 100% threshold: {report.coverage_percentage:.1f}%"
            )
            print(f"  Need to cover {len(report.uncovered_types)} more node types")

    except Exception as e:
        print(f"Error validating Python coverage: {e}")

    # 示例 2: 验证 JavaScript 插件覆盖度
    print("\n" + "=" * 70)
    print("\n2. Validating JavaScript plugin coverage...")
    print("-" * 70)

    try:
        report = validate_plugin_coverage_sync("javascript")
        report_text = generate_coverage_report(report)
        print(report_text)

        print("\n" + "=" * 70)
        if check_coverage_threshold(report.coverage_percentage, threshold=100.0):
            print("✓ Coverage meets 100% threshold")
        else:
            print(
                f"✗ Coverage below 100% threshold: {report.coverage_percentage:.1f}%"
            )

    except Exception as e:
        print(f"Error validating JavaScript coverage: {e}")

    # 示例 3: CI 集成示例
    print("\n" + "=" * 70)
    print("\n3. CI Integration Example (Exit code based on threshold)")
    print("-" * 70)

    languages_to_check = ["python", "javascript", "go"]
    all_passed = True

    for language in languages_to_check:
        try:
            report = validate_plugin_coverage_sync(language)
            passed = check_coverage_threshold(report.coverage_percentage)

            status = "PASS" if passed else "FAIL"
            print(
                f"{status}: {language.capitalize()} - "
                f"{report.coverage_percentage:.1f}% "
                f"({report.covered_node_types}/{report.total_node_types})"
            )

            if not passed:
                all_passed = False

        except Exception as e:
            print(f"ERROR: {language.capitalize()} - {e}")
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✓ All languages meet 100% coverage threshold")
        print("Exit code: 0")
    else:
        print("✗ Some languages are below 100% coverage threshold")
        print("Exit code: 1")


if __name__ == "__main__":
    main()
