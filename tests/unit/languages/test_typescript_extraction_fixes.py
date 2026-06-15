"""Regression tests for TypeScript extraction bugs #772 #773 #774 #795.

#772 — Visibility modifiers collapse to public:
  Public methods whose body text mentions 'private'/'protected' were mis-classified
  because _visibility_from_text did a naive string search on the full node text.

#773 — Decorators dropped:
  @Injectable(), @Component({...}), @Column() were not captured at all.
  A `decorators` field (list[str] of decorator names without '@') must be populated.

#774 — is_abstract and is_async always False:
  Non-async methods whose body text contains the word 'async' (in a string, comment,
  or call expression) were incorrectly marked is_async=True. Similarly, text-based
  detection could miss or mis-set is_async on method_definition nodes.

#795 — TypeScript enum extracted as class in AST cache:
  enum_declaration nodes were indexed with kind="class" in ast_symbol_rows.
  They must be indexed with kind="enum" so downstream symbol queries work correctly.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_typescript

from tree_sitter_analyzer.languages.typescript_plugin import TypeScriptElementExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(code: str) -> tree_sitter.Tree:
    lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode())


def _functions(code: str):
    tree = _parse(code)
    extractor = TypeScriptElementExtractor()
    return extractor.extract_functions(tree, code)


def _classes(code: str):
    tree = _parse(code)
    extractor = TypeScriptElementExtractor()
    return extractor.extract_classes(tree, code)


def _fn_by_name(code: str, name: str):
    fns = _functions(code)
    for f in fns:
        if f.name == name:
            return f
    raise AssertionError(
        f"Function {name!r} not found; extracted: {[f.name for f in fns]}"
    )


def _cls_by_name(code: str, name: str):
    classes = _classes(code)
    for c in classes:
        if c.name == name:
            return c
    raise AssertionError(
        f"Class {name!r} not found; extracted: {[c.name for c in classes]}"
    )


# ---------------------------------------------------------------------------
# #772 — Visibility must come from AST modifier, not text search
# ---------------------------------------------------------------------------

_VISIBILITY_CODE = """\
class Foo {
  processTask(): void {
    const msg = 'this is a private thing';
    const isProtected = true;
  }

  doProtected(): void {
    const note = 'public note';
  }

  private reallyPrivate(): void {}
  protected reallyProtected(): void {}
  public reallyPublic(): void {}
}
"""


def test_visibility_public_method_with_private_in_body() -> None:
    """Public method whose body contains 'private' must still report visibility='public'."""
    fn = _fn_by_name(_VISIBILITY_CODE, "processTask")
    assert fn.visibility == "public"


def test_visibility_public_method_with_protected_in_body() -> None:
    """Public method whose body contains 'protected' must report visibility='public'."""
    fn = _fn_by_name(_VISIBILITY_CODE, "doProtected")
    assert fn.visibility == "public"


def test_visibility_private_method() -> None:
    fn = _fn_by_name(_VISIBILITY_CODE, "reallyPrivate")
    assert fn.visibility == "private"


def test_visibility_protected_method() -> None:
    fn = _fn_by_name(_VISIBILITY_CODE, "reallyProtected")
    assert fn.visibility == "protected"


def test_visibility_public_method() -> None:
    fn = _fn_by_name(_VISIBILITY_CODE, "reallyPublic")
    assert fn.visibility == "public"


# ---------------------------------------------------------------------------
# #774 — is_async must come from AST node, not text search
# ---------------------------------------------------------------------------

_ASYNC_CODE = """\
class Service {
  processTask(): void {
    const result = this.asyncHelper();
    const msg = 'async operation done';
  }

  async reallyAsync(): Promise<void> {}
  private async privateAsync(): Promise<string> { return ''; }

  syncMethod(): void {
    // This comment mentions async flows
    void 0;
  }
}
"""


def test_is_async_false_for_method_with_async_in_body() -> None:
    """Sync method whose body text contains 'async' must have is_async=False."""
    fn = _fn_by_name(_ASYNC_CODE, "processTask")
    assert fn.is_async is False


def test_is_async_false_for_sync_method_with_async_in_comment() -> None:
    """Sync method with 'async' only in a comment must have is_async=False."""
    fn = _fn_by_name(_ASYNC_CODE, "syncMethod")
    assert fn.is_async is False


def test_is_async_true_for_async_method() -> None:
    fn = _fn_by_name(_ASYNC_CODE, "reallyAsync")
    assert fn.is_async is True


def test_is_async_true_for_private_async_method() -> None:
    fn = _fn_by_name(_ASYNC_CODE, "privateAsync")
    assert fn.is_async is True
    assert fn.visibility == "private"


# ---------------------------------------------------------------------------
# #773 — Decorators must be captured
# ---------------------------------------------------------------------------

_DECORATOR_CLASS_CODE = """\
@Injectable()
@Singleton
class UserService {
  @Column({ nullable: false })
  name: string = '';

  @Get('/users')
  async getUsers(): Promise<void> {}

  @Post('/users')
  @Validate
  async createUser(): Promise<void> {}
}
"""


def test_class_decorator_injectable() -> None:
    """@Injectable() on a class must be captured in decorators."""
    cls = _cls_by_name(_DECORATOR_CLASS_CODE, "UserService")
    assert hasattr(cls, "decorators"), "Class model must have a 'decorators' field"
    assert "Injectable" in cls.decorators


def test_class_decorator_singleton() -> None:
    """@Singleton (no parens) on a class must be captured in decorators."""
    cls = _cls_by_name(_DECORATOR_CLASS_CODE, "UserService")
    assert "Singleton" in cls.decorators


def test_class_has_exactly_two_decorators() -> None:
    cls = _cls_by_name(_DECORATOR_CLASS_CODE, "UserService")
    assert len(cls.decorators) == 2


def test_method_decorator_get() -> None:
    """@Get('/users') on a method must be captured in decorators."""
    fn = _fn_by_name(_DECORATOR_CLASS_CODE, "getUsers")
    assert hasattr(fn, "decorators"), "Function model must have a 'decorators' field"
    assert "Get" in fn.decorators


def test_method_has_exactly_one_decorator() -> None:
    fn = _fn_by_name(_DECORATOR_CLASS_CODE, "getUsers")
    assert len(fn.decorators) == 1


def test_method_multiple_decorators() -> None:
    """@Post and @Validate must both appear on createUser."""
    fn = _fn_by_name(_DECORATOR_CLASS_CODE, "createUser")
    assert "Post" in fn.decorators
    assert "Validate" in fn.decorators
    assert len(fn.decorators) == 2


def test_method_without_decorator_has_empty_list() -> None:
    """Methods without decorators must have an empty decorators list, not None."""
    code = """\
class Foo {
  doSomething(): void {}
}
"""
    fn = _fn_by_name(code, "doSomething")
    assert hasattr(fn, "decorators")
    assert fn.decorators == []


def test_property_decorator_column() -> None:
    """@Column() on a class field must be captured in Variable.decorators."""
    tree = _parse(_DECORATOR_CLASS_CODE)
    extractor = TypeScriptElementExtractor()
    variables = extractor.extract_variables(tree, _DECORATOR_CLASS_CODE)
    name_field = next(v for v in variables if v.name == "name")

    assert "Column" in name_field.decorators


def test_class_without_decorator_has_empty_list() -> None:
    code = """\
class Foo {}
"""
    cls = _cls_by_name(code, "Foo")
    assert hasattr(cls, "decorators")
    assert cls.decorators == []


# ---------------------------------------------------------------------------
# #795 — Enums must have kind="enum" in _ast_extraction output
# ---------------------------------------------------------------------------


def test_enum_class_type_is_enum() -> None:
    """TypeScript enum must have class_type='enum' in extracted Class object."""
    code = "enum Status { Active, Inactive }"
    cls = _cls_by_name(code, "Status")
    assert cls.class_type == "enum"


def test_const_enum_class_type_is_enum() -> None:
    """TypeScript const enum must have class_type='enum' in extracted Class object."""
    code = "const enum Direction { Up, Down, Left, Right }"
    cls = _cls_by_name(code, "Direction")
    assert cls.class_type == "enum"


def test_enum_not_confused_with_class() -> None:
    """Enum and class in the same file: enum must be 'enum', class must be 'class'."""
    code = """\
enum Color { Red, Green, Blue }
class Painter {}
"""
    classes = _classes(code)
    by_name = {c.name: c for c in classes}
    assert by_name["Color"].class_type == "enum"
    assert by_name["Painter"].class_type == "class"


def test_enum_kind_in_ast_extraction() -> None:
    """enum_declaration must produce kind='enum' in the _ast_extraction symbol list."""
    from tree_sitter_analyzer._ast_extraction import _extract_symbols

    code = "enum Status { Active, Inactive }\nconst enum Dir { Up, Down }"
    tree = _parse(code)
    result = _extract_symbols(tree, code, "typescript")
    symbols = result.get("symbols", [])
    enum_syms = [s for s in symbols if s.get("name") in ("Status", "Dir")]
    assert len(enum_syms) == 2
    for sym in enum_syms:
        assert sym["kind"] == "enum", (
            f"Expected kind='enum' for {sym['name']!r}, got {sym['kind']!r}"
        )


def test_exported_enum_interface_and_type_are_detected() -> None:
    code = """\
export enum Status { Active, Inactive }
export interface Shape {}
export type Id = string
class Local {}
export { Local }
"""
    classes = {c.name: c for c in _classes(code)}

    assert classes["Status"].is_exported is True
    assert classes["Shape"].is_exported is True
    assert classes["Id"].is_exported is True
    assert classes["Local"].is_exported is True


def test_enum_export_surface_includes_members() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.element_extractor import get_all_exports
    from tree_sitter_analyzer.models import AnalysisResult

    code = "export enum Status { Active = 'active', Inactive = 'inactive' }"
    result = AnalysisResult(
        file_path="status.ts",
        language="typescript",
        elements=_classes(code),
        source_code=code,
    )
    exports = get_all_exports(result)
    enum_export = next(e for e in exports if e["name"] == "Status")

    assert enum_export["kind"] == "enum"
    assert enum_export["members"] == ["Active", "Inactive"]


def test_enum_kind_is_available_in_symbol_search_filters() -> None:
    from tree_sitter_analyzer.mcp.tools.symbol_search_tool import SYMBOL_SEARCH_KINDS

    assert "enum" in SYMBOL_SEARCH_KINDS


# ---------------------------------------------------------------------------
# #975 — enum member split must respect quoted / parenthesised commas
#   _enum_members_from_raw_text split the raw body on every ',', so a comma
#   inside a quoted string value (or a call-expr value) fabricated a phantom
#   member from the value text. e.g. { A = "x,y", B } returned ['A','y','B'].
# ---------------------------------------------------------------------------


def test_enum_members_phantom_from_quoted_comma() -> None:
    """A comma inside a quoted value must NOT fabricate a phantom member."""
    from tree_sitter_analyzer.mcp.tools.utils.element_extractor import (
        _enum_members_from_raw_text,
    )

    assert _enum_members_from_raw_text('A = "x,y", B = "z"') == ["A", "B"]


def test_enum_members_phantom_from_call_expr_comma() -> None:
    """A comma inside a call-expression value must NOT fabricate a member."""
    from tree_sitter_analyzer.mcp.tools.utils.element_extractor import (
        _enum_members_from_raw_text,
    )

    assert _enum_members_from_raw_text("A = f(1, 2), B") == ["A", "B"]


def test_enum_members_plain_string_values_regression() -> None:
    """Common string-valued enum still splits correctly."""
    from tree_sitter_analyzer.mcp.tools.utils.element_extractor import (
        _enum_members_from_raw_text,
    )

    assert _enum_members_from_raw_text(
        '{ Active = "active", Inactive = "inactive" }'
    ) == ["Active", "Inactive"]


def test_enum_export_surface_no_phantom_member() -> None:
    """End-to-end through get_all_exports: quoted comma must not add a member."""
    from tree_sitter_analyzer.mcp.tools.utils.element_extractor import get_all_exports
    from tree_sitter_analyzer.models import AnalysisResult

    code = 'export enum E { A = "x,y", B = "z" }'
    result = AnalysisResult(
        file_path="e.ts",
        language="typescript",
        elements=_classes(code),
        source_code=code,
    )
    enum_export = next(e for e in get_all_exports(result) if e["name"] == "E")
    assert enum_export["members"] == ["A", "B"]


# ---------------------------------------------------------------------------
# #975 (P3) — is_exported_class re-export form must tolerate spacing/multi-name
# ---------------------------------------------------------------------------


def test_reexport_no_inner_spaces() -> None:
    code = "class Local {}\nexport {Local}\n"
    assert {c.name: c for c in _classes(code)}["Local"].is_exported is True


def test_reexport_multi_name() -> None:
    code = "class Local {}\nclass Other {}\nexport { Local, Other }\n"
    by_name = {c.name: c for c in _classes(code)}
    assert by_name["Local"].is_exported is True
    assert by_name["Other"].is_exported is True


def test_reexport_aliased() -> None:
    code = "class Local {}\nexport { Local as Foo }\n"
    assert {c.name: c for c in _classes(code)}["Local"].is_exported is True
