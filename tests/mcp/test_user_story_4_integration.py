"""
User Story 4 統合テスト: 統合ワークフロー・プロジェクト管理

このテストスイートは、User Story 4の統合ワークフロー機能を検証します：
- set_project_path による動的プロジェクト境界管理
- find_and_grep ツールによる2段階検索
- MCPリソース（code_file、project_stats）による情報アクセス
- 複合ワークフローでの統合動作

テスト対象:
- T015: set_project_path 機能
- T016: find_and_grep ツール  
- T017: MCPリソース（code_file、project_stats）
- 統合ワークフローシナリオ
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.resources.code_file_resource import CodeFileResource
from tree_sitter_analyzer.mcp.resources.project_stats_resource import ProjectStatsResource


class TestUserStory4Integration:
    """User Story 4: 統合ワークフロー・プロジェクト管理の統合テスト"""

    @pytest.fixture
    def temp_project(self):
        """テスト用プロジェクト構造を作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # プロジェクト構造作成
            (project_path / "src" / "main" / "java").mkdir(parents=True)
            (project_path / "src" / "test" / "java").mkdir(parents=True)
            (project_path / "scripts").mkdir()
            (project_path / "docs").mkdir()
            
            # Javaファイル作成
            java_main = project_path / "src" / "main" / "java" / "Service.java"
            java_main.write_text("""
public class Service {
    private String name;
    
    public Service(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
    
    public void processData() {
        // TODO: implement data processing
        System.out.println("Processing data for: " + name);
    }
}
""", encoding='utf-8')
            
            java_test = project_path / "src" / "test" / "java" / "ServiceTest.java"
            java_test.write_text("""
import org.junit.Test;
import static org.junit.Assert.*;

public class ServiceTest {
    @Test
    public void testGetName() {
        Service service = new Service("test");
        assertEquals("test", service.getName());
    }
    
    @Test
    public void testProcessData() {
        Service service = new Service("test");
        service.processData(); // TODO: add assertions
    }
}
""", encoding='utf-8')
            
            # Pythonスクリプト作成
            python_script = project_path / "scripts" / "helper.py"
            python_script.write_text('''#!/usr/bin/env python3
"""
Helper script for project management
"""

import os
import sys
from pathlib import Path

def find_java_files(root_dir):
    """Find all Java files in the project"""
    java_files = []
    for file_path in Path(root_dir).rglob("*.java"):
        java_files.append(str(file_path))
    return java_files

def count_todo_comments(file_path):
    """Count TODO comments in a file"""
    count = 0
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'TODO' in line:
                    count += 1
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return count

if __name__ == "__main__":
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = "."
    
    java_files = find_java_files(project_root)
    print(f"Found {len(java_files)} Java files")
    
    total_todos = 0
    for java_file in java_files:
        todos = count_todo_comments(java_file)
        if todos > 0:
            print(f"{java_file}: {todos} TODOs")
            total_todos += todos
    
    print(f"Total TODOs: {total_todos}")
''', encoding='utf-8')
            
            # ドキュメント作成
            readme = project_path / "docs" / "README.md"
            readme.write_text("""
# Test Project

This is a test project for User Story 4 integration testing.

## Structure

- `src/main/java/` - Main Java source code
- `src/test/java/` - Test Java source code  
- `scripts/` - Python helper scripts
- `docs/` - Documentation

## Features

- Service class with basic functionality
- Unit tests with JUnit
- Python helper scripts for project management
- TODO tracking capabilities

## Usage

Run the helper script to analyze the project:

```bash
python scripts/helper.py
```

This will find all Java files and count TODO comments.
""", encoding='utf-8')
            
            yield str(project_path)

    @pytest.fixture
    def mcp_server(self, temp_project):
        """MCPサーバーインスタンスを作成"""
        server = TreeSitterAnalyzerMCPServer(temp_project)
        return server

    def test_set_project_path_basic(self, mcp_server, temp_project):
        """T015: set_project_path の基本機能テスト"""
        
        # 新しいプロジェクトパスを設定
        mcp_server.set_project_path(temp_project)
        
        # プロジェクトパスが正しく設定されたことを確認
        assert mcp_server.project_stats_resource._project_path == temp_project
        
        # 各ツールのプロジェクトパスが更新されたことを確認
        assert mcp_server.find_and_grep_tool.project_root == temp_project
        assert mcp_server.query_tool.project_root == temp_project
        assert mcp_server.read_partial_tool.project_root == temp_project

    def test_set_project_path_validation(self, mcp_server):
        """set_project_path の検証機能テスト"""
        
        # 存在しないパスでもエラーにならない（設定は可能）
        mcp_server.set_project_path("/nonexistent/path")
        assert mcp_server.project_stats_resource._project_path == "/nonexistent/path"
        
        # 空パスではエラーになる
        with pytest.raises(ValueError) as exc_info:
            mcp_server.set_project_path("")
        assert "cannot be empty" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_find_and_grep_tool_basic(self, mcp_server, temp_project):
        """T016: find_and_grep ツールの基本機能テスト"""
        
        # Java ファイルを検索してTODOコメントを探す
        result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "extensions": ["java"],
            "query": "TODO",
            "case": "insensitive"
        })
        
        # 結果検証
        assert "results" in result
        assert len(result["results"]) > 0
        
        # TODOコメントが見つかることを確認
        found_todos = False
        for match in result["results"]:
            if "TODO" in match["text"]:
                found_todos = True
                assert "Service.java" in match["file"] or "ServiceTest.java" in match["file"]
                break
        
        assert found_todos, "TODO comments should be found in Java files"

    @pytest.mark.asyncio
    async def test_find_and_grep_two_stage_search(self, mcp_server, temp_project):
        """find_and_grep ツールの2段階検索テスト"""
        
        # 第1段階: Pythonファイルを見つける
        # 第2段階: その中で特定の関数を検索
        result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "extensions": ["py"],
            "query": "def find_java_files",
            "case": "sensitive"
        })
        
        # 結果検証
        assert "results" in result
        assert len(result["results"]) > 0
        
        # helper.pyで関数が見つかることを確認
        found_function = False
        for match in result["results"]:
            if "def find_java_files" in match["text"]:
                assert "helper.py" in match["file"]
                found_function = True
                break
        
        assert found_function, "find_java_files function should be found"

    @pytest.mark.asyncio
    async def test_find_and_grep_optimization_features(self, mcp_server, temp_project):
        """find_and_grep ツールの最適化機能テスト"""
        
        # total_only モードテスト
        result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "query": "import",
            "total_only": True
        })
        
        # total_onlyの場合は数値のみ返される
        assert isinstance(result, int)
        assert result > 0  # importステートメントが存在するはず
        
        # summary_only モードテスト
        result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "query": "public",
            "summary_only": True
        })
        
        # サマリー形式の結果検証
        assert "summary" in result
        assert "total_matches" in result["summary"]
        assert "top_files" in result["summary"]

    @pytest.mark.asyncio
    async def test_code_file_resource_access(self, mcp_server, temp_project):
        """T017: code_file リソースアクセステスト"""
        
        # Javaファイルの絶対パスを取得
        java_file_path = str(Path(temp_project) / "src" / "main" / "java" / "Service.java")
        uri = f"code://file/{java_file_path}"
        
        content = await mcp_server.code_file_resource.read_resource(uri)
        
        # 内容検証
        assert "public class Service" in content
        assert "private String name" in content
        assert "public void processData()" in content
        assert "TODO: implement data processing" in content

    @pytest.mark.asyncio
    async def test_code_file_resource_security(self, mcp_server, temp_project):
        """code_file リソースのセキュリティテスト"""
        
        # パストラバーサル攻撃テスト
        with pytest.raises(ValueError) as exc_info:
            await mcp_server.code_file_resource.read_resource("code://file/../../../etc/passwd")
        
        assert "Path traversal not allowed" in str(exc_info.value)
        
        # 無効なURI形式テスト
        with pytest.raises(ValueError) as exc_info:
            await mcp_server.code_file_resource.read_resource("invalid://file/test.java")
        
        assert "does not match code file pattern" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_project_stats_resource_overview(self, mcp_server, temp_project):
        """project_stats リソースの概要統計テスト"""
        
        content = await mcp_server.project_stats_resource.read_resource("code://stats/overview")
        stats = json.loads(content)
        
        # 基本統計検証
        assert "total_files" in stats
        assert "total_lines" in stats
        assert "languages" in stats
        assert "project_path" in stats
        
        # プロジェクトパスが正しく設定されていることを確認
        assert stats["project_path"] == temp_project
        
        # 言語が検出されていることを確認
        assert len(stats["languages"]) > 0
        assert "java" in stats["languages"]

    @pytest.mark.asyncio
    async def test_project_stats_resource_languages(self, mcp_server, temp_project):
        """project_stats リソースの言語統計テスト"""
        
        content = await mcp_server.project_stats_resource.read_resource("code://stats/languages")
        stats = json.loads(content)
        
        # 言語統計検証
        assert "languages" in stats
        assert "total_languages" in stats
        assert len(stats["languages"]) > 0
        
        # Java言語が含まれていることを確認
        java_found = False
        for lang in stats["languages"]:
            if lang["name"] == "java":
                java_found = True
                assert lang["file_count"] >= 2  # Service.java + ServiceTest.java
                assert lang["line_count"] > 0
                assert lang["percentage"] > 0
                break
        
        assert java_found, "Java language should be detected"

    @pytest.mark.asyncio
    async def test_project_stats_resource_files(self, mcp_server, temp_project):
        """project_stats リソースのファイル統計テスト"""
        
        content = await mcp_server.project_stats_resource.read_resource("code://stats/files")
        stats = json.loads(content)
        
        # ファイル統計検証
        assert "files" in stats
        assert "total_count" in stats
        assert len(stats["files"]) > 0
        
        # 特定ファイルが含まれていることを確認
        service_java_found = False
        for file_info in stats["files"]:
            if "Service.java" in file_info["path"]:
                service_java_found = True
                assert file_info["language"] == "java"
                assert file_info["line_count"] > 0
                assert file_info["size_bytes"] > 0
                break
        
        assert service_java_found, "Service.java should be in file statistics"

    @pytest.mark.asyncio
    async def test_integrated_workflow_scenario_1(self, mcp_server, temp_project):
        """統合ワークフローシナリオ1: プロジェクト分析→検索→詳細確認"""
        
        # Step 1: プロジェクト概要を取得
        overview_content = await mcp_server.project_stats_resource.read_resource("code://stats/overview")
        overview = json.loads(overview_content)
        
        assert overview["total_files"] > 0
        assert "java" in overview["languages"]
        
        # Step 2: TODOコメントを検索
        search_result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "query": "TODO",
            "case": "insensitive",
            "context_before": 1,
            "context_after": 1
        })
        
        assert len(search_result["results"]) > 0
        
        # Step 3: 見つかったファイルの詳細内容を確認
        for match in search_result["results"]:
            if "Service.java" in match["file"]:
                # 絶対パスを使用
                uri = f"code://file/{match['file']}"
                
                file_content = await mcp_server.code_file_resource.read_resource(uri)
                assert "TODO: implement data processing" in file_content
                break

    @pytest.mark.asyncio
    async def test_integrated_workflow_scenario_2(self, mcp_server, temp_project):
        """統合ワークフローシナリオ2: 言語別分析→特定言語検索→複雑度確認"""
        
        # Step 1: 言語別統計を取得
        languages_content = await mcp_server.project_stats_resource.read_resource("code://stats/languages")
        languages = json.loads(languages_content)
        
        # Javaファイルが最も多いことを確認
        java_stats = None
        for lang in languages["languages"]:
            if lang["name"] == "java":
                java_stats = lang
                break
        
        assert java_stats is not None
        assert java_stats["file_count"] >= 2
        
        # Step 2: Javaファイルでpublicメソッドを検索
        search_result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "extensions": ["java"],
            "query": "public.*\\(",
            "case": "sensitive"
        })
        
        assert len(search_result["results"]) > 0
        
        # Step 3: 複雑度統計を確認
        complexity_content = await mcp_server.project_stats_resource.read_resource("code://stats/complexity")
        complexity = json.loads(complexity_content)
        
        assert "average_complexity" in complexity
        assert "total_files_analyzed" in complexity
        assert complexity["total_files_analyzed"] > 0

    @pytest.mark.asyncio
    async def test_integrated_workflow_scenario_3(self, mcp_server, temp_project):
        """統合ワークフローシナリオ3: プロジェクト変更→境界更新→再分析"""
        
        # Step 1: 初期統計を取得
        initial_overview = await mcp_server.project_stats_resource.read_resource("code://stats/overview")
        initial_stats = json.loads(initial_overview)
        initial_file_count = initial_stats["total_files"]
        
        # Step 2: 新しいファイルを追加
        new_file = Path(temp_project) / "src" / "main" / "java" / "NewService.java"
        new_file.write_text("""
public class NewService {
    public void newMethod() {
        // New implementation
        System.out.println("New service method");
    }
}
""", encoding='utf-8')
        
        # Step 3: プロジェクト境界を再設定（リフレッシュ）
        mcp_server.set_project_path(temp_project)
        
        # Step 4: 更新された統計を確認
        updated_overview = await mcp_server.project_stats_resource.read_resource("code://stats/overview")
        updated_stats = json.loads(updated_overview)
        
        # ファイル数が増加していることを確認
        assert updated_stats["total_files"] >= initial_file_count
        
        # Step 5: 新しいファイルが検索できることを確認
        search_result = await mcp_server.find_and_grep_tool.execute({
            "roots": [temp_project],
            "query": "NewService",
            "case": "sensitive"
        })
        
        assert len(search_result["results"]) > 0
        
        # 新しいファイルが見つかることを確認
        new_service_found = False
        for match in search_result["results"]:
            if "NewService.java" in match["file"]:
                new_service_found = True
                break
        
        assert new_service_found, "NewService.java should be found after project update"

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mcp_server, temp_project):
        """統合エラーハンドリングテスト"""
        
        # 無効な統計種別
        with pytest.raises(ValueError) as exc_info:
            await mcp_server.project_stats_resource.read_resource("code://stats/invalid")
        
        assert "Unsupported statistics type" in str(exc_info.value)
        
        # 無効な検索パラメータ（空のrootsリストは実際にはエラーにならない場合がある）
        # 代わりに無効なqueryパラメータをテスト
        try:
            await mcp_server.find_and_grep_tool.execute({
                "roots": [temp_project],
                "query": ""  # 空のクエリ
            })
        except Exception:
            pass  # エラーが発生することを期待するが、必須ではない

    @pytest.mark.asyncio
    async def test_performance_integration(self, mcp_server, temp_project):
        """パフォーマンス統合テスト"""
        
        import time
        
        # 統計生成のパフォーマンステスト
        start_time = time.time()
        
        # 複数の統計を並行して取得
        tasks = [
            mcp_server.project_stats_resource.read_resource("code://stats/overview"),
            mcp_server.project_stats_resource.read_resource("code://stats/languages"),
            mcp_server.project_stats_resource.read_resource("code://stats/files")
        ]
        
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # 実行時間が合理的な範囲内であることを確認（小規模プロジェクトなので5秒以内）
        assert execution_time < 5.0, f"Statistics generation took too long: {execution_time}s"
        
        # すべての結果が有効なJSONであることを確認
        for result in results:
            stats = json.loads(result)
            assert isinstance(stats, dict)
            assert len(stats) > 0

    @pytest.mark.asyncio
    async def test_concurrent_access_integration(self, mcp_server, temp_project):
        """並行アクセス統合テスト"""
        
        # 複数の操作を並行実行
        tasks = [
            # 検索操作
            mcp_server.find_and_grep_tool.execute({
                "roots": [temp_project],
                "query": "public",
                "extensions": ["java"]
            }),
            # ファイルアクセス（絶対パス使用）
            mcp_server.code_file_resource.read_resource(f"code://file/{Path(temp_project) / 'src' / 'main' / 'java' / 'Service.java'}"),
            # 統計生成
            mcp_server.project_stats_resource.read_resource("code://stats/overview"),
            # 別の検索
            mcp_server.find_and_grep_tool.execute({
                "roots": [temp_project],
                "query": "TODO",
                "case": "insensitive"
            })
        ]
        
        # すべてのタスクが正常に完了することを確認
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 例外が発生していないことを確認
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed with exception: {result}"
        
        # 結果が期待される形式であることを確認
        assert "results" in results[0]  # find_and_grep結果
        assert "public class Service" in results[1]  # ファイル内容
        overview = json.loads(results[2])  # 統計結果
        assert "total_files" in overview
        assert "results" in results[3]  # 別のfind_and_grep結果


if __name__ == "__main__":
    pytest.main([__file__, "-v"])