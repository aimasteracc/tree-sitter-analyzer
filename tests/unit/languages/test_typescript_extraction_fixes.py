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
