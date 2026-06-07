"""RFC-0010 first wave: the Go per-language callee resolver.

Go calls come in two syntactic shapes the resolver must classify
correctly without ever guessing:

* bare / same-file       — ``helper()`` resolves to a same-file ``func``.
* package-qualified call  — ``fmt.Println`` / ``strings.Split`` classify as
  ``stdlib`` ONLY when the qualifier is a conservative stdlib package name
  that the project does not itself define (shadowing preserved).
* receiver method call    — ``s.Run()`` (receiver is a *variable*, its type
  is not inferable from the edge) stays ``unknown``; the resolver never
  guesses a cross-struct/cross-file binding.

The mandatory moat assertion: a callee whose bare name also exists as a
symbol in ANOTHER language's file must NEVER bind to that file — Go only
ever resolves ``local`` against its own (same-language) caller file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.synapse_resolver import ResolvedCallee, resolve_callee
from tree_sitter_analyzer.synapse_resolver import languages as _languages
from tree_sitter_analyzer.synapse_resolver._context import ResolverContext
from tree_sitter_analyzer.synapse_resolver._registry import (
    get_language_resolver,
    registered_languages,
)
from tree_sitter_analyzer.synapse_resolver.languages.go import (
    GoResolverContext,
    build_go_resolver_context,
    resolve_go_callee,
)


# ---------------------------------------------------------------------------
# Registration / discovery
# ---------------------------------------------------------------------------
def test_go_is_registered_via_discovery() -> None:
    """Dropping ``languages/go.py`` auto-registers the Go resolver — no edit to
    any shared file."""
    assert "go" in registered_languages()
    assert get_language_resolver("go") is not None
    assert "go" in {
        m.name
        for m in __import__("pkgutil").iter_modules(_languages.__path__)
        if not m.name.startswith("_")
    }


# ---------------------------------------------------------------------------
# build_go_resolver_context gating (zero cost when no Go file is indexed)
# ---------------------------------------------------------------------------
def test_build_context_returns_none_without_go_files() -> None:
    ctx = build_go_resolver_context(
        imports_by_file={},
        file_languages={"a.py": "python"},
        file_symbols={},
        global_name_table={},
        file_class_methods=lambda: {},
    )
    assert ctx is None


def test_build_context_built_when_go_file_present() -> None:
    ctx = build_go_resolver_context(
        imports_by_file={},
        file_languages={"main.go": "go"},
        file_symbols={"main.go": [("helper", "function", 7)]},
        global_name_table={"helper": [("main.go", 7)]},
        file_class_methods=lambda: {},
    )
    assert isinstance(ctx, GoResolverContext)
    assert "main.go" in ctx.file_symbols


# ---------------------------------------------------------------------------
# Direct resolver unit tests
# ---------------------------------------------------------------------------
def _ctx(
    symbols: dict[str, list[tuple[str, str, int]]],
    *,
    imports: dict[str, str] | None = None,
) -> GoResolverContext:
    """Build a Go context for unit tests.

    ``imports`` maps a file path to its raw Go import-block text (exactly the
    string the indexer stores as a ``kind='import'`` symbol). When omitted, the
    helper synthesises a permissive import block that imports every stdlib
    package name referenced by the test as a qualifier — so a test that does
    NOT care about import-gating keeps classifying stdlib calls as before.
    """
    if imports is None:
        # Permissive default: import every canonical stdlib package so legacy
        # stdlib-classification tests still see import evidence.
        from tree_sitter_analyzer.synapse_resolver.languages._go_constants import (
            STDLIB_PACKAGES_GO,
        )

        block = (
            "import (\n"
            + "".join(f'\t"{p}"\n' for p in sorted(STDLIB_PACKAGES_GO))
            + ")"
        )
        imports = dict.fromkeys(symbols, block)
    built = build_go_resolver_context(
        imports_by_file={},
        file_languages=dict.fromkeys(symbols, "go"),
        file_symbols=symbols,
        global_name_table={},
        file_class_methods=lambda: {},
        go_import_blocks=imports,
    )
    assert built is not None
    return built


def test_same_file_func_resolves_local() -> None:
    ctx = _ctx({"main.go": [("helper", "function", 7), ("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_go_callee("helper", "helper", "main.go", ctx)
    assert (sym_id, resolution, resolved) == (7, "local", "main.go")


def test_stdlib_package_call_classifies_stdlib() -> None:
    ctx = _ctx(
        {"main.go": [("main", "function", 11)]},
        imports={"main.go": 'import "fmt"'},
    )
    sym_id, resolution, resolved = resolve_go_callee(
        "Println", "fmt.Println", "main.go", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "stdlib", "")


def test_strings_package_call_classifies_stdlib() -> None:
    ctx = _ctx(
        {"main.go": [("helper", "function", 7)]},
        imports={"main.go": 'import "strings"'},
    )
    _sym, resolution, _file = resolve_go_callee(
        "ToUpper", "strings.ToUpper", "main.go", ctx
    )
    assert resolution == "stdlib"


def test_stdlib_qualifier_without_import_stays_unknown() -> None:
    """Codex P2: a receiver whose name collides with a stdlib package
    (``var http Client; http.Get()``) but which is NOT imported must stay
    ``unknown`` — the stdlib tier requires import evidence, never just a
    name match."""
    ctx = _ctx(
        {"main.go": [("main", "function", 11)]},
        imports={"main.go": 'import "fmt"'},  # http NOT imported
    )
    sym_id, resolution, resolved = resolve_go_callee("Get", "http.Get", "main.go", ctx)
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_blank_import_does_not_enable_stdlib_qualifier() -> None:
    """A blank import (``_ "net/http"``) is side-effect only — the package
    name is NOT usable as a qualifier, so ``http.Get`` stays ``unknown``."""
    ctx = _ctx(
        {"main.go": [("main", "function", 11)]},
        imports={"main.go": 'import (\n\t_ "net/http"\n)'},
    )
    _sym, resolution, _file = resolve_go_callee("Get", "http.Get", "main.go", ctx)
    assert resolution == "unknown"


def test_aliased_stdlib_import_uses_alias_not_package_name() -> None:
    """``jsonx "encoding/json"`` makes ``jsonx`` the qualifier; a bare
    ``json.Marshal`` is therefore NOT imported and stays ``unknown`` (json is
    not in STDLIB set anyway, but the alias must not leak the package name)."""
    ctx = _ctx(
        {"main.go": [("main", "function", 11)]},
        imports={"main.go": 'import (\n\tstrs "strings"\n)'},
    )
    # `strs` is the local qualifier; a bare `strings.X` is not imported.
    _sym, resolution, _file = resolve_go_callee(
        "ToUpper", "strings.ToUpper", "main.go", ctx
    )
    assert resolution == "unknown"


def test_aliased_stdlib_import_resolves_under_alias() -> None:
    """The alias qualifier itself resolves to stdlib when it aliases a stdlib
    package (``strs "strings"`` → ``strs.ToUpper`` is stdlib)."""
    ctx = _ctx(
        {"main.go": [("main", "function", 11)]},
        imports={"main.go": 'import (\n\tstrs "strings"\n)'},
    )
    _sym, resolution, _file = resolve_go_callee(
        "ToUpper", "strs.ToUpper", "main.go", ctx
    )
    assert resolution == "stdlib"


# ---------------------------------------------------------------------------
# Codex P2 (finding 2): comments in a Go import block must be stripped before
# the import matcher runs, or a commented-out stdlib path leaks a spurious
# qualifier and a same-named variable is falsely classified as stdlib.
# ---------------------------------------------------------------------------
def test_line_comment_in_import_block_is_not_an_import() -> None:
    """A ``// "net/http"`` line comment inside a grouped import must NOT be
    parsed as a real import spec — only ``fmt`` is actually imported."""
    from tree_sitter_analyzer.synapse_resolver.languages._go_constants import (
        parse_go_import_block,
    )

    raw = 'import (\n\t"fmt"\n\t// "net/http"\n)'
    assert parse_go_import_block(raw) == {"fmt": "fmt"}


def test_trailing_line_comment_after_spec_is_not_an_import() -> None:
    """A trailing ``// "net/http"`` after a real ``"fmt"`` import must be
    ignored — the commented path is not imported."""
    from tree_sitter_analyzer.synapse_resolver.languages._go_constants import (
        parse_go_import_block,
    )

    raw = 'import "fmt" // "net/http"'
    assert parse_go_import_block(raw) == {"fmt": "fmt"}


def test_block_comment_in_import_block_is_not_an_import() -> None:
    """A ``/* "net/http" */`` block comment must be stripped before matching —
    the commented stdlib path must not leak an ``http`` qualifier."""
    from tree_sitter_analyzer.synapse_resolver.languages._go_constants import (
        parse_go_import_block,
    )

    raw = 'import (\n\t"fmt"\n\t/* "net/http" */\n)'
    assert parse_go_import_block(raw) == {"fmt": "fmt"}


def test_commented_import_does_not_enable_stdlib_qualifier() -> None:
    """End-to-end of finding 2 through the resolver: a ``// "net/http"`` comment
    next to a real ``"fmt"`` import must leave a later ``http.Get`` ``unknown`` —
    the commented path is not real import evidence."""
    ctx = _ctx(
        {"main.go": [("main", "function", 11)]},
        imports={"main.go": 'import (\n\t"fmt"\n\t// "net/http"\n)'},
    )
    _sym, resolution, _file = resolve_go_callee("Get", "http.Get", "main.go", ctx)
    assert resolution == "unknown"


def test_receiver_method_call_stays_unknown() -> None:
    """``s.Run()`` — ``s`` is a local variable whose struct type the edge does
    not carry. The resolver must NOT guess a same-name ``Run`` elsewhere."""
    ctx = _ctx({"svc.go": [("Run", "function", 5), ("Start", "function", 9)]})
    sym_id, resolution, resolved = resolve_go_callee("Run", "s.Run", "svc.go", ctx)
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_unknown_package_qualifier_stays_unknown() -> None:
    """A non-stdlib package qualifier (third-party / domain) is conservatively
    left ``unknown`` — never mis-classified as stdlib/external."""
    ctx = _ctx({"main.go": [("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_go_callee(
        "NewClient", "redis.NewClient", "main.go", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_project_shadows_stdlib_package_name() -> None:
    """If the project itself defines a symbol named like a stdlib package
    (e.g. a ``fmt`` func), a ``fmt.X`` call must NOT be claimed as stdlib —
    precision over recall."""
    ctx = _ctx({"main.go": [("fmt", "function", 3), ("main", "function", 11)]})
    _sym, resolution, _file = resolve_go_callee("X", "fmt.X", "main.go", ctx)
    assert resolution != "stdlib"


def test_bare_name_not_in_file_stays_unknown() -> None:
    ctx = _ctx({"main.go": [("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_go_callee(
        "missing", "missing", "main.go", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


# ---------------------------------------------------------------------------
# Integration through the registry dispatch (resolve_callee)
# ---------------------------------------------------------------------------
def test_resolve_callee_routes_go_to_go_resolver() -> None:
    go_ctx = _ctx({"main.go": [("helper", "function", 7)]})
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_languages={"main.go": "go"},
        lang_contexts={"go": go_ctx},
    )
    res = resolve_callee("helper", "main.go", ctx, "helper")
    assert isinstance(res, ResolvedCallee)
    assert (res.callee_symbol_id, res.resolution, res.resolved_file) == (
        7,
        "local",
        "main.go",
    )


def test_resolve_callee_go_stdlib_through_registry() -> None:
    go_ctx = _ctx({"main.go": [("main", "function", 11)]})
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_languages={"main.go": "go"},
        lang_contexts={"go": go_ctx},
    )
    res = resolve_callee("Println", "main.go", ctx, "fmt.Println")
    assert res.resolution == "stdlib"


# ---------------------------------------------------------------------------
# THE MOAT — no cross-language mis-wire
# ---------------------------------------------------------------------------
def test_no_cross_language_mis_wire_direct() -> None:
    """A Go caller's bare ``helper`` must NEVER resolve to a Python file that
    happens to define ``helper``. The Go resolver only consults its own caller
    file (same-language by construction)."""
    ctx = build_go_resolver_context(
        imports_by_file={},
        file_languages={"main.go": "go", "util.py": "python"},
        # Python file defines `helper`; the Go caller file does NOT.
        file_symbols={"util.py": [("helper", "function", 3)]},
        global_name_table={"helper": [("util.py", 3)]},
        file_class_methods=lambda: {},
    )
    assert ctx is not None
    sym_id, resolution, resolved = resolve_go_callee("helper", "helper", "main.go", ctx)
    # MUST NOT bind to util.py — stays unknown.
    assert (sym_id, resolution, resolved) == (None, "unknown", "")
    assert resolved != "util.py"


def test_no_cross_language_mis_wire_end_to_end(tmp_path: Path) -> None:
    """Index a polyglot repo where ``ToUpper`` exists as a Python def AND is
    called package-qualified from Go (``strings.ToUpper``). The Go edge must
    classify as ``stdlib`` (or unknown) — NEVER bind to the Python file."""
    (tmp_path / "py").mkdir()
    (tmp_path / "py" / "helpers.py").write_text(
        "def ToUpper(s):\n    return s.upper()\n"
    )
    (tmp_path / "app.go").write_text(
        "package main\n\n"
        'import (\n\t"fmt"\n\t"strings"\n)\n\n'
        "func main() {\n"
        '\tfmt.Println(strings.ToUpper("hi"))\n'
        "}\n"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    db = str(tmp_path / ".ast-cache" / "index.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_resolution, callee_resolved_file FROM edges "
            "WHERE kind = 'calls' AND callee_name = 'ToUpper' AND language = 'go'"
        ).fetchall()
    finally:
        conn.close()
    assert rows, "expected a Go strings.ToUpper edge"
    for r in rows:
        # The moat: a Go caller must NEVER bind to the Python helpers.py.
        assert r["callee_resolved_file"] != "py/helpers.py"
        assert r["callee_resolution"] in ("stdlib", "unknown")


def test_end_to_end_variable_named_like_stdlib_stays_unknown(tmp_path: Path) -> None:
    """Codex P2 end-to-end: a local variable named ``http`` (no ``net/http``
    import) calling ``http.Get`` must NOT be classified as stdlib — only
    ``fmt`` is imported, so ``http`` is a variable receiver and stays
    ``unknown``."""
    (tmp_path / "main.go").write_text(
        "package main\n\n"
        'import "fmt"\n\n'
        "type Client struct{}\n\n"
        "func (c Client) Get(s string) string { return s }\n\n"
        "func main() {\n"
        "\tvar http Client\n"
        '\tfmt.Println(http.Get("x"))\n'
        "}\n"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    db = str(tmp_path / ".ast-cache" / "index.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_name, callee_resolution FROM edges "
            "WHERE kind = 'calls' AND language = 'go' AND callee_name = 'Get'"
        ).fetchall()
    finally:
        conn.close()
    assert rows, "expected a Go http.Get edge"
    for r in rows:
        # http is a variable, not the imported package → must stay unknown.
        assert r["callee_resolution"] == "unknown"


def test_end_to_end_go_stdlib_and_local(tmp_path: Path) -> None:
    """Full index: a same-file func call stays ``local``; a stdlib
    package-qualified call becomes ``stdlib``."""
    (tmp_path / "main.go").write_text(
        "package main\n\n"
        'import (\n\t"fmt"\n\t"strings"\n)\n\n'
        "func helper(s string) string {\n"
        "\treturn strings.ToUpper(s)\n"
        "}\n\n"
        "func main() {\n"
        '\tfmt.Println(helper("hi"))\n'
        "}\n"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    db = str(tmp_path / ".ast-cache" / "index.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = {
            r["callee_name"]: r["callee_resolution"]
            for r in conn.execute(
                "SELECT callee_name, callee_resolution FROM edges "
                "WHERE kind = 'calls' AND language = 'go'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert rows.get("helper") == "local"
    assert rows.get("ToUpper") == "stdlib"
    assert rows.get("Println") == "stdlib"
