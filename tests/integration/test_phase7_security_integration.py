#!/usr/bin/env python3
"""
Phase 7: Security Integration Tests

エンタープライズグレードのセキュリティ統合テスト:
- 包括的なセキュリティ脅威シミュレーション
- 多層防御システムの統合検証
- セキュリティポリシーの一貫性確認
- 実世界の攻撃シナリオテスト
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

from ._test_phase7_comprehensive_security_helpers import (
    assert_comprehensive_security_checks,
    collect_comprehensive_security_checks,
)
from ._test_phase7_information_leakage_helpers import (
    collect_information_leakage_results,
    create_information_leakage_test_cases,
)
from ._test_phase7_malicious_query_helpers import collect_malicious_query_results
from ._test_phase7_path_traversal_helpers import collect_path_traversal_results
from ._test_phase7_security_integration_helpers import (
    create_secure_project_structure,
    create_security_test_files,
)
from ._test_phase7_security_load_helpers import collect_security_under_load_results
from ._test_phase7_security_policy_helpers import (
    assert_security_policy_consistency_results,
    collect_security_policy_results,
    create_security_policy_test_cases,
)
from ._test_phase7_security_scenarios import (
    create_malicious_paths,
    create_malicious_queries,
    create_unicode_attacks,
)
from ._test_phase7_security_stress_helpers import (
    assert_concurrent_security_stress_results,
    collect_concurrent_security_stress_results,
)
from ._test_phase7_sensitive_exposure_helpers import (
    collect_sensitive_exposure_results,
    create_sensitive_data_patterns,
)
from ._test_phase7_unicode_security_helpers import (
    assert_unicode_attacks_handled_safely,
    collect_unicode_attack_results,
)


@pytest.fixture(scope="class")
def secure_test_project():
    """セキュリティテスト用プロジェクト作成"""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)

        # 正常なファイル構造
        create_secure_project_structure(project_root)

        # 潜在的に危険なファイル（テスト用）
        create_security_test_files(project_root)

        yield str(project_root)


class TestPhase7SecurityIntegration:
    """Phase 7 セキュリティ統合テスト"""

    @pytest.mark.asyncio
    async def test_path_traversal_protection_comprehensive(self, secure_test_project):
        """包括的パストラバーサル保護テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        malicious_paths = create_malicious_paths()

        # 各ツールでパストラバーサル攻撃をテスト
        tools = [
            AnalyzeScaleTool(secure_test_project),
            TableFormatTool(secure_test_project),
            ReadPartialTool(secure_test_project),
            QueryTool(secure_test_project),
        ]

        attack_results = await collect_path_traversal_results(tools, malicious_paths)

        # セキュリティ検証
        successful_attacks = [r for r in attack_results if not r["blocked"]]
        blocked_attacks = [r for r in attack_results if r["blocked"]]

        print("Path Traversal Protection Results:")
        print(f"  Total attacks tested: {len(attack_results)}")
        print(f"  Successfully blocked: {len(blocked_attacks)}")
        print(f"  Failed to block: {len(successful_attacks)}")

        # 全ての攻撃がブロックされる必要がある
        assert len(successful_attacks) == 0, (
            f"Path traversal attacks succeeded: {successful_attacks}"
        )

        # 少なくとも90%の攻撃がブロックされる必要がある
        block_rate = len(blocked_attacks) / len(attack_results) if attack_results else 0
        assert block_rate >= 0.9, f"Block rate too low: {block_rate:.2%}"

    @pytest.mark.asyncio
    async def test_malicious_query_protection(self, secure_test_project):
        """悪意のあるクエリ保護テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        malicious_queries = create_malicious_queries()

        # 検索ツールでの悪意のあるクエリテスト
        search_tools = [
            SearchContentTool(secure_test_project),
            FindAndGrepTool(secure_test_project),
            QueryTool(secure_test_project),
        ]

        query_results = await collect_malicious_query_results(
            search_tools,
            malicious_queries,
            secure_test_project,
        )

        # DoS攻撃保護検証
        long_running_queries = [r for r in query_results if r["execution_time"] > 3.0]
        blocked_queries = [r for r in query_results if r["blocked"]]

        print("Malicious Query Protection Results:")
        print(f"  Total queries tested: {len(query_results)}")
        print(f"  Successfully blocked: {len(blocked_queries)}")
        print(f"  Long running (>3s): {len(long_running_queries)}")

        # DoS攻撃が効果的にブロックされることを確認
        assert len(long_running_queries) < len(query_results) * 0.1, (
            "Too many long-running queries (DoS vulnerability)"
        )

        # 悪意のあるクエリの一部がブロックされることを確認
        # 注意: 全てのクエリがブロックされるわけではないが、明らかに危険なものは検出される
        block_rate = len(blocked_queries) / len(query_results) if query_results else 0
        assert block_rate >= 0.1, (
            f"Malicious query block rate too low: {block_rate:.2%} (expected at least 10%)"
        )

    @pytest.mark.asyncio
    async def test_unicode_normalization_attacks(self, secure_test_project):
        """Unicode正規化攻撃テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        unicode_attacks = create_unicode_attacks()

        # ファイルパスでのUnicode攻撃テスト
        list_tool = ListFilesTool(secure_test_project)

        unicode_results = await collect_unicode_attack_results(
            list_tool,
            unicode_attacks,
            secure_test_project,
        )
        assert_unicode_attacks_handled_safely(unicode_results)

    @pytest.mark.asyncio
    async def test_sensitive_data_exposure_prevention(self, secure_test_project):
        """機密データ露出防止テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        # 機密データパターンを検索
        sensitive_patterns = create_sensitive_data_patterns()
        search_tool = SearchContentTool(secure_test_project)
        exposure_results = await collect_sensitive_exposure_results(
            search_tool,
            sensitive_patterns,
            secure_test_project,
        )

        print("Sensitive Data Exposure Prevention Results:")
        for result in exposure_results:
            print(f"  {result['pattern']}: {result['result']}")

        # 機密データが適切にサニタイズされていることを確認
        exposed_data = [r for r in exposure_results if not r["properly_sanitized"]]
        assert len(exposed_data) == 0, (
            f"Sensitive data exposure detected: {exposed_data}"
        )

    @pytest.mark.requires_fd
    @pytest.mark.requires_ripgrep
    @pytest.mark.asyncio
    async def test_concurrent_security_stress(self, secure_test_project):
        """同時セキュリティストレステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        # パストラバーサル攻撃
        malicious_paths = create_malicious_paths()[:10]

        # 悪意のあるクエリ攻撃
        malicious_queries = create_malicious_queries()[:10]
        (
            attack_results,
            execution_time,
        ) = await collect_concurrent_security_stress_results(
            secure_test_project,
            malicious_paths,
            malicious_queries,
        )

        assert_concurrent_security_stress_results(attack_results, execution_time)

    @pytest.mark.asyncio
    async def test_security_policy_consistency(self, secure_test_project):
        """セキュリティポリシー一貫性テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        # 全ツールで同じセキュリティポリシーが適用されることを確認
        tools = [
            AnalyzeScaleTool(secure_test_project),
            TableFormatTool(secure_test_project),
            ReadPartialTool(secure_test_project),
            QueryTool(secure_test_project),
            ListFilesTool(secure_test_project),
            SearchContentTool(secure_test_project),
            FindAndGrepTool(secure_test_project),
        ]

        # 共通のセキュリティテストケース
        test_cases = create_security_policy_test_cases()
        policy_results = await collect_security_policy_results(tools, test_cases)
        assert_security_policy_consistency_results(policy_results)

    @pytest.mark.asyncio
    async def test_information_leakage_prevention(self, secure_test_project):
        """情報漏洩防止テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        # 意図的にエラーを発生させて、エラーメッセージから情報が漏洩しないことを確認
        error_test_cases = create_information_leakage_test_cases(secure_test_project)
        leakage_results = await collect_information_leakage_results(error_test_cases)

        print("Information Leakage Prevention Results:")
        for result in leakage_results:
            print(
                f"  {result['description']}: {'SAFE' if result['safe'] else 'LEAKAGE DETECTED!'}"
            )
            if not result["safe"]:
                print(f"    Error message: {result['error_message']}")

        # 情報漏洩が発生していないことを確認
        unsafe_results = [r for r in leakage_results if not r["safe"]]
        assert len(unsafe_results) == 0, (
            f"Information leakage detected: {unsafe_results}"
        )

    @pytest.mark.asyncio
    async def test_security_under_load(self, secure_test_project):
        """負荷下でのセキュリティテスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        (
            successful_attacks,
            blocked_attacks,
            execution_time,
            total_attacks,
        ) = await collect_security_under_load_results(secure_test_project)

        block_rate = len(blocked_attacks) / total_attacks if total_attacks else 0

        print("Security Under Load Results:")
        print(f"  Execution time: {execution_time:.2f}s")
        print(f"  Total attacks: {total_attacks}")
        print(f"  Blocked attacks: {len(blocked_attacks)}")
        print(f"  Successful attacks: {len(successful_attacks)}")
        print(f"  Block rate: {block_rate:.2%}")

        # 負荷下でもセキュリティが維持されることを確認
        # パストラバーサル攻撃のみをチェック（通常の検索は成功することを期待）
        path_traversal_attacks = [
            a for a in successful_attacks if a["type"] == "path_traversal"
        ]
        assert len(path_traversal_attacks) == 0, (
            f"Path traversal attacks succeeded under load: {path_traversal_attacks}"
        )
        assert execution_time < 60.0, "System became unresponsive under security load"

    @pytest.mark.asyncio
    async def test_comprehensive_security_validation(self, secure_test_project):
        """包括的セキュリティ検証テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)

        # 全セキュリティ機能の統合テスト
        security_checks = await collect_comprehensive_security_checks(
            secure_test_project
        )

        assert_comprehensive_security_checks(security_checks)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
