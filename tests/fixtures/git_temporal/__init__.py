"""Git temporal-activation test fixtures.

Helpers for spinning up disposable git repositories with seeded commits,
used by tests under ``tests/unit/test_temporal_activation.py`` and
``tests/unit/test_temporal_change_impact.py``.

Tests must NOT depend on the host machine's global git config.
"""

from .make_repo import Commit, make_repo

__all__ = ["Commit", "make_repo"]
