#!/usr/bin/env python3
"""
Phase 7 Integration Test Runner

Phase 7の統合テストを実行し、エンタープライズ準備状況を検証するスクリプト
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


class Phase7TestRunner:
    """Phase 7統合テストランナー"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.test_results = {}
        self.start_time = None
        self.end_time = None

    def run_all_tests(self, verbose: bool = False, coverage: bool = False) -> bool:
        """全統合テストを実行"""
        print("🚀 Starting Phase 7 Integration Test Suite")
        print("=" * 60)

        self.start_time = time.time()

        # テストカテゴリ定義
        test_categories = [
            {
                "name": "End-to-End Tests",
                "path": "tests/integration/test_phase7_end_to_end.py",
                "description": "エンドツーエンド統合テスト",
            },
            {
                "name": "Performance Tests",
                "path": "tests/integration/test_phase7_performance_integration.py",
                "description": "パフォーマンス統合テスト",
            },
            {
                "name": "Security Tests",
                "path": "tests/integration/test_phase7_security_integration.py",
                "description": "セキュリティ統合テスト",
            },
            {
                "name": "Integration Suite",
                "path": "tests/integration/test_phase7_integration_suite.py",
                "description": "統合テストスイート",
            },
        ]

        overall_success = True

        for category in test_categories:
            print(f"\n📋 Running {category['name']}...")
            print(f"   {category['description']}")
            print("-" * 40)

            success = self._run_test_category(category, verbose, coverage)
            overall_success = overall_success and success

            if success:
                print(f"✅ {category['name']} completed successfully")
            else:
                print(f"❌ {category['name']} failed")

        self.end_time = time.time()

        # 結果レポート生成
        self._generate_final_report()

        return overall_success

    def _run_test_category(self, category: dict, verbose: bool, coverage: bool) -> bool:
        """テストカテゴリを実行"""
        test_path = self.project_root / category["path"]

        if not test_path.exists():
            print(f"⚠️  Test file not found: {test_path}")
            self.test_results[category["name"]] = {
                "success": False,
                "error": "Test file not found",
                "duration": 0,
            }
            return False

        # pytest実行コマンド構築
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_path),
            "-v" if verbose else "-q",
            "--tb=short",
        ]

        if coverage:
            cmd.extend(["--cov=tree_sitter_analyzer", "--cov-report=term-missing"])

        # テスト実行
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5分タイムアウト
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            self.test_results[category["name"]] = {
                "success": success,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

            if verbose or not success:
                print(f"STDOUT:\n{result.stdout}")
                if result.stderr:
                    print(f"STDERR:\n{result.stderr}")

            print(f"Duration: {duration:.2f}s")

            return success

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"❌ Test timed out after {duration:.2f}s")

            self.test_results[category["name"]] = {
                "success": False,
                "error": "Timeout",
                "duration": duration,
            }

            return False

        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ Test execution failed: {e}")

            self.test_results[category["name"]] = {
                "success": False,
                "error": str(e),
                "duration": duration,
            }

            return False

    def _generate_final_report(self):
        """最終レポート生成"""
        total_duration = (
            self.end_time - self.start_time if self.start_time and self.end_time else 0
        )

        print("\n" + "=" * 60)
        print("📊 PHASE 7 INTEGRATION TEST FINAL REPORT")
        print("=" * 60)

        # 基本統計
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results.values() if r["success"])
        failed_tests = total_tests - successful_tests
        success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0

        print(f"⏱️  Total Execution Time: {total_duration:.2f} seconds")
        print(f"📋 Test Categories: {total_tests}")
        print(f"✅ Successful: {successful_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"📈 Success Rate: {success_rate:.1f}%")

        # カテゴリ別結果
        print("\n📂 Results by Category:")
        print("-" * 40)

        for category, result in self.test_results.items():
            status_icon = "✅" if result["success"] else "❌"
            duration = result.get("duration", 0)

            print(f"{status_icon} {category}: {duration:.2f}s")

            if not result["success"]:
                error = result.get("error", "Unknown error")
                print(f"   Error: {error}")

        # 品質評価
        print("\n🎯 Enterprise Readiness Assessment:")
        print("-" * 40)

        if success_rate >= 95:
            quality_status = "🌟 EXCELLENT - Enterprise Ready"
            quality_desc = "All systems operational, ready for production deployment"
        elif success_rate >= 90:
            quality_status = "✅ GOOD - Production Ready"
            quality_desc = (
                "Minor issues detected, suitable for production with monitoring"
            )
        elif success_rate >= 80:
            quality_status = "⚠️ ACCEPTABLE - Needs Improvement"
            quality_desc = "Significant issues require attention before production"
        else:
            quality_status = "❌ POOR - Not Ready"
            quality_desc = "Critical issues must be resolved before deployment"

        print(f"Overall Status: {quality_status}")
        print(f"Assessment: {quality_desc}")

        # パフォーマンス評価
        avg_duration = (
            sum(r.get("duration", 0) for r in self.test_results.values()) / total_tests
            if total_tests > 0
            else 0
        )

        if avg_duration < 30:
            perf_status = "🚀 EXCELLENT"
        elif avg_duration < 60:
            perf_status = "✅ GOOD"
        elif avg_duration < 120:
            perf_status = "⚠️ ACCEPTABLE"
        else:
            perf_status = "❌ POOR"

        print(f"Performance: {perf_status} (avg: {avg_duration:.2f}s per category)")

        # 結果保存
        self._save_report()

        print("\n" + "=" * 60)

        if success_rate >= 95:
            print("🎉 Phase 7 Integration Tests PASSED!")
            print("✅ System is ready for enterprise deployment!")
        else:
            print("⚠️  Phase 7 Integration Tests completed with issues")
            print("❌ Please review and fix issues before deployment")

    def _save_report(self):
        """レポートをファイルに保存"""
        report_data = {
            "timestamp": time.time(),
            "total_duration": self.end_time - self.start_time
            if self.start_time and self.end_time
            else 0,
            "test_results": self.test_results,
            "summary": {
                "total_categories": len(self.test_results),
                "successful": sum(
                    1 for r in self.test_results.values() if r["success"]
                ),
                "failed": sum(
                    1 for r in self.test_results.values() if not r["success"]
                ),
                "success_rate": (
                    sum(1 for r in self.test_results.values() if r["success"])
                    / len(self.test_results)
                )
                * 100
                if self.test_results
                else 0,
            },
        }

        report_file = (
            self.project_root / "tests" / "integration" / "phase7_test_report.json"
        )
        report_file.parent.mkdir(parents=True, exist_ok=True)

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"📄 Detailed report saved to: {report_file}")


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="Run Phase 7 Integration Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_phase7_integration_tests.py
  python scripts/run_phase7_integration_tests.py --verbose
  python scripts/run_phase7_integration_tests.py --coverage
  python scripts/run_phase7_integration_tests.py --verbose --coverage
        """,
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    parser.add_argument(
        "--coverage", "-c", action="store_true", help="Enable coverage reporting"
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Project root directory (default: auto-detect)",
    )

    args = parser.parse_args()

    # プロジェクトルート確認
    if not (args.project_root / "pyproject.toml").exists():
        print(f"❌ Project root not found: {args.project_root}")
        print("Please specify correct project root with --project-root")
        sys.exit(1)

    # テストランナー実行
    runner = Phase7TestRunner(args.project_root)
    success = runner.run_all_tests(verbose=args.verbose, coverage=args.coverage)

    # 終了コード設定
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
