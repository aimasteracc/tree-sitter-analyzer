#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration tests for MCP Server (Fixed Version)

Tests the complete MCP server functionality including tools,
resources, and their interactions.

修正点：
- 根本原因に基づくクリーンアップフィクスチャの改良
- シングルトンインスタンスの明示的なクリーンアップ
- デストラクタでの非同期処理問題の解決
"""

import asyncio
import json
import tempfile
import gc
import warnings
from pathlib import Path
from typing import Any, Dict
# Mock functionality now provided by pytest-mock

import pytest
import pytest_asyncio

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.utils import get_cache_manager, get_error_handler, get_performance_monitor

@pytest_asyncio.fixture(autouse=True)
async def cleanup_event_loop():
    """イベントループクリーンアップフィクスチャ（根本修正版）"""
    yield
    
    # 明示的にシングルトンインスタンスをクリーンアップ
    try:
        # パフォーマンスモニター（UnifiedAnalysisEngine）のクリーンアップ
        monitor = get_performance_monitor()
        if monitor and hasattr(monitor, 'cleanup'):
            monitor.cleanup()
        
        # キャッシュマネージャーのクリーンアップ
        cache_manager = get_cache_manager()
        if cache_manager and hasattr(cache_manager, 'clear_all_caches'):
            cache_manager.clear_all_caches()
            
    except Exception as e:
        print(f"Warning: Error during explicit cleanup: {e}")
    
    # テスト後のクリーンアップ
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and not loop.is_closed():
        # 残っているタスクを調査
        pending = asyncio.all_tasks(loop)
        current_task = asyncio.current_task(loop)
        
        # 現在のタスクを除外
        pending = {task for task in pending if task is not current_task}
        
        if pending:
            # タスクをキャンセル
            for task in pending:
                if not task.done():
                    task.cancel()
            
            # 短時間待機してキャンセルを処理
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                print(f"Warning: {len(pending)} tasks did not complete within timeout")
                # 強制的にタスクの状態を確認
                for i, task in enumerate(pending):
                    if not task.done():
                        print(f"  Task {i} is still running: {task}")
                        # 強制終了を試行
                        try:
                            task.cancel()
                        except Exception:
                            pass
        
        # イベントループの明示的なクリーンアップ
        try:
            # 残っているコールバックを処理
            if hasattr(loop, '_ready'):
                loop._ready.clear()
            if hasattr(loop, '_scheduled'):
                loop._scheduled.clear()
            
            # ソケットとファイルディスクリプタのクリーンアップ
            if hasattr(loop, '_selector') and loop._selector:
                try:
                    # セレクターの登録されたファイルディスクリプタをクリーンアップ
                    for key in list(loop._selector.get_map().values()):
                        try:
                            loop._selector.unregister(key.fileobj)
                        except (KeyError, ValueError, OSError):
                            pass
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"Warning: Error during loop cleanup: {e}")
    
    # ガベージコレクションを強制実行
    gc.collect()



class TestMCPServerIntegration:
    """Integration tests for the complete MCP server"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.server = TreeSitterAnalyzerMCPServer()
        
        # Create temporary test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_files = self._create_test_files()
        
        # Set project path for statistics
        self.server.set_project_path(self.temp_dir)
        
        # Clear caches and metrics
        get_cache_manager().clear_all_caches()
        get_error_handler().clear_history()
        get_performance_monitor().clear_metrics()

    def teardown_method(self) -> None:
        """Clean up test fixtures"""
        import shutil
        
        # ResourceWarningを一時的に抑制
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            
            # 明示的なクリーンアップ
            try:
                monitor = get_performance_monitor()
                if monitor and hasattr(monitor, 'cleanup'):
                    monitor.cleanup()
            except Exception:
                pass
            
            # サーバーインスタンスのクリーンアップ
            if hasattr(self, 'server'):
                try:
                    # サーバーの参照をクリア
                    if hasattr(self.server, 'server') and self.server.server:
                        self.server.server = None
                    
                    # アナライザーの参照をクリア
                    if hasattr(self.server, 'universal_analyzers'):
                        self.server.universal_analyzers.clear()
                        
                    self.server = None
                except Exception:
                    pass
            
            # 一時ディレクトリの削除
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            
            # ガベージコレクションを強制実行
            gc.collect()

    def _create_test_files(self) -> Dict[str, Path]:
        """Create test files for integration testing"""
        test_files = {}
        
        # Java file
        java_content = '''package com.example.test;

import java.util.List;
import java.util.ArrayList;

/**
 * Test class for integration testing
 */
public class TestClass {
    private String name;
    private List<String> items;
    
    public TestClass(String name) {
        this.name = name;
        this.items = new ArrayList<>();
    }
    
    public void addItem(String item) {
        if (item != null && !item.isEmpty()) {
            items.add(item);
        }
    }
    
    public String getName() {
        return name;
    }
    
    public List<String> getItems() {
        return new ArrayList<>(items);
    }
}
'''
        java_file = Path(self.temp_dir) / "TestClass.java"
        java_file.write_text(java_content)
        test_files["java"] = java_file
        
        # Python file
        python_content = '''#!/usr/bin/env python3
"""
Test Python module for integration testing
"""

from typing import List, Optional


class DataProcessor:
    """Process data with various operations"""
    
    def __init__(self, name: str):
        self.name = name
        self.data: List[str] = []
    
    def add_data(self, item: str) -> None:
        """Add data item"""
        if item and isinstance(item, str):
            self.data.append(item)
    
    def process_data(self) -> List[str]:
        """Process all data items"""
        result = []
        for item in self.data:
            if len(item) > 3:
                result.append(item.upper())
        return result
    
    def get_stats(self) -> dict:
        """Get processing statistics"""
        return {
            "total_items": len(self.data),
            "processed_items": len(self.process_data()),
            "processor_name": self.name
        }


def main():
    """Main function"""
    processor = DataProcessor("test")
    processor.add_data("hello")
    processor.add_data("world")
    print(processor.get_stats())


if __name__ == "__main__":
    main()
'''
        python_file = Path(self.temp_dir) / "data_processor.py"
        python_file.write_text(python_content)
        test_files["python"] = python_file
        
        # JavaScript file
        js_content = '''/**
 * Test JavaScript module for integration testing
 */

class Calculator {
    constructor(name) {
        this.name = name;
        this.history = [];
    }
    
    add(a, b) {
        const result = a + b;
        this.history.push(`${a} + ${b} = ${result}`);
        return result;
    }
    
    multiply(a, b) {
        const result = a * b;
        this.history.push(`${a} * ${b} = ${result}`);
        return result;
    }
    
    getHistory() {
        return [...this.history];
    }
    
    clear() {
        this.history = [];
    }
}

function createCalculator(name) {
    return new Calculator(name);
}

module.exports = { Calculator, createCalculator };
'''
        js_file = Path(self.temp_dir) / "calculator.js"
        js_file.write_text(js_content)
        test_files["javascript"] = js_file
        
        return test_files

    @pytest.mark.asyncio
    async def test_complete_analysis_workflow(self) -> None:
        """Test complete analysis workflow with multiple tools"""
        # Test Java file analysis
        java_file = str(self.test_files["java"])
        
        # Test analyze_code_scale
        scale_result = await self.server._analyze_code_scale({
            "file_path": java_file,
            "include_complexity": True,
            "include_details": True
        })
        
        assert "metrics" in scale_result
        assert "elements" in scale_result["metrics"]
        assert scale_result["metrics"]["elements"]["classes"] > 0
        assert scale_result["metrics"]["elements"]["methods"] > 0
        
        # Test universal analysis
        universal_result = await self.server.universal_analyze_tool.execute({
            "file_path": java_file,
            "analysis_type": "detailed",
            "include_ast": True
        })
        
        assert "analyzer_type" in universal_result
        assert universal_result["language"] == "java"
        
        # Test partial reading
        partial_result = await self.server.read_partial_tool.execute({
            "file_path": java_file,
            "start_line": 1,
            "end_line": 10
        })
        
        assert "partial_content_result" in partial_result
        assert "package com.example.test" in partial_result["partial_content_result"]
        
        # Position detection functionality has been removed
        # Test continues with other tools

    @pytest.mark.asyncio
    async def test_multi_language_support(self) -> None:
        """Test multi-language analysis support"""
        languages_tested = []
        
        for lang, file_path in self.test_files.items():
            try:
                result = await self.server.universal_analyze_tool.execute({
                    "file_path": str(file_path),
                    "analysis_type": "basic"
                })
                
                assert result["language"] == lang
                assert "metrics" in result
                languages_tested.append(lang)
                
            except Exception as e:
                pytest.fail(f"Failed to analyze {lang} file: {e}")
        
        # Verify we tested multiple languages
        assert len(languages_tested) >= 2

    @pytest.mark.asyncio
    async def test_resource_functionality(self) -> None:
        """Test MCP resource functionality"""
        # Test code file resource
        java_file = str(self.test_files["java"])
        file_uri = f"code://file/{java_file}"
        
        assert self.server.code_file_resource.matches_uri(file_uri)
        
        file_content = await self.server.code_file_resource.read_resource(file_uri)
        assert "package com.example.test" in file_content
        
        # Test project statistics resource
        stats_uri = "code://stats/overview"
        assert self.server.project_stats_resource.matches_uri(stats_uri)
        
        overview_content = await self.server.project_stats_resource.read_resource(stats_uri)
        overview_data = json.loads(overview_content)
        
        assert "total_files" in overview_data
        assert "languages" in overview_data
        assert overview_data["total_files"] >= 0

    def test_server_initialization(self) -> None:
        """Test server initialization and configuration"""
        # Test server components are initialized
        assert self.server.analysis_engine is not None
        assert self.server.read_partial_tool is not None
        assert self.server.universal_analyze_tool is not None
        assert self.server.code_file_resource is not None
        assert self.server.project_stats_resource is not None
        
        # Test server metadata
        assert self.server.name is not None
        assert self.server.version is not None


if __name__ == "__main__":
    pytest.main([__file__])