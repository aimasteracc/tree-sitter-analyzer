"""Adversarial probes of the grep oracle: every real unlisted caller must stay residual.

Each fixture is a repro from the gate review: a hit that is a real call the
answer does not list must never be classified as a proof (``caller``,
``import_export``, ``other_symbol``, ...).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate.oracle_grep import Item, Repo, check_item, site_covered

pytest.importorskip("tree_sitter_java")
pytest.importorskip("tree_sitter_typescript")
pytestmark = pytest.mark.slow_ok  # real git repos + git grep subprocesses


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    subprocess.run(
        ["git", "-C", str(root), "init", "-q"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(root), "add", "."], check=True, capture_output=True
    )
    return root


def _hits(
    root: Path, name: str, file: str, qual: str, callers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    item = Item(
        key=["bare", file, qual], name=name, file=file, qual=qual, callers=callers
    )
    hits = check_item(Repo(root), item)["hits"]
    assert isinstance(hits, list)
    return hits


def _classes_at(hits: list[dict[str, Any]], file: str, line: int) -> list[str]:
    return [h["class"] for h in hits if h["file"] == file and h["line"] == line]


TS_FUNC = {
    "package.json": json.dumps({"name": "demo"}),
    "src/t.ts": "export function target(x?: number) { return 1; }\n",
    "src/sameline.ts": (
        "import { target } from './t';\n"
        "export const a = () => target(); export const b = () => target();\n"
    ),
    "src/nested.ts": (
        "import { target } from './t';\n"
        "export function outer() {\n"
        "  target();\n"
        "  function inner() {\n"
        "    return target();\n"
        "  }\n"
        "  return inner;\n"
        "}\n"
    ),
    "tsconfig.json": json.dumps(
        {"compilerOptions": {"baseUrl": "src", "paths": {"lib/*": ["*"]}}}
    ),
    "src/alias.ts": "import { target } from 'lib/t';\nexport function viaAlias() { return target(); }\n",
    "src/baseurl.ts": "import { target } from 't';\nexport function viaBaseUrl() { return target(); }\n",
    "src/tpl.ts": "import { target } from './t';\nexport function tpl() { return `${target()}`; }\n",
    "src/deco.ts": "import { target } from './t';\nexport class D { @target() m() {} }\n",
}
TS_FUNC_CALLERS = [
    {"file": "src/sameline.ts", "name": "a", "line": 2},
    {"file": "src/nested.ts", "name": "outer", "line": 2},
]


def test_two_arrows_on_one_line_each_need_their_own_caller(tmp_path: Path) -> None:
    hits = _hits(
        _git_repo(tmp_path, TS_FUNC), "target", "src/t.ts", "target", TS_FUNC_CALLERS
    )
    assert _classes_at(hits, "src/sameline.ts", 2) == ["caller", "residual"]


def test_a_nested_function_inside_a_listed_caller_is_not_covered(
    tmp_path: Path,
) -> None:
    hits = _hits(
        _git_repo(tmp_path, TS_FUNC), "target", "src/t.ts", "target", TS_FUNC_CALLERS
    )
    assert _classes_at(hits, "src/nested.ts", 3) == ["caller"]
    assert _classes_at(hits, "src/nested.ts", 5) == ["residual"]


def test_the_answers_own_end_line_is_not_trusted(tmp_path: Path) -> None:
    wide = [{"file": "src/nested.ts", "name": "outer", "line": 2, "end_line": 99}]
    hits = _hits(_git_repo(tmp_path, TS_FUNC), "target", "src/t.ts", "target", wide)
    assert _classes_at(hits, "src/nested.ts", 5) == ["residual"]


@pytest.mark.parametrize(
    "file", ["src/alias.ts", "src/baseurl.ts", "src/tpl.ts", "src/deco.ts"]
)
def test_tsconfig_path_aliases_templates_and_decorators_stay_residual(
    tmp_path: Path, file: str
) -> None:
    hits = _hits(
        _git_repo(tmp_path, TS_FUNC), "target", "src/t.ts", "target", TS_FUNC_CALLERS
    )
    assert _classes_at(hits, file, 2) == ["residual"]


def test_a_bare_import_is_external_only_when_it_is_a_declared_dependency(
    tmp_path: Path,
) -> None:
    files = {
        "package.json": json.dumps({"name": "demo", "dependencies": {"left-pad": "1"}}),
        "src/t.ts": "export function target() { return 1; }\n",
        "src/dep.ts": "import { target } from 'left-pad';\nexport function d() { return target(); }\n",
        "src/undeclared.ts": "import { target } from 'mystery';\nexport function u() { return target(); }\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "target", "src/t.ts", "target", [])
    assert _classes_at(hits, "src/dep.ts", 2) == ["other_symbol"]
    assert _classes_at(hits, "src/undeclared.ts", 2) == ["residual"]


def test_a_dependency_also_matched_by_tsconfig_paths_is_not_external(
    tmp_path: Path,
) -> None:
    files = {
        "package.json": json.dumps({"name": "demo", "dependencies": {"left-pad": "1"}}),
        "tsconfig.json": '{\n  // JSONC comment\n  "compilerOptions": {"paths": {"left-pad": ["./src/t.ts"]},},\n}\n',
        "src/t.ts": "export function target() { return 1; }\n",
        "src/dep.ts": "import { target } from 'left-pad';\nexport function d() { return target(); }\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "target", "src/t.ts", "target", [])
    assert _classes_at(hits, "src/dep.ts", 2) == ["residual"]


def test_an_unreadable_tsconfig_makes_no_import_external(tmp_path: Path) -> None:
    files = {
        "package.json": json.dumps({"name": "demo", "dependencies": {"left-pad": "1"}}),
        "tsconfig.json": "{ not json",
        "src/t.ts": "export function target() { return 1; }\n",
        "src/dep.ts": "import { target } from 'left-pad';\nexport function d() { return target(); }\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "target", "src/t.ts", "target", [])
    assert _classes_at(hits, "src/dep.ts", 2) == ["residual"]


TS_ALIAS = {
    "package.json": json.dumps({"name": "demo"}),
    "src/t.ts": "export function target() { return 1; }\nexport default target;\n",
    "src/alias.ts": "import { target as go } from './t';\nexport function viaAlias() { return go(); }\n",
    "src/dflt.ts": "import whatever from './t';\nexport function viaDefault() { return whatever(); }\n",
    "src/barrel.ts": "export { target as start } from './t';\n",
    "src/rex.ts": "import { start } from './barrel';\nexport function viaReexport() { return start(); }\n",
    "src/decl.ts": "export default function target() { return 2; }\n",
    "src/plain.ts": "import { target } from './t';\nexport function p() { return target(); }\n",
}


def test_aliased_imports_re_export_aliases_and_default_exports_are_residual(
    tmp_path: Path,
) -> None:
    root = _git_repo(tmp_path, TS_ALIAS)
    hits = _hits(root, "target", "src/t.ts", "target", [])
    assert _classes_at(hits, "src/alias.ts", 1) == ["residual"]
    assert _classes_at(hits, "src/barrel.ts", 1) == ["residual"]
    assert _classes_at(hits, "src/t.ts", 2) == ["residual"]
    # an un-aliased import is a binding, the call is a separate hit
    assert _classes_at(hits, "src/plain.ts", 1) == ["import_export"]
    assert _classes_at(hits, "src/plain.ts", 2) == ["residual"]


def test_a_default_exported_declaration_is_residual(tmp_path: Path) -> None:
    root = _git_repo(tmp_path, TS_ALIAS)
    hits = _hits(root, "target", "src/decl.ts", "target", [])
    assert _classes_at(hits, "src/decl.ts", 1) == ["residual"]


def test_an_aliased_import_whose_every_local_use_is_a_listed_caller_is_proven(
    tmp_path: Path,
) -> None:
    root = _git_repo(tmp_path, TS_ALIAS)
    listed = [{"file": "src/alias.ts", "name": "viaAlias", "line": 2}]
    hits = _hits(root, "target", "src/t.ts", "target", listed)
    assert _classes_at(hits, "src/alias.ts", 1) == ["import_export"]


TS_CLASS = {
    "package.json": json.dumps({"name": "demo"}),
    "src/a.ts": "export class A {\n  static m() { return 1; }\n  inst() { return 2; }\n}\n",
    "src/b.ts": "export class B {\n  static m() { return 3; }\n}\n",
    "src/c.ts": "export class C {}\n",
    "src/use_alias.ts": "import { A as B } from './a';\nexport function useAlias() { return B.m(); }\n",
    "src/use_shadow.ts": "import { A } from './a';\nexport function useShadow() { const C = A; return C.m(); }\n",
    "src/use_b.ts": "import { B } from './b';\nexport function useB() { return B.m(); }\n",
    "src/sub.ts": "import { A } from './a';\nexport class S extends A {\n  static m() { return super.m(); }\n}\n",
}


@pytest.mark.parametrize(
    "file,line", [("src/use_alias.ts", 2), ("src/use_shadow.ts", 2), ("src/sub.ts", 3)]
)
def test_an_uppercase_receiver_not_bound_to_its_class_is_residual(
    tmp_path: Path, file: str, line: int
) -> None:
    hits = _hits(_git_repo(tmp_path, TS_CLASS), "m", "src/a.ts", "A.m", [])
    assert "residual" in _classes_at(hits, file, line)
    assert set(_classes_at(hits, file, line)) <= {"residual", "declaration"}


def test_a_receiver_bound_by_a_plain_import_of_an_unrelated_class_is_proven(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, TS_CLASS), "m", "src/a.ts", "A.m", [])
    assert _classes_at(hits, "src/use_b.ts", 2) == ["other_symbol"]


TS_SUPER = {
    "package.json": json.dumps({"name": "demo"}),
    "src/a.ts": "export class A {\n  m() { return 1; }\n}\n",
    "src/base.ts": "export class Base {\n  n() { return 2; }\n}\n",
    "src/x.ts": "import { A as Base } from './a';\nexport class X extends Base {\n  k() { return this.m(); }\n}\n",
    "src/barrel.ts": "export { A as Base2 } from './a';\n",
    "src/base2.ts": "export class Base2 {}\n",
    "src/y.ts": "import { Base2 } from './barrel';\nexport class Y extends Base2 {\n  k() { return this.m(); }\n}\n",
    "src/z.ts": "import { Base } from './base';\nexport class Z extends Base {\n  k() { return this.m(); }\n}\n",
}


@pytest.mark.parametrize("file", ["src/x.ts", "src/y.ts"])
def test_a_supertype_bound_by_an_alias_or_aliased_re_export_is_unresolved(
    tmp_path: Path, file: str
) -> None:
    hits = _hits(_git_repo(tmp_path, TS_SUPER), "m", "src/a.ts", "A.m", [])
    assert _classes_at(hits, file, 3) == ["residual"]


def test_a_supertype_imported_from_its_own_module_still_resolves(
    tmp_path: Path,
) -> None:
    hits = _hits(_git_repo(tmp_path, TS_SUPER), "m", "src/a.ts", "A.m", [])
    assert _classes_at(hits, "src/z.ts", 3) == ["other_symbol"]


JAVA = {
    "src/p/Base.java": "package p;\npublic class Base {\n  public void m() {}\n}\n",
    "src/p/Foo.java": (
        "package p;\npublic interface Foo {\n  void m();\n"
        "  default void run() { m(); this.m(); }\n}\n"
    ),
    "src/p/S.java": "package p;\npublic class S extends Base implements Foo {}\n",
    "src/p/Outer.java": (
        "package p;\n"
        "public class Outer {\n"
        "  void listed(Base b) {\n"
        "    b.m();\n"
        "    Runnable r = new Runnable() {\n"
        "      public void run() { b.m(); }\n"
        "    };\n"
        "  }\n"
        "}\n"
    ),
}


def test_java_dispatch_through_an_interface_or_common_subtype_is_residual(
    tmp_path: Path,
) -> None:
    hits = _hits(
        _git_repo(tmp_path, JAVA),
        "m",
        "src/p/Base.java",
        "Base.m",
        [{"file": "src/p/Outer.java", "name": "listed", "line": 3, "end_line": 8}],
    )
    assert _classes_at(hits, "src/p/Foo.java", 4) == ["residual", "residual"]


def test_java_anonymous_class_method_inside_a_listed_caller_is_not_covered(
    tmp_path: Path,
) -> None:
    hits = _hits(
        _git_repo(tmp_path, JAVA),
        "m",
        "src/p/Base.java",
        "Base.m",
        [{"file": "src/p/Outer.java", "name": "listed", "line": 3, "end_line": 8}],
    )
    assert _classes_at(hits, "src/p/Outer.java", 4) == ["caller"]
    assert _classes_at(hits, "src/p/Outer.java", 6) == ["residual"]


def test_an_interface_is_always_related_and_plain_classes_stay_unrelated(
    tmp_path: Path,
) -> None:
    files = {
        "src/p/Base.java": "package p;\npublic class Base {\n  public void m() {}\n}\n",
        "src/p/Plain.java": "package p;\npublic class Plain {\n  void go() { this.m(); }\n  void m() {}\n}\n",
        "src/p/Lone.java": "package p;\npublic interface Lone {\n  void m();\n  default void go() { this.m(); }\n}\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "m", "src/p/Base.java", "Base.m", [])
    assert _classes_at(hits, "src/p/Plain.java", 3) == ["other_symbol"]
    assert _classes_at(hits, "src/p/Lone.java", 4) == ["residual"]


def test_a_common_subtype_relates_two_otherwise_unrelated_classes(
    tmp_path: Path,
) -> None:
    files = {
        "package.json": json.dumps({"name": "demo"}),
        "src/base.ts": "export class Base {\n  m() { return 1; }\n}\n",
        "src/other.ts": "export class Other {\n  go() { return this.m(); }\n  m() { return 2; }\n}\n",
        "src/joint.ts": (
            "import { Base } from './base';\nimport { Other } from './other';\n"
            "export class Joint extends Base implements Other {\n  go() { return 3; }\n}\n"
        ),
    }
    hits = _hits(_git_repo(tmp_path, files), "m", "src/base.ts", "Base.m", [])
    assert _classes_at(hits, "src/other.ts", 2) == ["residual"]


def test_a_comment_inside_a_parse_error_is_residual(tmp_path: Path) -> None:
    files = {
        "src/t.ts": "export function target() { return 1; }\n",
        "src/broken.ts": "class A {\n  m() { @@@ /* target */ target(); }\n}\n",
    }
    hits = _hits(_git_repo(tmp_path, files), "target", "src/t.ts", "target", [])
    assert _classes_at(hits, "src/broken.ts", 2) == ["residual", "residual"]
    assert all("parse error" in h["why"] for h in hits if h["file"] == "src/broken.ts")


def test_site_covered_maps_a_labelled_line_to_its_innermost_caller(
    tmp_path: Path,
) -> None:
    repo = Repo(_git_repo(tmp_path, TS_FUNC))
    outer = [{"file": "src/nested.ts", "name": "outer", "line": 2, "end_line": 8}]
    assert site_covered(repo, "src/nested.ts", 3, "target", outer)
    assert not site_covered(repo, "src/nested.ts", 5, "target", outer)
    a_only = [{"file": "src/sameline.ts", "name": "a", "line": 2}]
    assert not site_covered(repo, "src/sameline.ts", 2, "target", a_only)
    both = [*a_only, {"file": "src/sameline.ts", "name": "b", "line": 2}]
    assert site_covered(repo, "src/sameline.ts", 2, "target", both)
