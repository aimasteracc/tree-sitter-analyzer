"""Pulse reverse-import context for TypeScript/JavaScript.

``imported_by`` was Python-only: no ``module:`` edge carried a resolved file
for other languages, and the module-name equality branch is gated on
``t.language = 'python'``. Python can match by absolute dotted name because a
target file yields exactly one module name; a TS specifier like ``./parser``
is importer-relative and cannot be derived from the target, so TS resolves the
specifier at index time and stores it in ``callee_resolved_file`` — the
language-neutral branch the query already has.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.api.pulse import query_pulse


def _index(cache, paths: list) -> None:
    for path in paths:
        cache.index_file(str(path))


@pytest.fixture
def ts_project(tmp_path):
    from tree_sitter_analyzer.ast_cache import ASTCache

    def build(files: dict[str, str]):
        for rel, body in files.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        cache = ASTCache(str(tmp_path))
        _index(cache, [tmp_path / rel for rel in files])
        return cache

    return build


class TestTypeScriptReverseImport:
    def test_named_import_is_reported(self, ts_project):
        cache = ts_project(
            {
                "src/parser.ts": "export function parse() {\n  return 1;\n}\n",
                "src/consumer.ts": "import { parse } from './parser';\nparse();\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/parser.ts", "parse")
            assert result is not None
            assert result.imported_by == ("src/consumer.ts",)
        finally:
            cache.close()

    def test_parent_directory_specifier_is_reported(self, ts_project):
        cache = ts_project(
            {
                "src/parser.ts": "export function parse() {\n  return 1;\n}\n",
                "src/deep/consumer.ts": "import { parse } from '../parser';\nparse();\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/parser.ts", "parse")
            assert result is not None
            assert result.imported_by == ("src/deep/consumer.ts",)
        finally:
            cache.close()

    def test_multiple_importers_are_all_reported(self, ts_project):
        cache = ts_project(
            {
                "src/parser.ts": "export function parse() {\n  return 1;\n}\n",
                "src/a.ts": "import { parse } from './parser';\nparse();\n",
                "src/b.ts": "import { parse } from './parser';\nparse();\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/parser.ts", "parse")
            assert result is not None
            assert result.imported_by == ("src/a.ts", "src/b.ts")
        finally:
            cache.close()

    def test_javascript_importer_of_typescript_target(self, ts_project):
        # JS/TS are one language family; a gradual-migration repo cross-imports.
        cache = ts_project(
            {
                "src/parser.ts": "export function parse() {\n  return 1;\n}\n",
                "src/consumer.js": "import { parse } from './parser';\nparse();\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/parser.ts", "parse")
            assert result is not None
            assert result.imported_by == ("src/consumer.js",)
        finally:
            cache.close()


class TestNoFalseEdges:
    def test_bare_package_specifier_does_not_bind_to_a_project_file(self, ts_project):
        # A project file named like a package must not be reported as imported
        # just because a bare specifier shares its name.
        cache = ts_project(
            {
                "src/react.ts": "export function parse() {\n  return 1;\n}\n",
                "src/consumer.ts": "import { parse } from 'react';\nparse();\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/react.ts", "parse")
            assert result is not None
            assert result.imported_by == ()
        finally:
            cache.close()

    def test_unrelated_importer_is_not_reported(self, ts_project):
        cache = ts_project(
            {
                "src/parser.ts": "export function parse() {\n  return 1;\n}\n",
                "src/other.ts": "export function other() {\n  return 2;\n}\n",
                "src/consumer.ts": "import { other } from './other';\nother();\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/parser.ts", "parse")
            assert result is not None
            assert result.imported_by == ()
        finally:
            cache.close()

    def test_target_own_outgoing_import_is_not_self_reported(self, ts_project):
        cache = ts_project(
            {
                "src/parser.ts": (
                    "import { helper } from './helper';\n"
                    "export function parse() {\n  return helper();\n}\n"
                ),
                "src/helper.ts": "export function helper() {\n  return 1;\n}\n",
            }
        )
        try:
            result = query_pulse(cache.get_conn(), "src/parser.ts", "parse")
            assert result is not None
            assert "src/parser.ts" not in result.imported_by
        finally:
            cache.close()


class TestPythonBehaviourUnchanged:
    def test_python_reverse_import_still_works(self, tmp_path):
        # Regression guard: the Python module-name branch must keep working.
        from tree_sitter_analyzer.ast_cache import ASTCache

        package = tmp_path / "pkg"
        package.mkdir()
        (package / "mod.py").write_text("def run():\n    pass\n", encoding="utf-8")
        (package / "consumer.py").write_text("from .mod import run\n", encoding="utf-8")
        cache = ASTCache(str(tmp_path))
        try:
            _index(cache, [package / "mod.py", package / "consumer.py"])
            result = query_pulse(cache.get_conn(), "pkg/mod.py", "run")
            assert result is not None
            assert result.imported_by == ("pkg/consumer.py",)
        finally:
            cache.close()
