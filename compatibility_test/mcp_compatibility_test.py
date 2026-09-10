#!/usr/bin/env python3
"""
tree-sitter-analyzer MCP互換性テストスクリプト
バージョン1.6.1.2と1.9.2の8つのMCPツールの互換性をテストします。
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

# MCPツールのリスト (find_and_grep / search_content は廃止済み)
MCP_TOOLS = [
    "analyze_code_structure",
    "query_code",
    "check_code_scale",
    "extract_code_section",
    "set_project_path",
    "list_files",
]

# テスト対象バージョン
VERSIONS = ["1.6.1.2", "1.9.2"]


class MCPCompatibilityTester:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.mcp_settings_path = (
            Path.home()
            / "AppData/Roaming/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json"
        )
        self.results = {}

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
        target_server = f"tree-sitter-analyzer-{version}"
        if target_server in settings.get("mcpServers", {}):
            settings["mcpServers"][target_server]["disabled"] = False
            print(f"✅ {target_server}を有効化しました")
        else:
            print(f"❌ {target_server}が見つかりません")
            return False

        return self.save_mcp_settings(settings)

    def verify_tools_configuration(self, version: str) -> dict[str, bool]:
        """指定されたバージョンのツール設定を確認する"""
        settings = self.load_mcp_settings()
        server_name = f"tree-sitter-analyzer-{version}"

        if server_name not in settings.get("mcpServers", {}):
            return dict.fromkeys(MCP_TOOLS, False)

        allowed_tools = settings["mcpServers"][server_name].get("alwaysAllow", [])
        return {tool: tool in allowed_tools for tool in MCP_TOOLS}

    def test_basic_functionality(self, version: str) -> dict[str, Any]:
        """基本機能のテスト"""
        print(f"\n🧪 バージョン {version} の基本機能テスト開始...")

        test_results = {
            "version": version,
            "tools_configured": self.verify_tools_configuration(version),
            "server_enabled": False,
            "basic_tests": {},
        }

        # サーバー有効化
        if self.enable_version(version):
            test_results["server_enabled"] = True
            print("⏳ サーバー起動待機中...")
            time.sleep(3)  # サーバー起動待機

            # 基本的なテストケース
            basic_tests = {
                "set_project_path": self.test_set_project_path(),
                "list_files": self.test_list_files(),
                "check_code_scale": self.test_check_code_scale(),
                "analyze_code_structure": self.test_analyze_code_structure(),
                "query_code": self.test_query_code(),
                "extract_code_section": self.test_extract_code_section(),
                # find_and_grep と search_content は廃止済み
            }

            test_results["basic_tests"] = basic_tests

        return test_results

    def test_set_project_path(self) -> dict[str, Any]:
        """set_project_pathツールのテスト"""
        return {
            "description": "プロジェクトパスの設定テスト",
            "expected": "プロジェクトルートパスが正常に設定される",
            "status": "manual_verification_required",
        }

    def test_list_files(self) -> dict[str, Any]:
        """list_filesツールのテスト"""
        return {
            "description": "ファイル一覧取得テスト",
            "expected": "プロジェクト内のファイル一覧が取得される",
            "status": "manual_verification_required",
        }

    def test_check_code_scale(self) -> dict[str, Any]:
        """check_code_scaleツールのテスト"""
        return {
            "description": "コードスケール分析テスト",
            "expected": "ファイルの複雑度とスケール情報が取得される",
            "test_files": [
                "tree_sitter_analyzer/core/engine.py",
                "examples/Sample.java",
            ],
            "status": "manual_verification_required",
        }

    def test_analyze_code_structure(self) -> dict[str, Any]:
        """analyze_code_structureツールのテスト"""
        return {
            "description": "コード構造分析テスト",
            "expected": "クラス、メソッド、フィールドの詳細情報が取得される",
            "test_files": [
                "tree_sitter_analyzer/core/engine.py",
                "examples/Sample.java",
            ],
            "status": "manual_verification_required",
        }

    def test_query_code(self) -> dict[str, Any]:
        """query_codeツールのテスト"""
        return {
            "description": "tree-sitterクエリテスト",
            "expected": "指定されたクエリに基づいてコード要素が抽出される",
            "test_files": [
                {"file": "tree_sitter_analyzer/core/engine.py", "query_key": "methods"},
                {"file": "examples/Sample.java", "query_key": "methods"},
            ],
            "status": "manual_verification_required",
        }

    def test_extract_code_section(self) -> dict[str, Any]:
        """extract_code_sectionツールのテスト"""
        return {
            "description": "コードセクション抽出テスト",
            "expected": "指定された行範囲のコードが抽出される",
            "test_files": [
                {
                    "file": "tree_sitter_analyzer/core/engine.py",
                    "start_line": 1,
                    "end_line": 50,
                },
                {"file": "examples/Sample.java", "start_line": 1, "end_line": 30},
            ],
            "status": "manual_verification_required",
        }

    # test_find_and_grep と test_search_content は廃止済み:
    # find_and_grep (FindAndGrepTool) と search_content (SearchContentTool) が削除されたため。
    # テキスト検索には CC 組み込みの Grep tool を使用すること。

    def run_compatibility_test(self) -> dict[str, Any]:
        """互換性テストの実行"""
        print("🚀 tree-sitter-analyzer MCP互換性テスト開始")
        print("=" * 60)

        all_results = {}

        for version in VERSIONS:
            print(f"\n📋 バージョン {version} のテスト実行中...")
            results = self.test_basic_functionality(version)
            all_results[version] = results

            # 結果サマリー表示
            tools_configured = results["tools_configured"]
            configured_count = sum(
                1 for configured in tools_configured.values() if configured
            )
            print(f"📊 設定済みツール: {configured_count}/{len(MCP_TOOLS)}")

            missing_tools = [
                tool for tool, configured in tools_configured.items() if not configured
            ]
            if missing_tools:
                print(f"⚠️  未設定ツール: {', '.join(missing_tools)}")
            else:
                print("✅ 全ツールが設定済み")

        return all_results

    def generate_report(self, results: dict[str, Any]) -> str:
        """テスト結果レポートの生成"""
        report = []
        report.append("# tree-sitter-analyzer MCP互換性テストレポート")
        report.append(f"実行日時: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        for version, result in results.items():
            report.append(f"## バージョン {version}")
            report.append("")

            # ツール設定状況
            tools_configured = result["tools_configured"]
            configured_count = sum(
                1 for configured in tools_configured.values() if configured
            )
            report.append(f"### ツール設定状況: {configured_count}/{len(MCP_TOOLS)}")
            report.append("")

            for tool, configured in tools_configured.items():
                status = "✅" if configured else "❌"
                report.append(f"- {status} {tool}")
            report.append("")

            # 基本テスト結果
            if result.get("basic_tests"):
                report.append("### 基本テスト結果")
                report.append("")
                for tool, test_result in result["basic_tests"].items():
                    report.append(f"#### {tool}")
                    report.append(f"- 説明: {test_result['description']}")
                    report.append(f"- 期待結果: {test_result['expected']}")
                    report.append(f"- ステータス: {test_result['status']}")
                    report.append("")

        return "\n".join(report)

    def save_results(self, results: dict[str, Any]) -> None:
        """結果をファイルに保存"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # JSON結果保存
        json_file = (
            self.project_root
            / "compatibility_test"
            / f"mcp_test_results_{timestamp}.json"
        )
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"📄 JSON結果保存: {json_file}")

        # レポート保存
        report = self.generate_report(results)
        report_file = (
            self.project_root / "compatibility_test" / f"mcp_test_report_{timestamp}.md"
        )
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"📄 レポート保存: {report_file}")


def main():
    """メイン実行関数"""
    tester = MCPCompatibilityTester()

    try:
        # 互換性テスト実行
        results = tester.run_compatibility_test()

        # 結果保存
        tester.save_results(results)

        print("\n" + "=" * 60)
        print("🎉 互換性テスト完了!")
        print("📋 詳細な手動テストについては、生成されたレポートを参照してください。")

    except KeyboardInterrupt:
        print("\n⚠️  テストが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ テスト実行エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
