"""#1764：ES 模块导出表、项目包说明符与 ``.js`` -> ``.ts`` 说明符的纯函数单元。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.synapse_resolver._es_export_table import parse_export_table
from tree_sitter_analyzer.synapse_resolver._es_module_binding import (
    ABSENT,
    UNKNOWN,
    Definition,
    EsModuleBinder,
    Namespace,
)
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry
from tree_sitter_analyzer.synapse_resolver._javascript_object_exports import (
    ObjectExportResolver,
)
from tree_sitter_analyzer.synapse_resolver._package_specifiers import (
    PackageSpecifiers,
    split_package_specifier,
)
from tree_sitter_analyzer.synapse_resolver._typescript_imports import (
    parse_typescript_imports,
    resolve_typescript_specifier,
)


def test_export_table_reads_every_reexport_form() -> None:
    table = parse_export_table(
        "export * from './a.js';\n"
        "export type * from './types';\n"
        "export * as core from '../core/index.js';\n"
        "export { f, g as h } from './x';\n"
        "export {\n  type T,\n  default as d,\n} from './y';\n"
        "export { local as named, other };\n"
        "export async function run() {}\n"
        "export const k = 1;\n"
        "export default function main() {}\n"
        "// export function commented() {}\n"
    )
    assert table.complete is True
    assert table.stars == ("./a.js", "./types")
    assert table.reexports == {
        "core": ("../core/index.js", "*"),
        "f": ("./x", "f"),
        "h": ("./x", "g"),
        "T": ("./y", "T"),
        "d": ("./y", "default"),
    }
    assert table.local == {
        "named": "local",
        "other": "other",
        "run": "run",
        "k": "k",
        "default": "main",
    }


@pytest.mark.parametrize(
    "source",
    [
        "export = foo;\n",
        "export const { a, b } = obj;\n",
        "export const a = 1, b = 2;\n",
        "export { 'a-b' as c } from './x';\n",
        "export * as 'ns' from './x';\n",
        "module.exports = { f };\n",
        "exports.f = f;\n",
        "export as namespace Lib;\n",
    ],
)
def test_export_table_is_incomplete_when_names_are_unknowable(source: str) -> None:
    assert parse_export_table(source).complete is False


@pytest.mark.parametrize(
    ("source", "ident"),
    [
        ("export default foo;\n", "foo"),
        ("export default class Widget {}\n", "Widget"),
        ("export default async function () {}\n", ""),
        ("export default { a: 1 };\n", ""),
        ("export { x as default };\n", "x"),
    ],
)
def test_default_export_local_identifier(source: str, ident: str) -> None:
    assert parse_export_table(source).local["default"] == ident


def test_generic_commas_are_not_extra_declarators() -> None:
    table = parse_export_table("export const m = new Map<string, number>();\n")
    assert table.complete is True and table.local == {"m": "m"}


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("./errors.js", "src/errors.ts"),
        ("./view.jsx", "src/view.tsx"),
        ("./mod.mjs", "src/mod.mts"),
        ("./real.js", "src/real.js"),
        ("./missing.js", ""),
    ],
)
def test_emitted_extension_names_the_typescript_source(
    spec: str, expected: str
) -> None:
    indexed = {
        "src/errors.ts",
        "src/view.tsx",
        "src/mod.mts",
        "src/real.js",
        "src/real.ts",
    }
    assert resolve_typescript_specifier(spec, "src/use.ts", indexed) == expected


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("zod", ("zod", ".")),
        ("zod/v4", ("zod", "./v4")),
        ("@scope/pkg/a/b", ("@scope/pkg", "./a/b")),
        ("./rel", None),
        ("node:fs", None),
        ("@scope", None),
    ],
)
def test_split_package_specifier(spec: str, expected: Any) -> None:
    assert split_package_specifier(spec) == expected


def _package(root: Path, rel: str, data: Any) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, "utf-8")


def test_project_package_specifiers(tmp_path: Path) -> None:
    _package(
        tmp_path,
        "packages/zod/package.json",
        {
            "name": "zod",
            "exports": {
                ".": {"@zod/source": "./src/index.ts", "import": "./index.js"},
                "./v4": {"@zod/source": "./src/v4/index.ts", "types": "./v4/a.d.cts"},
                "./locales/*": "./src/locales/*.ts",
                "./both": ["./src/a.ts", "./src/b.ts"],
            },
        },
    )
    _package(
        tmp_path,
        "packages/plain/package.json",
        {"name": "plain", "exports": "./src/i.ts"},
    )
    _package(
        tmp_path, "packages/nox/package.json", {"name": "nox", "main": "./src/i.ts"}
    )
    _package(
        tmp_path, "packages/dup1/package.json", {"name": "dup", "exports": "./x.ts"}
    )
    _package(
        tmp_path, "packages/dup2/package.json", {"name": "dup", "exports": "./x.ts"}
    )
    _package(tmp_path, "packages/bad/package.json", "{not json")
    indexed = {
        "packages/zod/src/index.ts",
        "packages/zod/src/v4/index.ts",
        "packages/zod/src/locales/en.ts",
        "packages/zod/src/a.ts",
        "packages/zod/src/b.ts",
        "packages/zod/src/v4/test/a.test.ts",
        "packages/plain/src/i.ts",
        "packages/nox/src/i.ts",
        "packages/dup1/x.ts",
        "packages/dup2/x.ts",
        "packages/bad/x.ts",
    }
    specs = PackageSpecifiers(str(tmp_path), indexed)
    assert specs.resolve("zod") == "packages/zod/src/index.ts"
    assert specs.resolve("zod/v4") == "packages/zod/src/v4/index.ts"
    assert specs.resolve("zod/locales/en") == "packages/zod/src/locales/en.ts"
    assert specs.resolve("plain") == "packages/plain/src/i.ts"
    for unresolved in (
        "zod/both",
        "zod/nope",
        "nox",
        "dup",
        "react",
        "plain/sub",
        "./x",
    ):
        assert specs.resolve(unresolved) == "", unresolved
    assert PackageSpecifiers(None, indexed).resolve("zod") == ""


# ---------------------------------------------------------------- the binder
def _binder(
    root: Path, files: dict[str, str], symbols: dict[str, Any]
) -> EsModuleBinder:
    imports: dict[str, list[ImportEntry]] = {}
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.startswith("import "):
                imports.setdefault(rel, []).extend(
                    parse_typescript_imports(line, "typescript", rel, line_no)
                )
    indexed = frozenset(files)
    objects = ObjectExportResolver(
        project_root=str(root),
        imports_by_file=imports,
        indexed_files=indexed,
        file_symbols=symbols,
    )
    return EsModuleBinder(
        project_root=str(root),
        imports_by_file=imports,
        indexed_files=indexed,
        file_symbols=symbols,
        variables={},
        object_exports=objects,
    )


def test_export_star_cycles_terminate_and_do_not_poison_the_memo(
    tmp_path: Path,
) -> None:
    files = {
        "a.ts": "export * from './b';\nexport * from './c';\n",
        "b.ts": "export * from './a';\n",
        "c.ts": "export function x() {}\n",
    }
    binder = _binder(tmp_path, files, {"c.ts": [("x", "function", 7)]})
    assert binder.find("a.ts", "x", 0) == Definition(7, "c.ts", "x")
    # b re-exports a, which re-exports c: the cycle entry must not memoise ABSENT.
    assert binder.find("b.ts", "x", 0) == Definition(7, "c.ts", "x")
    assert binder.find("a.ts", "nope", 0) == ABSENT


def test_unreadable_or_unresolvable_sources_are_unknown(tmp_path: Path) -> None:
    files = {
        "a.ts": "export * from './gone';\n",
        "b.ts": "export { f } from 'pkg';\n",
        "c.ts": "export * as ns from './gone';\n",
    }
    binder = _binder(tmp_path, files, {})
    assert binder.find("a.ts", "f", 0) == UNKNOWN
    assert binder.find("b.ts", "f", 0) == UNKNOWN
    assert binder.find("c.ts", "ns", 0) == UNKNOWN
    assert binder.find("missing.ts", "f", 0) == UNKNOWN
    # ``export *`` never forwards a default export, whatever its source.
    assert binder.find("a.ts", "default", 0) == ABSENT


def test_namespace_and_default_bindings(tmp_path: Path) -> None:
    files = {
        "m.ts": "export function f() {}\nexport default function g() {}\n",
        "ns.ts": "import * as inner from './m';\nexport { inner };\n",
        "use.ts": (
            "import * as m from './m';\n"
            "import g, { f as ff } from './m';\n"
            "import { inner } from './ns';\n"
        ),
    }
    symbols = {"m.ts": [("f", "function", 1), ("g", "function", 2)]}
    binder = _binder(tmp_path, files, symbols)
    assert binder.find("ns.ts", "inner", 0) == Namespace("m.ts")
    assert binder.bind("m", "f", "use.ts") == (1, "m.ts", None)
    assert binder.bind("inner", "f", "use.ts") == (1, "m.ts", None)
    assert binder.bind("", "g", "use.ts") == (2, "m.ts", None)
    assert binder.bind("", "ff", "use.ts") == (
        1,
        "m.ts",
        {"local": "ff", "name": "f", "line": 2},
    )
    assert binder.bind("", "m", "use.ts") is None  # a namespace is not callable
    assert binder.bind("this", "f", "use.ts") is None
    assert binder.bind("m.x-y", "f", "use.ts") is None
    assert binder.bind("", "1bad", "use.ts") is None
