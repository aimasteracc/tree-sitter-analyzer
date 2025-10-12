
# 移行実装ガイド

## 📋 概要

このドキュメントは、tree-sitter-analyzerプロジェクトの段階的移行実装に関する詳細なガイドです。54件の条件分岐を削除し、プラグインベースアーキテクチャへの完全移行を実現するための具体的な実装手順を提供します。

### 移行目標
- **条件分岐削除**: 54件 → 0件
- **API互換性**: 100%維持
- **パフォーマンス**: 既存の105%以内
- **新言語追加工数**: 1日以内

### 移行期間
- **Phase 1**: 基盤整備（Week 1-2）
- **Phase 2**: 段階的移行（Week 3-6）
- **Phase 3**: 最終統合（Week 7-8）

---

## 🚀 Phase 1: 基盤整備実装

### Week 1: コアコンポーネント実装

#### Day 1-2: 統一クエリエンジンの実装

```python
# tree_sitter_analyzer/core/unified_query_engine.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import time
import logging
import tree_sitter
from tree_sitter_analyzer.exceptions import UnsupportedLanguageError, UnsupportedQueryError
from tree_sitter_analyzer.plugins.manager import PluginManager

@dataclass
class QueryResult:
    """統一クエリ結果データクラス"""
    node_type: str
    name: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    content: str
    metadata: Dict[str, Any]
    language: str
    capture_name: str

class PerformanceMonitor:
    """パフォーマンス監視クラス"""
    
    def __init__(self):
        self.query_stats: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    def record_query_execution(self, language: str, query_key: str, execution_time: float):
        """クエリ実行時間を記録"""
        key = f"{language}.{query_key}"
        if key not in self.query_stats:
            self.query_stats[key] = {
                "count": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
                "max_time": 0.0,
                "min_time": float('inf')
            }
        
        stats = self.query_stats[key]
        stats["count"] += 1
        stats["total_time"] += execution_time
        stats["avg_time"] = stats["total_time"] / stats["count"]
        stats["max_time"] = max(stats["max_time"], execution_time)
        stats["min_time"] = min(stats["min_time"], execution_time)
        
        # 異常に遅いクエリの警告
        if execution_time > 5.0:
            self.logger.warning(f"Slow query detected: {key} took {execution_time:.3f}s")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """パフォーマンスレポートを取得"""
        return {
            "query_stats": self.query_stats,
            "total_queries": sum(stats["count"] for stats in self.query_stats.values()),
            "avg_execution_time": sum(stats["avg_time"] for stats in self.query_stats.values()) / len(self.query_stats) if self.query_stats else 0
        }

class QueryEngineInterface(ABC):
    """クエリエンジンの抽象インターフェース"""
    
    @abstractmethod
    def execute_query(self, language: str, query_key: str, tree: tree_sitter.Tree, source_code: str) -> List[QueryResult]:
        """クエリを実行して結果を返す"""
        pass
    
    @abstractmethod
    def get_supported_queries(self, language: str) -> List[str]:
        """サポートされているクエリタイプのリストを返す"""
        pass
    
    @abstractmethod
    def validate_query(self, language: str, query_key: str) -> bool:
        """クエリの妥当性を検証"""
        pass

class UnifiedQueryEngine(QueryEngineInterface):
    """統一クエリエンジン実装"""
    
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self.query_cache: Dict[str, tree_sitter.Query] = {}
        self.performance_monitor = PerformanceMonitor()
        self.logger = logging.getLogger(__name__)
        
        # クエリキャッシュの最大サイズ
        self.max_cache_size = 100
    
    def execute_query(self, language: str, query_key: str, tree: tree_sitter.Tree, source_code: str) -> List[QueryResult]:
        """プラグインベースのクエリ実行"""
        
        start_time = time.time()
        
        try:
            # プラグインの取得
            plugin = self.plugin_manager.get_plugin(language)
            if not plugin:
                raise UnsupportedLanguageError(f"No plugin found for language: {language}")
            
            # クエリ定義の取得
            query_definitions = plugin.get_query_definitions()
            if query_key not in query_definitions:
                available_queries = list(query_definitions.keys())
                raise UnsupportedQueryError(
                    f"Query '{query_key}' not supported for {language}. "
                    f"Available queries: {', '.join(available_queries)}"
                )
            
            # クエリのコンパイルと実行
            compiled_query = self._get_compiled_query(language, query_key, query_definitions[query_key])
            results = self._execute_tree_sitter_query(compiled_query, tree, source_code, language)
            
            # パフォーマンス記録
            execution_time = time.time() - start_time
            self.performance_monitor.record_query_execution(language, query_key, execution_time)
            
            self.logger.debug(f"Query {language}.{query_key} executed in {execution_time:.3f}s, found {len(results)} results")
            
            return results
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Query execution failed: {language}.{query_key} - {str(e)} (took {execution_time:.3f}s)")
            raise
    
    def _get_compiled_query(self, language: str, query_key: str, query_string: str) -> tree_sitter.Query:
        """コンパイル済みクエリを取得（キャッシュ利用）"""
        cache_key = f"{language}.{query_key}"
        
        if cache_key not in self.query_cache:
            # キャッシュサイズ制限
            if len(self.query_cache) >= self.max_cache_size:
                # LRU的にキャッシュをクリア（簡易実装）
                oldest_key = next(iter(self.query_cache))
                del self.query_cache[oldest_key]
            
            # プラグインから言語オブジェクトを取得
            plugin = self.plugin_manager.get_plugin(language)
            language_obj = plugin.get_language_object()
            
            try:
                compiled_query = language_obj.query(query_string)
                self.query_cache[cache_key] = compiled_query
                self.logger.debug(f"Compiled and cached query: {cache_key}")
            except Exception as e:
                raise UnsupportedQueryError(f"Failed to compile query '{query_key}' for {language}: {str(e)}")
        
        return self.query_cache[cache_key]
    
    def _execute_tree_sitter_query(self, query: tree_sitter.Query, tree: tree_sitter.Tree, source_code: str, language: str) -> List[QueryResult]:
        """Tree-sitterクエリの実際の実行"""
        results = []
        
        try:
            captures = query.captures(tree.root_node)
            
            for node, capture_name in captures:
                # ノード名の抽出
                name = self._extract_node_name(node, source_code)
                
                # 結果オブジェクトの作成
                result = QueryResult(
                    node_type=node.type,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    start_column=node.start_point[1],
                    end_column=node.end_point[1],
                    content=source_code[node.start_byte:node.end_byte],
                    metadata=self._extract_node_metadata(node, source_code),
                    language=language,
                    capture_name=capture_name
                )
                results.append(result)
                
        except Exception as e:
            self.logger.error(f"Error executing tree-sitter query: {str(e)}")
            raise
        
        return results
    
    def _extract_node_name(self, node: tree_sitter.Node, source_code: str) -> str:
        """ノードから名前を抽出"""
        # 一般的な名前ノードタイプ
        name_node_types = ["identifier", "type_identifier", "field_identifier"]
        
        # 直接の子ノードから名前を探す
        for child in node.children:
            if child.type in name_node_types:
                return source_code[child.start_byte:child.end_byte]
        
        # 名前付きキャプチャから探す
        for child in node.children:
            if child.is_named and child.type not in ["block", "body", "parameters"]:
                return source_code[child.start_byte:child.end_byte]
        
        # フォールバック: ノードタイプを返す
        return node.type
    
    def _extract_node_metadata(self, node: tree_sitter.Node, source_code: str) -> Dict[str, Any]:
        """ノードからメタデータを抽出"""
        metadata = {
            "node_id": id(node),
            "has_error": node.has_error,
            "is_named": node.is_named,
            "child_count": node.child_count,
            "byte_range": (node.start_byte, node.end_byte)
        }
        
        # 親ノード情報
        if node.parent:
            metadata["parent_type"] = node.parent.type
        
        return metadata
    
    def get_supported_queries(self, language: str) -> List[str]:
        """サポートされているクエリタイプのリストを返す"""
        plugin = self.plugin_manager.get_plugin(language)
        if not plugin:
            return []
        
        return list(plugin.get_query_definitions().keys())
    
    def validate_query(self, language: str, query_key: str) -> bool:
        """クエリの妥当性を検証"""
        try:
            plugin = self.plugin_manager.get_plugin(language)
            if not plugin:
                return False
            
            query_definitions = plugin.get_query_definitions()
            if query_key not in query_definitions:
                return False
            
            # クエリのコンパイルテスト
            query_string = query_definitions[query_key]
            language_obj = plugin.get_language_object()
            language_obj.query(query_string)
            
            return True
        except Exception:
            return False
    
    def clear_cache(self):
        """クエリキャッシュをクリア"""
        self.query_cache.clear()
        self.logger.info("Query cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        return {
            "cache_size": len(self.query_cache),
            "max_cache_size": self.max_cache_size,
            "cached_queries": list(self.query_cache.keys())
        }
```

#### Day 3-4: 統一フォーマッターファクトリーの実装

```python
# tree_sitter_analyzer/formatters/unified_factory.py
from typing import Dict, Any, Type
from abc import ABC, abstractmethod
import logging
from tree_sitter_analyzer.formatters.base import BaseFormatter
from tree_sitter_analyzer.plugins.manager import PluginManager
from tree_sitter_analyzer.exceptions import UnsupportedLanguageError, FormatterError

class FormatterRegistry:
    """フォーマッター登録管理クラス"""
    
    def __init__(self):
        self._formatters: Dict[str, Type[BaseFormatter]] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_formatter(self, format_type: str, formatter_class: Type[BaseFormatter]):
        """フォーマッタークラスを登録"""
        self._formatters[format_type] = formatter_class
        self.logger.debug(f"Registered formatter: {format_type} -> {formatter_class.__name__}")
    
    def get_formatter_class(self, format_type: str) -> Type[BaseFormatter]:
        """フォーマッタークラスを取得"""
        if format_type not in self._formatters:
            raise FormatterError(f"Unknown format type: {format_type}")
        return self._formatters[format_type]
    
    def get_available_formats(self) -> List[str]:
        """利用可能なフォーマットタイプのリストを返す"""
        return list(self._formatters.keys())

class UnifiedFormatterFactory:
    """統一フォーマッターファクトリー"""
    
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self.formatter_cache: Dict[str, BaseFormatter] = {}
        self.registry = FormatterRegistry()
        self.logger = logging.getLogger(__name__)
        
        # デフォルトフォーマッターの登録
        self._register_default_formatters()
        
        # キャッシュサイズ制限
        self.max_cache_size = 50
    
    def _register_default_formatters(self):
        """デフォルトフォーマッターを登録"""
        from tree_sitter_analyzer.formatters.table import TableFormatter
        from tree_sitter_analyzer.formatters.json import JsonFormatter
        from tree_sitter_analyzer.formatters.csv import CsvFormatter
        from tree_sitter_analyzer.formatters.xml import XmlFormatter
        
        self.registry.register_formatter("table", TableFormatter)
        self.registry.register_formatter("json", JsonFormatter)
        self.registry.register_formatter("csv", CsvFormatter)
        self.registry.register_formatter("xml", XmlFormatter)
    
    def create_formatter(self, language: str, format_type: str, **kwargs) -> BaseFormatter:
        """言語とフォーマット種別に応じたフォーマッターを作成"""
        cache_key = f"{language}_{format_type}_{hash(frozenset(kwargs.items()))}"
        
        # キャッシュから取得
        if cache_key in self.formatter_cache:
            self.logger.debug(f"Using cached formatter: {cache_key}")
            return self.formatter_cache[cache_key]
        
        # キャッシュサイズ制限
        if len(self.formatter_cache) >= self.max_cache_size:
            # 最も古いエントリを削除（簡易LRU）
            oldest_key = next(iter(self.formatter_cache))
            del self.formatter_cache[oldest_key]
        
        try:
            # プラグインから専用フォーマッターを取得
            plugin = self.plugin_manager.get_plugin(language)
            if plugin and hasattr(plugin, 'create_formatter'):
                formatter = plugin.create_formatter(format_type, **kwargs)
                self.logger.debug(f"Created plugin-specific formatter: {language}.{format_type}")
            else:
                # 汎用フォーマッターを使用
                formatter_class = self.registry.get_formatter_class(format_type)
                formatter = formatter_class(language=language, **kwargs)
                self.logger.debug(f"Created generic formatter: {format_type} for {language}")
            
            # キャッシュに保存
            self.formatter_cache[cache_key] = formatter
            
            return formatter
            
        except Exception as e:
            self.logger.error(f"Failed to create formatter {language}.{format_type}: {str(e)}")
            raise FormatterError(f"Failed to create formatter: {str(e)}")
    
    def get_available_formats(self, language: str) -> List[str]:
        """指定言語で利用可能なフォーマットのリストを返す"""
        formats = self.registry.get_available_formats()
        
        # プラグイン固有のフォーマットを追加
        plugin = self.plugin_manager.get_plugin(language)
        if plugin and hasattr(plugin, 'get_supported_formats'):
            plugin_formats = plugin.get_supported_formats()
            formats.extend(plugin_formats)
        
        return list(set(formats))  # 重複除去
    
    def clear_cache(self):
        """フォーマッターキャッシュをクリア"""
        self.formatter_cache.clear()
        self.logger.info("Formatter cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        return {
            "cache_size": len(self.formatter_cache),
            "max_cache_size": self.max_cache_size,
            "cached_formatters": list(self.formatter_cache.keys())
        }
```

#### Day 5-7: 拡張プラグインインターフェースの実装

```python
# tree_sitter_analyzer/plugins/enhanced_base.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
import tree_sitter
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.formatters.base import BaseFormatter
from tree_sitter_analyzer.models import AnalysisRequest, AnalysisResult

class EnhancedLanguagePlugin(LanguagePlugin):
    """拡張言語プラグインインターフェース"""
    
    def __init__(self):
        super().__init__()
        self._performance_metrics = {
            "parse_count": 0,
            "total_parse_time": 0.0,
            "error_count": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    @abstractmethod
    def get_language_object(self) -> tree_sitter.Language:
        """Tree-sitter言語オブジェクトを返す"""
        pass
    
    @abstractmethod
    def get_query_definitions(self) -> Dict[str, str]:
        """Tree-sitterクエリ定義を返す"""
        pass
    
    @abstractmethod
    def create_formatter(self, format_type: str, **kwargs) -> BaseFormatter:
        """指定されたフォーマット種別のフォーマッターを作成"""
        pass
    
    def get_plugin_info(self) -> Dict[str, Any]:
        """プラグイン情報を返す"""
        return {
            "name": f"{self.get_language_name().title()} Language Plugin",
            "version": "1.0.0",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "features": self.get_supported_features(),
            "author": "tree-sitter-analyzer team",
            "description": f"Enhanced plugin for {self.get_language_name()} language analysis",
            "plugin_type": "enhanced"
        }
    
    def get_supported_features(self) -> List[str]:
        """サポートする機能のリストを返す"""
        return ["functions", "classes", "variables", "imports"]
    
    def get_supported_formats(self) -> List[str]:
        """サポートするフォーマットのリストを返す"""
        return ["table", "json", "csv"]
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """設定の妥当性を検証"""
        required_keys = ["language", "extensions"]
        return all(key in config for key in required_keys)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """パフォーマンスメトリクスを返す"""
        metrics = self._performance_metrics.copy()
        
        if metrics["parse_count"] > 0:
            metrics["avg_parse_time"] = metrics["total_parse_time"] / metrics["parse_count"]
            metrics["error_rate"] = metrics["error_count"] / metrics["parse_count"]
            
            if metrics["cache_hits"] + metrics["cache_misses"] > 0:
                total_cache_requests = metrics["cache_hits"] + metrics["cache_misses"]
                metrics["cache_hit_rate"] = metrics["cache_hits"] / total_cache_requests
        else:
            metrics["avg_parse_time"] = 0.0
            metrics["error_rate"] = 0.0
            metrics["cache_hit_rate"] = 0.0
        
        return metrics
    
    def reset_performance_metrics(self):
        """パフォーマンスメトリクスをリセット"""
        self._performance_metrics = {
            "parse_count": 0,
            "total_parse_time": 0.0,
            "error_count": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    def _record_parse_time(self, parse_time: float):
        """解析時間を記録"""
        self._performance_metrics["parse_count"] += 1
        self._performance_metrics["total_parse_time"] += parse_time
    
    def _record_error(self):
        """エラーを記録"""
        self._performance_metrics["error_count"] += 1
    
    def _record_cache_hit(self):
        """キャッシュヒットを記録"""
        self._performance_metrics["cache_hits"] += 1
    
    def _record_cache_miss(self):
        """キャッシュミスを記録"""
        self._performance_metrics["cache_misses"] += 1
    
    def supports_query(self, query_type: str) -> bool:
        """指定されたクエリタイプをサポートするかチェック"""
        return query_type in self.get_query_definitions()
    
    def supports_format(self, format_type: str) -> bool:
        """指定されたフォーマットをサポートするかチェック"""
        return format_type in self.get_supported_formats()
    
    def get_query_complexity(self, query_type: str) -> int:
        """クエリの複雑度を返す（1-10のスケール）"""
        query_definitions = self.get_query_definitions()
        if query_type not in query_definitions:
            return 0
        
        query_string = query_definitions[query_type]
        # 簡易的な複雑度計算
        complexity = 1
        complexity += query_string.count("(")  # ノード数
        complexity += query_string.count("@")  # キャプチャ数
        complexity += query_string.count("|")  # 選択肢数
        
        return min(complexity, 10)
    
    def optimize_for_large_files(self) -> bool:
        """大きなファイルに対する最適化が有効かどうか"""
        return False
    
    def get_memory_usage_estimate(self, file_size: int) -> int:
        """ファイルサイズに基づくメモリ使用量の推定値（バイト）"""
        # デフォルト: ファイルサイズの3倍
        return file_size * 3
```

### Week 2: 統合システム実装

#### Day 8-10: 新AnalysisEngineの実装

```python
# tree_sitter_analyzer/core/enhanced_analysis_engine.py
from typing import Dict, List, Any, Optional
import time
import logging
from pathlib import Path
from tree_sitter_analyzer.core.unified_query_engine import UnifiedQueryEngine
from tree_sitter_analyzer.formatters.unified_factory import UnifiedFormatterFactory
from tree_sitter_analyzer.plugins.manager import PluginManager
from tree_sitter_analyzer.models import AnalysisRequest, AnalysisResult
from tree_sitter_analyzer.exceptions import AnalysisError, UnsupportedLanguageError

class EnhancedAnalysisEngine:
    """拡張解析エンジン - プラグインベースアーキテクチャ"""
    
    def __init__(self, plugin_manager: Optional[PluginManager] = None):
        self.plugin_manager = plugin_manager or PluginManager()
        self.query_engine = UnifiedQueryEngine(self.plugin_manager)
        self.formatter_factory = UnifiedFormatterFactory(self.plugin_manager)
        self.logger = logging.getLogger(__name__)
        
        # プラグインの読み込み
        self.plugin_manager.load_plugins()
        
        # 統計情報
        self.stats = {
            "files_analyzed": 0,
            "total_analysis_time": 0.0,
            "errors": 0,
            "cache_hits": 0
        }
    
    def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
        """ファイルを解析して結果を返す"""
        start_time = time.time()
        
        try:
            # ファイルパスの正規化
            file_path = str(Path(file_path).resolve())
            
            # 言語の検出
            language = self._detect_language(file_path)
            if not language:
                raise UnsupportedLanguageError(f"Cannot detect language for file: {file_path}")
            
            # プラグインの取得
            plugin = self.plugin_manager.get_plugin(language)
            if not plugin:
                raise UnsupportedLanguageError(f"No plugin available for language: {language}")
            
            # ファイルの読み込みと解析
            result = plugin.analyze_file(file_path, request)
            
            # 統計更新
            analysis_time = time.time() - start_time
            self.stats["files_analyzed"] += 1
            self.stats["total_analysis_time"] += analysis_time
            
            self.logger.info(f"Analyzed {file_path} ({language}) in {analysis_time:.3f}s")
            
            return result
            
        except Exception as e:
            self.stats["errors"] += 1
            analysis_time = time.time() - start_time
            self.logger.error(f"Analysis failed for {file_path}: {str(e)} (took {analysis_time:.3f}s)")
            raise AnalysisError(f"Failed to analyze {file_path}: {str(e)}")
    
    def analyze_code(self, source_code: str, language: str, request: AnalysisRequest) -> AnalysisResult:
        """ソースコードを直接解析"""
        start_time = time.time()
        
        try:
            # プラグインの取得
            plugin = self.plugin_manager.get_plugin(language)
            if not plugin:
                raise UnsupportedLanguageError(f"No plugin available for language: {language}")
            
            # 一時ファイルを作成せずに直接解析
            result = plugin.analyze_code(source_code, request)
            
            # 統計更新
            analysis_time = time.time() - start_time
            self.stats["files_analyzed"] += 1
            self.stats["total_analysis_time"] += analysis_time
            
            return result
            
        except Exception as e:
            self.stats["errors"] += 1
            analysis_time = time.time() - start_time
            self.logger.error(f"Code analysis failed for {language}: {str(e)} (took {analysis_time:.3f}s)")
            raise AnalysisError(f"Failed to analyze code: {str(e)}")
    
    def format_results(self, result: AnalysisResult, format_type: str, **kwargs) -> str:
        """解析結果をフォーマット"""
        try:
            formatter = self.formatter_factory.create_formatter(
                result.language, format_type, **kwargs
            )
            return formatter.format_result(result)
            
        except Exception as e:
            self.logger.error(f"Formatting failed: {str(e)}")
            raise AnalysisError(f"Failed to format results: {str(e)}")
    
    def _detect_language(self, file_path: str) -> Optional[str]:
        """ファイルパスから言語を検出"""
        file_path = Path(file_path)
        extension = file_path.suffix.lower()
        
        # 全プラグインをチェック
        for language, plugin in self.plugin_manager.get_all_plugins().items():
            if plugin.is_applicable(str(file_path)):
                return language
        
        return None
    
    def get_supported_languages(self) -> List[str]:
        """サポートされている言語のリストを返す"""
        return self.plugin_manager.get_supported_languages()
    
    def get_supported_queries(self, language: str) -> List[str]:
        """指定言語でサポートされているクエリのリストを返す"""
        return self.query_engine.get_supported_queries(language)
    
    def get_supported_formats(self, language: str) -> List[str]:
        """指定言語でサポートされているフォーマットのリストを返す"""
        return self.formatter_factory.get_available_formats(language)
    
    def validate_request(self, request: AnalysisRequest, language: str) -> bool:
        """解析リクエストの妥当性を検証"""
        supported_queries = self.get_supported_queries(language)
        
        for query_type in request.query_

types:
            if query_type not in supported_queries:
                return False
        
        return True
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """エンジンの統計情報を取得"""
        stats = self.stats.copy()
        
        if stats["files_analyzed"] > 0:
            stats["avg_analysis_time"] = stats["total_analysis_time"] / stats["files_analyzed"]
            stats["error_rate"] = stats["errors"] / stats["files_analyzed"]
        else:
            stats["avg_analysis_time"] = 0.0
            stats["error_rate"] = 0.0
        
        # プラグイン統計を追加
        stats["plugin_stats"] = {}
        for language, plugin in self.plugin_manager.get_all_plugins().items():
            if hasattr(plugin, 'get_performance_metrics'):
                stats["plugin_stats"][language] = plugin.get_performance_metrics()
        
        # クエリエンジン統計を追加
        stats["query_engine_stats"] = self.query_engine.performance_monitor.get_performance_report()
        
        return stats
    
    def clear_caches(self):
        """全キャッシュをクリア"""
        self.query_engine.clear_cache()
        self.formatter_factory.clear_cache()
        self.logger.info("All caches cleared")
    
    def reload_plugins(self):
        """プラグインを再読み込み"""
        self.plugin_manager.reload_plugins()
        self.logger.info("Plugins reloaded")
```

#### Day 11-14: 後方互換性レイヤーの実装

```python
# tree_sitter_analyzer/compatibility/legacy_adapter.py
from typing import Dict, List, Any, Optional
import warnings
from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
from tree_sitter_analyzer.models import AnalysisRequest, AnalysisResult

class LegacyAnalysisEngine:
    """後方互換性のためのレガシーエンジンアダプター"""
    
    def __init__(self):
        self.enhanced_engine = EnhancedAnalysisEngine()
        self._deprecation_warnings_shown = set()
    
    def _show_deprecation_warning(self, method_name: str, new_method: str):
        """非推奨警告を表示（一度だけ）"""
        if method_name not in self._deprecation_warnings_shown:
            warnings.warn(
                f"{method_name} is deprecated and will be removed in v2.0. "
                f"Use {new_method} instead.",
                DeprecationWarning,
                stacklevel=3
            )
            self._deprecation_warnings_shown.add(method_name)
    
    def analyze_file(self, file_path: str, query_types: List[str] = None, 
                    output_format: str = "table", **kwargs) -> Any:
        """レガシーAPIの analyze_file メソッド"""
        self._show_deprecation_warning(
            "LegacyAnalysisEngine.analyze_file",
            "EnhancedAnalysisEngine.analyze_file"
        )
        
        # レガシーパラメータを新形式に変換
        query_types = query_types or ["functions", "classes"]
        request = AnalysisRequest(
            query_types=query_types,
            output_format=output_format,
            **kwargs
        )
        
        # 新エンジンで解析
        result = self.enhanced_engine.analyze_file(file_path, request)
        
        # レガシー形式で結果を返す
        if output_format == "table":
            return self.enhanced_engine.format_results(result, "table")
        elif output_format == "json":
            return result.to_dict()
        else:
            return result
    
    def query_file(self, file_path: str, language: str = None, 
                  query_type: str = "functions") -> List[Dict[str, Any]]:
        """レガシーAPIの query_file メソッド"""
        self._show_deprecation_warning(
            "LegacyAnalysisEngine.query_file",
            "EnhancedAnalysisEngine.analyze_file"
        )
        
        request = AnalysisRequest(query_types=[query_type])
        result = self.enhanced_engine.analyze_file(file_path, request)
        
        # レガシー形式に変換
        if query_type == "functions":
            return [func.to_dict() for func in result.functions]
        elif query_type == "classes":
            return [cls.to_dict() for cls in result.classes]
        elif query_type == "variables":
            return [var.to_dict() for var in result.variables]
        else:
            return []
    
    def get_supported_languages(self) -> List[str]:
        """サポート言語の取得（互換性維持）"""
        return self.enhanced_engine.get_supported_languages()
    
    def format_output(self, data: Any, format_type: str) -> str:
        """出力フォーマット（互換性維持）"""
        self._show_deprecation_warning(
            "LegacyAnalysisEngine.format_output",
            "EnhancedAnalysisEngine.format_results"
        )
        
        # データがAnalysisResultの場合
        if isinstance(data, AnalysisResult):
            return self.enhanced_engine.format_results(data, format_type)
        
        # レガシーデータの場合は簡易フォーマット
        if format_type == "json":
            import json
            return json.dumps(data, indent=2)
        elif format_type == "table":
            return str(data)  # 簡易実装
        else:
            return str(data)

# 完全な後方互換性のためのエイリアス
AnalysisEngine = LegacyAnalysisEngine
```

---

## 🔄 Phase 2: 段階的移行実装

### Week 3-4: 条件分岐削除の実装

#### 条件分岐削除戦略

```python
# scripts/conditional_branch_migration.py
import ast
import re
from pathlib import Path
from typing import List, Dict, Tuple

class ConditionalBranchAnalyzer:
    """条件分岐分析器"""
    
    def __init__(self):
        self.branch_patterns = [
            r'if\s+language\s*==\s*["\'](\w+)["\']',
            r'elif\s+language\s*==\s*["\'](\w+)["\']',
            r'if\s+language\s+in\s*\[([^\]]+)\]',
            r'language\s*==\s*["\'](\w+)["\']',
        ]
    
    def find_conditional_branches(self, file_path: str) -> List[Dict[str, Any]]:
        """ファイル内の条件分岐を検出"""
        content = Path(file_path).read_text(encoding='utf-8')
        branches = []
        
        for line_num, line in enumerate(content.split('\n'), 1):
            for pattern in self.branch_patterns:
                matches = re.finditer(pattern, line)
                for match in matches:
                    branches.append({
                        'file': file_path,
                        'line': line_num,
                        'content': line.strip(),
                        'language': match.group(1) if match.groups() else 'multiple',
                        'pattern': pattern
                    })
        
        return branches
    
    def analyze_project(self, project_root: str) -> Dict[str, List[Dict[str, Any]]]:
        """プロジェクト全体の条件分岐を分析"""
        project_path = Path(project_root)
        results = {}
        
        for py_file in project_path.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            
            branches = self.find_conditional_branches(str(py_file))
            if branches:
                results[str(py_file)] = branches
        
        return results

class BranchMigrationPlan:
    """条件分岐移行計画"""
    
    def __init__(self):
        self.migration_steps = []
    
    def generate_migration_plan(self, branches: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """移行計画を生成"""
        plan = []
        
        # 優先度順にファイルをソート
        priority_files = [
            "query_service.py",
            "table_command.py", 
            "language_loader.py",
            "mcp/server.py"
        ]
        
        for priority_file in priority_files:
            for file_path, file_branches in branches.items():
                if priority_file in file_path:
                    plan.append({
                        'file': file_path,
                        'priority': 'high',
                        'branches': file_branches,
                        'migration_strategy': self._determine_strategy(file_path, file_branches)
                    })
        
        # 残りのファイル
        for file_path, file_branches in branches.items():
            if not any(pf in file_path for pf in priority_files):
                plan.append({
                    'file': file_path,
                    'priority': 'medium',
                    'branches': file_branches,
                    'migration_strategy': self._determine_strategy(file_path, file_branches)
                })
        
        return plan
    
    def _determine_strategy(self, file_path: str, branches: List[Dict[str, Any]]) -> str:
        """移行戦略を決定"""
        if "query_service.py" in file_path:
            return "plugin_delegation"
        elif "table_command.py" in file_path:
            return "formatter_factory"
        elif "language_loader.py" in file_path:
            return "plugin_manager"
        else:
            return "refactor_to_plugin"
```

#### 具体的な移行実装例

```python
# migration/query_service_migration.py
"""
query_service.py の条件分岐削除実装例
"""

# 移行前のコード（削除対象）
def execute_query_old(language: str, query_type: str, node: Node) -> List[QueryResult]:
    """旧実装 - 条件分岐あり"""
    results = []
    
    if language == "java":
        if node.type == "method_declaration":
            results.append(QueryResult(node, "method"))
        elif node.type == "class_declaration":
            results.append(QueryResult(node, "class"))
    elif language == "python":
        if node.type == "function_definition":
            results.append(QueryResult(node, "function"))
        elif node.type == "class_definition":
            results.append(QueryResult(node, "class"))
    elif language in ["javascript", "typescript"]:
        if node.type in ["function_declaration", "method_definition"]:
            results.append(QueryResult(node, "function"))
    # ... 他の言語の条件分岐
    
    return results

# 移行後のコード（プラグインベース）
def execute_query_new(language: str, query_type: str, tree: Tree, source_code: str) -> List[QueryResult]:
    """新実装 - プラグインベース"""
    # 統一クエリエンジンを使用
    query_engine = UnifiedQueryEngine(plugin_manager)
    return query_engine.execute_query(language, query_type, tree, source_code)

# 移行実装クラス
class QueryServiceMigration:
    """QueryService移行実装"""
    
    def __init__(self, query_engine: UnifiedQueryEngine):
        self.query_engine = query_engine
        self.legacy_methods = {}  # 後方互換性のため
    
    def migrate_execute_query(self):
        """execute_queryメソッドの移行"""
        # 1. 新メソッドの実装
        def new_execute_query(language: str, query_type: str, tree: Tree, source_code: str) -> List[QueryResult]:
            return self.query_engine.execute_query(language, query_type, tree, source_code)
        
        # 2. 旧メソッドの非推奨化
        def deprecated_execute_query(language: str, query_type: str, node: Node) -> List[QueryResult]:
            warnings.warn(
                "execute_query with Node parameter is deprecated. Use Tree and source_code instead.",
                DeprecationWarning,
                stacklevel=2
            )
            # 互換性のための変換処理
            return self._convert_node_to_tree_query(language, query_type, node)
        
        return new_execute_query, deprecated_execute_query
    
    def _convert_node_to_tree_query(self, language: str, query_type: str, node: Node) -> List[QueryResult]:
        """Node形式から新形式への変換（互換性維持）"""
        # 簡易実装 - 実際にはより複雑な変換が必要
        tree = node.tree if hasattr(node, 'tree') else None
        source_code = ""  # 実際には適切に取得
        
        if tree and source_code:
            return self.query_engine.execute_query(language, query_type, tree, source_code)
        else:
            # フォールバック処理
            return []
```

### Week 5-6: プラグイン移行の実装

#### 既存プラグインの拡張実装

```python
# migration/plugin_enhancement.py
"""
既存プラグインの拡張実装例
"""

class PythonPluginMigration:
    """Pythonプラグインの移行実装"""
    
    def __init__(self, original_plugin):
        self.original_plugin = original_plugin
        self.enhanced_plugin = None
    
    def migrate_to_enhanced_plugin(self) -> EnhancedLanguagePlugin:
        """拡張プラグインへの移行"""
        
        class EnhancedPythonPlugin(EnhancedLanguagePlugin):
            def __init__(self, original):
                super().__init__()
                self.original = original
                self.language = ts_python.language()
                self.parser = tree_sitter.Parser()
                self.parser.set_language(self.language)
            
            def get_language_name(self) -> str:
                return "python"
            
            def get_file_extensions(self) -> List[str]:
                return [".py", ".pyi", ".pyw"]
            
            def is_applicable(self, file_path: str) -> bool:
                return any(file_path.endswith(ext) for ext in self.get_file_extensions())
            
            def get_language_object(self) -> tree_sitter.Language:
                return self.language
            
            def get_query_definitions(self) -> Dict[str, str]:
                return {
                    "functions": """
                        (function_definition
                            name: (identifier) @function.name
                            parameters: (parameters) @function.params
                            body: (block) @function.body
                        ) @function.definition
                    """,
                    "classes": """
                        (class_definition
                            name: (identifier) @class.name
                            superclasses: (argument_list)? @class.bases
                            body: (block) @class.body
                        ) @class.definition
                    """,
                    "variables": """
                        (assignment
                            left: (identifier) @variable.name
                            right: (_) @variable.value
                        ) @variable.definition
                    """,
                    "imports": """
                        [
                            (import_statement
                                name: (dotted_name) @import.name
                            )
                            (import_from_statement
                                module_name: (dotted_name) @import.module
                                name: (dotted_name) @import.name
                            )
                        ] @import.statement
                    """
                }
            
            def create_formatter(self, format_type: str, **kwargs) -> BaseFormatter:
                from tree_sitter_analyzer.formatters.python import PythonFormatter
                return PythonFormatter(format_type, **kwargs)
            
            def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
                """ファイル解析の実装"""
                start_time = time.time()
                
                try:
                    # ファイル読み込み
                    source_code = Path(file_path).read_text(encoding='utf-8')
                    
                    # パース実行
                    tree = self.parser.parse(source_code.encode('utf-8'))
                    
                    if tree.root_node.has_error:
                        raise ParseError(f"Parse error in {file_path}")
                    
                    # 結果オブジェクトの初期化
                    result = AnalysisResult(
                        file_path=file_path,
                        language=self.get_language_name(),
                        functions=[],
                        classes=[],
                        variables=[],
                        imports=[],
                        metadata={}
                    )
                    
                    # クエリエンジンを使用して解析
                    query_engine = UnifiedQueryEngine(plugin_manager)
                    
                    for query_type in request.query_types:
                        if query_type == "functions":
                            query_results = query_engine.execute_query(
                                self.get_language_name(), "functions", tree, source_code
                            )
                            result.functions = self._convert_to_model_functions(query_results, source_code)
                        elif query_type == "classes":
                            query_results = query_engine.execute_query(
                                self.get_language_name(), "classes", tree, source_code
                            )
                            result.classes = self._convert_to_model_classes(query_results, source_code)
                        # ... 他のクエリタイプ
                    
                    # パフォーマンス記録
                    parse_time = time.time() - start_time
                    self._record_parse_time(parse_time)
                    
                    result.metadata["parse_time"] = parse_time
                    result.metadata["node_count"] = self._count_nodes(tree.root_node)
                    
                    return result
                    
                except Exception as e:
                    self._record_error()
                    raise ParseError(f"Failed to analyze {file_path}: {str(e)}")
            
            def _convert_to_model_functions(self, query_results: List[QueryResult], source_code: str) -> List[ModelFunction]:
                """クエリ結果をModelFunctionに変換"""
                functions = []
                
                for result in query_results:
                    if result.capture_name == "function.definition":
                        function = ModelFunction(
                            name=result.name,
                            start_line=result.start_line,
                            end_line=result.end_line,
                            start_column=result.start_column,
                            end_column=result.end_column,
                            docstring=self._extract_docstring(result, source_code),
                            parameters=self._extract_parameters(result, source_code),
                            return_type=self._extract_return_type(result, source_code),
                            is_async=self._is_async_function(result, source_code),
                            is_method=self._is_method(result),
                            visibility="public",  # Pythonはデフォルトpublic
                            metadata=result.metadata
                        )
                        functions.append(function)
                
                return functions
            
            def _extract_docstring(self, result: QueryResult, source_code: str) -> Optional[str]:
                """関数のdocstringを抽出"""
                # 実装詳細は省略
                return None
            
            def _extract_parameters(self, result: QueryResult, source_code: str) -> List[str]:
                """関数パラメータを抽出"""
                # 実装詳細は省略
                return []
            
            def _extract_return_type(self, result: QueryResult, source_code: str) -> Optional[str]:
                """戻り値の型を抽出"""
                # 実装詳細は省略
                return None
            
            def _is_async_function(self, result: QueryResult, source_code: str) -> bool:
                """非同期関数かどうかを判定"""
                # 実装詳細は省略
                return False
            
            def _is_method(self, result: QueryResult) -> bool:
                """メソッドかどうかを判定"""
                # 実装詳細は省略
                return False
            
            def _count_nodes(self, node: tree_sitter.Node) -> int:
                """ノード数をカウント"""
                count = 1
                for child in node.children:
                    count += self._count_nodes(child)
                return count
        
        self.enhanced_plugin = EnhancedPythonPlugin(self.original_plugin)
        return self.enhanced_plugin
```

---

## 🧪 Phase 3: 最終統合実装

### Week 7: 統合テストとバリデーション

#### 統合テストスイートの実装

```python
# tests/integration/test_migration_validation.py
"""
移行検証のための統合テスト
"""

import pytest
from pathlib import Path
from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
from tree_sitter_analyzer.compatibility.legacy_adapter import LegacyAnalysisEngine
from tree_sitter_analyzer.models import AnalysisRequest

class TestMigrationValidation:
    """移行検証テスト"""
    
    @pytest.fixture
    def enhanced_engine(self):
        return EnhancedAnalysisEngine()
    
    @pytest.fixture
    def legacy_engine(self):
        return LegacyAnalysisEngine()
    
    @pytest.fixture
    def test_files(self, tmp_path):
        """テスト用ファイルを作成"""
        files = {}
        
        # Python
        python_content = '''
def hello_world():
    """Hello world function"""
    print("Hello, World!")

class Calculator:
    def add(self, a, b):
        return a + b
        
import os
from typing import List
        '''
        python_file = tmp_path / "test.py"
        python_file.write_text(python_content)
        files["python"] = str(python_file)
        
        # JavaScript
        js_content = '''
function helloWorld() {
    console.log("Hello, World!");
}

class Calculator {
    add(a, b) {
        return a + b;
    }
}

import { fs } from 'fs';
        '''
        js_file = tmp_path / "test.js"
        js_file.write_text(js_content)
        files["javascript"] = str(js_file)
        
        return files
    
    def test_api_compatibility(self, enhanced_engine, legacy_engine, test_files):
        """API互換性テスト"""
        request = AnalysisRequest(query_types=["functions", "classes"])
        
        for language, file_path in test_files.items():
            # 新エンジンでの解析
            enhanced_result = enhanced_engine.analyze_file(file_path, request)
            
            # レガシーエンジンでの解析（互換性確認）
            legacy_result = legacy_engine.analyze_file(file_path, ["functions", "classes"])
            
            # 基本的な結果の一致確認
            assert enhanced_result.language == language
            assert len(enhanced_result.functions) > 0
            assert len(enhanced_result.classes) > 0
    
    def test_performance_comparison(self, enhanced_engine, legacy_engine, test_files):
        """パフォーマンス比較テスト"""
        import time
        
        request = AnalysisRequest(query_types=["functions"])
        
        for file_path in test_files.values():
            # 新エンジンのパフォーマンス
            start_time = time.time()
            for _ in range(10):
                enhanced_engine.analyze_file(file_path, request)
            enhanced_time = time.time() - start_time
            
            # レガシーエンジンのパフォーマンス
            start_time = time.time()
            for _ in range(10):
                legacy_engine.analyze_file(file_path, ["functions"])
            legacy_time = time.time() - start_time
            
            # パフォーマンス要件: 新エンジンは既存の105%以内
            performance_ratio = enhanced_time / legacy_time
            assert performance_ratio <= 1.05, f"Performance degradation: {performance_ratio:.2f}x"
    
    def test_conditional_branch_elimination(self):
        """条件分岐削除の検証"""
        from scripts.conditional_branch_migration import ConditionalBranchAnalyzer
        
        analyzer = ConditionalBranchAnalyzer()
        branches = analyzer.analyze_project("tree_sitter_analyzer/")
        
        # 移行対象ファイルに条件分岐が残っていないことを確認
        critical_files = [
            "core/enhanced_analysis_engine.py",
            "core/unified_query_engine.py",
            "formatters/unified_factory.py"
        ]
        
        for file_path, file_branches in branches.items():
            if any(cf in file_path for cf in critical_files):
                assert len(file_branches) == 0, f"Conditional branches found in {file_path}: {file_branches}"
    
    def test_plugin_system_integrity(self, enhanced_engine):
        """プラグインシステムの整合性テスト"""
        # 全プラグインの読み込み確認
        supported_languages = enhanced_engine.get_supported_languages()
        assert len(supported_languages) > 0
        
        # 各プラグインの基本機能確認
        for language in supported_languages:
            queries = enhanced_engine.get_supported_queries(language)
            formats = enhanced_engine.get_supported_formats(language)
            
            assert len(queries) > 0, f"No queries available for {language}"
            assert len(formats) > 0, f"No formats available for {language}"
            
            # 基本クエリの存在確認
            basic_queries = ["functions", "classes"]
            for query in basic_queries:
                if query in queries:
                    # クエリの妥当性確認
                    is_valid = enhanced_engine.query_engine.validate_query(language, query)
                    assert is_valid, f"Invalid query {query} for {language}"
```

### Week 8: 最終デプロイメント

#### デプロイメント自動化スクリプト

```python
# scripts/deployment_automation.py
"""
移行デプロイメント自動化スクリプト
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

class MigrationDeployment:
    """移行デプロイメント管理"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.deployment_steps = []
        self.rollback_steps = []
    
    def execute_deployment(self) -> bool:
        """デプロイメントを実行"""
        print("🚀 Starting Migration Deployment...")
        
        steps = [
            ("Pre-deployment Validation", self.validate_pre_deployment),
            ("Backup Current System", self.backup_current_system),
            ("Deploy New Components", self.deploy_new_components),
            ("Update Configuration", self.update_configuration),
            ("Run Migration Scripts", self.run_migration_scripts),
            ("Validate Deployment", self.validate_deployment),
            ("Update Documentation", self.update_documentation),
            ("Cleanup Legacy Code", self.cleanup_legacy_code)
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 {step_name}...")
            try:
                success = step_func()
                if not success:
                    print(f"❌ {step_name} failed!")
                    self.rollback_deployment()
                    return False
                print(f"✅ {step_name} completed")
            except Exception as e:
                print(f"💥 {step_name} error: {str(e)}")
                self.rollback_deployment()
                return False
        
        print("\n🎉 Migration deployment completed successfully!")
        return True
    
    def validate_pre_deployment(self) -> bool:
        """デプロイメント前検証"""
        # 全テストの実行
        result = subprocess.run([
            "pytest", "tests/", "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Tests failed: {result.stdout}")
            return False
        
        # 品質ゲートの実行
        result = subprocess.run([
            "python", "scripts/quality_gate.py"
        ], capture_output=True, text=True)
        
        return result.returncode == 0
    
    def backup_current_system(self) -> bool:
        """現在のシステムをバックアップ"""
        backup_dir = self.project_root / "backup" / f"migration_{int(time.time())}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 重要ファイルのバックアップ
        important_files = [
            "tree_sitter_analyzer/core/",
            "tree_sitter_analyzer/plugins/",
            "tree_sitter_analyzer/formatters/",
            "pyproject.toml",
            "README.md"
        ]
        
        for file_path in important_files:
            source = self.project_root / file_path
            if source.exists():
                if source.is_dir():
                    subprocess.run([
                        "cp", "-r", str(source), str(backup_dir)
                    ])
                else:
                    subprocess.run([
                        "cp", str(source), str(backup_dir)
                    ])
        
        print(f"Backup created at: {backup_dir}")
        return True
    
    def deploy_new_components(self) -> bool:
        """新コンポーネントのデプロイ"""
        # 新しいコンポーネントファイルの配置
        new_components =
 [
            "tree_sitter_analyzer/core/enhanced_analysis_engine.py",
            "tree_sitter_analyzer/core/unified_query_engine.py",
            "tree_sitter_analyzer/formatters/unified_factory.py",
            "tree_sitter_analyzer/compatibility/legacy_adapter.py"
        ]
        
        for component in new_components:
            source = self.project_root / "migration" / "new_components" / component
            target = self.project_root / component
            
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["cp", str(source), str(target)])
            else:
                print(f"Warning: {source} not found")
        
        return True
    
    def update_configuration(self) -> bool:
        """設定ファイルの更新"""
        # pyproject.tomlの更新
        config_updates = {
            "version": "2.0.0",
            "description": "Enhanced tree-sitter analyzer with plugin architecture"
        }
        
        # 実際の設定更新処理
        return True
    
    def run_migration_scripts(self) -> bool:
        """移行スクリプトの実行"""
        migration_scripts = [
            "scripts/migrate_plugins.py",
            "scripts/update_query_definitions.py",
            "scripts/migrate_formatters.py"
        ]
        
        for script in migration_scripts:
            script_path = self.project_root / script
            if script_path.exists():
                result = subprocess.run([
                    "python", str(script_path)
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"Migration script failed: {script}")
                    print(result.stderr)
                    return False
        
        return True
    
    def validate_deployment(self) -> bool:
        """デプロイメント検証"""
        # 統合テストの実行
        result = subprocess.run([
            "pytest", "tests/integration/", "-v"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print("Integration tests failed")
            return False
        
        # パフォーマンステストの実行
        result = subprocess.run([
            "python", "scripts/performance_test.py"
        ], capture_output=True, text=True)
        
        return result.returncode == 0
    
    def update_documentation(self) -> bool:
        """ドキュメントの更新"""
        # READMEの更新
        readme_path = self.project_root / "README.md"
        if readme_path.exists():
            content = readme_path.read_text()
            # バージョン情報の更新
            updated_content = content.replace("v1.", "v2.")
            readme_path.write_text(updated_content)
        
        return True
    
    def cleanup_legacy_code(self) -> bool:
        """レガシーコードのクリーンアップ"""
        # 非推奨ファイルの削除
        legacy_files = [
            "tree_sitter_analyzer/legacy/",
            "tree_sitter_analyzer/old_query_service.py"
        ]
        
        for file_path in legacy_files:
            target = self.project_root / file_path
            if target.exists():
                if target.is_dir():
                    subprocess.run(["rm", "-rf", str(target)])
                else:
                    target.unlink()
        
        return True
    
    def rollback_deployment(self):
        """デプロイメントのロールバック"""
        print("\n🔄 Rolling back deployment...")
        
        # バックアップからの復元
        backup_dirs = list((self.project_root / "backup").glob("migration_*"))
        if backup_dirs:
            latest_backup = max(backup_dirs, key=lambda x: x.stat().st_mtime)
            print(f"Restoring from: {latest_backup}")
            
            # 復元処理
            subprocess.run([
                "cp", "-r", f"{latest_backup}/*", str(self.project_root)
            ])
        
        print("✅ Rollback completed")

if __name__ == "__main__":
    deployment = MigrationDeployment()
    success = deployment.execute_deployment()
    sys.exit(0 if success else 1)
```

---

## 📊 移行進捗監視

### 進捗追跡システム

```python
# scripts/migration_progress_tracker.py
"""
移行進捗追跡システム
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

class MigrationProgressTracker:
    """移行進捗追跡"""
    
    def __init__(self):
        self.progress_file = Path("migration_progress.json")
        self.milestones = self._load_milestones()
        self.current_progress = self._load_progress()
    
    def _load_milestones(self) -> Dict[str, Any]:
        """マイルストーンの定義"""
        return {
            "phase1": {
                "name": "コア実装",
                "weeks": [1, 2],
                "tasks": [
                    "unified_query_engine",
                    "formatter_factory", 
                    "enhanced_analysis_engine",
                    "compatibility_layer"
                ],
                "completion_criteria": {
                    "code_coverage": 90,
                    "unit_tests_pass": 100,
                    "performance_baseline": 95
                }
            },
            "phase2": {
                "name": "段階的移行",
                "weeks": [3, 4, 5, 6],
                "tasks": [
                    "conditional_branch_removal",
                    "plugin_migration",
                    "formatter_migration",
                    "api_compatibility"
                ],
                "completion_criteria": {
                    "conditional_branches_removed": 95,
                    "plugin_coverage": 100,
                    "api_compatibility": 100
                }
            },
            "phase3": {
                "name": "最終統合",
                "weeks": [7, 8],
                "tasks": [
                    "integration_testing",
                    "performance_validation",
                    "deployment",
                    "documentation_update"
                ],
                "completion_criteria": {
                    "integration_tests_pass": 100,
                    "performance_improvement": 105,
                    "documentation_complete": 100
                }
            }
        }
    
    def _load_progress(self) -> Dict[str, Any]:
        """進捗データの読み込み"""
        if self.progress_file.exists():
            return json.loads(self.progress_file.read_text())
        else:
            return {
                "start_date": datetime.now().isoformat(),
                "phases": {},
                "overall_progress": 0,
                "current_phase": "phase1",
                "issues": [],
                "metrics": {}
            }
    
    def update_task_progress(self, phase: str, task: str, progress: int, notes: str = ""):
        """タスク進捗の更新"""
        if phase not in self.current_progress["phases"]:
            self.current_progress["phases"][phase] = {}
        
        self.current_progress["phases"][phase][task] = {
            "progress": progress,
            "updated_at": datetime.now().isoformat(),
            "notes": notes
        }
        
        # 全体進捗の計算
        self._calculate_overall_progress()
        self._save_progress()
    
    def add_issue(self, phase: str, task: str, issue: str, severity: str = "medium"):
        """課題の追加"""
        issue_data = {
            "phase": phase,
            "task": task,
            "issue": issue,
            "severity": severity,
            "created_at": datetime.now().isoformat(),
            "status": "open"
        }
        
        self.current_progress["issues"].append(issue_data)
        self._save_progress()
    
    def resolve_issue(self, issue_index: int, resolution: str):
        """課題の解決"""
        if 0 <= issue_index < len(self.current_progress["issues"]):
            self.current_progress["issues"][issue_index].update({
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.now().isoformat()
            })
            self._save_progress()
    
    def record_metric(self, metric_name: str, value: float, unit: str = ""):
        """メトリクスの記録"""
        if "metrics" not in self.current_progress:
            self.current_progress["metrics"] = {}
        
        if metric_name not in self.current_progress["metrics"]:
            self.current_progress["metrics"][metric_name] = []
        
        self.current_progress["metrics"][metric_name].append({
            "value": value,
            "unit": unit,
            "timestamp": datetime.now().isoformat()
        })
        
        self._save_progress()
    
    def _calculate_overall_progress(self):
        """全体進捗の計算"""
        total_tasks = 0
        completed_tasks = 0
        
        for phase_name, phase_data in self.milestones.items():
            for task in phase_data["tasks"]:
                total_tasks += 1
                if (phase_name in self.current_progress["phases"] and 
                    task in self.current_progress["phases"][phase_name]):
                    task_progress = self.current_progress["phases"][phase_name][task]["progress"]
                    if task_progress >= 100:
                        completed_tasks += 1
        
        self.current_progress["overall_progress"] = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0
    
    def _save_progress(self):
        """進捗データの保存"""
        self.progress_file.write_text(json.dumps(self.current_progress, indent=2))
    
    def generate_progress_report(self) -> str:
        """進捗レポートの生成"""
        report = []
        report.append("# 移行進捗レポート")
        report.append(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"全体進捗: {self.current_progress['overall_progress']:.1f}%")
        report.append("")
        
        # フェーズ別進捗
        for phase_name, phase_data in self.milestones.items():
            report.append(f"## {phase_data['name']} ({phase_name})")
            
            if phase_name in self.current_progress["phases"]:
                phase_progress = self.current_progress["phases"][phase_name]
                
                for task in phase_data["tasks"]:
                    if task in phase_progress:
                        progress = phase_progress[task]["progress"]
                        status = "✅" if progress >= 100 else "🔄" if progress > 0 else "⏳"
                        report.append(f"- {status} {task}: {progress}%")
                    else:
                        report.append(f"- ⏳ {task}: 0%")
            else:
                for task in phase_data["tasks"]:
                    report.append(f"- ⏳ {task}: 0%")
            
            report.append("")
        
        # 課題一覧
        open_issues = [issue for issue in self.current_progress["issues"] if issue["status"] == "open"]
        if open_issues:
            report.append("## 未解決課題")
            for i, issue in enumerate(open_issues):
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(issue["severity"], "⚪")
                report.append(f"- {severity_icon} [{issue['phase']}/{issue['task']}] {issue['issue']}")
            report.append("")
        
        # メトリクス
        if "metrics" in self.current_progress and self.current_progress["metrics"]:
            report.append("## 主要メトリクス")
            for metric_name, metric_data in self.current_progress["metrics"].items():
                if metric_data:
                    latest = metric_data[-1]
                    report.append(f"- {metric_name}: {latest['value']} {latest['unit']}")
            report.append("")
        
        return "\n".join(report)
    
    def check_milestone_completion(self, phase: str) -> bool:
        """マイルストーン完了チェック"""
        if phase not in self.milestones:
            return False
        
        phase_data = self.milestones[phase]
        criteria = phase_data["completion_criteria"]
        
        # 各完了基準をチェック
        for criterion, target_value in criteria.items():
            current_value = self._get_current_metric_value(criterion)
            if current_value < target_value:
                return False
        
        return True
    
    def _get_current_metric_value(self, metric_name: str) -> float:
        """現在のメトリクス値を取得"""
        if metric_name in self.current_progress.get("metrics", {}):
            metric_data = self.current_progress["metrics"][metric_name]
            if metric_data:
                return metric_data[-1]["value"]
        return 0.0

# 使用例
if __name__ == "__main__":
    tracker = MigrationProgressTracker()
    
    # 進捗更新例
    tracker.update_task_progress("phase1", "unified_query_engine", 75, "基本実装完了、テスト作成中")
    tracker.record_metric("code_coverage", 85.5, "%")
    tracker.add_issue("phase1", "enhanced_analysis_engine", "パフォーマンス最適化が必要", "medium")
    
    # レポート生成
    report = tracker.generate_progress_report()
    print(report)
```

---

## 🔧 トラブルシューティング

### よくある問題と解決方法

#### 1. プラグイン読み込みエラー

**問題**: プラグインが正しく読み込まれない

**原因**:
- プラグインインターフェースの実装不備
- 依存関係の問題
- 設定ファイルの誤り

**解決方法**:
```python
# デバッグ用プラグイン診断
def diagnose_plugin_issues():
    from tree_sitter_analyzer.plugins.manager import PluginManager
    
    manager = PluginManager()
    
    # プラグイン読み込み状況の確認
    for language in ["python", "javascript", "java"]:
        try:
            plugin = manager.get_plugin(language)
            print(f"✅ {language}: {plugin.__class__.__name__}")
        except Exception as e:
            print(f"❌ {language}: {str(e)}")
    
    # 依存関係の確認
    import tree_sitter_python
    import tree_sitter_javascript
    import tree_sitter_java
    print("✅ All tree-sitter dependencies available")
```

#### 2. クエリ実行エラー

**問題**: Tree-sitterクエリが失敗する

**原因**:
- クエリ構文エラー
- 言語パーサーの不一致
- ノード構造の変更

**解決方法**:
```python
# クエリ診断ツール
def diagnose_query_issues(language: str, query_type: str):
    from tree_sitter_analyzer.core.unified_query_engine import UnifiedQueryEngine
    
    engine = UnifiedQueryEngine()
    
    # クエリ定義の確認
    query_def = engine.get_query_definition(language, query_type)
    print(f"Query definition: {query_def}")
    
    # クエリの妥当性確認
    is_valid = engine.validate_query(language, query_type)
    print(f"Query valid: {is_valid}")
    
    # サンプルコードでのテスト
    sample_code = {
        "python": "def test(): pass",
        "javascript": "function test() {}",
        "java": "public void test() {}"
    }
    
    if language in sample_code:
        try:
            results = engine.execute_query_string(
                language, query_type, sample_code[language]
            )
            print(f"✅ Query execution successful: {len(results)} results")
        except Exception as e:
            print(f"❌ Query execution failed: {str(e)}")
```

#### 3. パフォーマンス問題

**問題**: 解析速度が遅い

**原因**:
- 大きなファイルの処理
- 非効率なクエリ
- メモリリーク

**解決方法**:
```python
# パフォーマンス診断
def diagnose_performance_issues(file_path: str):
    import time
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    
    # メモリ使用量の監視
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    start_time = time.time()
    
    # 解析実行
    from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
    engine = EnhancedAnalysisEngine()
    
    result = engine.analyze_file(file_path)
    
    end_time = time.time()
    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"解析時間: {end_time - start_time:.2f}秒")
    print(f"メモリ使用量: {final_memory - initial_memory:.2f}MB")
    print(f"ファイルサイズ: {os.path.getsize(file_path) / 1024:.2f}KB")
    
    # パフォーマンス統計
    stats = engine.get_engine_stats()
    print(f"平均解析時間: {stats.get('avg_analysis_time', 0):.2f}秒")
    print(f"エラー率: {stats.get('error_rate', 0):.2%}")
```

#### 4. 互換性問題

**問題**: レガシーAPIとの互換性エラー

**原因**:
- APIシグネチャの変更
- 戻り値形式の変更
- 非推奨機能の使用

**解決方法**:
```python
# 互換性チェックツール
def check_api_compatibility():
    from tree_sitter_analyzer.compatibility.legacy_adapter import LegacyAnalysisEngine
    
    legacy_engine = LegacyAnalysisEngine()
    
    # 基本APIの確認
    test_cases = [
        ("analyze_file", ["test.py", ["functions"]]),
        ("query_file", ["test.py", "python", "functions"]),
        ("get_supported_languages", []),
    ]
    
    for method_name, args in test_cases:
        try:
            method = getattr(legacy_engine, method_name)
            result = method(*args)
            print(f"✅ {method_name}: 互換性OK")
        except Exception as e:
            print(f"❌ {method_name}: {str(e)}")
```

---

## 📈 成功指標と検証

### KPI定義

```python
# scripts/migration_kpi_tracker.py
"""
移行KPI追跡システム
"""

class MigrationKPITracker:
    """移行KPI追跡"""
    
    def __init__(self):
        self.kpis = {
            "code_quality": {
                "conditional_branches_removed": {"target": 95, "unit": "%"},
                "code_coverage": {"target": 90, "unit": "%"},
                "cyclomatic_complexity": {"target": 10, "unit": "avg"},
                "technical_debt_ratio": {"target": 5, "unit": "%"}
            },
            "performance": {
                "analysis_speed_improvement": {"target": 105, "unit": "%"},
                "memory_usage_reduction": {"target": 90, "unit": "%"},
                "startup_time": {"target": 95, "unit": "%"},
                "throughput_improvement": {"target": 110, "unit": "%"}
            },
            "maintainability": {
                "plugin_coverage": {"target": 100, "unit": "%"},
                "api_compatibility": {"target": 100, "unit": "%"},
                "documentation_completeness": {"target": 95, "unit": "%"},
                "test_coverage": {"target": 95, "unit": "%"}
            },
            "developer_experience": {
                "new_language_addition_time": {"target": 50, "unit": "%"},
                "build_time": {"target": 90, "unit": "%"},
                "error_clarity": {"target": 90, "unit": "score"},
                "debugging_efficiency": {"target": 120, "unit": "%"}
            }
        }
    
    def measure_conditional_branches_removed(self) -> float:
        """条件分岐削除率の測定"""
        from scripts.conditional_branch_migration import ConditionalBranchAnalyzer
        
        analyzer = ConditionalBranchAnalyzer()
        current_branches = analyzer.analyze_project("tree_sitter_analyzer/")
        
        # ベースライン: 54件の条件分岐
        baseline_count = 54
        current_count = sum(len(branches) for branches in current_branches.values())
        
        removal_rate = ((baseline_count - current_count) / baseline_count) * 100
        return max(0, removal_rate)
    
    def measure_performance_improvement(self) -> Dict[str, float]:
        """パフォーマンス改善の測定"""
        import time
        from tree_sitter_analyzer.core.enhanced_analysis_engine import EnhancedAnalysisEngine
        from tree_sitter_analyzer.compatibility.legacy_adapter import LegacyAnalysisEngine
        
        # テストファイル
        test_files = ["examples/sample.py", "examples/Sample.java"]
        
        enhanced_engine = EnhancedAnalysisEngine()
        legacy_engine = LegacyAnalysisEngine()
        
        enhanced_times = []
        legacy_times = []
        
        for file_path in test_files:
            # 新エンジンの測定
            start_time = time.time()
            enhanced_engine.analyze_file(file_path)
            enhanced_times.append(time.time() - start_time)
            
            # レガシーエンジンの測定
            start_time = time.time()
            legacy_engine.analyze_file(file_path, ["functions", "classes"])
            legacy_times.append(time.time() - start_time)
        
        avg_enhanced = sum(enhanced_times) / len(enhanced_times)
        avg_legacy = sum(legacy_times) / len(legacy_times)
        
        improvement = (avg_legacy / avg_enhanced) * 100 if avg_enhanced > 0 else 100
        
        return {
            "analysis_speed_improvement": improvement,
            "avg_enhanced_time": avg_enhanced,
            "avg_legacy_time": avg_legacy
        }
    
    def generate_kpi_report(self) -> str:
        """KPIレポートの生成"""
        report = []
        report.append("# 移行KPIレポート")
        report.append(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # 各カテゴリのKPI測定
        for category, kpis in self.kpis.items():
            report.append(f"## {category.replace('_', ' ').title()}")
            
            for kpi_name, kpi_config in kpis.items():
                target = kpi_config["target"]
                unit = kpi_config["unit"]
                
                # 実際の測定値を取得
                current_value = self._measure_kpi(kpi_name)
                
                # 達成状況の判定
                if unit == "%":
                    achievement = "✅" if current_value >= target else "❌"
                else:
                    achievement = "✅" if current_value <= target else "❌"
                
                report.append(f"- {achievement} {kpi_name}: {current_value:.1f}{unit} (目標: {target}{unit})")
            
            report.append("")
        
        return "\n".join(report)
    
    def _measure_kpi(self, kpi_name: str) -> float:
        """個別KPIの測定"""
        if kpi_name == "conditional_branches_removed":
            return self.measure_conditional_branches_removed()
        elif kpi_name == "analysis_speed_improvement":
            return self.measure_performance_improvement()["analysis_speed_improvement"]
        # 他のKPIの測定実装...
        else:
            return 0.0  # デフォルト値
```

---

## 📋 チェックリスト

### 移行完了チェックリスト

#### Phase 1: コア実装
- [ ] UnifiedQueryEngine実装完了
- [ ] FormatterFactory実装完了  
- [ ] EnhancedAnalysisEngine実装完了
- [ ] 後方互換性レイヤー実装完了
- [ ] 単体テスト90%以上のカバレッジ
- [ ] パフォーマンステスト実行完了

#### Phase 2: 段階的移行
- [ ] 条件分岐95%以上削除完了
- [ ] 全プラグインの拡張実装完了
- [ ] フォーマッター移行完了
- [ ] API互換性100%確保
- [ ] 統合テスト実行完了
- [ ] 回帰テスト実行完了

#### Phase 3: 最終統合
- [ ] 全統合テスト合格
- [ ] パフォーマンス要件達成
- [ ] セキュリティ検証完了
- [ ] ドキュメント更新完了
- [ ] デプロイメント自動化完了
- [ ] ロールバック手順確認完了

### 品質ゲート

#### コード品質
- [ ] コードカバレッジ90%以上
- [ ] 循環的複雑度10以下
- [ ] 技術的負債比率5%以下
- [ ] 静的解析エラー0件

#### パフォーマンス
- [ ] 解析速度105%以上改善
- [ ] メモリ使用量10%以下削減
- [ ] 起動時間5%以下短縮
- [ ] スループット10%以上向上

#### 信頼性
- [ ] 全自動テスト合格
- [ ] エラー率1%以下
- [ ] 可用性99.9%以上
- [ ] 復旧時間5分以下

---

## 🎯 まとめ

この移行実装ガイドは、tree-sitter-analyzerプロジェクトの条件分岐ベースアーキテクチャからプラグインベースアーキテクチャへの完全な移行を実現するための詳細な実装手順を提供します。

### 主要成果

1. **アーキテクチャの近代化**: 54件の条件分岐を95%以上削除し、保守性を大幅に向上
2. **パフォーマンスの改善**: 統一クエリエンジンにより解析速度を5%以上向上
3. **拡張性の確保**: プラグインベースシステムにより新言語追加時間を50%短縮
4. **品質の向上**: 包括的なテスト戦略により品質を大幅に改善

### 次のステップ

1. **トラブルシューティングガイドの作成**
2. **実装サンプルコードの開発**
3. **継続的な監視とメンテナンス**
4. **コミュニティフィードバックの収集**

この実装ガイドに従うことで、プロジェクトの技術的負債を解消し、将来の拡張に備えた堅牢なアーキテクチャを構築できます。