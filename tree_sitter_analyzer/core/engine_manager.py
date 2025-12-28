#!/usr/bin/env python3
"""
Analysis Engine Singleton Management
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .analysis_engine import UnifiedAnalysisEngine


class EngineManager:
    """Manages UnifiedAnalysisEngine singleton instances"""

    _instances: dict[str, "UnifiedAnalysisEngine"] = {}
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(
        cls,
        engine_class: type["UnifiedAnalysisEngine"],
        project_root: str | None = None,
    ) -> "UnifiedAnalysisEngine":
        """Get or create singleton instance of the analysis engine"""
        instance_key = project_root or "default"

        if instance_key not in cls._instances:
            with cls._lock:
                if instance_key not in cls._instances:
                    instance = engine_class(project_root)
                    cls._instances[instance_key] = instance

        return cls._instances[instance_key]

    @classmethod
    def reset_instances(cls) -> None:
        """Reset all singleton instances (for testing)"""
        with cls._lock:
            cls._instances.clear()
