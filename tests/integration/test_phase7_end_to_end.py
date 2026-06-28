#!/usr/bin/env python3
"""
Phase 7: Integration & Validation - End-to-End Tests

エンタープライズグレードの統合テストスイート:
- 完全なワークフローテスト
- 実世界のユースケース検証
- パフォーマンス・セキュリティ統合検証
- 品質保証の最終確認
"""

import asyncio
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil
import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

from ._test_phase7_end_to_end_helpers import run_performance_under_load
from ._test_phase7_project_builders import (
    create_config_and_docs,
    create_java_enterprise_structure,
    create_javascript_enterprise_structure,
    create_python_enterprise_structure,
)


class TestPhase7EndToEnd:
    """Phase 7 エンドツーエンド統合テスト"""

    @pytest.fixture(scope="class")
    def enterprise_project(self):
        """エンタープライズ規模のテストプロジェクト作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # 大規模Javaプロジェクト構造
            self._create_java_enterprise_structure(project_root)

            # 大規模Pythonプロジェクト構造
            self._create_python_enterprise_structure(project_root)

            # 大規模JavaScriptプロジェクト構造
            self._create_javascript_enterprise_structure(project_root)

            # 設定ファイルとドキュメント
            self._create_config_and_docs(project_root)

            yield str(project_root)

    def _create_java_enterprise_structure(self, project_root: Path):
        """エンタープライズJavaプロジェクト構造"""
        create_java_enterprise_structure(project_root)

    def _create_python_enterprise_structure(self, project_root: Path):
        """エンタープライズPythonプロジェクト構造"""
        create_python_enterprise_structure(project_root)

    def _create_javascript_enterprise_structure(self, project_root: Path):
        """エンタープライズJavaScriptプロジェクト構造"""
        create_javascript_enterprise_structure(project_root)

    def _create_config_and_docs(self, project_root: Path):
        """設定ファイルとドキュメント作成"""
        create_config_and_docs(project_root)

    @pytest.mark.asyncio
    async def test_complete_enterprise_workflow(self, enterprise_project):
        """完全なエンタープライズワークフローテスト"""
        # 外部依存関係チェック
        has_ripgrep = shutil.which("rg") is not None
        has_fd = shutil.which("fd") is not None

        if not has_ripgrep or not has_fd:
            pytest.skip(
                f"External dependencies missing: ripgrep={has_ripgrep}, fd={has_fd}"
            )

        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)

        try:
            # Phase 1: プロジェクト全体の概要把握
            overview_results = await self._analyze_project_overview(
                server, enterprise_project
            )

            # Phase 2: 各言語の詳細分析
            detailed_results = await self._analyze_language_details(
                server, enterprise_project
            )

            # Phase 3: セキュリティ・パフォーマンス検証
            security_results = await self._verify_security_compliance(
                server, enterprise_project
            )
            performance_results = await self._verify_performance_requirements(
                server, enterprise_project
            )

            # Phase 4: 統合検証
            integration_results = await self._verify_integration_quality(
                server, enterprise_project, overview_results, detailed_results
            )

            # 最終検証
            assert overview_results["success"]
            assert detailed_results["success"]
            assert security_results["success"]
            assert performance_results["success"]
            assert integration_results["success"]
        except Exception as e:
            pytest.fail(f"Enterprise workflow test failed: {e}")

    async def _analyze_project_overview(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """プロジェクト全体の概要分析"""
        results = {"success": True, "analyses": []}

        # 1. ファイル一覧取得
        list_tool = ListFilesTool(project_path)
        file_list_result = await list_tool.execute(
            {
                "roots": [project_path],
                "extensions": ["java", "py", "js", "md", "json"],
                "limit": 1000,
            }
        )

        assert file_list_result["success"]
        assert file_list_result["count"]
        results["analyses"].append(("file_listing", file_list_result))

        # 2. 主要ファイルの規模チェック
        scale_tool = AnalyzeScaleTool(project_path)
        main_files = [
            "backend/src/main/java/com/enterprise/domain/User.java",
            "backend/python/enterprise_app/models/user.py",
            "frontend/src/components/UserManagement.js",
        ]

        for file_path in main_files:
            full_path = Path(project_path) / file_path
            if full_path.exists():
                scale_result = await scale_tool.execute(
                    {
                        "file_path": str(full_path),
                        "include_complexity": True,
                        "include_guidance": True,
                    }
                )
                assert scale_result["success"]
                results["analyses"].append((f"scale_{file_path}", scale_result))

        return results

    async def _analyze_language_details(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """各言語の詳細分析"""
        results = {"success": True, "analyses": []}

        # Java分析
        java_results = await self._analyze_java_components(server, project_path)
        results["analyses"].append(("java_analysis", java_results))

        # Python分析
        python_results = await self._analyze_python_components(server, project_path)
        results["analyses"].append(("python_analysis", python_results))

        # JavaScript分析
        js_results = await self._analyze_javascript_components(server, project_path)
        results["analyses"].append(("javascript_analysis", js_results))

        return results

    async def _analyze_java_components(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """Java コンポーネント分析"""
        results = {"success": True, "components": []}

        # User.java の詳細分析
        user_java_path = (
            Path(project_path) / "backend/src/main/java/com/enterprise/domain/User.java"
        )
        if user_java_path.exists():
            # 構造分析
            table_tool = TableFormatTool(project_path)
            structure_result = await table_tool.execute(
                {"file_path": str(user_java_path), "format_type": "full"}
            )
            assert structure_result["success"]
            results["components"].append(("user_structure", structure_result))

            # クエリ分析
            query_tool = QueryTool(project_path)
            methods_result = await query_tool.execute(
                {
                    "file_path": str(user_java_path),
                    "query_key": "methods",
                    "output_format": "json",
                }
            )
            assert methods_result["success"]
            results["components"].append(("user_methods", methods_result))

        return results

    async def _analyze_python_components(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """Python コンポーネント分析"""
        results = {"success": True, "components": []}

        # user.py の詳細分析
        user_py_path = (
            Path(project_path) / "backend/python/enterprise_app/models/user.py"
        )
        if user_py_path.exists():
            # 構造分析
            table_tool = TableFormatTool(project_path)
            structure_result = await table_tool.execute(
                {"file_path": str(user_py_path), "format_type": "full"}
            )
            assert structure_result["success"]
            results["components"].append(("user_structure", structure_result))

            # 部分読み取り
            read_tool = ReadPartialTool(project_path)
            partial_result = await read_tool.execute(
                {
                    "file_path": str(user_py_path),
                    "start_line": 1,
                    "end_line": 50,
                    "format": "json",
                }
            )
            assert partial_result["success"]
            results["components"].append(("user_partial", partial_result))

        return results

    async def _analyze_javascript_components(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """JavaScript コンポーネント分析"""
        results = {"success": True, "components": []}

        # UserManagement.js の詳細分析
        user_js_path = Path(project_path) / "frontend/src/components/UserManagement.js"
        if user_js_path.exists():
            # 構造分析
            table_tool = TableFormatTool(project_path)
            structure_result = await table_tool.execute(
                {"file_path": str(user_js_path), "format_type": "full"}
            )
            assert structure_result["success"]
            results["components"].append(
                ("user_management_structure", structure_result)
            )

        return results

    async def _verify_security_compliance(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """セキュリティコンプライアンス検証"""
        results = {"success": True, "security_checks": []}

        # 1. パストラバーサル攻撃テスト
        scale_tool = AnalyzeScaleTool(project_path)

        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
        ]

        for malicious_path in malicious_paths:
            try:
                await scale_tool.execute({"file_path": malicious_path})
                results["success"] = False  # Should not reach here
            except Exception:
                # Expected to fail - security working
                results["security_checks"].append(f"blocked_{malicious_path}")

        # 2. 入力サニタイゼーションテスト
        try:
            await scale_tool.execute(
                {
                    "file_path": str(Path(project_path) / "README.md"),
                    "language": "<script>alert('xss')</script>",
                }
            )
            # Should handle malicious input safely
            results["security_checks"].append("input_sanitization_passed")
        except Exception:
            # Also acceptable if it rejects malicious input
            results["security_checks"].append("input_sanitization_rejected")

        return results

    async def _verify_performance_requirements(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """パフォーマンス要件検証"""
        results = {"success": True, "performance_metrics": []}

        # 1. 単一ツール実行時間テスト（3秒以内）
        scale_tool = AnalyzeScaleTool(project_path)
        readme_path = Path(project_path) / "README.md"

        start_time = time.time()
        scale_result = await scale_tool.execute(
            {"file_path": str(readme_path), "include_complexity": True}
        )
        execution_time = time.time() - start_time

        assert scale_result["success"]
        assert execution_time < 3.0, f"実行時間が3秒を超過: {execution_time:.2f}秒"
        results["performance_metrics"].append(("scale_tool_time", execution_time))

        # 2. メモリ使用量テスト
        process = psutil.Process()
        initial_memory = process.memory_info().rss

        # 複数ツールの並行実行
        table_tool = TableFormatTool(project_path)
        read_tool = ReadPartialTool(project_path)

        tasks = [
            scale_tool.execute({"file_path": str(readme_path)}),
            table_tool.execute({"file_path": str(readme_path)}),
            read_tool.execute(
                {"file_path": str(readme_path), "start_line": 1, "end_line": 10}
            ),
        ]

        await asyncio.gather(*tasks)

        final_memory = process.memory_info().rss
        memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB

        assert memory_increase < 100, (
            f"メモリ使用量増加が100MBを超過: {memory_increase:.2f}MB"
        )
        results["performance_metrics"].append(("memory_usage", memory_increase))

        return results

    async def _verify_integration_quality(
        self,
        server: TreeSitterAnalyzerMCPServer,
        project_path: str,
        overview_results: dict,
        detailed_results: dict,
    ) -> dict[str, Any]:
        """統合品質検証"""
        results = {"success": True, "integration_checks": []}

        # 1. ワークフロー一貫性テスト
        search_tool = SearchContentTool(project_path)

        # クラス定義の検索
        search_result = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "class",
                "include_globs": ["*.java", "*.py", "*.js"],
                "max_count": 50,
            }
        )

        assert search_result["success"]
        results["integration_checks"].append(("class_search", search_result["count"]))

        # 2. ファイル出力機能テスト
        output_file = "integration_test_output"
        search_with_output = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "function",
                "include_globs": ["*.js", "*.py"],
                "output_file": output_file,
                "suppress_output": True,
                "max_count": 20,
            }
        )

        assert search_with_output["success"]
        results["integration_checks"].append(("file_output_test", "passed"))

        # 3. 多言語対応テスト
        languages_tested = []
        test_files = [
            ("java", "backend/src/main/java/com/enterprise/domain/User.java"),
            ("python", "backend/python/enterprise_app/models/user.py"),
            ("javascript", "frontend/src/components/UserManagement.js"),
        ]

        scale_tool = AnalyzeScaleTool(project_path)
        for lang, file_path in test_files:
            full_path = Path(project_path) / file_path
            if full_path.exists():
                try:
                    result = await scale_tool.execute(
                        {"file_path": str(full_path), "language": lang}
                    )
                    if result["success"]:
                        languages_tested.append(lang)
                except Exception as e:
                    # 言語サポートがない場合はスキップ
                    if "not supported" in str(e).lower():
                        continue
                    raise

        assert languages_tested, "少なくとも1つの言語がテストされる必要があります"
        results["integration_checks"].append(("languages_tested", languages_tested))

        return results

    @pytest.mark.asyncio
    async def test_real_world_development_workflow(self, enterprise_project):
        """実世界の開発ワークフローシミュレーション"""
        # 外部依存関係チェック
        has_ripgrep = shutil.which("rg") is not None
        has_fd = shutil.which("fd") is not None

        if not has_ripgrep or not has_fd:
            pytest.skip(
                f"External dependencies missing: ripgrep={has_ripgrep}, fd={has_fd}"
            )

        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)

        try:
            # シナリオ1: 新機能開発のためのコード調査
            investigation_results = await self._simulate_code_investigation(
                server, enterprise_project
            )

            # シナリオ2: バグ修正のためのコード分析
            bug_analysis_results = await self._simulate_bug_analysis(
                server, enterprise_project
            )

            # シナリオ3: リファクタリングのための影響範囲調査
            refactoring_results = await self._simulate_refactoring_analysis(
                server, enterprise_project
            )

            # 全シナリオが成功することを確認
            assert investigation_results["success"]
            assert bug_analysis_results["success"]
            assert refactoring_results["success"]
        except Exception as e:
            pytest.fail(f"Real world development workflow test failed: {e}")

    async def _simulate_code_investigation(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """新機能開発のためのコード調査シミュレーション"""
        results = {"success": True, "steps": []}

        # Step 1: 関連するユーザー管理機能を検索
        search_tool = SearchContentTool(project_path)
        user_search = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "user",
                "case": "insensitive",
                "include_globs": ["*.java", "*.py", "*.js"],
                "max_count": 30,
            }
        )
        assert user_search["success"]
        results["steps"].append(("user_search", user_search["count"]))

        # Step 2: 主要なユーザークラスの詳細分析
        user_java_path = (
            Path(project_path) / "backend/src/main/java/com/enterprise/domain/User.java"
        )
        if user_java_path.exists():
            table_tool = TableFormatTool(project_path)
            structure_analysis = await table_tool.execute(
                {"file_path": str(user_java_path), "format_type": "full"}
            )
            assert structure_analysis["success"]
            results["steps"].append(("structure_analysis", "completed"))

        # Step 3: 認証関連のメソッドを検索
        auth_search = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "auth|login|password",
                "case": "insensitive",
                "include_globs": ["*.java", "*.py"],
                "max_count": 20,
            }
        )
        assert auth_search["success"]
        results["steps"].append(("auth_search", auth_search["count"]))

        return results

    async def _simulate_bug_analysis(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """バグ修正のためのコード分析シミュレーション"""
        results = {"success": True, "steps": []}

        # Step 1: エラーハンドリング関連のコードを検索
        search_tool = SearchContentTool(project_path)
        error_search = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "exception|error|throw|catch",
                "case": "insensitive",
                "include_globs": ["*.java", "*.py", "*.js"],
                "max_count": 25,
            }
        )
        assert error_search["success"]
        results["steps"].append(("error_search", error_search["count"]))

        # Step 2: 特定のメソッドの詳細確認
        user_service_path = (
            Path(project_path)
            / "backend/src/main/java/com/enterprise/service/UserService.java"
        )
        if user_service_path.exists():
            read_tool = ReadPartialTool(project_path)
            method_details = await read_tool.execute(
                {
                    "file_path": str(user_service_path),
                    "start_line": 30,
                    "end_line": 60,
                    "format": "text",
                }
            )
            assert method_details["success"]
            results["steps"].append(("method_analysis", "completed"))

        # Step 3: バリデーション関連のコードを検索
        validation_search = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "validate|validation",
                "case": "insensitive",
                "include_globs": ["*.java", "*.py"],
                "max_count": 15,
            }
        )
        assert validation_search["success"]
        results["steps"].append(("validation_search", validation_search["count"]))

        return results

    async def _simulate_refactoring_analysis(
        self, server: TreeSitterAnalyzerMCPServer, project_path: str
    ) -> dict[str, Any]:
        """リファクタリングのための影響範囲調査シミュレーション"""
        results = {"success": True, "steps": []}

        # Step 1: 特定のクラス/メソッドの使用箇所を検索
        search_tool = SearchContentTool(project_path)
        usage_search = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "UserService|User\\.",
                "case": "sensitive",
                "include_globs": ["*.java", "*.py", "*.js"],
                "max_count": 40,
            }
        )
        assert usage_search["success"]
        results["steps"].append(("usage_search", usage_search["count"]))

        # Step 2: 依存関係の分析
        import_search = await search_tool.execute(
            {
                "roots": [project_path],
                "query": "import.*User|from.*user",
                "case": "insensitive",
                "include_globs": ["*.java", "*.py"],
                "max_count": 20,
            }
        )
        assert import_search["success"]
        results["steps"].append(("import_search", import_search["count"]))

        # Step 3: 設定ファイルの確認
        config_files = ["package.json", "README.md"]
        for config_file in config_files:
            config_path = Path(project_path) / config_file
            if config_path.exists():
                scale_tool = AnalyzeScaleTool(project_path)
                config_analysis = await scale_tool.execute(
                    {"file_path": str(config_path)}
                )
                assert config_analysis["success"]
                results["steps"].append((f"config_analysis_{config_file}", "completed"))

        return results

    @pytest.mark.asyncio
    async def test_performance_under_load(self, enterprise_project):
        """負荷下でのパフォーマンステスト"""
        # 外部依存関係チェック
        has_ripgrep = shutil.which("rg") is not None
        has_fd = shutil.which("fd") is not None

        if not has_ripgrep or not has_fd:
            pytest.skip(
                f"External dependencies missing: ripgrep={has_ripgrep}, fd={has_fd}"
            )

        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)

        try:
            await run_performance_under_load(enterprise_project)
        except Exception as e:
            pytest.fail(f"Performance test failed: {e}")

    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, enterprise_project):
        """エラー回復と回復力テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)

        # 1. 存在しないファイルでのエラーハンドリング
        scale_tool = AnalyzeScaleTool(enterprise_project)
        try:
            result = await scale_tool.execute({"file_path": "nonexistent_file.py"})
            # ツールがエラー辞書を返す場合
            if isinstance(result, dict):
                assert not result.get("success", True) or "error" in result
            else:
                pytest.fail("Expected error handling for nonexistent file")
        except (ValueError, FileNotFoundError):
            # 例外が発生する場合も正常
            pass

        # 2. 無効な入力でのエラーハンドリング
        search_tool = SearchContentTool(enterprise_project)
        try:
            result = await search_tool.execute(
                {"roots": ["nonexistent_directory"], "query": "test"}
            )
            # エラーが適切に処理されることを確認
            if isinstance(result, dict):
                assert not result.get("success", True) or result.get("count", 0) == 0
        except (ValueError, AnalysisError) as e:
            # 存在しないディレクトリに対する適切なエラーが発生することを確認
            assert "does not exist" in str(e) or "Invalid root" in str(e)
        except FileNotFoundError:
            # 例外が発生する場合も正常
            pass

        # 3. 正常なファイルでの回復確認
        normal_result = await scale_tool.execute(
            {"file_path": str(Path(enterprise_project) / "README.md")}
        )
        assert normal_result["success"]

        print("エラー回復テスト完了: システムは適切にエラーを処理し、回復しています")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
