#!/usr/bin/env python3
"""Helpers for Phase 7 performance integration tests."""

import gc
import os
import time
from pathlib import Path
from typing import Any

import psutil

DEFAULT_MEMORY_EFFICIENCY_FILES = 8
DEFAULT_RESOURCE_CLEANUP_SETTLE_SECONDS = 0.05
DEFAULT_SCALABILITY_RECOVERY_SECONDS = 0.05
DEFAULT_SUSTAINED_LOAD_INTERVAL_SECONDS = 0.05
DEFAULT_SUSTAINED_LOAD_ITERATIONS = 12


def positive_int_from_env(name: str, default: int) -> int:
    """Read a positive integer env override without making test collection brittle."""
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def nonnegative_float_from_env(name: str, default: float) -> float:
    """Read a non-negative float env override without making test collection brittle."""
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(0.0, value)


class PerformanceProfiler:
    """Performance measurement utility for integration tests."""

    def __init__(self) -> None:
        self.process = psutil.Process()
        self.start_time: float | None = None
        self.start_memory: int | None = None
        self.start_cpu: float | None = None

    def start_profiling(self) -> None:
        """Start profiling after forcing collection."""
        gc.collect()
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss
        self.start_cpu = self.process.cpu_percent()

    def end_profiling(self) -> dict[str, Any]:
        """Stop profiling and return elapsed resource metrics."""
        end_time = time.time()
        end_memory = self.process.memory_info().rss
        end_cpu = self.process.cpu_percent()
        start_time = self.start_time or end_time
        start_memory = self.start_memory or end_memory

        return {
            "execution_time": end_time - start_time,
            "memory_used": end_memory - start_memory,
            "peak_memory": self.process.memory_info().rss,
            "cpu_usage": end_cpu,
            "memory_mb": (end_memory - start_memory) / 1024 / 1024,
        }


def create_large_scale_structure(project_root: Path) -> None:
    """Create a mixed-language project fixture for performance tests."""
    _create_java_classes(project_root)
    _create_python_modules(project_root)
    _create_javascript_components(project_root)


def _create_java_classes(project_root: Path) -> None:
    java_root = project_root / "src" / "main" / "java" / "com" / "enterprise"
    java_root.mkdir(parents=True)

    for index in range(100):
        package_dir = java_root / f"package{index // 10}"
        package_dir.mkdir(exist_ok=True)
        (package_dir / f"GeneratedClass{index}.java").write_text(
            _java_class_content(index)
        )


def _java_class_content(index: int) -> str:
    package_index = index // 10
    return f"""
package com.enterprise.package{package_index};

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

/**
 * Generated class {index} for performance testing
 */
public class GeneratedClass{index} {{
    private String name;
    private List<String> items;
    private Map<String, Object> properties;

    public GeneratedClass{index}(String name) {{
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


def _create_python_modules(project_root: Path) -> None:
    python_root = project_root / "python" / "modules"
    python_root.mkdir(parents=True)

    for index in range(50):
        (python_root / f"module_{index}.py").write_text(_python_module_content(index))


def _python_module_content(index: int) -> str:
    return f'''#!/usr/bin/env python3
"""
Generated module {index} for performance testing
"""

from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class DataModel{index}:
    """Generated data model {index}"""
    id: int = {index}
    name: str = "model_{index}"
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


class ProcessorService{index}:
    """Generated processor service {index}"""

    def __init__(self):
        self.models: List[DataModel{index}] = []
        self.cache: Dict[int, Any] = {{}}

    def add_model(self, model: DataModel{index}) -> None:
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


def create_sample_data_{index}() -> List[DataModel{index}]:
    """Create sample data for testing"""
    models = []
    for j in range(5):
        model = DataModel{index}(
            id=j,
            name=f"sample_model_{{j}}"
        )
        model.process_data()
        models.append(model)
    return models


def main():
    """Main function for module {index}"""
    processor = ProcessorService{index}()
    sample_data = create_sample_data_{index}()

    for model in sample_data:
        processor.add_model(model)

    results = processor.process_all()
    stats = processor.get_statistics()

    print(f"Module {index} processed {{len(results)}} models")
    print(f"Statistics: {{stats}}")

    processor.cleanup()


if __name__ == "__main__":
    main()
'''


def _create_javascript_components(project_root: Path) -> None:
    js_root = project_root / "frontend" / "src" / "components"
    js_root.mkdir(parents=True)

    for index in range(30):
        (js_root / f"GeneratedComponent{index}.js").write_text(
            _javascript_component_content(index)
        )


def _javascript_component_content(index: int) -> str:
    return f"""/**
 * Generated React component {index} for performance testing
 */

import React, {{ useState, useEffect, useCallback, useMemo }} from 'react';

const GeneratedComponent{index} = ({{ data, onUpdate, config }}) => {{
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

        return data.map((item, itemIndex) => ({{
            ...item,
            id: `item_${{itemIndex}}`,
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

            const newItems = Array.from({{ length: 10 }}, (_, itemIndex) => ({{
                id: `generated_${{itemIndex}}`,
                name: `Item ${{itemIndex}}`,
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
            <h3>Component {index} Statistics</h3>
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
        return <div className="loading">Loading component {index}...</div>;
    }}

    if (state.error) {{
        return (
            <div className="error">
                <h3>Error in Component {index}</h3>
                <p>{{state.error}}</p>
                <button onClick={{handleDataRefresh}}>Retry</button>
            </div>
        );
    }}

    return (
        <div className="generated-component-{index}">
            <header>
                <h2>Generated Component {index}</h2>
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
GeneratedComponent{index}.defaultProps = {{
    data: [],
    config: {{
        autoRefresh: false,
        refreshInterval: 5000
    }}
}};

export default GeneratedComponent{index};
"""
