"""Bundled tsa-* skills shipped inside the wheel for PyPI / uvx installs.

Use ``tree-sitter-analyzer --install-skills [target]`` (or
``--install-skills-global``) to copy these skills into a project's
``.claude/skills/`` directory so Claude Code auto-discovers them.

Git-clone users already have the skills under ``.claude/skills/`` and
do NOT need ``--install-skills``.
"""

import os as _os

#: Absolute path to this directory (works in editable installs and wheels).
SKILLS_DIR = _os.path.dirname(_os.path.abspath(__file__))
