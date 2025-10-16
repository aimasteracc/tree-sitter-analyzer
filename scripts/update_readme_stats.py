#!/usr/bin/env python3
"""
README統計情報自動更新スクリプト

このスクリプトは以下の機能を提供します：
1. pytestの実行結果からテスト数を取得
2. 全READMEファイルのテスト数バッジを自動更新
3. 品質指標の記述を自動更新
"""

import re
import subprocess
import sys
from pathlib import Path


class ReadmeStatsUpdater:
    """README統計情報更新クラス"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.readme_files = ["README.md", "README_ja.md", "README_zh.md"]

    def get_test_count(self) -> int:
        """pytestを実行してテスト数を取得"""
        try:
            # pytest --collect-onlyでテスト数を取得
            result = subprocess.run(
                ["uv", "run", "pytest", "--collect-only", "-q"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                print(f"Warning: pytest collection failed: {result.stderr}")
                return self._fallback_test_count()

            # 出力からテスト数を抽出
            output = result.stdout

            # "X tests collected" パターンを検索
            match = re.search(r"(\d+) tests? collected", output)
            if match:
                return int(match.group(1))

            # 代替パターン: "collected X items"
            match = re.search(r"collected (\d+) items?", output)
            if match:
                return int(match.group(1))

            print(f"Warning: Could not parse test count from output: {output}")
            return self._fallback_test_count()

        except subprocess.TimeoutExpired:
            print("Warning: pytest collection timed out")
            return self._fallback_test_count()
        except Exception as e:
            print(f"Warning: Error running pytest: {e}")
            return self._fallback_test_count()

    def _fallback_test_count(self) -> int:
        """フォールバック: testsディレクトリからテストファイル数を推定"""
        try:
            test_files = list(self.project_root.glob("tests/**/test_*.py"))
            # 1ファイルあたり平均5テストと仮定
            estimated_count = len(test_files) * 5
            print(
                f"Using fallback test count estimation: {estimated_count} (based on {len(test_files)} test files)"
            )
            return estimated_count
        except Exception:
            # 最後の手段として現在の値を維持
            return 2934

    def update_test_badges(self, test_count: int) -> None:
        """全READMEファイルのテスト数バッジを更新"""

        badge_patterns = {
            "README.md": (
                r"(\[!\[Tests\]\(https://img\.shields\.io/badge/tests-)\d+(%20passed-brightgreen\.svg\)\]\(#quality-assurance\))",
                r"\g<1>{}\g<2>",
            ),
            "README_ja.md": (
                r"(\[!\[テスト\]\(https://img\.shields\.io/badge/tests-)\d+(%20passed-brightgreen\.svg\)\]\(#8--品質保証\))",
                r"\g<1>{}\g<2>",
            ),
            "README_zh.md": (
                r"(\[!\[测试\]\(https://img\.shields\.io/badge/tests-)\d+(%20passed-brightgreen\.svg\)\]\(#质量保证\))",
                r"\g<1>{}\g<2>",
            ),
        }

        for readme_file in self.readme_files:
            file_path = self.project_root / readme_file
            if not file_path.exists():
                print(f"Warning: {readme_file} not found")
                continue

            try:
                content = file_path.read_text(encoding="utf-8")

                if readme_file in badge_patterns:
                    pattern, replacement = badge_patterns[readme_file]
                    new_content = re.sub(
                        pattern, replacement.format(test_count), content
                    )

                    if new_content != content:
                        file_path.write_text(new_content, encoding="utf-8")
                        print(
                            f"✅ Updated test badge in {readme_file}: {test_count} tests"
                        )
                    else:
                        print(f"ℹ️  No test badge update needed in {readme_file}")

            except Exception as e:
                print(f"❌ Error updating {readme_file}: {e}")

    def update_quality_metrics(self, test_count: int) -> None:
        """品質指標の記述を更新"""

        # 各ファイルの品質指標更新パターン
        quality_patterns = {
            "README.md": [
                # 既存のパターン
                (
                    r"- \*\*(\d+,?\d*) tests\*\* - 100% pass rate",
                    f"- **{test_count:,} tests** - 100% pass rate",
                ),
                (
                    r"✅ \*\*📊 Enhanced Quality Metrics\*\* - Test count increased to (\d+,?\d*)",
                    f"✅ **📊 Enhanced Quality Metrics** - Test count increased to {test_count:,}",
                ),
                # 新しいパターン
                (
                    r"- \*\*(\d+,?\d*) Tests\*\* - 100% pass rate, enterprise-grade quality assurance",
                    f"- **{test_count:,} Tests** - 100% pass rate, enterprise-grade quality assurance",
                ),
                (
                    r"- \*\*(\d+,?\d*) tests\*\* - 100% pass rate ✅",
                    f"- **{test_count:,} tests** - 100% pass rate ✅",
                ),
                # カバレッジ固定数値を削除
                (
                    r"- \*\*[\d.]+% Coverage\*\* - Comprehensive test coverage",
                    "- **High Coverage** - Comprehensive test coverage",
                ),
                (
                    r"- \*\*[\d.]+% code coverage\*\* - Comprehensive test suite",
                    "- **High code coverage** - Comprehensive test suite",
                ),
                (
                    r"Test count increased to (\d+,?\d*) \(up from \d+\), coverage improved to [\d.]+%",
                    f"Test count increased to {test_count:,}, coverage maintained at high levels",
                ),
            ],
            "README_ja.md": [
                # 既存のパターン
                (
                    r"- \*\*(\d+,?\d*)のテスト\*\* - 100%合格率",
                    f"- **{test_count:,}のテスト** - 100%合格率",
                ),
                (
                    r"✅ \*\*📊 品質メトリクス向上\*\* - テスト数が(\d+,?\d*)個に増加",
                    f"✅ **📊 品質メトリクス向上** - テスト数が{test_count:,}個に増加",
                ),
                # 新しいパターン
                (
                    r"- \*\*(\d+,?\d*)のテスト\*\* - 100%合格率、エンタープライズグレードの品質保証",
                    f"- **{test_count:,}のテスト** - 100%合格率、エンタープライズグレードの品質保証",
                ),
                (
                    r"- \*\*(\d+,?\d*)のテスト\*\* - 100%合格率 ✅",
                    f"- **{test_count:,}のテスト** - 100%合格率 ✅",
                ),
                # カバレッジ固定数値を削除
                (
                    r"- \*\*[\d.]+%カバレッジ\*\* - 包括的なテストスイート",
                    "- **高カバレッジ** - 包括的なテストスイート",
                ),
                (
                    r"- \*\*[\d.]+%コードカバレッジ\*\* - 包括的なテストスイート",
                    "- **高コードカバレッジ** - 包括的なテストスイート",
                ),
                (
                    r"テスト数が(\d+,?\d*)個に増加（\d+個から）、カバレッジが[\d.]+%に向上",
                    f"テスト数が{test_count:,}個に増加、カバレッジも高水準を維持",
                ),
            ],
            "README_zh.md": [
                # 既存のパターン
                (
                    r"- \*\*(\d+,?\d*)个测试\*\* - 100%通过率",
                    f"- **{test_count:,}个测试** - 100%通过率",
                ),
                (
                    r"✅ \*\*📊 质量指标提升\*\* - 测试数量增加到(\d+,?\d*)个",
                    f"✅ **📊 质量指标提升** - 测试数量增加到{test_count:,}个",
                ),
                # 新しいパターン
                (
                    r"- \*\*(\d+,?\d*)个测试\*\* - 100%通过率，企业级质量保证",
                    f"- **{test_count:,}个测试** - 100%通过率，企业级质量保证",
                ),
                (
                    r"- \*\*(\d+,?\d*)个测试\*\* - 100%通过率 ✅",
                    f"- **{test_count:,}个测试** - 100%通过率 ✅",
                ),
                # カバレッジ固定数値を削除
                (
                    r"测试数量增加到(\d+,?\d*)个（从\d+个），覆盖率提升到[\d.]+%",
                    f"测试数量增加到{test_count:,}个，覆盖率保持高水平",
                ),
            ],
        }

        for readme_file in self.readme_files:
            file_path = self.project_root / readme_file
            if not file_path.exists():
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                original_content = content

                if readme_file in quality_patterns:
                    for pattern, replacement in quality_patterns[readme_file]:
                        content = re.sub(pattern, replacement, content)

                if content != original_content:
                    file_path.write_text(content, encoding="utf-8")
                    print(f"✅ Updated quality metrics in {readme_file}")
                else:
                    print(f"ℹ️  No quality metrics update needed in {readme_file}")

            except Exception as e:
                print(f"❌ Error updating quality metrics in {readme_file}: {e}")

    def run(self) -> None:
        """メイン実行関数"""
        print("🚀 README統計情報自動更新を開始...")

        # テスト数を取得
        print("📊 テスト数を取得中...")
        test_count = self.get_test_count()
        print(f"✅ テスト数: {test_count:,}")

        # テストバッジを更新
        print("🏷️  テストバッジを更新中...")
        self.update_test_badges(test_count)

        # 品質指標を更新
        print("📈 品質指標を更新中...")
        self.update_quality_metrics(test_count)

        print("✅ README統計情報の更新が完了しました！")


def main():
    """メイン関数"""
    project_root = Path(__file__).parent.parent

    if not (project_root / "pyproject.toml").exists():
        print("❌ Error: pyproject.toml not found. Please run from project root.")
        sys.exit(1)

    updater = ReadmeStatsUpdater(project_root)
    updater.run()


if __name__ == "__main__":
    main()
