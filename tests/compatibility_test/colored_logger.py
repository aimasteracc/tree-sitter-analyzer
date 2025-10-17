#!/usr/bin/env python3
"""
色付きログシステム

coloramaライブラリを使用してエラーレベル別の色分けログ出力を提供します。
- ERROR: 赤色 - 重要なエラー
- WARNING: 黄色 - 警告
- INFO: 緑色 - 情報
- SUCCESS: 青色 - 成功
- DEBUG: マゼンタ - デバッグ情報
"""

import logging
import sys
from typing import Optional

try:
    from colorama import Fore, Back, Style, init
    # Windows環境でのANSIエスケープシーケンス対応
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # coloramaが利用できない場合のフォールバック
    class _DummyColor:
        RED = ""
        YELLOW = ""
        GREEN = ""
        BLUE = ""
        MAGENTA = ""
        CYAN = ""
        WHITE = ""
        RESET = ""
    
    Fore = _DummyColor()
    Style = _DummyColor()


class ColoredFormatter(logging.Formatter):
    """色付きログフォーマッター"""
    
    # ログレベル別の色設定
    COLORS = {
        'DEBUG': Fore.MAGENTA,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT if hasattr(Style, 'BRIGHT') else Fore.RED,
        'SUCCESS': Fore.BLUE,
    }
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        if fmt is None:
            fmt = '%(asctime)s - %(levelname)s - %(message)s'
        if datefmt is None:
            datefmt = '%Y-%m-%d %H:%M:%S'
        super().__init__(fmt, datefmt)
    
    def format(self, record: logging.LogRecord) -> str:
        # 元のフォーマット処理
        log_message = super().format(record)
        
        # coloramaが利用可能な場合のみ色付け
        if COLORAMA_AVAILABLE:
            # ログレベルに応じた色を取得
            color = self.COLORS.get(record.levelname, '')
            if color:
                # ログレベル部分のみを色付け
                colored_level = f"{color}{record.levelname}{Style.RESET_ALL}"
                log_message = log_message.replace(record.levelname, colored_level, 1)
        
        return log_message


class ColoredLogger:
    """色付きログ出力クラス"""
    
    def __init__(self, name: str = __name__, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # 既存のハンドラーをクリア
        self.logger.handlers.clear()
        
        # コンソールハンドラーを設定
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)
        
        # ファイルハンドラーを設定（色なし）
        file_handler = logging.FileHandler('compatibility_test.log', encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(file_handler)
        
        # 親ロガーへの伝播を無効化（重複出力を防ぐ）
        self.logger.propagate = False
    
    def debug(self, message: str) -> None:
        """デバッグメッセージ（マゼンタ）"""
        self.logger.debug(message)
    
    def info(self, message: str) -> None:
        """情報メッセージ（緑）"""
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """警告メッセージ（黄）"""
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """エラーメッセージ（赤）"""
        self.logger.error(message)
    
    def critical(self, message: str) -> None:
        """重要エラーメッセージ（明るい赤）"""
        self.logger.critical(message)
    
    def success(self, message: str) -> None:
        """成功メッセージ（青）"""
        # カスタムレベルとして SUCCESS を追加
        if not hasattr(logging, 'SUCCESS'):
            logging.addLevelName(25, 'SUCCESS')
        self.logger.log(25, message)
    
    def progress(self, message: str, current: int, total: int) -> None:
        """進捗表示（シアン）"""
        percentage = (current / total) * 100 if total > 0 else 0
        progress_bar = self._create_progress_bar(current, total)
        
        if COLORAMA_AVAILABLE:
            colored_message = f"{Fore.CYAN}[{current:3d}/{total:3d}] {progress_bar} {percentage:5.1f}% - {message}{Style.RESET_ALL}"
        else:
            colored_message = f"[{current:3d}/{total:3d}] {progress_bar} {percentage:5.1f}% - {message}"
        
        # 進捗は改行なしで出力
        print(f"\r{colored_message}", end='', flush=True)
    
    def progress_complete(self, message: str = "完了") -> None:
        """進捗完了"""
        if COLORAMA_AVAILABLE:
            print(f"\r{Fore.GREEN}[OK] {message}{Style.RESET_ALL}")
        else:
            print(f"\r[OK] {message}")
    
    def _create_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """プログレスバーを作成"""
        if total == 0:
            return "#" * width
        
        filled = int(width * current / total)
        bar = "#" * filled + "-" * (width - filled)
        return f"[{bar}]"
    
    def test_result(self, test_id: str, success: bool, message: str = "") -> None:
        """テスト結果の表示"""
        if success:
            if COLORAMA_AVAILABLE:
                status = f"{Fore.GREEN}[PASS]{Style.RESET_ALL}"
            else:
                status = "[PASS]"
        else:
            if COLORAMA_AVAILABLE:
                status = f"{Fore.RED}[FAIL]{Style.RESET_ALL}"
            else:
                status = "[FAIL]"
        
        result_message = f"{status} {test_id}"
        if message:
            result_message += f" - {message}"
        
        print(result_message)
    
    def section_header(self, title: str) -> None:
        """セクションヘッダーの表示"""
        separator = "=" * 60
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}{separator}")
            print(f"{title:^60}")
            print(f"{separator}{Style.RESET_ALL}\n")
        else:
            print(f"\n{separator}")
            print(f"{title:^60}")
            print(f"{separator}\n")
    
    def summary(self, total: int, success: int, failed: int) -> None:
        """テスト結果サマリーの表示"""
        success_rate = (success / total) * 100 if total > 0 else 0
        
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}{'=' * 60}")
            print(f"{'テスト結果サマリー':^60}")
            print(f"{'=' * 60}{Style.RESET_ALL}")
            
            print(f"総テスト数: {total}")
            print(f"{Fore.GREEN}成功: {success}{Style.RESET_ALL}")
            print(f"{Fore.RED}失敗: {failed}{Style.RESET_ALL}")
            
            if success_rate >= 90:
                color = Fore.GREEN
            elif success_rate >= 70:
                color = Fore.YELLOW
            else:
                color = Fore.RED
            
            print(f"成功率: {color}{success_rate:.1f}%{Style.RESET_ALL}")
        else:
            print(f"\n{'=' * 60}")
            print(f"{'テスト結果サマリー':^60}")
            print(f"{'=' * 60}")
            
            print(f"総テスト数: {total}")
            print(f"成功: {success}")
            print(f"失敗: {failed}")
            print(f"成功率: {success_rate:.1f}%")


def get_logger(name: str = __name__, level: int = logging.INFO) -> ColoredLogger:
    """色付きロガーのインスタンスを取得"""
    return ColoredLogger(name, level)


# デモ用関数
def demo_colored_logging():
    """色付きログのデモ"""
    logger = get_logger("demo", logging.DEBUG)
    
    logger.section_header("色付きログシステムのデモ")
    
    logger.debug("これはデバッグメッセージです")
    logger.info("これは情報メッセージです")
    logger.warning("これは警告メッセージです")
    logger.error("これはエラーメッセージです")
    logger.critical("これは重要エラーメッセージです")
    logger.success("これは成功メッセージです")
    
    # 進捗表示のデモ
    import time
    total_steps = 5
    for i in range(total_steps + 1):
        logger.progress(f"処理中... ステップ {i}", i, total_steps)
        time.sleep(0.5)
    logger.progress_complete("処理完了")
    
    # テスト結果のデモ
    logger.test_result("TEST-001", True, "基本機能テスト")
    logger.test_result("TEST-002", False, "エラーハンドリングテスト")
    logger.test_result("TEST-003", True, "パフォーマンステスト")
    
    # サマリーのデモ
    logger.summary(total=10, success=8, failed=2)


if __name__ == "__main__":
    demo_colored_logging()