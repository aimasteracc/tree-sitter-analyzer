"""项目边界、源码资源与统计资源的集成行为；退役检索接口另见 RFC-0033。"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


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
            java_main.write_text(
                """
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
""",
                encoding="utf-8",
                newline="\n",
            )

            java_test = project_path / "src" / "test" / "java" / "ServiceTest.java"
            java_test.write_text(
                """
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
""",
                encoding="utf-8",
                newline="\n",
            )

            # Pythonスクリプト作成
            python_script = project_path / "scripts" / "helper.py"
            python_script.write_text(
                '''#!/usr/bin/env python3
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
''',
                encoding="utf-8",
                newline="\n",
            )

            # ドキュメント作成
            readme = project_path / "docs" / "README.md"
            readme.write_text(
                """
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
""",
                encoding="utf-8",
                newline="\n",
            )

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
    async def test_code_file_resource_access(self, mcp_server, temp_project):
        """T017: code_file リソースアクセステスト"""

        # Javaファイルの絶対パスを取得
        java_file_path = str(
            Path(temp_project) / "src" / "main" / "java" / "Service.java"
        )
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
            await mcp_server.code_file_resource.read_resource(
                "code://file/../../../etc/passwd"
            )

        assert "Path traversal not allowed" in str(exc_info.value)

        # 無効なURI形式テスト
        with pytest.raises(ValueError) as exc_info:
            await mcp_server.code_file_resource.read_resource(
                "invalid://file/test.java"
            )

        assert "does not match code file pattern" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_project_stats_resource_overview(self, mcp_server, temp_project):
        """project_stats リソースの概要統計テスト"""

        content = await mcp_server.project_stats_resource.read_resource(
            "code://stats/overview"
        )
        stats = json.loads(content)

        # 基本統計検証
        assert "total_files" in stats
        assert "total_lines" in stats
        assert "languages" in stats
        assert "project_path" in stats

        # プロジェクトパスが正しく設定されていることを確認
        assert stats["project_path"] == temp_project

        # 言語が検出されていることを確認
        assert len(stats["languages"]) == 3
        assert "java" in stats["languages"]

    @pytest.mark.asyncio
    async def test_project_stats_resource_languages(self, mcp_server, temp_project):
        """project_stats リソースの言語統計テスト"""

        content = await mcp_server.project_stats_resource.read_resource(
            "code://stats/languages"
        )
        stats = json.loads(content)

        # 言語統計検証
        assert "languages" in stats
        assert "total_languages" in stats
        assert len(stats["languages"]) == 3

        # Java言語が含まれていることを確認
        java_found = False
        for lang in stats["languages"]:
            if lang["name"] == "java":
                java_found = True
                assert lang["file_count"] == 2  # Service.java + ServiceTest.java
                assert lang["line_count"] == 34
                assert lang["percentage"] == 31.78
                break

        assert java_found, "Java language should be detected"

    @pytest.mark.asyncio
    async def test_project_stats_resource_files(self, mcp_server, temp_project):
        """project_stats リソースのファイル統計テスト"""

        content = await mcp_server.project_stats_resource.read_resource(
            "code://stats/files"
        )
        stats = json.loads(content)

        # ファイル統計検証
        assert "files" in stats
        assert "total_count" in stats
        assert len(stats["files"]) == 4

        # 特定ファイルが含まれていることを確認
        service_java_found = False
        for file_info in stats["files"]:
            if "Service.java" in file_info["path"]:
                service_java_found = True
                assert file_info["language"] == "java"
                assert file_info["line_count"] == 17
                assert file_info["size_bytes"] == 318
                break

        assert service_java_found, "Service.java should be in file statistics"

    @pytest.mark.asyncio
    async def test_project_stats_complexity_survives_search_retirement(
        self, mcp_server, temp_project
    ):
        # 2026-09-09：原混合场景退役时仍须保留复杂度统计的独立责任。
        stats = json.loads(
            await mcp_server.project_stats_resource.read_resource(
                "code://stats/complexity"
            )
        )
        assert stats["total_files_analyzed"] == 2
        assert stats["average_complexity"] == 2.5
        assert stats["files_by_complexity"] == [
            {"file": "src/main/java/Service.java", "language": "java", "complexity": 3},
            {
                "file": "src/test/java/ServiceTest.java",
                "language": "java",
                "complexity": 2,
            },
        ]

    @pytest.mark.asyncio
    async def test_reset_project_path_refreshes_file_inventory(
        self, mcp_server, temp_project
    ):
        # 2026-09-09：旧场景的弱增量断言改为四个文件到五个文件的精确见证。
        before = json.loads(
            await mcp_server.project_stats_resource.read_resource(
                "code://stats/overview"
            )
        )
        (Path(temp_project) / "src/main/java/NewService.java").write_text(
            "public class NewService {}", encoding="utf-8"
        )
        mcp_server.set_project_path(temp_project)
        after = json.loads(
            await mcp_server.project_stats_resource.read_resource(
                "code://stats/overview"
            )
        )
        assert (before["total_files"], after["total_files"]) == (4, 5)

    @pytest.mark.asyncio
    async def test_concurrent_file_and_stats_reads_preserve_results(
        self, mcp_server, temp_project
    ):
        # 2026-09-09：并发场景保留文件与统计读取，不再调用退役搜索包装器。
        source = Path(temp_project) / "src/main/java/Service.java"
        content, overview = await asyncio.gather(
            mcp_server.code_file_resource.read_resource(f"code://file/{source}"),
            mcp_server.project_stats_resource.read_resource("code://stats/overview"),
        )
        assert content == source.read_text(encoding="utf-8")
        assert json.loads(overview)["total_files"] == 4

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mcp_server, temp_project):
        """統合エラーハンドリングテスト"""

        # 無効な統計種別
        with pytest.raises(ValueError) as exc_info:
            await mcp_server.project_stats_resource.read_resource(
                "code://stats/invalid"
            )

        assert "Unsupported statistics type" in str(exc_info.value)

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
            mcp_server.project_stats_resource.read_resource("code://stats/files"),
        ]

        results = await asyncio.gather(*tasks)

        end_time = time.time()
        execution_time = end_time - start_time

        # 実行時間が合理的な範囲内であることを確認（小規模プロジェクトなので5秒以内）
        assert execution_time < 5.0, (
            f"Statistics generation took too long: {execution_time}s"
        )

        # すべての結果が有効なJSONであることを確認 (overview=5 keys, languages=3 keys, files=3 keys)
        expected_lens = [5, 3, 3]
        for i, result in enumerate(results):
            stats = json.loads(result)
            assert isinstance(stats, dict)
            assert len(stats) == expected_lens[i]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
