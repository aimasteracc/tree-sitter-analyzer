#!/usr/bin/env python3
"""
設定管理クラス

互換性テストシステムの設定を一元管理します。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    """設定管理クラス"""
    
    def __init__(self, config_file: str = "config.json"):
        """
        初期化
        
        Args:
            config_file: 設定ファイルのパス
        """
        self.config_file = Path(__file__).parent / config_file
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """設定ファイルを読み込み"""
        try:
            if not self.config_file.exists():
                logger.warning(f"設定ファイルが見つかりません: {self.config_file}")
                return self._get_default_config()
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info(f"設定ファイルを読み込みました: {self.config_file}")
            return config
            
        except Exception as e:
            logger.error(f"設定ファイルの読み込みに失敗: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """デフォルト設定を取得"""
        return {
            "test_settings": {
                "timeout": 30,
                "max_retries": 3,
                "log_level": "INFO",
                "output_formats": ["json", "html"],
                "enable_performance_logging": True
            },
            "mcp_settings": {
                "project_root_auto_detect": True,
                "normalize_paths": True,
                "handle_total_only_results": True,
                "error_handling": {
                    "continue_on_error": True,
                    "log_errors": True,
                    "save_error_details": True
                }
            },
            "cli_settings": {
                "resolve_relative_paths": True,
                "normalize_output": True,
                "parse_json_output": True,
                "encoding": "utf-8"
            },
            "comparison_settings": {
                "tolerance": 0.001,
                "ignore_timestamps": True,
                "ignore_execution_times": True,
                "normalize_file_paths": True
            },
            "report_settings": {
                "generate_html": True,
                "generate_json": True,
                "include_winmerge_files": True,
                "compatibility_thresholds": {
                    "excellent": 0.95,
                    "good": 0.90,
                    "acceptable": 0.80,
                    "poor": 0.70
                }
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """設定値を取得"""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_test_settings(self) -> Dict[str, Any]:
        """テスト設定を取得"""
        return self.get("test_settings", {})
    
    def get_mcp_settings(self) -> Dict[str, Any]:
        """MCP設定を取得"""
        return self.get("mcp_settings", {})
    
    def get_cli_settings(self) -> Dict[str, Any]:
        """CLI設定を取得"""
        return self.get("cli_settings", {})
    
    def get_comparison_settings(self) -> Dict[str, Any]:
        """比較設定を取得"""
        return self.get("comparison_settings", {})
    
    def get_report_settings(self) -> Dict[str, Any]:
        """レポート設定を取得"""
        return self.get("report_settings", {})
    
    def get_timeout(self) -> int:
        """タイムアウト値を取得"""
        return self.get("test_settings.timeout", 30)
    
    def get_log_level(self) -> str:
        """ログレベルを取得"""
        return self.get("test_settings.log_level", "INFO")
    
    def get_compatibility_threshold(self, level: str) -> float:
        """互換性閾値を取得"""
        return self.get(f"report_settings.compatibility_thresholds.{level}", 0.8)
    
    def is_performance_logging_enabled(self) -> bool:
        """パフォーマンスログが有効かチェック"""
        return self.get("test_settings.enable_performance_logging", True)
    
    def should_continue_on_error(self) -> bool:
        """エラー時に継続するかチェック"""
        return self.get("mcp_settings.error_handling.continue_on_error", True)
    
    def should_normalize_paths(self) -> bool:
        """パス正規化が有効かチェック"""
        return self.get("mcp_settings.normalize_paths", True)
    
    def should_resolve_relative_paths(self) -> bool:
        """相対パス解決が有効かチェック"""
        return self.get("cli_settings.resolve_relative_paths", True)
    
    def should_generate_html_report(self) -> bool:
        """HTMLレポート生成が有効かチェック"""
        return self.get("report_settings.generate_html", True)
    
    def should_generate_json_report(self) -> bool:
        """JSONレポート生成が有効かチェック"""
        return self.get("report_settings.generate_json", True)
    
    def update_config(self, key: str, value: Any) -> None:
        """設定値を更新"""
        keys = key.split('.')
        config = self._config
        
        # 最後のキー以外をたどる
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 最後のキーに値を設定
        config[keys[-1]] = value
    
    def save_config(self) -> None:
        """設定ファイルに保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.info(f"設定ファイルを保存しました: {self.config_file}")
        except Exception as e:
            logger.error(f"設定ファイルの保存に失敗: {e}")

# グローバル設定インスタンス
config = ConfigManager()