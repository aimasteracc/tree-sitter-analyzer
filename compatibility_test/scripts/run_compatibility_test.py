#!/usr/bin/env python3
"""
tree-sitter-analyzer MCP互換性テスト標準化スクリプト

使用方法:
    python compatibility_test/scripts/run_compatibility_test.py --version-a 1.9.2 --version-b 1.9.3
"""

import argparse
import asyncio
import difflib
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# キャッシュ管理のインポート
try:
    from ..utils.cache_manager import CacheManager
    from ..utils.cache_reporter import CacheReporter
except ImportError:
    # 相対インポートが失敗した場合の代替
    sys.path.append(str(Path(__file__).parent.parent))
    from utils.cache_manager import CacheManager
    from utils.cache_reporter import CacheReporter


def _set_project_path_result(params: dict[str, Any]) -> dict[str, Any]:
    project_path = params.get("project_path")
    if not project_path:
        raise ValueError("project_path parameter is required")
    return {"status": "success", "project_root": project_path}


def _load_mcp_tool_class(tool_name: str) -> type[Any]:
    if tool_name == "check_code_scale":
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        return AnalyzeScaleTool

    if tool_name == "analyze_code_structure":
        from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

        return TableFormatTool

    if tool_name == "query_code":
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        return QueryTool

    if tool_name == "extract_code_section":
        from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

        return ReadPartialTool

    if tool_name == "list_files":
        from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool

        return ListFilesTool

    if tool_name == "find_and_grep":
        from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool

        return FindAndGrepTool

    if tool_name == "search_content":
        from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

        return SearchContentTool

    raise ValueError(f"未知のツール名: {tool_name}")


class StandardizedCompatibilityTester:
    def __init__(
        self,
        version_a: str,
        version_b: str,
        project_root: str | None = None,
        clear_cache: bool = True,
    ):
        self.version_a = version_a
        self.version_b = version_b
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.compatibility_test_dir = self.project_root / "compatibility_test"
        self.mcp_settings_path = (
            Path.home()
            / "AppData/Roaming/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json"
        )

        # キャッシュ管理
        self.cache_manager = CacheManager(str(self.project_root))
        self.cache_reporter = CacheReporter(str(self.project_root))
        self.clear_cache = clear_cache

        # 結果ディレクトリ
        self.results_dir = self.compatibility_test_dir / "results"
        self.version_a_dir = self.results_dir / f"v{version_a}"
        self.version_b_dir = self.results_dir / f"v{version_b}"

        # テストケース
        self.test_cases_file = self.compatibility_test_dir / "test_cases.json"
        self.test_cases = {}

        # 結果
        self.test_results = {
            "version_a": version_a,
            "version_b": version_b,
            "test_date": datetime.now().isoformat(),
            "results": {},
            "summary": {},
            "cache_info": {},
        }

    def setup_directories(self):
        """必要なディレクトリを作成（既存ファイルのクリーンアップを含む）"""
        # テスト前のクリーンアップ
        self._cleanup_test_directories()

        # ディレクトリ作成
        self.version_a_dir.mkdir(parents=True, exist_ok=True)
        self.version_b_dir.mkdir(parents=True, exist_ok=True)
        (self.compatibility_test_dir / "reports").mkdir(exist_ok=True)
        print("✅ ディレクトリ構造を作成しました")

    def _cleanup_test_directories(self):
        """テスト結果とレポートディレクトリをクリーンアップ"""
        print("🧹 テスト前のクリーンアップを実行中...")

        cleanup_stats = {"results_cleaned": 0, "reports_cleaned": 0, "errors": []}

        # resultsディレクトリのクリーンアップ
        if self.results_dir.exists():
            try:
                for item in self.results_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                        cleanup_stats["results_cleaned"] += 1
                        print(f"  🗑️ 削除: {item.name}/")
                    elif item.is_file():
                        item.unlink()
                        cleanup_stats["results_cleaned"] += 1
                        print(f"  🗑️ 削除: {item.name}")
            except Exception as e:
                error_msg = f"resultsディレクトリクリーンアップエラー: {e}"
                cleanup_stats["errors"].append(error_msg)
                print(f"  ⚠️ {error_msg}")

        # reportsディレクトリのクリーンアップ
        reports_dir = self.compatibility_test_dir / "reports"
        if reports_dir.exists():
            try:
                for item in reports_dir.iterdir():
                    if item.is_file() and item.name.startswith("comparison_report_"):
                        item.unlink()
                        cleanup_stats["reports_cleaned"] += 1
                        print(f"  🗑️ 削除: {item.name}")
            except Exception as e:
                error_msg = f"reportsディレクトリクリーンアップエラー: {e}"
                cleanup_stats["errors"].append(error_msg)
                print(f"  ⚠️ {error_msg}")

        # クリーンアップ結果の表示
        total_cleaned = (
            cleanup_stats["results_cleaned"] + cleanup_stats["reports_cleaned"]
        )
        if total_cleaned > 0:
            print(
                f"✅ {total_cleaned} 個のファイル/ディレクトリをクリーンアップしました"
            )
        else:
            print("✅ クリーンアップ対象なし（既にクリーンな状態）")

        if cleanup_stats["errors"]:
            print(
                f"⚠️ クリーンアップ中に {len(cleanup_stats['errors'])} 件のエラーが発生しました"
            )

    def load_test_cases(self):
        """テストケースを読み込み"""
        try:
            with open(self.test_cases_file, encoding="utf-8") as f:
                self.test_cases = json.load(f)
            print(f"✅ テストケースを読み込みました: {len(self.test_cases)} ツール")
        except Exception as e:
            print(f"❌ テストケース読み込みエラー: {e}")
            sys.exit(1)

    def load_mcp_settings(self) -> dict[str, Any]:
        """mcp_settings.jsonを読み込む"""
        try:
            with open(self.mcp_settings_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ mcp_settings.json読み込みエラー: {e}")
            return {}

    def save_mcp_settings(self, settings: dict[str, Any]) -> bool:
        """mcp_settings.jsonを保存する"""
        try:
            with open(self.mcp_settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ mcp_settings.json保存エラー: {e}")
            return False

    def enable_version(self, version: str) -> bool:
        """指定されたバージョンを有効化し、他を無効化する"""
        settings = self.load_mcp_settings()
        if not settings:
            return False

        # 全てのtree-sitter-analyzerサーバーを無効化
        for server_name in settings.get("mcpServers", {}):
            if "tree-sitter-analyzer" in server_name:
                settings["mcpServers"][server_name]["disabled"] = True

        # 指定されたバージョンのみ有効化
        target_servers = [
            f"tree-sitter-analyzer-{version}",
            f"tree-sitter-analyzer-v{version}",
            f"tree-sitter-analyzer-{version.replace('.', '-')}",
        ]

        enabled = False
        for target_server in target_servers:
            if target_server in settings.get("mcpServers", {}):
                settings["mcpServers"][target_server]["disabled"] = False
                print(f"✅ {target_server}を有効化しました")
                enabled = True
                break

        if not enabled:
            print(f"❌ バージョン {version} のサーバー設定が見つかりません")
            print(f"利用可能なサーバー: {list(settings.get('mcpServers', {}).keys())}")
            return False

        return self.save_mcp_settings(settings)

    def wait_for_server_startup(self, timeout: int = 10):
        """MCPサーバーの起動を待機"""
        print(f"⏳ MCPサーバー起動待機中... ({timeout}秒)")
        time.sleep(timeout)

    async def execute_test_case(
        self, tool_name: str, test_case: dict[str, Any], output_dir: Path
    ) -> dict[str, Any]:
        """個別のテストケースを実行"""
        test_id = test_case["id"]
        params = test_case["params"]
        output_file = test_case["output_file"]

        print(f"  🧪 実行中: {tool_name}.{test_id}")

        # パラメータの{PROJECT_ROOT}を実際のパスに置換
        processed_params = self._process_params(params)

        result = {
            "test_id": test_id,
            "tool_name": tool_name,
            "params": processed_params,
            "output_file": output_file,
            "status": "unknown",
            "error": None,
            "execution_time": 0,
        }

        start_time = time.time()

        try:
            # 実際のMCPツールを実行
            tool_result = await self._execute_mcp_tool(tool_name, processed_params)
            result["status"] = "success"

            # 実際のツール結果を出力ファイルに保存
            output_path = output_dir / output_file
            with open(output_path, "w", encoding="utf-8") as f:
                if isinstance(tool_result, dict):
                    f.write(json.dumps(tool_result, indent=2, ensure_ascii=False))
                else:
                    f.write(str(tool_result))

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            print(f"    ❌ エラー: {e}")

            # エラーの場合もファイルを作成（デバッグ用）
            output_path = output_dir / output_file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Error in {tool_name}.{test_id}\n")
                f.write(f"# Params: {json.dumps(processed_params, indent=2)}\n")
                f.write(f"# Error: {str(e)}\n")
                f.write(f"# Generated at: {datetime.now().isoformat()}\n")

        result["execution_time"] = time.time() - start_time
        return result

    async def _execute_mcp_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """実際のMCPツールを実行"""
        try:
            if tool_name == "set_project_path":
                return _set_project_path_result(params)

            tool_class = _load_mcp_tool_class(tool_name)
            tool = tool_class(str(self.project_root))
            return await tool.execute(params)

        except ImportError as e:
            raise Exception(f"ツール {tool_name} のインポートに失敗: {e}") from e
        except Exception as e:
            raise Exception(f"ツール {tool_name} の実行に失敗: {e}") from e

    def _process_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """パラメータの{PROJECT_ROOT}などを実際の値に置換"""
        processed = {}
        for key, value in params.items():
            if isinstance(value, str) and "{PROJECT_ROOT}" in value:
                processed[key] = value.replace("{PROJECT_ROOT}", str(self.project_root))
            else:
                processed[key] = value
        return processed

    async def run_version_tests(self, version: str, output_dir: Path) -> dict[str, Any]:
        """指定されたバージョンでテストを実行"""
        print(f"\n📋 バージョン {version} のテスト実行中...")

        # キャッシュクリア（バージョン切り替え前）
        if self.clear_cache:
            print(f"🧹 バージョン {version} テスト前にキャッシュをクリア中...")
            cache_clear_result = self.cache_manager.clear_all_caches()
            print(
                f"✅ {cache_clear_result['total_cleared']} 個のキャッシュをクリアしました"
            )
            if cache_clear_result["errors"]:
                print(f"⚠️ キャッシュクリア時のエラー: {cache_clear_result['errors']}")

        # バージョンを有効化
        if not self.enable_version(version):
            return {"status": "failed", "error": "バージョンの有効化に失敗"}

        # サーバー起動待機
        self.wait_for_server_startup()

        # キャッシュクリア（バージョン切り替え後）
        if self.clear_cache:
            print(f"🧹 バージョン {version} 切り替え後にキャッシュを再クリア中...")
            cache_clear_result = self.cache_manager.clear_all_caches()
            print(
                f"✅ 追加で {cache_clear_result['total_cleared']} 個のキャッシュをクリアしました"
            )

        version_results = {
            "version": version,
            "status": "success",
            "test_results": {},
            "summary": {"total_tests": 0, "successful_tests": 0, "failed_tests": 0},
        }

        # 各ツールのテストを実行
        for tool_name, test_cases in self.test_cases.items():
            print(f"🔧 ツール: {tool_name}")
            tool_results = []

            for test_case in test_cases:
                result = await self.execute_test_case(tool_name, test_case, output_dir)
                tool_results.append(result)

                version_results["summary"]["total_tests"] += 1
                if result["status"] == "success":
                    version_results["summary"]["successful_tests"] += 1
                else:
                    version_results["summary"]["failed_tests"] += 1

            version_results["test_results"][tool_name] = tool_results

        return version_results

    def compare_outputs(self) -> dict[str, Any]:
        """バージョン間の出力を比較"""
        print("\n🔍 バージョン間の差分を分析中...")

        comparison_results = {
            "identical_files": [],
            "different_files": [],
            "missing_files": [],
            "detailed_diffs": {},
        }

        # バージョンAの出力ファイル一覧を取得
        version_a_files = set()
        if self.version_a_dir.exists():
            version_a_files = {
                f.name for f in self.version_a_dir.iterdir() if f.is_file()
            }

        # バージョンBの出力ファイル一覧を取得
        version_b_files = set()
        if self.version_b_dir.exists():
            version_b_files = {
                f.name for f in self.version_b_dir.iterdir() if f.is_file()
            }

        # 共通ファイルを比較
        common_files = version_a_files & version_b_files
        for filename in common_files:
            file_a = self.version_a_dir / filename
            file_b = self.version_b_dir / filename

            try:
                with open(file_a, encoding="utf-8") as f:
                    content_a = f.read()
                with open(file_b, encoding="utf-8") as f:
                    content_b = f.read()

                if content_a == content_b:
                    comparison_results["identical_files"].append(filename)
                else:
                    comparison_results["different_files"].append(filename)

                    # 詳細な差分を生成
                    diff = list(
                        difflib.unified_diff(
                            content_a.splitlines(keepends=True),
                            content_b.splitlines(keepends=True),
                            fromfile=f"v{self.version_a}/{filename}",
                            tofile=f"v{self.version_b}/{filename}",
                        )
                    )
                    comparison_results["detailed_diffs"][filename] = "".join(diff)

            except Exception as e:
                print(f"⚠️ ファイル比較エラー ({filename}): {e}")

        # 欠落ファイルを記録
        missing_in_b = version_a_files - version_b_files
        missing_in_a = version_b_files - version_a_files

        for filename in missing_in_b:
            comparison_results["missing_files"].append(
                f"{filename} (v{self.version_b}で欠落)"
            )
        for filename in missing_in_a:
            comparison_results["missing_files"].append(
                f"{filename} (v{self.version_a}で欠落)"
            )

        return comparison_results

    def generate_report(
        self,
        version_a_results: dict[str, Any],
        version_b_results: dict[str, Any],
        comparison_results: dict[str, Any],
    ) -> str:
        """比較レポートを生成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = (
            self.compatibility_test_dir
            / "reports"
            / f"comparison_report_{self.version_a}_vs_{self.version_b}_{timestamp}.md"
        )

        # テンプレートを読み込み
        template_file = (
            self.compatibility_test_dir / "templates" / "comparison_report_template.md"
        )

        try:
            with open(template_file, encoding="utf-8") as f:
                template = f.read()
        except Exception as e:
            print(f"⚠️ テンプレート読み込みエラー: {e}")
            template = "# 互換性比較レポート\n\n{SUMMARY}\n\n{DETAILED_RESULTS}"

        # キャッシュレポートを生成
        cache_report_content = self._generate_cache_report_content()

        # テンプレートの置換
        replacements = {
            "{VERSION_A}": self.version_a,
            "{VERSION_B}": self.version_b,
            "{TEST_DATE}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "{TESTER_NAME}": "自動テストスクリプト",
            "{TEST_ENVIRONMENT}": f"Windows, Python {sys.version.split()[0]}",
            "{SUMMARY}": self._generate_summary(
                version_a_results, version_b_results, comparison_results
            ),
            "{TOTAL_TEST_CASES}": str(version_a_results["summary"]["total_tests"]),
            "{SUCCESSFUL_CASES}": str(
                min(
                    version_a_results["summary"]["successful_tests"],
                    version_b_results["summary"]["successful_tests"],
                )
            ),
            "{FAILED_CASES}": str(
                max(
                    version_a_results["summary"]["failed_tests"],
                    version_b_results["summary"]["failed_tests"],
                )
            ),
            "{DIFF_DETECTED_CASES}": str(len(comparison_results["different_files"])),
            "{VERSION_A_SERVER_STATUS}": (
                "成功" if version_a_results["status"] == "success" else "失敗"
            ),
            "{VERSION_B_SERVER_STATUS}": (
                "成功" if version_b_results["status"] == "success" else "失敗"
            ),
            "{CACHE_REPORT}": cache_report_content,
            "{IDENTICAL_ITEMS_LIST}": self._format_identical_items(
                comparison_results["identical_files"]
            ),
            "{DETAILED_DIFFS}": self._format_detailed_diffs(
                comparison_results["detailed_diffs"]
            ),
            "{PROJECT_ROOT}": str(self.project_root),
        }

        report_content = template
        for placeholder, value in replacements.items():
            report_content = report_content.replace(placeholder, value)

        # レポートを保存
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        print(f"📄 レポートを生成しました: {report_file}")
        return str(report_file)

    def _generate_summary(
        self,
        version_a_results: dict[str, Any],
        version_b_results: dict[str, Any],
        comparison_results: dict[str, Any],
    ) -> str:
        """総評を生成"""
        total_files = len(comparison_results["identical_files"]) + len(
            comparison_results["different_files"]
        )
        identical_count = len(comparison_results["identical_files"])
        different_count = len(comparison_results["different_files"])

        if different_count == 0:
            return f"v{self.version_b}はv{self.version_a}と完全に互換性があります。全{total_files}ファイルが一致しました。"
        else:
            return f"v{self.version_b}はv{self.version_a}に対して{different_count}件の差分が検出されました。{identical_count}/{total_files}ファイルが一致しています。"

    def _format_identical_items(self, identical_files: list[str]) -> str:
        """一致項目をフォーマット"""
        if not identical_files:
            return "- なし"
        return "\n".join([f"- {filename}" for filename in identical_files])

    def _format_detailed_diffs(self, detailed_diffs: dict[str, str]) -> str:
        """詳細差分をフォーマット"""
        if not detailed_diffs:
            return "差分は検出されませんでした。"

        formatted = []
        for filename, diff in detailed_diffs.items():
            formatted.append(f"#### {filename}\n\n```diff\n{diff}\n```\n")

        return "\n".join(formatted)

    def _generate_cache_report_content(self) -> str:
        """キャッシュレポートコンテンツを生成"""
        if not self.clear_cache:
            return "## 2.3. キャッシュ状態\n\n⚠️ **キャッシュクリアが無効化されています** - テスト結果にキャッシュの影響がある可能性があります。\n"

        try:
            # 最終的なキャッシュ状態を取得
            final_cache_stats = self.cache_manager.get_cache_stats()
            cache_report = self.cache_reporter.generate_cache_report(final_cache_stats)

            # Markdownフォーマットで生成
            cache_content = self.cache_reporter.format_report_for_markdown(cache_report)

            # セクション番号を調整
            cache_content = cache_content.replace(
                "## 🧹 キャッシュ状態レポート", "## 2.3. キャッシュ状態"
            )
            cache_content = cache_content.replace("### ", "#### ")

            return cache_content

        except Exception as e:
            return f"## 2.3. キャッシュ状態\n\n❌ **キャッシュレポート生成エラー**: {str(e)}\n"

    async def run_compatibility_test(self) -> bool:
        """互換性テストの実行"""
        print("🚀 tree-sitter-analyzer MCP互換性テスト開始")
        print("=" * 60)
        print(f"📊 比較対象: v{self.version_a} vs v{self.version_b}")
        print(f"🧹 キャッシュクリア: {'有効' if self.clear_cache else '無効'}")

        try:
            # 準備
            self.setup_directories()
            self.load_test_cases()

            # 初期キャッシュ状態を記録
            if self.clear_cache:
                print("📊 初期キャッシュ状態を確認中...")
                initial_cache_stats = self.cache_manager.get_cache_stats()
                self.test_results["cache_info"]["initial_stats"] = initial_cache_stats
                print(f"初期キャッシュ状態: {initial_cache_stats}")

            # バージョンAのテスト実行
            version_a_results = await self.run_version_tests(
                self.version_a, self.version_a_dir
            )

            # バージョンBのテスト実行
            version_b_results = await self.run_version_tests(
                self.version_b, self.version_b_dir
            )

            # 最終キャッシュ状態を記録
            if self.clear_cache:
                final_cache_stats = self.cache_manager.get_cache_stats()
                self.test_results["cache_info"]["final_stats"] = final_cache_stats

            # 結果比較
            comparison_results = self.compare_outputs()

            # レポート生成
            report_file = self.generate_report(
                version_a_results, version_b_results, comparison_results
            )

            # 結果サマリー表示
            print("\n" + "=" * 60)
            print("🎉 互換性テスト完了!")
            print(f"📋 詳細レポート: {report_file}")
            print(f"📊 一致ファイル: {len(comparison_results['identical_files'])}")
            print(f"📊 差分ファイル: {len(comparison_results['different_files'])}")

            if self.clear_cache:
                print("🧹 キャッシュクリア実行回数: 各バージョンで2回ずつ")

            return True

        except KeyboardInterrupt:
            print("\n⚠️ テストが中断されました")
            return False
        except Exception as e:
            print(f"\n❌ テスト実行エラー: {e}")
            return False


async def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description="tree-sitter-analyzer MCP互換性テスト")
    parser.add_argument(
        "--version-a", required=True, help="比較元バージョン (例: 1.9.2)"
    )
    parser.add_argument(
        "--version-b", required=True, help="比較先バージョン (例: 1.9.3)"
    )
    parser.add_argument(
        "--project-root", help="プロジェクトルートパス (デフォルト: 自動検出)"
    )
    parser.add_argument(
        "--no-cache-clear",
        action="store_true",
        help="キャッシュクリアを無効化（デバッグ用）",
    )

    args = parser.parse_args()

    tester = StandardizedCompatibilityTester(
        version_a=args.version_a,
        version_b=args.version_b,
        project_root=args.project_root,
        clear_cache=not args.no_cache_clear,
    )

    success = await tester.run_compatibility_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
