"""Auto-discovered language resolver modules (RFC-0010).

Every non-underscore module here is imported once at package load so it can call
``register_language(...)``. Adding a language is therefore NEW-FILES-ONLY — drop
``languages/<lang>.py`` (+ its constants + tests); no existing file is edited, so
any number of language PRs land without merge conflicts or worktree races.
"""

from __future__ import annotations

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    if not _module.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module.name}")
