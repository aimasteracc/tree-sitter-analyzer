"""
Project Index Package — Persistent cross-session codebase memory.

Stores a lightweight snapshot of project structure to disk so Claude can
instantly recall architecture on the next session without re-scanning.

Public API re-exported from sub-modules:
  ProjectIndex          — dataclass snapshot
  ProjectIndexManager   — build / load / save / render helpers
"""

from __future__ import annotations

from ._manager import ProjectIndexManager
from ._models import ProjectIndex

__all__ = [
    "ProjectIndex",
    "ProjectIndexManager",
]
