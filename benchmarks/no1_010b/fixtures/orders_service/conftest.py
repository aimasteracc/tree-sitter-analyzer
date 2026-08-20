"""Anchor the fixture root on ``sys.path`` so ``src`` imports resolve.

Collecting a root ``conftest.py`` makes pytest prepend this directory, which
is what lets both the suite and the NO1-010B oracles import ``src.*`` with the
worktree root as cwd.
"""
