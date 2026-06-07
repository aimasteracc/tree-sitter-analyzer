"""RFC-0010: language resolver registry + auto-discovery."""

from __future__ import annotations

import pkgutil

from tree_sitter_analyzer.synapse_resolver import (
    ResolvedCallee,
    resolve_callee,
)
from tree_sitter_analyzer.synapse_resolver import languages as _languages
from tree_sitter_analyzer.synapse_resolver._context import ResolverContext
from tree_sitter_analyzer.synapse_resolver._registry import (
    get_language_resolver,
    register_language,
    registered_languages,
)


def test_java_is_registered_via_discovery() -> None:
    """The languages/ subpackage auto-registers Java (migrated from the inline
    dispatch) — no shared-file edit needed."""
    assert "java" in registered_languages()
    assert get_language_resolver("java") is not None


def test_every_language_module_registers_a_resolver() -> None:
    """Discovery guard: every non-underscore module under languages/ must have
    registered a resolver (catches a typo or a module that forgot to register)."""
    discovered = {
        m.name
        for m in pkgutil.iter_modules(_languages.__path__)
        if not m.name.startswith("_")
    }
    registered = set(registered_languages())
    assert discovered <= registered, (
        f"modules that did not register: {discovered - registered}"
    )


def test_resolve_callee_routes_to_registered_language() -> None:
    """A file whose language has a registered resolver (and a built context) is
    dispatched to that resolver; the result flows back through ResolvedCallee."""
    seen: list[tuple[str, str, str, object]] = []

    def fake_resolve(bare, full, caller_file, lang_ctx):
        seen.append((bare, full, caller_file, lang_ctx))
        return (42, "external", "fake/lib.fk")

    register_language("fakelang", lambda **_: {"marker": True}, fake_resolve)
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_languages={"a.fk": "fakelang"},
        lang_contexts={"fakelang": {"marker": True}},
    )
    res = resolve_callee("doThing", "a.fk", ctx, "obj.doThing")
    assert isinstance(res, ResolvedCallee)
    assert (res.callee_symbol_id, res.resolution, res.resolved_file) == (
        42,
        "external",
        "fake/lib.fk",
    )
    assert seen == [("doThing", "obj.doThing", "a.fk", {"marker": True})]


def test_resolve_callee_falls_back_when_no_registered_language() -> None:
    """A file whose language has no registered resolver falls through to the
    Python cascade (does not crash, does not mis-route)."""
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_languages={"a.rb": "ruby"},  # not registered
        lang_contexts={},
    )
    res = resolve_callee("foo", "a.rb", ctx, "foo")
    assert isinstance(res, ResolvedCallee)  # python fallback, no crash
