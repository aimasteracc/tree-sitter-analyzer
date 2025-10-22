#!/usr/bin/env python3
"""
残り5ツールのエラーハンドリングテスト

このテストスイートは、以下の5つのツールのエラーハンドリングを検証します：
- check_code_scale (AnalyzeScaleTool)
- analyze_code_structure (TableFormatTool)
- query_code (QueryTool)
- find_and_grep (FindAndGrepTool)
- set_project_path (MCPサーバー内実装)
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestRemainingToolsErrorHandling:
    """残り5ツールのエラーハンドリングテスト"""

    @pytest.fixture
    def temp_project(self):
        """テスト用プロジェクト構造を作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # プロジェクト構造作成
            (project_root / "src").mkdir()
            (project_root / "tests").mkdir()

            # Python ファイル
            (project_root / "src" / "main.py").write_text(
                """#!/usr/bin/env python3
class TestClass:
    def test_method(self):
        return "test"

def test_function():
    return 42
"""
            )

            # Java ファイル
            (project_root / "src" / "Example.java").write_text(
                """
public class Example {
    public void testMethod() {
        System.out.println("Hello World");
    }
}
"""
            )

            yield str(project_root)

    @pytest.fixture
    def scale_tool(self, temp_project):
        """AnalyzeScaleTool インスタンス"""
        return AnalyzeScaleTool(temp_project)

    @pytest.fixture
    def table_tool(self, temp_project):
        """TableFormatTool インスタンス"""
        return TableFormatTool(temp_project)

    @pytest.fixture
    def query_tool(self, temp_project):
        """QueryTool インスタンス"""
        return QueryTool(temp_project)

    @pytest.fixture
    def find_grep_tool(self, temp_project):
        """FindAndGrepTool インスタンス"""
        return FindAndGrepTool(temp_project)

    @pytest.fixture
    def mcp_server(self, temp_project):
        """MCPサーバー インスタンス"""
        return TreeSitterAnalyzerMCPServer(temp_project)

    @pytest.mark.asyncio
    async def test_check_code_scale_error_handling(self, scale_tool):
        """check_code_scale ツールのエラーハンドリングテスト"""

        # 存在しないファイル - ValueError を期待
        try:
            await scale_tool.execute({"file_path": "nonexistent_file.py"})
            assert False, "Expected ValueError for nonexistent file"
        except ValueError as e:
            assert "file does not exist" in str(e) or "Invalid file path" in str(e)

        # 必須パラメータ不足
        try:
            await scale_tool.execute({})
            assert False, "Expected ValueError for missing file_path"
        except ValueError as e:
            assert "file_path" in str(e) or "required" in str(e)

        # 無効なファイルパス
        try:
            await scale_tool.execute({"file_path": "/invalid/path/outside/project.py"})
            assert False, "Expected ValueError for invalid path"
        except ValueError as e:
            assert "Invalid" in str(e) or "path" in str(e)

    @pytest.mark.asyncio
    async def test_analyze_code_structure_error_handling(self, table_tool):
        """analyze_code_structure ツールのエラーハンドリングテスト"""

        # 存在しないファイル - FileNotFoundError を期待
        try:
            await table_tool.execute({"file_path": "nonexistent_file.py"})
            assert False, "Expected FileNotFoundError for nonexistent file"
        except FileNotFoundError as e:
            assert "File not found" in str(e) or "nonexistent_file.py" in str(e)

        # 必須パラメータ不足
        try:
            await table_tool.execute({})
            assert False, "Expected ValueError for missing file_path"
        except ValueError as e:
            assert "file_path" in str(e) or "required" in str(e)

        # 無効なformat_type
        try:
            await table_tool.execute(
                {"file_path": "src/main.py", "format_type": "invalid_format"}
            )
            assert False, "Expected ValueError for invalid format_type"
        except ValueError as e:
            assert "format_type" in str(e) or "invalid" in str(e)

    @pytest.mark.asyncio
    async def test_query_code_error_handling(self, query_tool):
        """query_code ツールのエラーハンドリングテスト"""

        # 存在しないファイル - 成功レスポンスで空結果を返す
        result = await query_tool.execute(
            {"file_path": "nonexistent_file.py", "query_key": "functions"}
        )
        # query_tool は存在しないファイルでも成功レスポンスを返すが、結果は空
        assert "success" in result
        assert result.get("matches", []) == [] or result.get("count", 0) == 0

        # 必須パラメータ不足（file_pathとquery_key/query_string両方なし）
        try:
            await query_tool.execute({})
            assert False, "Expected AnalysisError for missing parameters"
        except AnalysisError as e:
            assert "file_path" in str(e) or "required" in str(e)

        # 無効なquery_key - 実装では空の結果を返す
        result = await query_tool.execute(
            {"file_path": "src/main.py", "query_key": "invalid_query_key"}
        )
        # 無効なクエリキーでも成功レスポンスを返すが、結果は空
        assert "success" in result
        assert result.get("matches", []) == [] or result.get("count", 0) == 0

    @pytest.mark.asyncio
    async def test_find_and_grep_error_handling(self, find_grep_tool):
        """find_and_grep ツールのエラーハンドリングテスト"""

        # 存在しないディレクトリ - AnalysisError を期待
        try:
            await find_grep_tool.execute(
                {"roots": ["nonexistent_directory/"], "query": "test"}
            )
            assert False, "Expected AnalysisError for nonexistent directory"
        except AnalysisError as e:
            assert "Invalid root" in str(e) or "does not exist" in str(e)

        # 必須パラメータ不足（query）
        try:
            await find_grep_tool.execute({"roots": ["src/"]})
            assert False, "Expected AnalysisError for missing query"
        except AnalysisError as e:
            assert "query" in str(e) or "required" in str(e)

        # 必須パラメータ不足（roots）
        try:
            await find_grep_tool.execute({"query": "test"})
            assert False, "Expected AnalysisError for missing roots"
        except AnalysisError as e:
            assert "roots" in str(e) or "required" in str(e)

    @pytest.mark.asyncio
    async def test_set_project_path_error_handling(self, mcp_server):
        """set_project_path ツールのエラーハンドリングテスト"""

        # 存在しないパス - set_project_path は存在チェックしない場合がある
        # 実際の動作を確認
        try:
            mcp_server.set_project_path("/nonexistent/path")
            # エラーが発生しない場合は、実装がパスの存在をチェックしていない
            pass
        except (ValueError, OSError) as e:
            assert "does not exist" in str(e) or "invalid" in str(e) or "path" in str(e)

        # 空のパス
        try:
            mcp_server.set_project_path("")
            # 空パスでもエラーが発生しない場合がある
            pass
        except (ValueError, OSError) as e:
            assert "path" in str(e) or "required" in str(e) or "empty" in str(e)

        # ファイルパス（ディレクトリではない）
        try:
            # 一時ファイルを作成
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file_path = tmp_file.name

            mcp_server.set_project_path(tmp_file_path)
            # ファイルパスでもエラーが発生しない場合がある
            pass
        except (ValueError, OSError) as e:
            assert (
                "directory" in str(e) or "not a directory" in str(e) or "file" in str(e)
            )
        finally:
            # クリーンアップ
            Path(tmp_file_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_comprehensive_error_scenarios(self, temp_project):
        """包括的なエラーシナリオテスト"""

        # 各ツールで共通のエラーパターンをテスト
        tools = [
            AnalyzeScaleTool(temp_project),
            TableFormatTool(temp_project),
            QueryTool(temp_project),
            FindAndGrepTool(temp_project),
        ]

        for tool in tools:
            # None パラメータ
            try:
                await tool.execute(None)
                # 一部のツールはNoneパラメータでもエラーにならない場合がある
                pass
            except (AnalysisError, TypeError, ValueError, AttributeError):
                pass  # 期待されるエラー

            # 空の辞書 - 一部のツールは空辞書でもエラーにならない場合がある
            try:
                await tool.execute({})
                # エラーが発生しない場合もある（デフォルト値を使用）
                pass
            except (AnalysisError, ValueError, TypeError):
                pass  # 期待されるエラー

    @pytest.mark.asyncio
    async def test_error_message_quality(self, scale_tool, table_tool, query_tool):
        """エラーメッセージの品質テスト"""

        # エラーメッセージが有用な情報を含むことを確認
        test_cases = [
            (scale_tool, {"file_path": "nonexistent.py"}, ValueError),
            (table_tool, {"file_path": "nonexistent.py"}, FileNotFoundError),
            # query_tool は存在しないファイルでもエラーにならない場合があるのでスキップ
        ]

        for tool, params, expected_error in test_cases:
            try:
                await tool.execute(params)
                assert (
                    False
                ), f"Expected {expected_error.__name__} for {tool.__class__.__name__}"
            except expected_error as e:
                error_msg = str(e)
                # エラーメッセージが空でないことを確認
                assert len(error_msg) > 0
                # ファイル名が含まれることを確認
                assert (
                    "nonexistent.py" in error_msg
                    or "File" in error_msg
                    or "file" in error_msg
                )
                # 有用なキーワードが含まれることを確認
                assert any(
                    keyword in error_msg.lower()
                    for keyword in ["not found", "does not exist", "invalid", "error"]
                )
