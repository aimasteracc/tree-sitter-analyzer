#!/usr/bin/env python3
"""Debug async QueryService"""

import asyncio
import tempfile
from pathlib import Path

from tree_sitter_analyzer.core.query_service import QueryService


async def debug_test():
    """デバッグテスト"""
    print("🔍 Debugging async QueryService...")

    # テストファイルを作成
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        test_content = """
def test_function():
    return 42

class TestClass:
    def method(self):
        pass
"""
        f.write(test_content)
        test_file = f.name

    try:
        service = QueryService()

        # 1. ファイル読み込みテスト
        print(f"📁 Testing file reading: {test_file}")
        if hasattr(service, "_read_file_async"):
            content, encoding = await service._read_file_async(test_file)
            print(f"📄 File content length: {len(content)}")
            print(f"📄 File encoding: {encoding}")
            print(f"📄 File content preview: {content[:100]}...")
        else:
            print("❌ _read_file_async method not found")

        # 2. 利用可能なクエリの確認
        print("🔍 Available queries for Python:")
        available_queries = service.get_available_queries("python")
        print(f"📋 Available queries: {available_queries}")

        # 3. クエリ実行テスト
        print("🚀 Testing query execution...")
        try:
            results = await service.execute_query(
                file_path=test_file, language="python", query_key="function"
            )
            print(f"✅ Query results: {len(results) if results else 0} items")
            if results:
                for i, result in enumerate(results[:3]):  # 最初の3つを表示
                    print(f"  {i + 1}. {result}")
            else:
                print("  No results found")
        except Exception as e:
            print(f"❌ Query execution failed: {e}")
            import traceback

            traceback.print_exc()

        # 4. カスタムクエリテスト
        print("🔧 Testing custom query...")
        try:
            custom_results = await service.execute_query(
                file_path=test_file,
                language="python",
                query_string="(function_definition) @function",
            )
            print(
                f"✅ Custom query results: {len(custom_results) if custom_results else 0} items"
            )
        except Exception as e:
            print(f"❌ Custom query failed: {e}")

    finally:
        # クリーンアップ
        Path(test_file).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(debug_test())
