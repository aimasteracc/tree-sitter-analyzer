#!/usr/bin/env python3
"""
Phase 7: Performance Integration Tests

エンタープライズグレードのパフォーマンス統合テスト:
- 実世界の負荷条件下でのパフォーマンス検証
- スケーラビリティテスト
- メモリ効率性テスト
- 同時実行性能テスト
"""

import asyncio
import gc
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil
import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


class PerformanceProfiler:
    """パフォーマンス測定ユーティリティ"""

    def __init__(self):
        self.process = psutil.Process()
        self.start_time = None
        self.start_memory = None
        self.start_cpu = None

    def start_profiling(self):
        """プロファイリング開始"""
        gc.collect()  # ガベージコレクション実行
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss
        self.start_cpu = self.process.cpu_percent()

    def end_profiling(self) -> dict[str, Any]:
        """プロファイリング終了と結果取得"""
        end_time = time.time()
        end_memory = self.process.memory_info().rss
        end_cpu = self.process.cpu_percent()

        return {
            "execution_time": end_time - self.start_time,
            "memory_used": end_memory - self.start_memory,
            "peak_memory": self.process.memory_info().rss,
            "cpu_usage": end_cpu,
            "memory_mb": (end_memory - self.start_memory) / 1024 / 1024,
        }


class TestPhase7PerformanceIntegration:
    """Phase 7 パフォーマンス統合テスト"""

    @pytest.fixture(scope="class")
    def large_scale_project(self):
        """大規模プロジェクト作成（パフォーマンステスト用）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # 大量のファイルを作成
            self._create_large_scale_structure(project_root)

            yield str(project_root)

    def _create_large_scale_structure(self, project_root: Path):
        """大規模プロジェクト構造作成"""
        # 100個のJavaクラス
        java_root = project_root / "src" / "main" / "java" / "com" / "enterprise"
        java_root.mkdir(parents=True)

        for i in range(100):
            package_dir = java_root / f"package{i // 10}"
            package_dir.mkdir(exist_ok=True)

            class_content = f"""
package com.enterprise.package{i // 10};

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

/**
 * Generated class {i} for performance testing
 */
public class GeneratedClass{i} {{
    private String name;
    private List<String> items;
    private Map<String, Object> properties;

    public GeneratedClass{i}(String name) {{
        this.name = name;
        this.items = new ArrayList<>();
        this.properties = new HashMap<>();
    }}

    public String getName() {{ return name; }}
    public void setName(String name) {{ this.name = name; }}

    public List<String> getItems() {{ return items; }}
    public void addItem(String item) {{ items.add(item); }}

    public Map<String, Object> getProperties() {{ return properties; }}
    public void setProperty(String key, Object value) {{ properties.put(key, value); }}

    public void processData() {{
        for (int j = 0; j < 10; j++) {{
            items.add("item_" + j);
            properties.put("key_" + j, "value_" + j);
        }}
    }}

    public String generateReport() {{
        StringBuilder report = new StringBuilder();
        report.append("Class: ").append(name).append("\\n");
        report.append("Items: ").append(items.size()).append("\\n");
        report.append("Properties: ").append(properties.size()).append("\\n");
        return report.toString();
    }}

    public boolean validateData() {{
        return name != null && !name.isEmpty() && items != null && properties != null;
    }}

    public void cleanup() {{
        items.clear();
        properties.clear();
    }}
}}
"""
            (package_dir / f"GeneratedClass{i}.java").write_text(class_content)

        # 50個のPythonモジュール
        python_root = project_root / "python" / "modules"
        python_root.mkdir(parents=True)

        for i in range(50):
            module_content = f'''#!/usr/bin/env python3
"""
Generated module {i} for performance testing
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class DataModel{i}:
    """Generated data model {i}"""
    id: int = {i}
    name: str = "model_{i}"
    items: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def add_item(self, item: str) -> None:
        """Add item to the model"""
        self.items.append(item)

    def set_property(self, key: str, value: Any) -> None:
        """Set property value"""
        self.properties[key] = value

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get property value"""
        return self.properties.get(key, default)

    def process_data(self) -> Dict[str, Any]:
        """Process model data"""
        result = {{}}
        for j in range(10):
            self.add_item(f"item_{{j}}")
            self.set_property(f"key_{{j}}", f"value_{{j}}")

        result["item_count"] = len(self.items)
        result["property_count"] = len(self.properties)
        result["processed_at"] = datetime.now().isoformat()

        return result

    def validate(self) -> bool:
        """Validate model data"""
        return (
            self.id >= 0 and
            self.name and
            isinstance(self.items, list) and
            isinstance(self.properties, dict)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {{
            "id": self.id,
            "name": self.name,
            "items": self.items,
            "properties": self.properties,
            "created_at": self.created_at.isoformat()
        }}

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


class ProcessorService{i}:
    """Generated processor service {i}"""

    def __init__(self):
        self.models: List[DataModel{i}] = []
        self.cache: Dict[int, Any] = {{}}

    def add_model(self, model: DataModel{i}) -> None:
        """Add model to processor"""
        if model.validate():
            self.models.append(model)
            self.cache[model.id] = model.to_dict()

    def process_all(self) -> List[Dict[str, Any]]:
        """Process all models"""
        results = []
        for model in self.models:
            result = model.process_data()
            results.append(result)
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {{
            "total_models": len(self.models),
            "cache_size": len(self.cache),
            "average_items": sum(len(m.items) for m in self.models) / len(self.models) if self.models else 0,
            "average_properties": sum(len(m.properties) for m in self.models) / len(self.models) if self.models else 0
        }}

    def cleanup(self) -> None:
        """Cleanup processor"""
        self.models.clear()
        self.cache.clear()


def create_sample_data_{i}() -> List[DataModel{i}]:
    """Create sample data for testing"""
    models = []
    for j in range(5):
        model = DataModel{i}(
            id=j,
            name=f"sample_model_{{j}}"
        )
        model.process_data()
        models.append(model)
    return models


def main():
    """Main function for module {i}"""
    processor = ProcessorService{i}()
    sample_data = create_sample_data_{i}()

    for model in sample_data:
        processor.add_model(model)

    results = processor.process_all()
    stats = processor.get_statistics()

    print(f"Module {i} processed {{len(results)}} models")
    print(f"Statistics: {{stats}}")

    processor.cleanup()


if __name__ == "__main__":
    main()
'''
            (python_root / f"module_{i}.py").write_text(module_content)

        # 30個のJavaScriptファイル
        js_root = project_root / "frontend" / "src" / "components"
        js_root.mkdir(parents=True)

        for i in range(30):
            js_content = f"""/**
 * Generated React component {i} for performance testing
 */

import React, {{ useState, useEffect, useCallback, useMemo }} from 'react';

const GeneratedComponent{i} = ({{ data, onUpdate, config }}) => {{
    const [state, setState] = useState({{
        items: [],
        loading: false,
        error: null,
        counter: 0
    }});

    const [cache, setCache] = useState(new Map());

    // Memoized calculations
    const processedData = useMemo(() => {{
        if (!data) return [];

        return data.map((item, index) => ({{
            ...item,
            id: `item_${{index}}`,
            processed: true,
            timestamp: Date.now()
        }}));
    }}, [data]);

    const statistics = useMemo(() => ({{
        totalItems: processedData.length,
        loadingState: state.loading,
        errorCount: state.error ? 1 : 0,
        cacheSize: cache.size
    }}), [processedData, state.loading, state.error, cache.size]);

    // Event handlers
    const handleItemClick = useCallback((itemId) => {{
        setState(prev => ({{
            ...prev,
            counter: prev.counter + 1
        }}));

        if (onUpdate) {{
            onUpdate({{
                action: 'item_clicked',
                itemId,
                timestamp: Date.now()
            }});
        }}
    }}, [onUpdate]);

    const handleDataRefresh = useCallback(async () => {{
        setState(prev => ({{ ...prev, loading: true, error: null }}));

        try {{
            // Simulate API call
            await new Promise(resolve => setTimeout(resolve, 100));

            const newItems = Array.from({{ length: 10 }}, (_, index) => ({{
                id: `generated_${{index}}`,
                name: `Item ${{index}}`,
                value: Math.random() * 100
            }}));

            setState(prev => ({{
                ...prev,
                items: newItems,
                loading: false
            }}));

            // Update cache
            setCache(prev => {{
                const newCache = new Map(prev);
                newItems.forEach(item => {{
                    newCache.set(item.id, item);
                }});
                return newCache;
            }});

        }} catch (error) {{
            setState(prev => ({{
                ...prev,
                loading: false,
                error: error.message
            }}));
        }}
    }}, []);

    const handleClearCache = useCallback(() => {{
        setCache(new Map());
        setState(prev => ({{ ...prev, counter: 0 }}));
    }}, []);

    // Effects
    useEffect(() => {{
        if (config?.autoRefresh) {{
            const interval = setInterval(handleDataRefresh, config.refreshInterval || 5000);
            return () => clearInterval(interval);
        }}
    }}, [config, handleDataRefresh]);

    useEffect(() => {{
        // Cleanup on unmount
        return () => {{
            setCache(new Map());
        }};
    }}, []);

    // Render helpers
    const renderItem = useCallback((item) => (
        <div
            key={{item.id}}
            className="item"
            onClick={{() => handleItemClick(item.id)}}
        >
            <h4>{{item.name}}</h4>
            <p>Value: {{item.value?.toFixed(2)}}</p>
            <small>ID: {{item.id}}</small>
        </div>
    ), [handleItemClick]);

    const renderStatistics = useCallback(() => (
        <div className="statistics">
            <h3>Component {i} Statistics</h3>
            <ul>
                <li>Total Items: {{statistics.totalItems}}</li>
                <li>Loading: {{statistics.loadingState ? 'Yes' : 'No'}}</li>
                <li>Errors: {{statistics.errorCount}}</li>
                <li>Cache Size: {{statistics.cacheSize}}</li>
                <li>Click Counter: {{state.counter}}</li>
            </ul>
        </div>
    ), [statistics, state.counter]);

    if (state.loading) {{
        return <div className="loading">Loading component {i}...</div>;
    }}

    if (state.error) {{
        return (
            <div className="error">
                <h3>Error in Component {i}</h3>
                <p>{{state.error}}</p>
                <button onClick={{handleDataRefresh}}>Retry</button>
            </div>
        );
    }}

    return (
        <div className="generated-component-{i}">
            <header>
                <h2>Generated Component {i}</h2>
                <div className="actions">
                    <button onClick={{handleDataRefresh}} disabled={{state.loading}}>
                        Refresh Data
                    </button>
                    <button onClick={{handleClearCache}}>
                        Clear Cache
                    </button>
                </div>
            </header>

            {{renderStatistics()}}

            <main className="content">
                <div className="processed-data">
                    <h3>Processed Data ({{processedData.length}} items)</h3>
                    <div className="items-grid">
                        {{processedData.map(renderItem)}}
                    </div>
                </div>

                <div className="state-items">
                    <h3>State Items ({{state.items.length}} items)</h3>
                    <div className="items-grid">
                        {{state.items.map(renderItem)}}
                    </div>
                </div>
            </main>
        </div>
    );
}};

// Default props
GeneratedComponent{i}.defaultProps = {{
    data: [],
    config: {{
        autoRefresh: false,
        refreshInterval: 5000
    }}
}};

export default GeneratedComponent{i};
"""
            (js_root / f"GeneratedComponent{i}.js").write_text(js_content)

    @pytest.mark.asyncio
    async def test_large_scale_file_analysis_performance(self, large_scale_project):
        """大規模ファイル分析のパフォーマンステスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        profiler.start_profiling()

        # 1. 全ファイル一覧取得（180ファイル）
        list_tool = ListFilesTool(large_scale_project)
        file_list_result = await list_tool.execute(
            {
                "roots": [large_scale_project],
                "extensions": ["java", "py", "js"],
                "limit": 200,
            }
        )

        assert file_list_result["success"]
        assert file_list_result["count"] == 180  # 100 Java + 50 Python + 30 JS

        # 2. 複数ファイルの並行分析
        scale_tool = AnalyzeScaleTool(large_scale_project)
        analysis_tasks = []

        # 各言語から5ファイルずつ選択
        test_files = [
            "src/main/java/com/enterprise/package0/GeneratedClass0.java",
            "src/main/java/com/enterprise/package1/GeneratedClass10.java",
            "src/main/java/com/enterprise/package2/GeneratedClass20.java",
            "python/modules/module_0.py",
            "python/modules/module_10.py",
            "python/modules/module_20.py",
            "frontend/src/components/GeneratedComponent0.js",
            "frontend/src/components/GeneratedComponent10.js",
            "frontend/src/components/GeneratedComponent20.js",
        ]

        for file_path in test_files:
            full_path = Path(large_scale_project) / file_path
            if full_path.exists():
                task = scale_tool.execute(
                    {"file_path": str(full_path), "include_complexity": True}
                )
                analysis_tasks.append(task)

        # 並行実行
        results = await asyncio.gather(*analysis_tasks)

        metrics = profiler.end_profiling()

        # パフォーマンス要件検証
        assert metrics["execution_time"] < 15.0, (
            f"実行時間が15秒を超過: {metrics['execution_time']:.2f}秒"
        )
        assert metrics["memory_mb"] < 200, (
            f"メモリ使用量が200MBを超過: {metrics['memory_mb']:.2f}MB"
        )

        # 結果検証
        successful_analyses = [r for r in results if r["success"]]
        assert len(successful_analyses) >= len(test_files) * 0.8, (
            "80%以上の分析が成功する必要があります"
        )

        print(f"大規模分析完了: {len(successful_analyses)}/{len(test_files)} 成功")
        print(
            f"実行時間: {metrics['execution_time']:.2f}秒, メモリ: {metrics['memory_mb']:.2f}MB"
        )

    @pytest.mark.asyncio
    async def test_concurrent_search_performance(self, large_scale_project):
        """同時検索のパフォーマンステスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        profiler.start_profiling()

        # 複数の検索クエリを並行実行
        search_tool = SearchContentTool(large_scale_project)
        search_queries = [
            ("class", ["*.java", "*.py", "*.js"]),
            ("function", ["*.py", "*.js"]),
            ("import", ["*.java", "*.py", "*.js"]),
            ("public", ["*.java"]),
            ("def ", ["*.py"]),
            ("const", ["*.js"]),
            ("useState", ["*.js"]),
            ("@dataclass", ["*.py"]),
            ("private", ["*.java"]),
            ("export", ["*.js"]),
        ]

        search_tasks = []
        for query, globs in search_queries:
            task = search_tool.execute(
                {
                    "roots": [large_scale_project],
                    "query": query,
                    "include_globs": globs,
                    "max_count": 50,
                }
            )
            search_tasks.append(task)

        # 並行実行
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        metrics = profiler.end_profiling()

        # パフォーマンス要件検証
        assert metrics["execution_time"] < 30.0, (
            f"検索実行時間が30秒を超過: {metrics['execution_time']:.2f}秒"
        )
        assert metrics["memory_mb"] < 150, (
            f"メモリ使用量が150MBを超過: {metrics['memory_mb']:.2f}MB"
        )

        # 結果検証
        successful_searches = [
            r for r in results if isinstance(r, dict) and r.get("success")
        ]
        assert len(successful_searches) >= len(search_queries) * 0.8, (
            "80%以上の検索が成功する必要があります"
        )

        total_matches = sum(r.get("count", 0) for r in successful_searches)
        assert total_matches > 0, "検索結果が見つからない"

        print(f"同時検索完了: {len(successful_searches)}/{len(search_queries)} 成功")
        print(
            f"総マッチ数: {total_matches}, 実行時間: {metrics['execution_time']:.2f}秒"
        )

    @pytest.mark.asyncio
    async def test_memory_efficiency_under_load(self, large_scale_project):
        """負荷下でのメモリ効率性テスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        # 初期メモリ使用量
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

        # 大量のファイル処理
        table_tool = TableFormatTool(large_scale_project)
        memory_measurements = []

        # 20個のファイルを順次処理
        java_files = list(Path(large_scale_project).glob("src/main/java/**/*.java"))[
            :20
        ]

        for i, java_file in enumerate(java_files):
            profiler.start_profiling()

            result = await table_tool.execute(
                {
                    "file_path": str(java_file),
                    "format_type": "full",
                    "suppress_output": True,  # メモリ最適化
                    "output_file": f"temp_output_{i}",
                }
            )

            metrics = profiler.end_profiling()
            current_memory = psutil.Process().memory_info().rss / 1024 / 1024

            memory_measurements.append(
                {
                    "file_index": i,
                    "memory_used": metrics["memory_mb"],
                    "total_memory": current_memory,
                    "execution_time": metrics["execution_time"],
                }
            )

            assert result["success"], f"ファイル {i} の処理に失敗"

            # ガベージコレクション
            if i % 5 == 0:
                gc.collect()

        # メモリ効率性検証
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory

        # メモリ増加が合理的な範囲内であることを確認
        assert memory_growth < 300, f"メモリ増加が300MBを超過: {memory_growth:.2f}MB"

        # 平均実行時間が合理的であることを確認
        avg_execution_time = sum(
            m["execution_time"] for m in memory_measurements
        ) / len(memory_measurements)
        assert avg_execution_time < 2.0, (
            f"平均実行時間が2秒を超過: {avg_execution_time:.2f}秒"
        )

        print("メモリ効率性テスト完了:")
        print(f"初期メモリ: {initial_memory:.2f}MB")
        print(f"最終メモリ: {final_memory:.2f}MB")
        print(f"メモリ増加: {memory_growth:.2f}MB")
        print(f"平均実行時間: {avg_execution_time:.2f}秒")

    @pytest.mark.asyncio
    async def test_scalability_limits(self, large_scale_project):
        """スケーラビリティ限界テスト"""
        profiler = PerformanceProfiler()
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        # 段階的に負荷を増加
        load_levels = [5, 10, 20, 30]
        scalability_results = []

        for load_level in load_levels:
            profiler.start_profiling()

            # 指定された数のタスクを並行実行
            tasks = []
            tools = [
                AnalyzeScaleTool(large_scale_project),
                TableFormatTool(large_scale_project),
                SearchContentTool(large_scale_project),
            ]

            for i in range(load_level):
                tool = tools[i % len(tools)]

                if isinstance(tool, AnalyzeScaleTool):
                    # 異なるファイルを分析
                    java_files = list(
                        Path(large_scale_project).glob("src/main/java/**/*.java")
                    )
                    if java_files:
                        file_path = java_files[i % len(java_files)]
                        task = tool.execute({"file_path": str(file_path)})
                        tasks.append(task)

                elif isinstance(tool, TableFormatTool):
                    # 異なるファイルの構造分析
                    python_files = list(
                        Path(large_scale_project).glob("python/**/*.py")
                    )
                    if python_files:
                        file_path = python_files[i % len(python_files)]
                        task = tool.execute(
                            {"file_path": str(file_path), "format_type": "compact"}
                        )
                        tasks.append(task)

                elif isinstance(tool, SearchContentTool):
                    # 異なる検索クエリ
                    queries = ["class", "function", "import", "def", "const"]
                    query = queries[i % len(queries)]
                    task = tool.execute(
                        {
                            "roots": [large_scale_project],
                            "query": query,
                            "max_count": 10,
                        }
                    )
                    tasks.append(task)

            # 並行実行
            results = await asyncio.gather(*tasks, return_exceptions=True)
            metrics = profiler.end_profiling()

            # 結果分析
            successful_tasks = [
                r for r in results if isinstance(r, dict) and r.get("success")
            ]
            error_tasks = [r for r in results if isinstance(r, Exception)]

            success_rate = len(successful_tasks) / len(results) if results else 0

            scalability_results.append(
                {
                    "load_level": load_level,
                    "execution_time": metrics["execution_time"],
                    "memory_mb": metrics["memory_mb"],
                    "success_rate": success_rate,
                    "successful_tasks": len(successful_tasks),
                    "error_tasks": len(error_tasks),
                }
            )

            print(
                f"負荷レベル {load_level}: {metrics['execution_time']:.2f}秒, "
                f"成功率: {success_rate:.2%}, メモリ: {metrics['memory_mb']:.2f}MB"
            )

            # 基本的な要件確認
            assert success_rate >= 0.7, (
                f"負荷レベル {load_level} で成功率が70%を下回りました: {success_rate:.2%}"
            )

            # 短い休憩でシステム回復
            await asyncio.sleep(1)

        # スケーラビリティ分析
        max_load_result = scalability_results[-1]
        assert max_load_result["execution_time"] < 60.0, (
            "最大負荷での実行時間が60秒を超過"
        )
        assert max_load_result["memory_mb"] < 500, (
            "最大負荷でのメモリ使用量が500MBを超過"
        )

        print("スケーラビリティテスト完了:")
        for result in scalability_results:
            print(
                f"  負荷 {result['load_level']}: {result['execution_time']:.2f}秒, "
                f"成功率 {result['success_rate']:.2%}, メモリ {result['memory_mb']:.2f}MB"
            )

    @pytest.mark.asyncio
    async def test_sustained_load_performance(self, large_scale_project):
        """持続負荷パフォーマンステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        # 5分間の持続負荷テスト
        test_duration = 60  # 実際のテストでは300秒（5分）
        start_time = time.time()

        performance_samples = []
        iteration = 0

        while time.time() - start_time < test_duration:
            iteration += 1
            profiler = PerformanceProfiler()
            profiler.start_profiling()

            # 軽量なタスクを実行
            search_tool = SearchContentTool(large_scale_project)
            result = await search_tool.execute(
                {
                    "roots": [large_scale_project],
                    "query": f"class{iteration % 10}",
                    "max_count": 5,
                    "total_only": True,  # 軽量化
                }
            )

            metrics = profiler.end_profiling()

            performance_samples.append(
                {
                    "iteration": iteration,
                    "execution_time": metrics["execution_time"],
                    "memory_mb": metrics["memory_mb"],
                    "success": isinstance(result, dict)
                    and result.get("success", False)
                    or isinstance(result, int),
                }
            )

            # 短い間隔
            await asyncio.sleep(0.5)

        # 持続負荷分析
        successful_iterations = [s for s in performance_samples if s["success"]]
        total_iterations = len(performance_samples)
        success_rate = (
            len(successful_iterations) / total_iterations if total_iterations > 0 else 0
        )

        avg_execution_time = (
            sum(s["execution_time"] for s in successful_iterations)
            / len(successful_iterations)
            if successful_iterations
            else 0
        )
        avg_memory = (
            sum(s["memory_mb"] for s in successful_iterations)
            / len(successful_iterations)
            if successful_iterations
            else 0
        )

        # 持続負荷要件検証
        assert success_rate >= 0.95, (
            f"持続負荷での成功率が95%を下回りました: {success_rate:.2%}"
        )
        assert avg_execution_time < 3.0, (
            f"平均実行時間が3秒を超過: {avg_execution_time:.2f}秒"
        )
        assert avg_memory < 100, f"平均メモリ使用量が100MBを超過: {avg_memory:.2f}MB"

        print("持続負荷テスト完了:")
        print(f"総反復回数: {total_iterations}")
        print(f"成功率: {success_rate:.2%}")
        print(f"平均実行時間: {avg_execution_time:.2f}秒")
        print(f"平均メモリ使用量: {avg_memory:.2f}MB")

    @pytest.mark.asyncio
    async def test_resource_cleanup_efficiency(self, large_scale_project):
        """リソースクリーンアップ効率性テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

        # 大量のタスクを実行してリソースを消費
        for cycle in range(5):
            print(f"リソース消費サイクル {cycle + 1}/5")

            # 複数のツールを使用
            tools_and_params = [
                (
                    AnalyzeScaleTool(large_scale_project),
                    {
                        "file_path": str(
                            list(Path(large_scale_project).glob("**/*.java"))[0]
                        ),
                        "include_complexity": True,
                    },
                ),
                (
                    TableFormatTool(large_scale_project),
                    {
                        "file_path": str(
                            list(Path(large_scale_project).glob("**/*.py"))[0]
                        ),
                        "format_type": "full",
                    },
                ),
                (
                    SearchContentTool(large_scale_project),
                    {
                        "roots": [large_scale_project],
                        "query": "class",
                        "max_count": 100,
                    },
                ),
            ]

            # 各ツールを実行
            for tool, params in tools_and_params:
                result = await tool.execute(params)
                assert result["success"], f"サイクル {cycle} でツール実行に失敗"

            # 明示的なガベージコレクション
            gc.collect()

            current_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_growth = current_memory - initial_memory

            print(f"  サイクル {cycle + 1} 後のメモリ増加: {memory_growth:.2f}MB")

            # メモリ増加が制御されていることを確認
            assert memory_growth < 200, (
                f"サイクル {cycle} でメモリ増加が200MBを超過: {memory_growth:.2f}MB"
            )

        # 最終クリーンアップ
        gc.collect()
        await asyncio.sleep(1)  # システムがクリーンアップする時間を与える

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        total_growth = final_memory - initial_memory

        print("リソースクリーンアップテスト完了:")
        print(f"初期メモリ: {initial_memory:.2f}MB")
        print(f"最終メモリ: {final_memory:.2f}MB")
        print(f"総メモリ増加: {total_growth:.2f}MB")

        # 最終的なメモリ増加が合理的であることを確認
        assert total_growth < 150, f"総メモリ増加が150MBを超過: {total_growth:.2f}MB"

    @pytest.mark.asyncio
    async def test_error_recovery_performance(self, large_scale_project):
        """エラー回復パフォーマンステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(large_scale_project)

        profiler = PerformanceProfiler()
        profiler.start_profiling()

        # 意図的にエラーを発生させるタスクと正常なタスクを混在
        tasks = []

        # 正常なタスク
        valid_java_file = str(list(Path(large_scale_project).glob("**/*.java"))[0])
        scale_tool = AnalyzeScaleTool(large_scale_project)

        for _i in range(5):
            task = scale_tool.execute(
                {"file_path": valid_java_file, "include_complexity": True}
            )
            tasks.append(("valid", task))

        # エラーを発生させるタスク
        for _i in range(3):
            task = scale_tool.execute(
                {
                    "file_path": "/nonexistent/file.java",  # 存在しないファイル
                    "include_complexity": True,
                }
            )
            tasks.append(("error", task))

        # 並行実行
        task_results = await asyncio.gather(
            *[task for _, task in tasks], return_exceptions=True
        )

        metrics = profiler.end_profiling()

        # 結果分析
        valid_results = []
        error_results = []

        for _i, (task_type, result) in enumerate(
            zip([t[0] for t in tasks], task_results, strict=False)
        ):
            if task_type == "valid":
                valid_results.append(result)
            else:
                error_results.append(result)

        # 正常なタスクが影響を受けていないことを確認
        successful_valid = [
            r for r in valid_results if isinstance(r, dict) and r.get("success")
        ]
        assert len(successful_valid) == 5, "エラーが正常なタスクに影響を与えました"

        # エラー処理が適切に行われていることを確認（例外またはエラー辞書）
        handled_errors = []
        for r in error_results:
            if isinstance(r, Exception):
                handled_errors.append(r)  # 例外として処理された
            elif isinstance(r, dict) and not r.get("success", True):
                handled_errors.append(r)  # エラー辞書として処理された

        assert len(handled_errors) >= 2, (
            f"エラーが適切に処理されていません: {len(handled_errors)}/3"
        )

        # パフォーマンスが大幅に劣化していないことを確認
        assert metrics["execution_time"] < 10.0, (
            f"エラー混在時の実行時間が10秒を超過: {metrics['execution_time']:.2f}秒"
        )

        print("エラー回復パフォーマンステスト完了:")
        print(f"正常タスク成功: {len(successful_valid)}/5")
        print(f"エラー処理: {len(handled_errors)}/3")
        print(f"実行時間: {metrics['execution_time']:.2f}秒")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
