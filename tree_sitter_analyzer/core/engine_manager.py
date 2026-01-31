#!/usr/bin/env python3
"""
Analysis Engine Singleton Management.

This module provides singleton management for UnifiedAnalysisEngine instances,
delegating to UnifiedAnalysisEngine's internal instance management.

Key Features:
    - Singleton pattern delegation to UnifiedAnalysisEngine
    - Thread-safe instance retrieval
    - No duplicate instance dictionaries
    - Project root-scoped instances

Classes:
    EngineManager: Manages UnifiedAnalysisEngine singleton instances

Version: 1.10.5
Date: 2026-01-28
Author: tree-sitter-analyzer team
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .analysis_engine import UnifiedAnalysisEngine

__all__ = ["EngineManager"]


class EngineManager:
    """
    Manages UnifiedAnalysisEngine singleton instances.

    このクラスは UnifiedAnalysisEngine の __new__ パターンに委譲します。
    別々の _instances 辞書を持たず、UnifiedAnalysisEngine._instances を使用します。
    """

    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(
        cls,
        engine_class: type[UnifiedAnalysisEngine],
        project_root: str | None = None,
    ) -> UnifiedAnalysisEngine:
        """
        Get or create singleton instance of the analysis engine.

        UnifiedAnalysisEngine の __new__ に委譲してインスタンスを取得します。
        """
        # UnifiedAnalysisEngine の __new__ が既にシングルトンロジックを実装しているため、
        # 単純にインスタンス化を呼び出すだけで良い
        return engine_class(project_root)

    @classmethod
    def reset_instances(cls) -> None:
        """
        Reset all singleton instances (for testing).

        UnifiedAnalysisEngine._instances をクリアします。
        """
        # 循環インポートを避けるためにここでインポート
        from .analysis_engine import UnifiedAnalysisEngine

        with cls._lock:
            # UnifiedAnalysisEngine の内部ロックも取得して安全にクリア
            with UnifiedAnalysisEngine._lock:
                UnifiedAnalysisEngine._instances.clear()
