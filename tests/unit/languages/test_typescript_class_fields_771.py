"""Regression test for GitHub issue #771.

TypeScript class property declarations were dropped; function/method body
locals were phantom-reported as fields.

Root cause: the variable extractor traversed into statement_block nodes
(method/function bodies) and treated local const/let as fields, while
real class fields (public_field_definition nodes) were never targeted.

This test pins the exact correct behaviour after the fix:
- Real class member declarations appear as variables (fields).
- Local const/let inside method/function bodies do NOT appear.
"""

from __future__ import annotations

import tree_sitter
from tree_sitter_typescript import language_typescript

from tree_sitter_analyzer.languages.typescript_plugin.extractor import (
    TypeScriptElementExtractor,
)

# ─── Source fixture ───────────────────────────────────────────────────────────

TS_SRC = """\
abstract class BaseEntity {
    protected readonly id: string;
    protected createdAt: Date;
    protected updatedAt: Date;

    protected updateTimestamp(): void {
        this.updatedAt = new Date();
    }
}

class UserService extends BaseEntity {
    private static instance: UserService;
    private users: Map<string, User> = new Map();
    private eventEmitter: EventEmitter;

    public async delete(id: string): Promise<boolean> {
        const deleted = this.users.delete(id);
        return deleted;
    }

    public async findAll(): Promise<User[]> {
        let users = Array.from(this.users.values());
        return users;
    }
}

class AsyncDataProcessor {
    private cache: Map<string, any> = new Map();

    public async fetchData(url: string): Promise<any> {
        const result = await fetch(url);
        const promises = [result.json()];
        return promises;
    }
}

class Application {
    private userService: UserService;
    private dataProcessor: AsyncDataProcessor;

    public async run(): Promise<void> {
        const app = new Application();
        const batches = [];
        const results = [];
        const allUsers = await this.userService.findAll();
    }
}

interface IUser {
    id: string;
    name: string;
}
"""


def _parse(src: str = TS_SRC) -> tree_sitter.Tree:
    lang = tree_sitter.Language(language_typescript())
    parser = tree_sitter.Parser(lang)
    return parser.parse(src.encode())


def _extract_variable_names(src: str = TS_SRC) -> set[str]:
    extractor = TypeScriptElementExtractor()
    variables = extractor.extract_variables(_parse(src), src)
    return {v.name for v in variables}


# ─── Issue #771: class fields captured ───────────────────────────────────────


def test_base_entity_fields_captured() -> None:
    """BaseEntity protected readonly fields must appear."""
    names = _extract_variable_names()
    assert "id" in names, f"'id' not found; got {sorted(names)}"
    assert "createdAt" in names, f"'createdAt' not found; got {sorted(names)}"
    assert "updatedAt" in names, f"'updatedAt' not found; got {sorted(names)}"


def test_user_service_fields_captured() -> None:
    """UserService private/static class property declarations must appear."""
    names = _extract_variable_names()
    assert "instance" in names, f"'instance' not found; got {sorted(names)}"
    assert "users" in names, f"'users' not found; got {sorted(names)}"
    assert "eventEmitter" in names, f"'eventEmitter' not found; got {sorted(names)}"


def test_async_data_processor_field_captured() -> None:
    """AsyncDataProcessor.cache class field must appear."""
    names = _extract_variable_names()
    assert "cache" in names, f"'cache' not found; got {sorted(names)}"


def test_application_fields_captured() -> None:
    """Application class fields must appear."""
    names = _extract_variable_names()
    assert "userService" in names, f"'userService' not found; got {sorted(names)}"
    assert "dataProcessor" in names, f"'dataProcessor' not found; got {sorted(names)}"


# ─── Issue #771: body-locals excluded ────────────────────────────────────────


def test_method_body_const_excluded() -> None:
    """Local 'const deleted' inside delete() must NOT appear as a field."""
    names = _extract_variable_names()
    assert "deleted" not in names, (
        f"body-local 'deleted' leaked into fields; got {sorted(names)}"
    )


def test_method_body_let_excluded() -> None:
    """Local 'let users' inside findAll() must NOT appear as a field.

    Uses a focused source where 'users' only exists as a body-local.
    """
    focused_src = """\
class S {
    public findAll(): string[] {
        let users = [];
        return users;
    }
}
"""
    names = _extract_variable_names(focused_src)
    assert "users" not in names, (
        f"body-local 'let users' leaked into fields; got {sorted(names)}"
    )


def test_body_locals_excluded_exactly() -> None:
    """The set of body-locals from run() must all be absent."""
    names = _extract_variable_names()
    body_locals = {"app", "batches", "results", "allUsers"}
    leaked = body_locals & names
    assert leaked == set(), f"Body-locals leaked as fields: {sorted(leaked)}"


def test_promises_result_excluded() -> None:
    """Locals 'result' and 'promises' inside fetchData() must NOT appear."""
    names = _extract_variable_names()
    assert "result" not in names, f"body-local 'result' leaked; got {sorted(names)}"
    assert "promises" not in names, f"body-local 'promises' leaked; got {sorted(names)}"


# ─── Interface property signatures still captured ────────────────────────────


def test_interface_property_signatures_still_captured() -> None:
    """IUser interface property signatures must still be captured."""
    names = _extract_variable_names()
    assert "id" in names, f"Interface 'id' not found; got {sorted(names)}"
    assert "name" in names, f"Interface 'name' not found; got {sorted(names)}"


# ─── Exact field count pin ────────────────────────────────────────────────────


def test_exact_field_count() -> None:
    """Pin the exact number of variables extracted from the fixture.

    Expected fields:
      BaseEntity:         id, createdAt, updatedAt                    (3)
      UserService:        instance, users, eventEmitter               (3)
      AsyncDataProcessor: cache                                       (1)
      Application:        userService, dataProcessor                  (2)
      IUser interface:    id, name  (property_signature)              (2)
                                                                  total = 11
    """
    extractor = TypeScriptElementExtractor()
    variables = extractor.extract_variables(_parse(), TS_SRC)
    assert len(variables) == 11, (
        f"Expected 11 fields, got {len(variables)}: {sorted(v.name for v in variables)}"
    )
