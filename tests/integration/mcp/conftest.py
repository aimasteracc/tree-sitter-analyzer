#!/usr/bin/env python3
"""
Shared fixtures for User Story 3 MCP integration tests.

Consolidates the duplicated temp_project fixture from:
  - test_user_story_3_extract_integration.py
  - test_user_story_3_query_integration.py

Union of both originals:
  - Path.resolve() on temp_dir (macOS symlink workaround from extract side)
  - docs/ directory with API_Reference.md (from query side)
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project():
    """Shared test project structure for User Story 3 tests.

    Creates a temporary directory with:
      src/ComplexService.java  (~157 lines)
      src/DataManager.ts       (~127 lines)
      src/analytics_engine.py  (~156 lines)
      docs/API_Reference.md    (Markdown, used by query tests)

    The root is resolved so that Path.relative_to() works correctly
    on macOS where /tmp is a symlink into /private/var/folders.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # macOS tmp paths live under /var/folders -> /private/var/folders;
        # the MCP layer resolves symlinks when constructing output paths,
        # so callers' .relative_to(temp_project) fails unless we resolve
        # the fixture root too. CLAUDE.md §2 documents the wider issue;
        # this is the test-side workaround.
        project_root = Path(temp_dir).resolve()

        (project_root / "src").mkdir()
        (project_root / "docs").mkdir()

        # 複雑なJavaファイル
        (project_root / "src" / "ComplexService.java").write_text(
            """package com.example.service;

import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

/**
 * Complex service class demonstrating various Java features
 */
public class ComplexService implements ServiceInterface {
    private static final String DEFAULT_CONFIG = "default.properties";
    private final Map<String, Object> cache = new ConcurrentHashMap<>();
    private volatile boolean initialized = false;

    public ComplexService() {
        this.initialized = false;
    }

    public ComplexService(String configPath) {
        loadConfiguration(configPath);
        this.initialized = true;
    }

    @Override
    public void initialize() throws ServiceException {
        if (initialized) {
            throw new ServiceException("Service already initialized");
        }

        try {
            loadDefaultConfiguration();
            setupCache();
            this.initialized = true;
        } catch (Exception e) {
            throw new ServiceException("Failed to initialize service", e);
        }
    }

    public <T> CompletableFuture<T> processAsync(String key, Callable<T> processor) {
        validateInitialized();

        return CompletableFuture.supplyAsync(() -> {
            try {
                T result = processor.call();
                cache.put(key, result);
                return result;
            } catch (Exception e) {
                throw new RuntimeException("Processing failed", e);
            }
        });
    }

    public List<String> getProcessedKeys() {
        return cache.keySet().stream()
                .filter(key -> key.startsWith("processed_"))
                .sorted()
                .collect(Collectors.toList());
    }

    private void loadConfiguration(String configPath) {
        // Configuration loading logic
        System.out.println("Loading config from: " + configPath);
    }

    private void loadDefaultConfiguration() {
        loadConfiguration(DEFAULT_CONFIG);
    }

    private void setupCache() {
        cache.clear();
        cache.put("initialized", true);
    }

    private void validateInitialized() {
        if (!initialized) {
            throw new IllegalStateException("Service not initialized");
        }
    }

    public static class Builder {
        private String configPath;
        private boolean autoInitialize = true;

        public Builder withConfig(String configPath) {
            this.configPath = configPath;
            return this;
        }

        public Builder autoInitialize(boolean autoInitialize) {
            this.autoInitialize = autoInitialize;
            return this;
        }

        public ComplexService build() throws ServiceException {
            ComplexService service = new ComplexService(configPath);
            if (autoInitialize) {
                service.initialize();
            }
            return service;
        }
    }
}

interface ServiceInterface {
    void initialize() throws ServiceException;
}

class ServiceException extends Exception {
    public ServiceException(String message) {
        super(message);
    }

    public ServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}
"""
        )

        # 複雑なTypeScriptファイル
        (project_root / "src" / "DataManager.ts").write_text(
            """import { EventEmitter } from 'events';

interface DataItem {
    id: string;
    name: string;
    value: number;
    metadata?: Record<string, any>;
}

interface DataManagerConfig {
    cacheSize: number;
    autoSave: boolean;
    debounceMs: number;
}

type DataChangeEvent = {
    type: 'add' | 'update' | 'delete';
    item: DataItem;
    timestamp: number;
};

class DataManager extends EventEmitter {
    private readonly config: DataManagerConfig;
    private readonly cache = new Map<string, DataItem>();

    constructor(config: Partial<DataManagerConfig> = {}) {
        super();
        this.config = {
            cacheSize: 1000,
            autoSave: true,
            debounceMs: 300,
            ...config
        };
    }

    public async addItem(item: DataItem): Promise<void> {
        this.validateItem(item);

        if (this.cache.size >= this.config.cacheSize) {
            await this.evictOldestItem();
        }

        this.cache.set(item.id, { ...item });
        this.emitChange('add', item);

        if (this.config.autoSave) {
            await this.saveToStorage(item);
        }
    }

    public async updateItem(id: string, updates: Partial<DataItem>): Promise<DataItem | null> {
        const existing = this.cache.get(id);
        if (!existing) {
            return null;
        }

        const updated = { ...existing, ...updates, id };
        this.validateItem(updated);

        this.cache.set(id, updated);
        this.emitChange('update', updated);

        if (this.config.autoSave) {
            await this.saveToStorage(updated);
        }

        return updated;
    }

    public deleteItem(id: string): boolean {
        const item = this.cache.get(id);
        if (!item) {
            return false;
        }

        this.cache.delete(id);
        this.emitChange('delete', item);
        return true;
    }

    public getItem(id: string): DataItem | undefined {
        return this.cache.get(id);
    }

    public getAllItems(): DataItem[] {
        return Array.from(this.cache.values());
    }

    private validateItem(item: DataItem): void {
        if (!item.id || !item.name) {
            throw new Error('Item must have id and name');
        }

        if (typeof item.value !== 'number') {
            throw new Error('Item value must be a number');
        }
    }

    private async evictOldestItem(): Promise<void> {
        const firstKey = this.cache.keys().next().value;
        if (firstKey) {
            this.cache.delete(firstKey);
        }
    }

    private async saveToStorage(item: DataItem): Promise<void> {
        // Simulate async storage operation
        await new Promise(resolve => setTimeout(resolve, 10));
        console.log(`Saved item ${item.id} to storage`);
    }

    private emitChange(type: DataChangeEvent['type'], item: DataItem): void {
        const event: DataChangeEvent = {
            type,
            item: { ...item },
            timestamp: Date.now()
        };
    }
}

export { DataManager, DataItem, DataManagerConfig, DataChangeEvent };
"""
        )

        # 複雑なPythonファイル
        (project_root / "src" / "analytics_engine.py").write_text(
            """#!/usr/bin/env python3
\"\"\"
Advanced Analytics Engine

Provides comprehensive data analysis capabilities with multiple algorithms
and real-time processing features.
\"\"\"

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Callable, Any, TypeVar, Generic
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

T = TypeVar('T')
R = TypeVar('R')

logger = logging.getLogger(__name__)


@dataclass
class AnalysisConfig:
    \"\"\"Configuration for analysis operations\"\"\"
    algorithm: str = "default"
    parallel_workers: int = 4
    cache_results: bool = True
    timeout_seconds: int = 300
    precision: float = 0.001
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult(Generic[T]):
    \"\"\"Result container for analysis operations\"\"\"
    data: T
    confidence: float
    execution_time: float
    algorithm_used: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AnalysisAlgorithm(ABC, Generic[T, R]):
    \"\"\"Abstract base class for analysis algorithms\"\"\"

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.name = self.__class__.__name__

    @abstractmethod
    async def analyze(self, data: T) -> R:
        \"\"\"Perform analysis on input data\"\"\"
        pass

    @abstractmethod
    def validate_input(self, data: T) -> bool:
        \"\"\"Validate input data format\"\"\"
        pass


class StatisticalAnalyzer(AnalysisAlgorithm):
    \"\"\"Statistical analysis algorithm\"\"\"

    async def analyze(self, data):
        \"\"\"Perform statistical analysis\"\"\"
        if not self.validate_input(data):
            raise ValueError("Invalid input data for statistical analysis")

        # Simulate async computation
        await asyncio.sleep(0.1)

        return {"mean": 1.0, "std": 0.5}

    def validate_input(self, data) -> bool:
        \"\"\"Validate DataFrame input\"\"\"
        return data is not None


class AnalyticsEngine:
    \"\"\"Main analytics engine coordinating multiple algorithms\"\"\"

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.algorithms: Dict[str, AnalysisAlgorithm] = {}
        self.cache: Dict[str, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=config.parallel_workers)
        self._setup_algorithms()

    def _setup_algorithms(self):
        \"\"\"Initialize available algorithms\"\"\"
        self.algorithms["statistical"] = StatisticalAnalyzer(self.config)

    async def analyze_dataset(self, data, algorithm: Optional[str] = None):
        \"\"\"Analyze dataset using specified or auto-detected algorithm\"\"\"
        start_time = asyncio.get_event_loop().time()

        # Auto-detect algorithm if not specified
        if algorithm is None:
            algorithm = self._detect_algorithm(data)

        if algorithm not in self.algorithms:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        # Perform analysis
        analyzer = self.algorithms[algorithm]

        try:
            result_data = await asyncio.wait_for(
                analyzer.analyze(data),
                timeout=self.config.timeout_seconds
            )

            execution_time = asyncio.get_event_loop().time() - start_time

            return AnalysisResult(
                data=result_data,
                confidence=0.8,
                execution_time=execution_time,
                algorithm_used=algorithm,
                metadata={"config": self.config.metadata}
            )

        except asyncio.TimeoutError:
            raise TimeoutError(f"Analysis timed out after {self.config.timeout_seconds} seconds")

    def _detect_algorithm(self, data: Any) -> str:
        \"\"\"Auto-detect appropriate algorithm for data\"\"\"
        return "statistical"

    def clear_cache(self):
        \"\"\"Clear analysis cache\"\"\"
        self.cache.clear()
        logger.info("Analysis cache cleared")


def create_default_engine() -> AnalyticsEngine:
    \"\"\"Create analytics engine with default configuration\"\"\"
    config = AnalysisConfig()
    return AnalyticsEngine(config)


def create_high_performance_engine() -> AnalyticsEngine:
    \"\"\"Create analytics engine optimized for performance\"\"\"
    config = AnalysisConfig(
        parallel_workers=8,
        cache_results=True,
        timeout_seconds=600
    )
    return AnalyticsEngine(config)


async def quick_analyze(data) -> AnalysisResult:
    \"\"\"Quick analysis function for simple use cases\"\"\"
    engine = create_default_engine()
    return await engine.analyze_dataset(data)
"""
        )

        # Markdownファイル (used by query tests)
        (project_root / "docs" / "API_Reference.md").write_text(
            """# API Reference

## Overview

This document provides comprehensive API reference for the analytics engine.

## Core Classes

### AnalyticsEngine

Main engine class for performing data analysis.

#### Constructor

```python
AnalyticsEngine(config: AnalysisConfig)
```

#### Methods

##### analyze_dataset

```python
async def analyze_dataset(
    data: Union[pd.DataFrame, List[float]],
    algorithm: Optional[str] = None
) -> AnalysisResult
```

Analyzes a dataset using the specified algorithm.

**Parameters:**
- `data`: Input data (DataFrame or list of floats)
- `algorithm`: Algorithm name (optional, auto-detected if not provided)

**Returns:**
- `AnalysisResult`: Analysis results with metadata

### AnalysisConfig

Configuration class for analysis operations.

#### Fields

- `algorithm: str` - Default algorithm name
- `parallel_workers: int` - Number of parallel workers
- `cache_results: bool` - Enable result caching
- `timeout_seconds: int` - Analysis timeout
- `precision: float` - Numerical precision
- `metadata: Dict[str, Any]` - Additional metadata

## Usage Examples

### Basic Usage

```python
import asyncio
from analytics_engine import create_default_engine

async def main():
    engine = create_default_engine()

    # Analyze time series data
    data = [1.0, 2.1, 1.8, 2.5, 3.2]
    result = await engine.analyze_dataset(data)
    print(result.data)

asyncio.run(main())
```

## Links

- [GitHub Repository](https://github.com/example/analytics-engine)
- [Documentation](https://docs.example.com/analytics-engine)
- [Examples](https://github.com/example/analytics-engine/tree/main/examples)
"""
        )

        yield project_root
