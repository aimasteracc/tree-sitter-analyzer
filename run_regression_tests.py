#!/usr/bin/env python3
"""Regression test runner for async QueryService fix"""

import json
import subprocess
import sys
import time
from pathlib import Path


class RegressionTestRunner:
    """回帰テスト実行クラス"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.results = []

    def run_command(self, cmd, description, timeout=60):
        """コマンド実行とログ出力"""
        print(f"\n🔧 {description}")
        print(f"Command: {' '.join(cmd)}")

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=Path.cwd()
            )
            duration = time.time() - start_time

            if result.returncode == 0:
                print(f"✅ {description} passed ({duration:.2f}s)")
                self.passed += 1
                self.results.append(
                    {
                        "test": description,
                        "status": "PASSED",
                        "duration": duration,
                        "output": result.stdout[:500] if result.stdout else "",
                    }
                )
                return True
            else:
                print(f"❌ {description} failed ({duration:.2f}s)")
                print(f"STDOUT: {result.stdout[:500]}")
                print(f"STDERR: {result.stderr[:500]}")
                self.failed += 1
                self.results.append(
                    {
                        "test": description,
                        "status": "FAILED",
                        "duration": duration,
                        "stdout": result.stdout[:500],
                        "stderr": result.stderr[:500],
                    }
                )
                return False

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"⏰ {description} timed out ({duration:.2f}s)")
            self.failed += 1
            self.results.append(
                {"test": description, "status": "TIMEOUT", "duration": duration}
            )
            return False
        except Exception as e:
            duration = time.time() - start_time
            print(f"💥 {description} error: {e} ({duration:.2f}s)")
            self.failed += 1
            self.results.append(
                {
                    "test": description,
                    "status": "ERROR",
                    "duration": duration,
                    "error": str(e),
                }
            )
            return False

    def run_pytest_test(self, test_path, description, markers="", timeout=120):
        """pytestテストの実行"""
        cmd = ["python", "-m", "pytest", test_path, "-v", "--tb=short"]
        if markers:
            cmd.extend(["-m", markers])

        return self.run_command(cmd, description, timeout)

    def check_dependencies(self):
        """依存関係の確認"""
        print("🔍 Checking dependencies...")

        dependencies = [
            (["python", "-c", "import pytest"], "pytest availability"),
            (["python", "-c", "import asyncio"], "asyncio availability"),
            (
                ["python", "-c", "import tree_sitter_analyzer"],
                "tree_sitter_analyzer import",
            ),
            (
                [
                    "python",
                    "-c",
                    "from tree_sitter_analyzer.core.query_service import QueryService",
                ],
                "QueryService import",
            ),
            (
                [
                    "python",
                    "-c",
                    "from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool",
                ],
                "QueryTool import",
            ),
        ]

        for cmd, desc in dependencies:
            if not self.run_command(cmd, desc, timeout=10):
                print(f"❌ Dependency check failed: {desc}")
                return False

        print("✅ All dependencies available")
        return True

    def run_new_async_tests(self):
        """新規非同期テストの実行"""
        print("\n📋 Running new async tests...")

        tests = [
            ("tests/test_async_query_service.py", "Async QueryService tests"),
            ("tests/test_cli_async_integration.py", "CLI async integration tests"),
            ("tests/test_mcp_async_integration.py", "MCP async integration tests"),
            ("tests/test_async_performance.py", "Async performance tests"),
        ]

        all_passed = True
        for test_path, description in tests:
            if Path(test_path).exists():
                if not self.run_pytest_test(test_path, description):
                    all_passed = False
            else:
                print(f"⚠️ Test file not found: {test_path}")
                self.skipped += 1

        return all_passed

    def run_existing_core_tests(self):
        """既存のコアテストの実行"""
        print("\n📋 Running existing core tests...")

        # 重要な既存テストファイルを特定
        core_tests = [
            ("tests/test_query_service.py", "Core QueryService tests"),
            (
                "tests/test_mcp_query_tool_definition.py",
                "MCP QueryTool definition tests",
            ),
            ("tests/test_mcp_server.py", "MCP server tests"),
            ("tests/test_engine.py", "Analysis engine tests"),
            ("tests/test_main_entry.py", "Main entry tests"),
        ]

        all_passed = True
        for test_path, description in core_tests:
            if Path(test_path).exists():
                if not self.run_pytest_test(test_path, description):
                    all_passed = False
            else:
                print(f"⚠️ Core test file not found: {test_path}")
                self.skipped += 1

        return all_passed

    def run_integration_tests(self):
        """統合テストの実行"""
        print("\n📋 Running integration tests...")

        integration_tests = [
            ("tests/test_mcp_tools_integration.py", "MCP tools integration tests"),
            ("tests/test_tree_sitter_integration.py", "Tree-sitter integration tests"),
        ]

        all_passed = True
        for test_path, description in integration_tests:
            if Path(test_path).exists():
                if not self.run_pytest_test(test_path, description):
                    all_passed = False
            else:
                print(f"⚠️ Integration test file not found: {test_path}")
                self.skipped += 1

        return all_passed

    def run_emergency_fix_verification(self):
        """緊急修正の検証"""
        print("\n📋 Running emergency fix verification...")

        if Path("test_emergency_fix.py").exists():
            return self.run_command(
                ["python", "test_emergency_fix.py"],
                "Emergency fix verification",
                timeout=30,
            )
        else:
            print("⚠️ Emergency fix test not found")
            self.skipped += 1
            return True

    def run_sample_queries(self):
        """サンプルクエリの実行テスト"""
        print("\n📋 Running sample query tests...")

        sample_tests = [
            (
                [
                    "python",
                    "-m",
                    "tree_sitter_analyzer",
                    "query",
                    "--file-path",
                    "examples/sample.py",
                    "--query-key",
                    "function",
                ],
                "Sample Python function query",
            ),
            (
                [
                    "python",
                    "-m",
                    "tree_sitter_analyzer",
                    "query",
                    "--file-path",
                    "examples/ModernJavaScript.js",
                    "--query-key",
                    "function",
                ],
                "Sample JavaScript function query",
            ),
        ]

        all_passed = True
        for cmd, description in sample_tests:
            # サンプルファイルが存在する場合のみ実行
            file_path = cmd[cmd.index("--file-path") + 1]
            if Path(file_path).exists():
                if not self.run_command(cmd, description, timeout=30):
                    all_passed = False
            else:
                print(f"⚠️ Sample file not found: {file_path}")
                self.skipped += 1

        return all_passed

    def run_comprehensive_test_suite(self):
        """包括的テストスイートの実行"""
        print("\n📋 Running comprehensive test suite...")

        # 全テストの実行（失敗時に停止しない）
        return self.run_command(
            ["python", "-m", "pytest", "tests/", "--tb=short", "-x"],
            "Comprehensive test suite",
            timeout=300,  # 5分のタイムアウト
        )

    def generate_report(self):
        """テスト結果レポートの生成"""
        print("\n📊 Regression test results:")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"⚠️ Skipped: {self.skipped}")

        total_tests = self.passed + self.failed
        if total_tests > 0:
            success_rate = (self.passed / total_tests) * 100
            print(f"📈 Success rate: {success_rate:.1f}%")

        # 詳細レポートをJSONファイルに保存
        report = {
            "summary": {
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "success_rate": (self.passed / (self.passed + self.failed)) * 100
                if (self.passed + self.failed) > 0
                else 0,
            },
            "results": self.results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            with open("regression_test_report.json", "w") as f:
                json.dump(report, f, indent=2)
            print("📄 Detailed report saved to: regression_test_report.json")
        except Exception as e:
            print(f"⚠️ Could not save report: {e}")

        return self.failed == 0

    def run_all_tests(self):
        """全ての回帰テストを実行"""
        print(
            "🚀 Starting comprehensive regression tests for async QueryService fix..."
        )
        print(f"Working directory: {Path.cwd()}")

        # 1. 依存関係の確認
        if not self.check_dependencies():
            print("💥 Dependency check failed! Cannot proceed with tests.")
            return False

        # 2. 緊急修正の検証
        self.run_emergency_fix_verification()

        # 3. 新規非同期テストの実行
        self.run_new_async_tests()

        # 4. 既存コアテストの実行
        self.run_existing_core_tests()

        # 5. 統合テストの実行
        self.run_integration_tests()

        # 6. サンプルクエリテスト
        self.run_sample_queries()

        # 7. 包括的テストスイート（オプション）
        print("\n📋 Running final comprehensive test suite...")
        self.run_comprehensive_test_suite()

        # 8. レポート生成
        success = self.generate_report()

        if success:
            print("🎉 All regression tests passed!")
            print("✅ Async QueryService fix is ready for production!")
        else:
            print("💥 Some regression tests failed!")
            print("❌ Please review the failures before proceeding.")

        return success


def main():
    """メイン実行関数"""
    runner = RegressionTestRunner()
    success = runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
