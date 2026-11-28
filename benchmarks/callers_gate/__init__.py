"""Callers verification gate: replay the callers corpus, base vs head, and judge the diff.

See ``docs/dev/callers-gate.md``. Entry point: ``py -3 -m benchmarks.callers_gate``.
The CLI itself is stdlib-only; everything that needs ``tree_sitter`` or the
analyzer runs in a subprocess under the configured gate interpreter.
"""
