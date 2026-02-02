"""
Integration tests for encoding detection with MCP tools.

Tests encoding integration with:
- find_and_grep tool
- check_code_scale tool
- analyze_code_structure tool
"""

from pathlib import Path

import pytest


@pytest.fixture
def encoding_fixtures_dir():
    """Return path to encoding fixtures directory."""
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "encoding_fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


class TestFindAndGrepWithEncoding:
    """Test find_and_grep tool with multi-encoding files."""

    def test_search_japanese_shift_jis_file(self, encoding_fixtures_dir):
        """Test searching in Shift_JIS encoded Japanese file."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        # Create Shift_JIS file with Japanese content
        test_file = encoding_fixtures_dir / "japanese_code.py"
        japanese_content = """# -*- coding: shift_jis -*-
def こんにちは():
    # 日本語のコメント
    return "Hello"

class 日本語クラス:
    pass
"""
        with open(test_file, "wb") as f:
            f.write(japanese_content.encode("shift_jis"))

        tool = FindAndGrepTool()

        # Search for Japanese text
        result = tool.execute(
            {"roots": [str(encoding_fixtures_dir)], "pattern": "*.py", "query": "日本語"}
        )

        assert result["success"] is True
        assert len(result["files"]) >= 1
        # Normalize paths for comparison (handle Windows vs Unix path separators)
        result_paths = [Path(p).resolve() for p in result["files"]]
        assert test_file.resolve() in result_paths

    def test_search_chinese_gbk_file(self, encoding_fixtures_dir):
        """Test searching in GBK encoded Chinese file."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        # Create GBK file with Chinese content
        test_file = encoding_fixtures_dir / "chinese_code.py"
        chinese_content = """# -*- coding: gbk -*-
def 你好():
    # 中文注释
    return "Hello"

class 中文类:
    pass
"""
        with open(test_file, "wb") as f:
            f.write(chinese_content.encode("gbk"))

        tool = FindAndGrepTool()

        # Search for Chinese text
        result = tool.execute(
            {"roots": [str(encoding_fixtures_dir)], "pattern": "*.py", "query": "中文"}
        )

        assert result["success"] is True
        assert len(result["files"]) >= 1
        # Normalize paths for comparison (handle Windows vs Unix path separators)
        result_paths = [Path(p).resolve() for p in result["files"]]
        assert test_file.resolve() in result_paths


class TestCheckCodeScaleWithEncoding:
    """Test check_code_scale tool with multi-encoding files."""

    def test_analyze_japanese_file(self, encoding_fixtures_dir):
        """Test analyzing Shift_JIS encoded Japanese file."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        # Create Shift_JIS file with Japanese content
        test_file = encoding_fixtures_dir / "japanese_sample.py"
        japanese_content = """# -*- coding: shift_jis -*-
\"\"\"
日本語のPythonファイル
This is a Japanese Python file
\"\"\"

def こんにちは():
    \"\"\"挨拶関数\"\"\"
    print("こんにちは世界")

class 日本語クラス:
    \"\"\"日本語のクラス\"\"\"

    def メソッド(self):
        pass

if __name__ == "__main__":
    こんにちは()
"""
        with open(test_file, "wb") as f:
            f.write(japanese_content.encode("shift_jis"))

        tool = CheckCodeScaleTool()

        result = tool.execute({"file_path": str(test_file), "include_details": True})

        assert result["success"] is True
        assert "structure" in result
        # Should detect function and class
        assert result["structure"]["total_functions"] >= 1
        assert result["structure"]["total_classes"] >= 1

    def test_analyze_chinese_file(self, encoding_fixtures_dir):
        """Test analyzing GBK encoded Chinese file."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        # Create GBK file with Chinese content
        test_file = encoding_fixtures_dir / "chinese_sample.py"
        chinese_content = """# -*- coding: gbk -*-
\"\"\"
中文Python文件
This is a Chinese Python file
\"\"\"

def 你好():
    \"\"\"问候函数\"\"\"
    print("你好世界")

class 中文类:
    \"\"\"中文类\"\"\"

    def 方法(self):
        pass

if __name__ == "__main__":
    你好()
"""
        with open(test_file, "wb") as f:
            f.write(chinese_content.encode("gbk"))

        tool = CheckCodeScaleTool()

        result = tool.execute({"file_path": str(test_file), "include_details": True})

        assert result["success"] is True
        assert "structure" in result
        # Should detect function and class
        assert result["structure"]["total_functions"] >= 1
        assert result["structure"]["total_classes"] >= 1


class TestAnalyzeToolWithEncoding:
    """Test analyze_code_structure tool with multi-encoding files."""

    def test_analyze_japanese_structure(self, encoding_fixtures_dir):
        """Test analyzing structure of Japanese file."""
        from tree_sitter_analyzer_v2.mcp.tools.analyze import AnalyzeTool

        # Create Shift_JIS file
        test_file = encoding_fixtures_dir / "japanese_struct.py"
        japanese_content = """# -*- coding: shift_jis -*-
class データクラス:
    def __init__(self, 名前):
        self.名前 = 名前

    def 表示(self):
        print(f"名前: {self.名前}")
"""
        with open(test_file, "wb") as f:
            f.write(japanese_content.encode("shift_jis"))

        tool = AnalyzeTool()

        result = tool.execute({"file_path": str(test_file)})

        assert result["success"] is True
        # analyze tool returns "data" field with TOON-formatted structure
        assert "data" in result
        # Should contain class information in the TOON output
        assert "classes:" in result["data"]
