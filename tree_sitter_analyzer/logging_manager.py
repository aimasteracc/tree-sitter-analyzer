#!/usr/bin/env python3
"""
統一ログ管理システム

ログ出力の重複問題を解決するためのLoggerManagerクラスを提供します。
シングルトンパターンによりロガーインスタンスを一意に管理し、
重複ハンドラーを防止します。
"""

import logging
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class LoggerManager:
    """
    統一されたロガー管理クラス
    
    シングルトンパターンでロガーインスタンスを管理し、
    重複ハンドラーを防止する。
    """
    
    _instance: Optional['LoggerManager'] = None
    _lock: threading.Lock = threading.Lock()
    _loggers: Dict[str, logging.Logger] = {}
    _handler_registry: Dict[str, List[str]] = {}
    _initialized: bool = False
    _file_log_message_shown: bool = False
    
    def __new__(cls) -> 'LoggerManager':
        """スレッドセーフなシングルトン実装"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """初期化（シングルトンのため一度のみ実行）"""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._loggers = {}
                    self._handler_registry = {}
                    self._initialized = True
    
    def get_logger(
        self, 
        name: str = "tree_sitter_analyzer", 
        level: int | str = logging.WARNING
    ) -> logging.Logger:
        """
        重複を防ぐロガー取得
        
        Args:
            name: ロガー名
            level: ログレベル
            
        Returns:
            設定済みロガーインスタンス
        """
        with self._lock:
            if name not in self._loggers:
                self._loggers[name] = self._create_logger(name, level)
            return self._loggers[name]
    
    def _create_logger(self, name: str, level: int | str) -> logging.Logger:
        """
        ロガー作成とハンドラー設定
        
        Args:
            name: ロガー名
            level: ログレベル
            
        Returns:
            設定済みロガーインスタンス
        """
        # レベル変換処理
        numeric_level = self._convert_level(level)
        
        # 環境変数からのレベル設定
        env_level = os.environ.get("LOG_LEVEL", "").upper()
        if env_level and env_level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            numeric_level = getattr(logging, env_level)
        
        logger = logging.getLogger(name)
        
        # 重複ハンドラーチェック
        if not self._has_required_handlers(logger, name):
            self._setup_handlers(logger, name, numeric_level)
        
        # ロガーレベル設定
        logger.setLevel(numeric_level)
        
        return logger
    
    def _convert_level(self, level: int | str) -> int:
        """ログレベル文字列を数値に変換"""
        if isinstance(level, str):
            level_upper = level.upper()
            level_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
            }
            return level_map.get(level_upper, logging.WARNING)
        return level
    
    def _has_required_handlers(self, logger: logging.Logger, name: str) -> bool:
        """
        必要なハンドラーが既に設定されているかチェック
        
        Args:
            logger: チェック対象ロガー
            name: ロガー名
            
        Returns:
            必要なハンドラーが設定済みの場合True
        """
        if name in self._handler_registry:
            # 既に管理されているロガーの場合は設定済みとみなす
            return True
        
        # 既存ハンドラーの有無をチェック
        has_stream_handler = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in logger.handlers
        )
        
        if has_stream_handler:
            # ハンドラー登録を記録
            handler_types = [type(h).__name__ for h in logger.handlers]
            self._handler_registry[name] = handler_types
            return True
        
        return False
    
    def _setup_handlers(self, logger: logging.Logger, name: str, level: int) -> None:
        """
        ロガーにハンドラーを設定
        
        Args:
            logger: 設定対象ロガー
            name: ロガー名
            level: ログレベル
        """
        # メインハンドラー（stderr）の追加
        if not self._has_stream_handler(logger):
            stream_handler = SafeStreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
        
        # ファイルログハンドラーの追加（環境変数で有効化）
        enable_file_log = (
            os.environ.get("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "").lower() == "true"
        )
        
        if enable_file_log and not self._has_file_handler(logger):
            file_handler = self._create_file_handler(level)
            if file_handler:
                logger.addHandler(file_handler)
        
        # ハンドラー登録を記録
        handler_types = [type(h).__name__ for h in logger.handlers]
        self._handler_registry[name] = handler_types
    
    def _has_stream_handler(self, logger: logging.Logger) -> bool:
        """StreamHandlerの存在チェック"""
        return any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in logger.handlers
        )
    
    def _has_file_handler(self, logger: logging.Logger) -> bool:
        """FileHandlerの存在チェック"""
        return any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    
    def _create_file_handler(self, level: int) -> Optional[logging.FileHandler]:
        """
        ファイルハンドラーの作成
        
        Args:
            level: ログレベル
            
        Returns:
            作成されたFileHandlerまたはNone
        """
        try:
            # ログディレクトリの決定
            log_dir = os.environ.get("TREE_SITTER_ANALYZER_LOG_DIR")
            if log_dir:
                log_path = Path(log_dir) / "tree_sitter_analyzer.log"
                Path(log_dir).mkdir(parents=True, exist_ok=True)
            else:
                temp_dir = tempfile.gettempdir()
                log_path = Path(temp_dir) / "tree_sitter_analyzer.log"
            
            # ファイルログレベルの決定
            file_log_level_str = os.environ.get(
                "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", ""
            ).upper()
            file_log_level = level  # デフォルトはメインレベル
            
            if file_log_level_str in ["DEBUG", "INFO", "WARNING", "ERROR"]:
                file_log_level = getattr(logging, file_log_level_str)
            
            # ファイルハンドラー作成
            file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(file_log_level)
            
            # ファイルパス情報を出力（1回のみ）
            if not LoggerManager._file_log_message_shown:
                LoggerManager._file_log_message_shown = True
                if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                    try:
                        sys.stderr.write(
                            f"[LoggerManager] File logging enabled: {log_path}\n"
                        )
                    except Exception:
                        pass
            
            return file_handler
            
        except Exception as e:
            # ファイルハンドラー作成に失敗してもメインの動作は継続
            if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                try:
                    sys.stderr.write(
                        f"[LoggerManager] File handler creation failed: {e}\n"
                    )
                except Exception:
                    pass
            return None
    
    def reset_for_testing(self) -> None:
        """
        テスト用リセット機能
        
        Note:
            本番環境では使用しないこと
        """
        with self._lock:
            # 全ハンドラーのクリーンアップ
            for logger in self._loggers.values():
                for handler in logger.handlers[:]:
                    try:
                        handler.close()
                        logger.removeHandler(handler)
                    except Exception:
                        pass
            
            self._loggers.clear()
            self._handler_registry.clear()
            LoggerManager._file_log_message_shown = False


class SafeStreamHandler(logging.StreamHandler):
    """
    安全なStreamHandler実装
    
    MCPプロトコルのstdio通信やテスト環境での
    ストリームクローズ問題に対応。
    """
    
    def __init__(self, stream=None):
        # デフォルトでstderrを使用（stdoutはMCP用に保持）
        super().__init__(stream if stream is not None else sys.stderr)
    
    def emit(self, record: Any) -> None:
        """
        レコードの安全な出力
        
        Args:
            record: ログレコード
        """
        try:
            # ストリームの状態チェック
            if hasattr(self.stream, "closed") and self.stream.closed:
                return
            
            if not hasattr(self.stream, "write"):
                return
            
            # pytest環境での特別処理
            stream_name = getattr(self.stream, "name", "")
            if stream_name is None or "pytest" in str(type(self.stream)).lower():
                try:
                    super().emit(record)
                    return
                except (ValueError, OSError, AttributeError, UnicodeError):
                    return
            
            # 通常のストリーム書き込み可能性チェック
            try:
                if hasattr(self.stream, "writable") and not self.stream.writable():
                    return
            except (ValueError, OSError, AttributeError, UnicodeError):
                return
            
            super().emit(record)
            
        except (ValueError, OSError, AttributeError, UnicodeError):
            # I/Oエラーは静かに無視（シャットダウン時やpytestキャプチャ時）
            pass
        except Exception:
            # その他の予期しないエラーも静かに無視
            pass


# グローバルインスタンス
_logger_manager = LoggerManager()


def get_logger_manager() -> LoggerManager:
    """
    LoggerManagerのグローバルインスタンス取得
    
    Returns:
        LoggerManagerインスタンス
    """
    return _logger_manager


def get_unified_logger(
    name: str = "tree_sitter_analyzer", 
    level: int | str = logging.WARNING
) -> logging.Logger:
    """
    統一されたロガー取得関数
    
    Args:
        name: ロガー名
        level: ログレベル
        
    Returns:
        設定済みロガーインスタンス
    """
    return _logger_manager.get_logger(name, level)