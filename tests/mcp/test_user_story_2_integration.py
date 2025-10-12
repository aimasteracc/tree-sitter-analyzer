#!/usr/bin/env python3
"""
User Story 2 統合テスト: 高度な解析ツール

User Story 2: 高度な解析ツール
- extract_code_section: 特定コード部分の抽出
- list_files: 高性能ファイル検索
- search_content: ripgrep統合コンテンツ検索

このテストスイートは、User Story 2の3つのツールが正常に動作し、
相互に連携して高度な解析機能を提供することを検証します。
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestUserStory2Integration:
    """User Story 2: 高度な解析ツール統合テスト"""

    @pytest.fixture
    def temp_project(self):
        """テスト用プロジェクト構造を作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            
            # プロジェクト構造作成
            (project_root / "src").mkdir()
            (project_root / "tests").mkdir()
            (project_root / "docs").mkdir()
            (project_root / "config").mkdir()
            
            # Python ファイル
            (project_root / "src" / "main.py").write_text("""#!/usr/bin/env python3
\"\"\"
Main application module
\"\"\"

import os
import sys
from typing import List, Dict, Any

class DataProcessor:
    \"\"\"Process data with various methods\"\"\"
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data = []
    
    def load_data(self, file_path: str) -> bool:
        \"\"\"Load data from file\"\"\"
        try:
            with open(file_path, 'r') as f:
                self.data = json.load(f)
            return True
        except Exception as e:
            print(f"Error loading data: {e}")
            return False
    
    def process_data(self) -> List[Dict[str, Any]]:
        \"\"\"Process loaded data\"\"\"
        # TODO: Implement advanced processing
        processed = []
        for item in self.data:
            if isinstance(item, dict):
                processed.append(item)
        return processed
    
    def save_results(self, output_path: str) -> bool:
        \"\"\"Save processed results\"\"\"
        try:
            with open(output_path, 'w') as f:
                json.dump(self.process_data(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving results: {e}")
            return False

def main():
    \"\"\"Main entry point\"\"\"
    processor = DataProcessor({"debug": True})
    if processor.load_data("input.json"):
        processor.save_results("output.json")
        print("Processing completed successfully")
    else:
        print("Failed to process data")
        sys.exit(1)

if __name__ == "__main__":
    main()
""")
            
            # JavaScript ファイル
            (project_root / "src" / "utils.js").write_text("""/**
 * Utility functions for data processing
 */

const fs = require('fs');
const path = require('path');

class FileManager {
    constructor(basePath) {
        this.basePath = basePath;
    }
    
    /**
     * Read file contents
     * @param {string} filename - File to read
     * @returns {Promise<string>} File contents
     */
    async readFile(filename) {
        const fullPath = path.join(this.basePath, filename);
        try {
            return await fs.promises.readFile(fullPath, 'utf8');
        } catch (error) {
            console.error(`Error reading file ${filename}:`, error);
            throw error;
        }
    }
    
    /**
     * Write file contents
     * @param {string} filename - File to write
     * @param {string} content - Content to write
     * @returns {Promise<void>}
     */
    async writeFile(filename, content) {
        const fullPath = path.join(this.basePath, filename);
        try {
            await fs.promises.writeFile(fullPath, content, 'utf8');
        } catch (error) {
            console.error(`Error writing file ${filename}:`, error);
            throw error;
        }
    }
    
    /**
     * List files in directory
     * @param {string} dirPath - Directory path
     * @returns {Promise<string[]>} List of files
     */
    async listFiles(dirPath = '.') {
        const fullPath = path.join(this.basePath, dirPath);
        try {
            const files = await fs.promises.readdir(fullPath);
            return files.filter(file => {
                const stat = fs.statSync(path.join(fullPath, file));
                return stat.isFile();
            });
        } catch (error) {
            console.error(`Error listing files in ${dirPath}:`, error);
            return [];
        }
    }
}

module.exports = { FileManager };
""")
            
            # テストファイル
            (project_root / "tests" / "test_main.py").write_text("""#!/usr/bin/env python3
\"\"\"
Tests for main module
\"\"\"

import unittest
import tempfile
import json
from pathlib import Path
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import DataProcessor

class TestDataProcessor(unittest.TestCase):
    \"\"\"Test DataProcessor class\"\"\"
    
    def setUp(self):
        \"\"\"Set up test fixtures\"\"\"
        self.temp_dir = tempfile.mkdtemp()
        self.config = {"debug": True, "temp_dir": self.temp_dir}
        self.processor = DataProcessor(self.config)
    
    def test_load_data_success(self):
        \"\"\"Test successful data loading\"\"\"
        test_data = [{"id": 1, "name": "test"}, {"id": 2, "name": "example"}]
        test_file = Path(self.temp_dir) / "test_input.json"
        
        with open(test_file, 'w') as f:
            json.dump(test_data, f)
        
        result = self.processor.load_data(str(test_file))
        self.assertTrue(result)
        self.assertEqual(len(self.processor.data), 2)
    
    def test_load_data_failure(self):
        \"\"\"Test data loading failure\"\"\"
        result = self.processor.load_data("nonexistent_file.json")
        self.assertFalse(result)
    
    def test_process_data(self):
        \"\"\"Test data processing\"\"\"
        self.processor.data = [
            {"id": 1, "name": "valid"},
            "invalid_string",
            {"id": 2, "name": "also_valid"}
        ]
        
        processed = self.processor.process_data()
        self.assertEqual(len(processed), 2)
        self.assertIsInstance(processed[0], dict)
        self.assertIsInstance(processed[1], dict)
    
    def test_save_results(self):
        \"\"\"Test saving results\"\"\"
        self.processor.data = [{"id": 1, "name": "test"}]
        output_file = Path(self.temp_dir) / "test_output.json"
        
        result = self.processor.save_results(str(output_file))
        self.assertTrue(result)
        self.assertTrue(output_file.exists())
        
        # Verify saved content
        with open(output_file, 'r') as f:
            saved_data = json.load(f)
        self.assertEqual(len(saved_data), 1)
        self.assertEqual(saved_data[0]["id"], 1)

if __name__ == "__main__":
    unittest.main()
""")
            
            # 設定ファイル
            (project_root / "config" / "settings.json").write_text("""{
  "application": {
    "name": "Data Processor",
    "version": "1.0.0",
    "debug": false
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "dataprocessor",
    "user": "admin"
  },
  "processing": {
    "batch_size": 1000,
    "timeout": 30,
    "retry_count": 3
  },
  "logging": {
    "level": "INFO",
    "file": "app.log",
    "max_size": "10MB"
  }
}""")
            
            # README ファイル
            (project_root / "README.md").write_text("""# Data Processor

A powerful data processing application with advanced analysis capabilities.

## Features

- **High-performance file processing**: Process large datasets efficiently
- **Flexible configuration**: JSON-based configuration system
- **Comprehensive testing**: Full test suite with unit and integration tests
- **Multi-language support**: Python and JavaScript components

## Installation

```bash
pip install -r requirements.txt
npm install
```

## Usage

### Basic Usage

```python
from src.main import DataProcessor

processor = DataProcessor({"debug": True})
processor.load_data("input.json")
results = processor.process_data()
processor.save_results("output.json")
```

### JavaScript Utilities

```javascript
const { FileManager } = require('./src/utils.js');

const manager = new FileManager('/path/to/data');
const files = await manager.listFiles();
```

## Configuration

Edit `config/settings.json` to customize application behavior:

- `application.debug`: Enable debug mode
- `processing.batch_size`: Number of items to process at once
- `logging.level`: Log level (DEBUG, INFO, WARNING, ERROR)

## Testing

Run the test suite:

```bash
python -m pytest tests/
```

## TODO

- [ ] Implement advanced processing algorithms
- [ ] Add support for CSV input/output
- [ ] Create web interface
- [ ] Add performance monitoring
- [ ] Implement data validation
""")
            
            # .gitignore ファイル
            (project_root / ".gitignore").write_text("""# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# JavaScript
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Temporary files
*.tmp
*.temp
temp/
""")
            
            yield str(project_root)

    @pytest.fixture
    def extract_tool(self, temp_project):
        """ReadPartialTool インスタンス"""
        return ReadPartialTool(project_root=temp_project)

    @pytest.fixture
    def list_files_tool(self, temp_project):
        """ListFilesTool インスタンス"""
        return ListFilesTool(project_root=temp_project)

    @pytest.fixture
    def search_tool(self, temp_project):
        """SearchContentTool インスタンス"""
        return SearchContentTool(project_root=temp_project)

    @pytest.mark.asyncio
    async def test_extract_code_section_basic(self, extract_tool):
        """T010-1: extract_code_section基本機能テスト"""
        # DataProcessorクラスの抽出
        result = await extract_tool.execute({
            "file_path": "src/main.py",
            "start_line": 9,
            "end_line": 20,
            "format": "text"
        })
        
        assert "file_path" in result
        assert "partial_content_result" in result
        content = result["partial_content_result"]
        assert "class DataProcessor:" in content
        assert "def __init__" in content

    @pytest.mark.asyncio
    async def test_extract_code_section_json_format(self, extract_tool):
        """T010-2: extract_code_section JSON形式出力テスト"""
        result = await extract_tool.execute({
            "file_path": "src/main.py",
            "start_line": 23,
            "end_line": 30,
            "format": "json"
        })
        
        assert "file_path" in result
        assert "partial_content_result" in result
        # JSON形式では構造化されたデータが返される
        assert result["content_length"] > 0

    @pytest.mark.asyncio
    async def test_list_files_basic_search(self, list_files_tool):
        """T010-3: list_files基本検索テスト"""
        result = await list_files_tool.execute({
            "roots": ["."],
            "pattern": "*.py",
            "glob": True
        })
        
        assert result["success"] is True
        assert result["count"] >= 2  # main.py, test_main.py
        
        # Python ファイルのみが含まれることを確認
        for file_info in result["results"]:
            assert file_info["path"].endswith(".py")
            assert file_info["ext"] == "py"

    @pytest.mark.asyncio
    async def test_list_files_advanced_filtering(self, list_files_tool):
        """T010-4: list_files高度フィルタリングテスト"""
        result = await list_files_tool.execute({
            "roots": ["src/", "tests/"],
            "extensions": ["py", "js"],
            "types": ["f"],
            "exclude": ["__pycache__", "*.tmp"]
        })
        
        assert result["success"] is True
        assert result["count"] >= 3  # main.py, utils.js, test_main.py
        
        # 指定された拡張子のみが含まれることを確認
        for file_info in result["results"]:
            assert file_info["ext"] in ["py", "js"]

    @pytest.mark.asyncio
    async def test_list_files_count_only(self, list_files_tool):
        """T010-5: list_filesカウントモードテスト"""
        result = await list_files_tool.execute({
            "roots": ["."],
            "count_only": True
        })
        
        assert result["success"] is True
        assert result["count_only"] is True
        assert "total_count" in result
        assert result["total_count"] >= 5  # 複数ファイルが存在

    @pytest.mark.asyncio
    async def test_search_content_basic(self, search_tool):
        """T010-6: search_content基本検索テスト"""
        result = await search_tool.execute({
            "query": "class",
            "roots": ["src/"]
        })
        
        assert result["success"] is True
        assert result["count"] >= 2  # DataProcessor, FileManager
        
        # 検索結果の構造確認
        for match in result["results"]:
            assert "file" in match
            assert "line" in match
            assert "text" in match
            assert "class" in match["text"]

    @pytest.mark.asyncio
    async def test_search_content_regex_pattern(self, search_tool):
        """T010-7: search_content正規表現パターンテスト"""
        result = await search_tool.execute({
            "query": "def\\s+\\w+\\(",
            "roots": ["src/"],
            "case": "sensitive"
        })
        
        assert result["success"] is True
        assert result["count"] >= 5  # 複数のメソッド定義
        
        # 正規表現マッチの確認
        for match in result["results"]:
            assert "def " in match["text"]
            assert "(" in match["text"]

    @pytest.mark.asyncio
    async def test_search_content_count_only(self, search_tool):
        """T010-8: search_contentカウントモードテスト"""
        result = await search_tool.execute({
            "query": "TODO",
            "roots": ["."],
            "count_only_matches": True
        })
        
        assert result["success"] is True
        assert result["count_only"] is True
        assert "total_matches" in result
        assert "file_counts" in result
        assert result["total_matches"] >= 1  # README.mdにTODOが存在

    @pytest.mark.asyncio
    async def test_search_content_total_only(self, search_tool):
        """T010-9: search_content合計モードテスト"""
        result = await search_tool.execute({
            "query": "import",
            "roots": ["src/"],
            "total_only": True
        })
        
        # total_onlyモードでは数値のみが返される
        assert isinstance(result, int)
        assert result >= 2  # 複数のimport文が存在

    @pytest.mark.asyncio
    async def test_workflow_file_discovery_and_analysis(self, list_files_tool, search_tool, extract_tool):
        """T010-10: ワークフロー統合テスト - ファイル発見→検索→抽出"""
        
        # Step 1: Python ファイルを発見
        files_result = await list_files_tool.execute({
            "roots": ["src/"],
            "extensions": ["py"],
            "types": ["f"]
        })
        
        assert files_result["success"] is True
        python_files = [f["path"] for f in files_result["results"]]
        assert len(python_files) >= 1
        
        # Step 2: クラス定義を検索
        search_result = await search_tool.execute({
            "query": "class\\s+\\w+",
            "files": python_files
        })
        
        assert search_result["success"] is True
        assert search_result["count"] >= 1
        
        # Step 3: 見つかったクラスの詳細を抽出
        class_match = search_result["results"][0]
        class_file = class_match["file"]
        class_line = class_match["line"]
        
        extract_result = await extract_tool.execute({
            "file_path": class_file,
            "start_line": class_line,
            "end_line": class_line + 10
        })
        
        assert "file_path" in extract_result
        assert "class" in extract_result["partial_content_result"]

    @pytest.mark.asyncio
    async def test_workflow_todo_analysis(self, search_tool, extract_tool):
        """T010-11: ワークフロー統合テスト - TODO分析"""
        
        # Step 1: TODO項目を検索
        todo_result = await search_tool.execute({
            "query": "TODO",
            "roots": ["."],
            "context_before": 1,
            "context_after": 2
        })
        
        assert todo_result["success"] is True
        assert todo_result["count"] >= 1
        
        # Step 2: TODO周辺のコードを詳細抽出
        for match in todo_result["results"][:2]:  # 最初の2つのTODOを分析
            file_path = match["file"]
            line_num = match["line"]
            
            # TODO周辺のより広いコンテキストを抽出
            context_result = await extract_tool.execute({
                "file_path": file_path,
                "start_line": max(1, line_num - 3),
                "end_line": line_num + 5,
                "format": "text"
            })
            
            assert "file_path" in context_result
            assert "TODO" in context_result["partial_content_result"]

    @pytest.mark.asyncio
    async def test_workflow_configuration_analysis(self, list_files_tool, search_tool, extract_tool):
        """T010-12: ワークフロー統合テスト - 設定ファイル分析"""
        
        # Step 1: 設定ファイルを発見
        config_files = await list_files_tool.execute({
            "roots": ["config/"],
            "extensions": ["json", "yaml", "yml", "toml"],
            "types": ["f"]
        })
        
        assert config_files["success"] is True
        assert config_files["count"] >= 1
        
        # Step 2: 設定値を検索
        for config_file in config_files["results"]:
            if config_file["ext"] == "json":
                # JSON設定ファイル内の特定設定を検索
                setting_search = await search_tool.execute({
                    "query": "\"debug\"",
                    "files": [config_file["path"]],
                    "fixed_strings": True
                })
                
                if setting_search["success"] and setting_search["count"] > 0:
                    # 設定周辺のコンテキストを抽出
                    match = setting_search["results"][0]
                    context = await extract_tool.execute({
                        "file_path": match["file"],
                        "start_line": max(1, match["line"] - 2),
                        "end_line": match["line"] + 2,
                        "format": "text"
                    })
                    
                    assert "file_path" in context
                    assert "debug" in context["partial_content_result"]

    @pytest.mark.asyncio
    async def test_performance_large_search(self, search_tool):
        """T010-13: パフォーマンステスト - 大規模検索"""
        import time
        
        start_time = time.time()
        
        # 全ファイルでの包括的検索
        result = await search_tool.execute({
            "query": "\\w+",  # 任意の単語
            "roots": ["."],
            "max_count": 100,  # 結果を制限
            "summary_only": True
        })
        
        elapsed = time.time() - start_time
        
        assert result["success"] is True
        assert elapsed < 5.0  # 5秒以内で完了
        assert "summary" in result
        assert result["count"] <= 100

    @pytest.mark.asyncio
    async def test_error_handling_invalid_paths(self, extract_tool, list_files_tool, search_tool):
        """T010-14: エラーハンドリングテスト - 無効なパス"""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError
        
        # extract_code_section: 存在しないファイル
        extract_result = await extract_tool.execute({
            "file_path": "nonexistent/file.py",
            "start_line": 1,
            "end_line": 10
        })
        # エラーが適切にハンドリングされることを確認
        assert extract_result["success"] is False
        assert "file does not exist" in extract_result["error"]
        
        # list_files: 存在しないディレクトリ
        try:
            await list_files_tool.execute({
                "roots": ["nonexistent_directory/"]
            })
            assert False, "Expected AnalysisError for nonexistent directory"
        except AnalysisError as e:
            assert "Invalid root" in str(e) or "does not exist" in str(e)
        
        # search_content: 存在しないファイル
        try:
            await search_tool.execute({
                "query": "test",
                "files": ["nonexistent_file.py"]
            })
            assert False, "Expected AnalysisError for nonexistent file"
        except AnalysisError as e:
            assert "File not found" in str(e) or "does not exist" in str(e)

    @pytest.mark.asyncio
    async def test_file_output_integration(self, search_tool, extract_tool, temp_project):
        """T010-15: ファイル出力統合テスト"""
        
        # search_contentでファイル出力
        search_result = await search_tool.execute({
            "query": "class",
            "roots": ["src/"],
            "output_file": "search_results",
            "suppress_output": True
        })
        
        assert search_result["success"] is True
        assert search_result["count"] >= 1
        
        # ファイル出力機能が動作することを確認
        assert "output_file" in search_result
        assert "file_saved" in search_result
        assert search_result["output_file"] == "search_results"
        
        # extract_code_sectionでファイル出力
        extract_result = await extract_tool.execute({
            "file_path": "src/main.py",
            "start_line": 1,
            "end_line": 20,
            "output_file": "extracted_code",
            "suppress_output": True
        })
        
        assert "file_path" in extract_result
        assert "output_file_path" in extract_result
        assert "file_saved" in extract_result
        
        # ファイル出力機能が正常に動作することを確認
        # suppress_outputが有効な場合、ファイルに保存され、file_savedがTrueになる
        assert extract_result["file_saved"] is True
        assert extract_result["content_length"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])