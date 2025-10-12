"""
移行実装例

このファイルは、tree-sitter-analyzerプロジェクトの条件分岐ベースアーキテクチャから
プラグインベースアーキテクチャへの移行を実装する際の参考として使用できる
完全なサンプル実装です。
"""

import warnings
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import time
import json

# 移行前の旧実装（レガシーコード）
class LegacyQueryService:
    """
    移行前のクエリサービス（条件分岐ベース）
    
    この実装は移行対象となる条件分岐を含んでいます。
    """
    
    def __init__(self):
        self.supported_languages = ["python", "javascript", "java"]
    
    def execute_query(self, language: str, query_type: str, source_code: str) -> List[Dict[str, Any]]:
        """
        旧実装: 条件分岐ベースのクエリ実行
        
        この実装は移行対象です。
        """
        results = []
        
        # 条件分岐1: 言語別処理
        if language == "python":
            if query_type == "functions":
                results = self._extract_python_functions(source_code)
            elif query_type == "classes":
                results = self._extract_python_classes(source_code)
            elif query_type == "variables":
                results = self._extract_python_variables(source_code)
        
        elif language == "javascript":
            if query_type == "functions":
                results = self._extract_javascript_functions(source_code)
            elif query_type == "classes":
                results = self._extract_javascript_classes(source_code)
            elif query_type == "variables":
                results = self._extract_javascript_variables(source_code)
        
        elif language == "java":
            if query_type == "functions":
                results = self._extract_java_methods(source_code)
            elif query_type == "classes":
                results = self._extract_java_classes(source_code)
            elif query_type == "variables":
                results = self._extract_java_fields(source_code)
        
        else:
            raise ValueError(f"Unsupported language: {language}")
        
        return results
    
    def _extract_python_functions(self, source_code: str) -> List[Dict[str, Any]]:
        """Python関数抽出（簡易実装）"""
        # 実際の実装は省略
        return [{"name": "sample_function", "type": "function", "language": "python"}]
    
    def _extract_python_classes(self, source_code: str) -> List[Dict[str, Any]]:
        """Pythonクラス抽出（簡易実装）"""
        return [{"name": "SampleClass", "type": "class", "language": "python"}]
    
    def _extract_python_variables(self, source_code: str) -> List[Dict[str, Any]]:
        """Python変数抽出（簡易実装）"""
        return [{"name": "sample_var", "type": "variable", "language": "python"}]
    
    def _extract_javascript_functions(self, source_code: str) -> List[Dict[str, Any]]:
        """JavaScript関数抽出（簡易実装）"""
        return [{"name": "sampleFunction", "type": "function", "language": "javascript"}]
    
    def _extract_javascript_classes(self, source_code: str) -> List[Dict[str, Any]]:
        """JavaScriptクラス抽出（簡易実装）"""
        return [{"name": "SampleClass", "type": "class", "language": "javascript"}]
    
    def _extract_javascript_variables(self, source_code: str) -> List[Dict[str, Any]]:
        """JavaScript変数抽出（簡易実装）"""
        return [{"name": "sampleVar", "type": "variable", "language": "javascript"}]
    
    def _extract_java_methods(self, source_code: str) -> List[Dict[str, Any]]:
        """Javaメソッド抽出（簡易実装）"""
        return [{"name": "sampleMethod", "type": "method", "language": "java"}]
    
    def _extract_java_classes(self, source_code: str) -> List[Dict[str, Any]]:
        """Javaクラス抽出（簡易実装）"""
        return [{"name": "SampleClass", "type": "class", "language": "java"}]
    
    def _extract_java_fields(self, source_code: str) -> List[Dict[str, Any]]:
        """Javaフィールド抽出（簡易実装）"""
        return [{"name": "sampleField", "type": "field", "language": "java"}]


class LegacyFormatter:
    """
    移行前のフォーマッター（条件分岐ベース）
    """
    
    def format_results(self, results: List[Dict[str, Any]], format_type: str, language: str) -> str:
        """
        旧実装: 条件分岐ベースのフォーマット
        """
        if format_type == "table":
            if language == "python":
                return self._format_python_table(results)
            elif language == "javascript":
                return self._format_javascript_table(results)
            elif language == "java":
                return self._format_java_table(results)
        
        elif format_type == "json":
            if language == "python":
                return self._format_python_json(results)
            elif language == "javascript":
                return self._format_javascript_json(results)
            elif language == "java":
                return self._format_java_json(results)
        
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def _format_python_table(self, results: List[Dict[str, Any]]) -> str:
        """Python用テーブルフォーマット"""
        return "Python Table Format"
    
    def _format_javascript_table(self, results: List[Dict[str, Any]]) -> str:
        """JavaScript用テーブルフォーマット"""
        return "JavaScript Table Format"
    
    def _format_java_table(self, results: List[Dict[str, Any]]) -> str:
        """Java用テーブルフォーマット"""
        return "Java Table Format"
    
    def _format_python_json(self, results: List[Dict[str, Any]]) -> str:
        """Python用JSONフォーマット"""
        return json.dumps({"language": "python", "results": results})
    
    def _format_javascript_json(self, results: List[Dict[str, Any]]) -> str:
        """JavaScript用JSONフォーマット"""
        return json.dumps({"language": "javascript", "results": results})
    
    def _format_java_json(self, results: List[Dict[str, Any]]) -> str:
        """Java用JSONフォーマット"""
        return json.dumps({"language": "java", "results": results})


# 移行後の新実装（プラグインベース）
class MigratedQueryService:
    """
    移行後のクエリサービス（プラグインベース）
    
    条件分岐を削除し、プラグインシステムを使用します。
    """
    
    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager
        self.performance_stats = {
            "queries_executed": 0,
            "total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        self.query_cache = {}
    
    def execute_query(self, language: str, query_type: str, source_code: str) -> List[Dict[str, Any]]:
        """
        新実装: プラグインベースのクエリ実行
        
        条件分岐を削除し、プラグインに委譲します。
        """
        start_time = time.time()
        
        try:
            # キャッシュチェック
            cache_key = self._generate_cache_key(language, query_type, source_code)
            if cache_key in self.query_cache:
                self.performance_stats["cache_hits"] += 1
                return self.query_cache[cache_key]
            
            self.performance_stats["cache_misses"] += 1
            
            # プラグインの取得
            plugin = self.plugin_manager.get_plugin(language)
            if not plugin:
                raise ValueError(f"No plugin available for language: {language}")
            
            # プラグインによるクエリ実行
            results = plugin.execute_query(query_type, source_code)
            
            # キャッシュに保存
            self.query_cache[cache_key] = results
            
            # 統計更新
            self.performance_stats["queries_executed"] += 1
            self.performance_stats["total_time"] += time.time() - start_time
            
            return results
            
        except Exception as e:
            raise Exception(f"Query execution failed for {language}/{query_type}: {str(e)}")
    
    def _generate_cache_key(self, language: str, query_type: str, source_code: str) -> str:
        """キャッシュキーの生成"""
        import hashlib
        content = f"{language}:{query_type}:{source_code}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """パフォーマンス統計の取得"""
        stats = self.performance_stats.copy()
        if stats["queries_executed"] > 0:
            stats["avg_query_time"] = stats["total_time"] / stats["queries_executed"]
            stats["cache_hit_rate"] = stats["cache_hits"] / (stats["cache_hits"] + stats["cache_misses"])
        return stats
    
    def clear_cache(self):
        """キャッシュのクリア"""
        self.query_cache.clear()


class MigratedFormatter:
    """
    移行後のフォーマッター（プラグインベース）
    """
    
    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager
    
    def format_results(self, results: List[Dict[str, Any]], format_type: str, language: str) -> str:
        """
        新実装: プラグインベースのフォーマット
        
        条件分岐を削除し、プラグインのフォーマッターに委譲します。
        """
        try:
            # プラグインの取得
            plugin = self.plugin_manager.get_plugin(language)
            if not plugin:
                raise ValueError(f"No plugin available for language: {language}")
            
            # プラグインのフォーマッターを使用
            formatter = plugin.create_formatter(format_type)
            return formatter.format_results(results)
            
        except Exception as e:
            raise Exception(f"Formatting failed for {language}/{format_type}: {str(e)}")


# 移行プロセス管理
class MigrationManager:
    """
    移行プロセスを管理するクラス
    
    段階的な移行を実行し、後方互換性を保ちます。
    """
    
    def __init__(self):
        self.migration_phase = "legacy"  # legacy, transitional, migrated
        self.legacy_query_service = LegacyQueryService()
        self.legacy_formatter = LegacyFormatter()
        self.migrated_query_service = None
        self.migrated_formatter = None
        self.migration_log = []
    
    def initialize_migrated_services(self, plugin_manager):
        """移行後サービスの初期化"""
        self.migrated_query_service = MigratedQueryService(plugin_manager)
        self.migrated_formatter = MigratedFormatter(plugin_manager)
        self._log_migration_event("Migrated services initialized")
    
    def set_migration_phase(self, phase: str):
        """移行フェーズの設定"""
        valid_phases = ["legacy", "transitional", "migrated"]
        if phase not in valid_phases:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {valid_phases}")
        
        old_phase = self.migration_phase
        self.migration_phase = phase
        self._log_migration_event(f"Migration phase changed: {old_phase} -> {phase}")
    
    def execute_query(self, language: str, query_type: str, source_code: str) -> List[Dict[str, Any]]:
        """
        移行フェーズに応じたクエリ実行
        """
        if self.migration_phase == "legacy":
            return self._execute_legacy_query(language, query_type, source_code)
        
        elif self.migration_phase == "transitional":
            return self._execute_transitional_query(language, query_type, source_code)
        
        elif self.migration_phase == "migrated":
            return self._execute_migrated_query(language, query_type, source_code)
        
        else:
            raise ValueError(f"Unknown migration phase: {self.migration_phase}")
    
    def format_results(self, results: List[Dict[str, Any]], format_type: str, language: str) -> str:
        """
        移行フェーズに応じたフォーマット
        """
        if self.migration_phase == "legacy":
            return self._format_legacy_results(results, format_type, language)
        
        elif self.migration_phase == "transitional":
            return self._format_transitional_results(results, format_type, language)
        
        elif self.migration_phase == "migrated":
            return self._format_migrated_results(results, format_type, language)
        
        else:
            raise ValueError(f"Unknown migration phase: {self.migration_phase}")
    
    def _execute_legacy_query(self, language: str, query_type: str, source_code: str) -> List[Dict[str, Any]]:
        """レガシーシステムでのクエリ実行"""
        self._log_migration_event(f"Using legacy query service for {language}/{query_type}")
        return self.legacy_query_service.execute_query(language, query_type, source_code)
    
    def _execute_transitional_query(self, language: str, query_type: str, source_code: str) -> List[Dict[str, Any]]:
        """移行期間中のクエリ実行（フォールバック付き）"""
        try:
            # 新システムを試行
            if self.migrated_query_service:
                self._log_migration_event(f"Trying migrated query service for {language}/{query_type}")
                return self.migrated_query_service.execute_query(language, query_type, source_code)
            else:
                raise Exception("Migrated service not available")
        
        except Exception as e:
            # フォールバック
            self._log_migration_event(f"Falling back to legacy query service: {str(e)}")
            warnings.warn(
                f"Migrated query service failed, using legacy fallback: {str(e)}",
                UserWarning
            )
            return self.legacy_query_service.execute_query(language, query_type, source_code)
    
    def _execute_migrated_query(self, language: str, query_type: str, source_code: str) -> List[Dict[str, Any]]:
        """移行後システムでのクエリ実行"""
        if not self.migrated_query_service:
            raise Exception("Migrated query service not initialized")
        
        self._log_migration_event(f"Using migrated query service for {language}/{query_type}")
        return self.migrated_query_service.execute_query(language, query_type, source_code)
    
    def _format_legacy_results(self, results: List[Dict[str, Any]], format_type: str, language: str) -> str:
        """レガシーシステムでのフォーマット"""
        self._log_migration_event(f"Using legacy formatter for {language}/{format_type}")
        return self.legacy_formatter.format_results(results, format_type, language)
    
    def _format_transitional_results(self, results: List[Dict[str, Any]], format_type: str, language: str) -> str:
        """移行期間中のフォーマット（フォールバック付き）"""
        try:
            # 新システムを試行
            if self.migrated_formatter:
                self._log_migration_event(f"Trying migrated formatter for {language}/{format_type}")
                return self.migrated_formatter.format_results(results, format_type, language)
            else:
                raise Exception("Migrated formatter not available")
        
        except Exception as e:
            # フォールバック
            self._log_migration_event(f"Falling back to legacy formatter: {str(e)}")
            warnings.warn(
                f"Migrated formatter failed, using legacy fallback: {str(e)}",
                UserWarning
            )
            return self.legacy_formatter.format_results(results, format_type, language)
    
    def _format_migrated_results(self, results: List[Dict[str, Any]], format_type: str, language: str) -> str:
        """移行後システムでのフォーマット"""
        if not self.migrated_formatter:
            raise Exception("Migrated formatter not initialized")
        
        self._log_migration_event(f"Using migrated formatter for {language}/{format_type}")
        return self.migrated_formatter.format_results(results, format_type, language)
    
    def _log_migration_event(self, message: str):
        """移行イベントのログ"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "phase": self.migration_phase,
            "message": message
        }
        self.migration_log.append(log_entry)
    
    def get_migration_log(self) -> List[Dict[str, Any]]:
        """移行ログの取得"""
        return self.migration_log.copy()
    
    def generate_migration_report(self) -> str:
        """移行レポートの生成"""
        report_lines = [
            "# 移行レポート",
            f"現在のフェーズ: {self.migration_phase}",
            f"ログエントリ数: {len(self.migration_log)}",
            "",
            "## 移行ログ"
        ]
        
        for entry in self.migration_log[-10:]:  # 最新10件
            report_lines.append(f"- {entry['timestamp']} [{entry['phase']}] {entry['message']}")
        
        # パフォーマンス統計
        if self.migrated_query_service:
            stats = self.migrated_query_service.get_performance_stats()
            report_lines.extend([
                "",
                "## パフォーマンス統計",
                f"- 実行クエリ数: {stats.get('queries_executed', 0)}",
                f"- 平均実行時間: {stats.get('avg_query_time', 0):.3f}秒",
                f"- キャッシュヒット率: {stats.get('cache_hit_rate', 0):.2%}"
            ])
        
        return "\n".join(report_lines)


# 移行テストとデモンストレーション
class MigrationDemo:
    """
    移行プロセスのデモンストレーション
    """
    
    def __init__(self):
        self.migration_manager = MigrationManager()
    
    def run_migration_demo(self):
        """移行デモの実行"""
        print("🚀 移行プロセスデモンストレーション開始")
        print("=" * 60)
        
        # サンプルデータ
        sample_code = '''
def hello_world():
    print("Hello, World!")

class Calculator:
    def add(self, a, b):
        return a + b
        '''
        
        # Phase 1: レガシーシステム
        print("\n📍 Phase 1: レガシーシステム")
        self.migration_manager.set_migration_phase("legacy")
        
        try:
            results = self.migration_manager.execute_query("python", "functions", sample_code)
            formatted = self.migration_manager.format_results(results, "json", "python")
            print(f"✅ レガシー実行成功: {len(results)}件の結果")
        except Exception as e:
            print(f"❌ レガシー実行失敗: {str(e)}")
        
        # Phase 2: 移行期間（フォールバック付き）
        print("\n📍 Phase 2: 移行期間（フォールバック）")
        self.migration_manager.set_migration_phase("transitional")
        
        try:
            results = self.migration_manager.execute_query("python", "functions", sample_code)
            formatted = self.migration_manager.format_results(results, "json", "python")
            print(f"✅ 移行期間実行成功: {len(results)}件の結果")
        except Exception as e:
            print(f"❌ 移行期間実行失敗: {str(e)}")
        
        # Phase 3: 完全移行（プラグインシステム）
        print("\n📍 Phase 3: 完全移行（プラグインシステム）")
        
        # 模擬プラグインマネージャーの初期化
        mock_plugin_manager = self._create_mock_plugin_manager()
        self.migration_manager.initialize_migrated_services(mock_plugin_manager)
        self.migration_manager.set_migration_phase("migrated")
        
        try:
            results = self.migration_manager.execute_query("python", "functions", sample_code)
            formatted = self.migration_manager.format_results(results, "json", "python")
            print(f"✅ 移行後実行成功: {len(results)}件の結果")
        except Exception as e:
            print(f"❌ 移行後実行失敗: {str(e)}")
        
        # 移行レポートの表示
        print("\n📊 移行レポート")
        print("-" * 40)
        report = self.migration_manager.generate_migration_report()
        print(report)
        
        print("\n🎉 移行プロセスデモンストレーション完了")
    
    def _create_mock_plugin_manager(self):
        """模擬プラグインマネージャーの作成"""
        class MockPlugin:
            def execute_query(self, query_type: str, source_code: str) -> List[Dict[str, Any]]:
                return [{"name": "mock_function", "type": "function", "source": "migrated"}]
            
            def create_formatter(self, format_type: str):
                class MockFormatter:
                    def format_results(self, results: List[Dict[str, Any]]) -> str:
                        return json.dumps({"migrated": True, "results": results})
                return MockFormatter()
        
        class MockPluginManager:
            def get_plugin(self, language: str):
                return MockPlugin()
        
        return MockPluginManager()
    
    def run_performance_comparison(self):
        """パフォーマンス比較デモ"""
        print("\n⚡ パフォーマンス比較デモ")
        print("=" * 40)
        
        sample_code = "def test(): pass" * 100  # 大きなサンプル
        iterations = 10
        
        # レガシーシステムのパフォーマンス
        self.migration_manager.set_migration_phase("legacy")
        
        start_time = time.time()
        for _ in range(iterations):
            self.migration_manager.execute_query("python", "functions", sample_code)
        legacy_time = time.time() - start_time
        
        print(f"📊 レガシーシステム: {legacy_time:.3f}秒 ({iterations}回)")
        
        # 移行後システムのパフォーマンス
        mock_plugin_manager = self._create_mock_plugin_manager()
        self.migration_manager.initialize_migrated_services(mock_plugin_manager)
        self.migration_manager.set_migration_phase("migrated")
        
        start_time = time.time()
        for _ in range(iterations):
            self.migration_manager.execute_query("python", "functions", sample_code)
        migrated_time = time.time() - start_time
        
        print(f"📊 移行後システム: {migrated_time:.3f}秒 ({iterations}回)")
        
        # パフォーマンス改善率
        if legacy_time > 0:
            improvement = ((legacy_time - migrated_time) / legacy_time) * 100
            print(f"🚀 パフォーマンス改善: {improvement:.1f}%")
        
        # キャッシュ統計
        stats = self.migration_manager.migrated_query_service.get_performance_stats()
        print(f"💾 キャッシュヒット率: {stats.get('cache_hit_rate', 0):.2%}")


# 実行例
if __name__ == "__main__":
    print("🔄 Tree-sitter-analyzer 移行実装例")
    print("=" * 60)
    
    # 移行デモの実行
    demo = MigrationDemo()
    demo.run_migration_demo()
    
    # パフォーマンス比較
    demo.run_performance_comparison()
    
    print(f"\n{'='*60}")
    print("移行実装例の実行完了")
    print("\n💡 この例では以下の移行パターンを示しています:")
    print("   1. 条件分岐の削除とプラグインシステムへの移行")
    print("   2. 段階的移行プロセス（レガシー → 移行期間 → 完全移行）")
    print("   3. フォールバック機能による安全な移行")
    print("   4. パフォーマンス監視とキャッシュシステム")
    print("   5. 移行ログとレポート機能")