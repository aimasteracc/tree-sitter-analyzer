#!/usr/bin/env python3
"""
覆盖率监控脚本。

用于检查、报告和分析测试覆盖率。
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


class CoverageMonitor:
    """覆盖率监控器。"""

    def __init__(self, project_root: Path) -> None:
        """初始化覆盖率监控器。

        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root
        self.coverage_file = project_root / ".coverage"
        self.coverage_json = project_root / "coverage.json"
        self.trend_file = project_root / ".coverage_trend.json"

    def run_coverage(self, target: str | None = None, verbose: bool = False) -> int:
        """运行覆盖率检查。

        Args:
            target: 测试目标（例如：tests/unit/）
            verbose: 是否显示详细输出

        Returns:
            退出代码
        """
        cmd = [
            "uv",
            "run",
            "pytest",
            "--cov=tree_sitter_analyzer",
            "--cov-report=term-missing",
            "--cov-report=json",
        ]

        if target:
            cmd.append(target)

        if verbose:
            cmd.append("-v")

        result = subprocess.run(cmd, cwd=self.project_root)
        return result.returncode

    def get_coverage_data(self) -> dict:
        """获取覆盖率数据。

        Returns:
            覆盖率数据字典
        """
        if not self.coverage_json.exists():
            return {}

        with open(self.coverage_json, encoding="utf-8") as f:
            return json.load(f)

    def get_overall_coverage(self) -> float:
        """获取总体覆盖率。

        Returns:
            总体覆盖率百分比
        """
        data = self.get_coverage_data()
        return data.get("totals", {}).get("percent_covered", 0.0)

    def get_module_coverage(self, module_name: str) -> dict:
        """获取特定模块的覆盖率。

        Args:
            module_name: 模块名称

        Returns:
            模块覆盖率数据
        """
        data = self.get_coverage_data()
        files = data.get("files", [])

        for file_data in files:
            if module_name in file_data.get("filename", ""):
                return file_data

        return {}

    def get_low_coverage_files(self, threshold: float = 80.0) -> list[dict]:
        """获取低覆盖率文件列表。

        Args:
            threshold: 覆盖率阈值（百分比）

        Returns:
            低覆盖率文件列表
        """
        data = self.get_coverage_data()
        files = data.get("files", [])

        low_coverage_files = []
        for file_data in files:
            summary = file_data.get("summary", {})
            percent_covered = summary.get("percent_covered", 0.0)

            if percent_covered < threshold:
                low_coverage_files.append(
                    {
                        "filename": file_data.get("filename", ""),
                        "percent_covered": percent_covered,
                        "lines_covered": summary.get("covered_lines", 0),
                        "lines_missing": summary.get("missing_lines", 0),
                        "total_lines": summary.get("num_statements", 0),
                    }
                )

        return low_coverage_files

    def get_uncovered_lines(self, file_path: str) -> list[int]:
        """获取文件的未覆盖行号。

        Args:
            file_path: 文件路径

        Returns:
            未覆盖行号列表
        """
        data = self.get_coverage_data()
        files = data.get("files", [])

        for file_data in files:
            if file_path in file_data.get("filename", ""):
                missing_lines = file_data.get("missing_lines", [])
                return [line["line_number"] for line in missing_lines]

        return []

    def save_trend(self, coverage: float) -> None:
        """保存覆盖率趋势数据。

        Args:
            coverage: 当前覆盖率
        """
        trend_data = []

        # 加载现有趋势数据
        if self.trend_file.exists():
            with open(self.trend_file, encoding="utf-8") as f:
                trend_data = json.load(f)

        # 添加新数据点
        trend_data.append(
            {"timestamp": datetime.now(UTC).isoformat(), "coverage": coverage}
        )

        # 保留最近100个数据点
        if len(trend_data) > 100:
            trend_data = trend_data[-100:]

        # 保存趋势数据
        with open(self.trend_file, "w", encoding="utf-8") as f:
            json.dump(trend_data, f, indent=2)

    def get_trend(self) -> list[dict]:
        """获取覆盖率趋势数据。

        Returns:
            趋势数据列表
        """
        if not self.trend_file.exists():
            return []

        with open(self.trend_file, encoding="utf-8") as f:
            return json.load(f)

    def generate_report(self, output_file: Path | None = None) -> str:
        """生成覆盖率报告。

        Args:
            output_file: 输出文件路径

        Returns:
            报告内容
        """
        overall_coverage = self.get_overall_coverage()
        low_coverage_files = self.get_low_coverage_files()
        trend_data = self.get_trend()

        # 生成报告
        report_lines = [
            "# 覆盖率报告",
            "",
            f"生成时间: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "## 总体覆盖率",
            "",
            f"**{overall_coverage:.2f}%**",
            "",
            "## 低覆盖率文件",
            "",
        ]

        if low_coverage_files:
            report_lines.append("| 文件 | 覆盖率 | 覆盖行数 | 缺失行数 | 总行数 |")
            report_lines.append("|------|--------|----------|----------|--------|")

            for file_data in sorted(
                low_coverage_files, key=lambda x: x["percent_covered"]
            ):
                filename = file_data["filename"]
                percent = file_data["percent_covered"]
                covered = file_data["lines_covered"]
                missing = file_data["lines_missing"]
                total = file_data["total_lines"]

                report_lines.append(
                    f"| {filename} | {percent:.2f}% | {covered} | {missing} | {total} |"
                )
        else:
            report_lines.append("✅ 所有文件覆盖率都在80%以上！")

        report_lines.extend(
            [
                "",
                "## 覆盖率趋势",
                "",
            ]
        )

        if trend_data:
            # 计算趋势
            recent = trend_data[-10:]  # 最近10个数据点
            if len(recent) >= 2:
                first_coverage = recent[0]["coverage"]
                last_coverage = recent[-1]["coverage"]
                change = last_coverage - first_coverage

                if change > 0:
                    trend_str = f"📈 上升 {change:.2f}%"
                elif change < 0:
                    trend_str = f"📉 下降 {abs(change):.2f}%"
                else:
                    trend_str = "➡️ 持平"

                report_lines.append(f"**{trend_str}**")

            report_lines.append("")
            report_lines.append("| 时间 | 覆盖率 |")
            report_lines.append("|------|--------|")

            for data_point in trend_data[-10:]:
                timestamp = data_point["timestamp"][:19]  # 移除时区信息
                coverage = data_point["coverage"]
                report_lines.append(f"| {timestamp} | {coverage:.2f}% |")
        else:
            report_lines.append("暂无趋势数据")

        report = "\n".join(report_lines)

        # 保存到文件
        if output_file:
            output_file.write_text(report, encoding="utf-8")
            print(f"报告已保存到: {output_file}")

        return report

    def check_threshold(self, threshold: float = 80.0) -> bool:
        """检查覆盖率是否达到阈值。

        Args:
            threshold: 覆盖率阈值

        Returns:
            是否达到阈值
        """
        coverage = self.get_overall_coverage()
        return coverage >= threshold

    def print_summary(self) -> None:
        """打印覆盖率摘要。"""
        coverage = self.get_overall_coverage()
        low_coverage_files = self.get_low_coverage_files()

        print(f"\n{'=' * 60}")
        print("覆盖率摘要")
        print(f"{'=' * 60}")
        print(f"\n总体覆盖率: {coverage:.2f}%")

        if low_coverage_files:
            print(f"\n⚠️  {len(low_coverage_files)} 个文件覆盖率低于80%:")
            for file_data in low_coverage_files[:10]:  # 只显示前10个
                filename = file_data["filename"]
                percent = file_data["percent_covered"]
                print(f"  - {filename}: {percent:.2f}%")

            if len(low_coverage_files) > 10:
                print(f"  ... 还有 {len(low_coverage_files) - 10} 个文件")
        else:
            print("\n✅ 所有文件覆盖率都在80%以上！")

        print(f"\n{'=' * 60}\n")


def main():
    """主函数。"""
    parser = argparse.ArgumentParser(
        description="覆盖率监控脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 运行覆盖率检查
    run_parser = subparsers.add_parser("run", help="运行覆盖率检查")
    run_parser.add_argument("--target", help="测试目标（例如：tests/unit/）")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="显示详细输出")

    # 生成报告
    report_parser = subparsers.add_parser("report", help="生成覆盖率报告")
    report_parser.add_argument("--output", type=Path, help="输出文件路径")

    # 检查阈值
    check_parser = subparsers.add_parser("check", help="检查覆盖率阈值")
    check_parser.add_argument(
        "--threshold", type=float, default=80.0, help="覆盖率阈值（默认：80.0）"
    )

    # 获取低覆盖率文件
    low_parser = subparsers.add_parser("low", help="获取低覆盖率文件")
    low_parser.add_argument(
        "--threshold", type=float, default=80.0, help="覆盖率阈值（默认：80.0）"
    )

    # 显示趋势
    _ = subparsers.add_parser("trend", help="显示覆盖率趋势")

    # 显示摘要
    _ = subparsers.add_parser("summary", help="显示覆盖率摘要")

    args = parser.parse_args()

    # 获取项目根目录
    project_root = Path(__file__).parent.parent

    # 创建监控器
    monitor = CoverageMonitor(project_root)

    # 执行命令
    if args.command == "run":
        exit_code = monitor.run_coverage(args.target, args.verbose)

        # 保存趋势数据
        coverage = monitor.get_overall_coverage()
        monitor.save_trend(coverage)

        sys.exit(exit_code)

    elif args.command == "report":
        report = monitor.generate_report(args.output)
        print(report)

    elif args.command == "check":
        threshold = args.threshold
        coverage = monitor.get_overall_coverage()

        if monitor.check_threshold(threshold):
            print(f"✅ 覆盖率 {coverage:.2f}% 达到阈值 {threshold}%")
            sys.exit(0)
        else:
            print(f"❌ 覆盖率 {coverage:.2f}% 未达到阈值 {threshold}%")
            sys.exit(1)

    elif args.command == "low":
        threshold = args.threshold
        low_coverage_files = monitor.get_low_coverage_files(threshold)

        if low_coverage_files:
            print(f"\n⚠️  {len(low_coverage_files)} 个文件覆盖率低于 {threshold}%:")
            for file_data in low_coverage_files:
                filename = file_data["filename"]
                percent = file_data["percent_covered"]
                print(f"  - {filename}: {percent:.2f}%")
        else:
            print(f"\n✅ 所有文件覆盖率都在 {threshold}% 以上！")

    elif args.command == "trend":
        trend_data = monitor.get_trend()

        if trend_data:
            print("\n覆盖率趋势:")
            print("-" * 40)
            for data_point in trend_data[-20:]:
                timestamp = data_point["timestamp"][:19]
                coverage = data_point["coverage"]
                bar_length = int(coverage / 2)  # 每2%一个字符
                bar = "█" * bar_length + "░" * (50 - bar_length)
                print(f"{timestamp} | {bar} {coverage:.2f}%")
        else:
            print("\n暂无趋势数据")
            print("提示：运行 'python scripts/monitor_coverage.py run' 来生成趋势数据")

    elif args.command == "summary":
        monitor.print_summary()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
