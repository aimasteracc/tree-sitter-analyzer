"""``scripts.wrong_complete.token_oracle`` 的单元测试（Java / TypeScript，不运行 TSA）。"""

from __future__ import annotations

import pytest

from scripts.wrong_complete.sites import OTHER, POSSIBLE, TARGET, Target
from scripts.wrong_complete.token_oracle import token_sites
from scripts.wrong_complete.token_text import code_view

_JAVA_BASE = {
    "src/Base.java": "public abstract class Base {\n  public abstract void write(String s);\n}\n",
    "src/Foo.java": (
        "public final class Foo extends Base {\n"
        "  @Override\n"
        "  public void write(String s) {\n"
        "  }\n\n"
        "  void self() {\n"
        '    write("a");\n'
        '    this.write("b");\n'
        "  }\n"
        "}\n"
    ),
    "src/Other.java": (
        "public final class Other {\n"
        "  public void write(String s) {\n"
        "  }\n\n"
        "  void go() {\n"
        '    this.write("c");\n'
        "  }\n"
        "}\n"
    ),
}
_FOO = Target("src/Foo.java", "write", "Foo", 3)


def _verdicts(
    files: dict[str, str], target: Target
) -> dict[tuple[str, int], tuple[str, str]]:
    return {s.key(): (s.verdict, s.reason) for s in token_sites(files, target)}


def test_definition_lines_are_not_call_sites() -> None:
    verdicts = _verdicts(_JAVA_BASE, _FOO)
    assert sorted(verdicts) == [
        ("src/Foo.java", 7),
        ("src/Foo.java", 8),
        ("src/Other.java", 6),
    ]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (("src/Foo.java", 7), (TARGET, "implicit_this")),
        (("src/Foo.java", 8), (TARGET, "this")),
        (("src/Other.java", 6), (OTHER, "this_other")),
    ],
    ids=["implicit-this", "this", "this-in-unrelated-class"],
)
def test_this_receivers_resolve_to_the_enclosing_class(
    key: tuple[str, int], expected: tuple[str, str]
) -> None:
    assert _verdicts(_JAVA_BASE, _FOO)[key] == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '  void a(Base b) {\n    b.write("x");\n  }\n',
            (POSSIBLE, "override_dispatch"),
        ),
        ('  void a(Foo f) {\n    f.write("x");\n  }\n', (TARGET, "declared")),
        ('  void a(Object o) {\n    ((Foo) o).write("x");\n  }\n', (TARGET, "cast")),
        (
            '  void a(StringBuilder sb) {\n    sb.write("x");\n  }\n',
            (OTHER, "external_type"),
        ),
        ('  void a(Other o) {\n    o.write("x");\n  }\n', (OTHER, "declared_other")),
        (
            '  void a() {\n    make().write("x");\n  }\n',
            (POSSIBLE, "unresolved_receiver"),
        ),
        (
            '  private Foo field;\n  void a() {\n    field.write("x");\n  }\n',
            (TARGET, "declared"),
        ),
    ],
    ids=[
        "supertype",
        "exact-type",
        "cast",
        "external-type",
        "unrelated-type",
        "call-chain",
        "field",
    ],
)
def test_a_java_receiver_is_classified_by_its_declared_type(
    body: str, expected: tuple[str, str]
) -> None:
    files = {**_JAVA_BASE, "src/Use.java": f"public final class Use {{\n{body}}}\n"}
    sites = {k: v for k, v in _verdicts(files, _FOO).items() if k[0] == "src/Use.java"}
    assert list(sites.values()) == [expected]


def test_comments_strings_and_constructors_are_not_sites() -> None:
    body = '  void a() {\n    // f.write("x");\n    String s = "f.write(1)";\n    new write();\n  }\n'
    files = {**_JAVA_BASE, "src/Use.java": f"public final class Use {{\n{body}}}\n"}
    assert [k for k in _verdicts(files, _FOO) if k[0] == "src/Use.java"] == []


def test_code_view_keeps_length_and_lines() -> None:
    text = 'a = "x // y"; // c\n/* d\ne */ b = `t`;\n'
    view = code_view(text)
    assert (len(view), view.count("\n"), "//" in view.split("\n")[0][:12]) == (
        len(text),
        text.count("\n"),
        False,
    )


_TS = {
    "src/jws.ts": "export function verifying(k: string) {\n  return k;\n}\nexport default function signer() {\n  return 1;\n}\n",
    "src/index.ts": "export { verifying } from './jws';\nexport * from './jws';\n",
}
_VERIFYING = Target("src/jws.ts", "verifying", None, 1)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "import { verifying } from './jws';\nexport function a() {\n  return verifying('x');\n}\n",
            (TARGET, "es_import"),
        ),
        (
            "import { verifying as check } from './jws.js';\nexport function a() {\n  return check('x');\n}\n",
            (TARGET, "alias:es_import"),
        ),
        (
            "import * as jws from './jws';\nexport function a() {\n  return jws.verifying('x');\n}\n",
            (TARGET, "namespace_import"),
        ),
        (
            "import { verifying } from './index';\nexport function a() {\n  return verifying('x');\n}\n",
            (TARGET, "es_import"),
        ),
        (
            "import { verifying } from 'jsonwebtoken';\nexport function a() {\n  return verifying('x');\n}\n",
            (OTHER, "package_import"),
        ),
        (
            "export function a(x: any) {\n  return x.verifying('x');\n}\n",
            (POSSIBLE, "opaque_type"),
        ),
        (
            "export function a(x) {\n  return x.verifying('x');\n}\n",
            (POSSIBLE, "unresolved_receiver"),
        ),
    ],
    ids=[
        "named",
        "renamed",
        "namespace",
        "barrel",
        "package",
        "any-member",
        "untyped-member",
    ],
)
def test_a_ts_call_follows_es_module_bindings(
    body: str, expected: tuple[str, str]
) -> None:
    files = {**_TS, "src/use.ts": body}
    sites = {
        k: v for k, v in _verdicts(files, _VERIFYING).items() if k[0] == "src/use.ts"
    }
    assert list(sites.values()) == [expected]


def test_a_renamed_default_import_reaches_the_default_export() -> None:
    # #1768：``import makeSig from './jws'; makeSig()``。
    files = {
        **_TS,
        "src/use.ts": "import makeSig from './jws';\nexport function a() {\n  return makeSig();\n}\n",
    }
    verdicts = _verdicts(files, Target("src/jws.ts", "signer", None, 4))
    assert verdicts == {("src/use.ts", 3): (TARGET, "alias:es_import")}


def test_a_string_literal_element_access_is_a_call_of_that_member() -> None:
    # #1762：``this["~validate"](data)``。
    files = {
        "src/types.ts": (
            "export class ZodType {\n"
            "  run(data: unknown) {\n"
            '    return this["~validate"](data);\n'
            "  }\n"
            '  "~validate"(data: unknown): unknown {\n'
            "    return data;\n"
            "  }\n"
            "}\n"
        )
    }
    verdicts = _verdicts(files, Target("src/types.ts", '"~validate"', "ZodType", 5))
    assert verdicts == {("src/types.ts", 3): (TARGET, "this")}
