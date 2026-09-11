"""Unit tests for TypeScript/JavaScript relative-specifier -> file resolution.

ES-module specifiers omit the extension (``./parser`` may be ``parser.ts``,
``parser.tsx``, or ``parser/index.ts``), so resolution needs an ordered
candidate list checked against the set of indexed files. Only ``./``/``../``
specifiers resolve; bare package specifiers must never resolve to a project
file even when a same-named file happens to be indexed.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.synapse_resolver._typescript_imports import (
    resolve_typescript_specifier,
)


class TestExtensionCandidateOrder:
    @pytest.mark.parametrize(
        ("indexed", "expected"),
        [
            ({"src/parser.ts"}, "src/parser.ts"),
            ({"src/parser.tsx"}, "src/parser.tsx"),
            ({"src/parser.d.ts"}, "src/parser.d.ts"),
            ({"src/parser.js"}, "src/parser.js"),
            ({"src/parser.jsx"}, "src/parser.jsx"),
            ({"src/parser.mts"}, "src/parser.mts"),
            ({"src/parser/index.ts"}, "src/parser/index.ts"),
            ({"src/parser/index.tsx"}, "src/parser/index.tsx"),
            ({"src/parser/index.js"}, "src/parser/index.js"),
        ],
    )
    def test_each_supported_extension_resolves(
        self, indexed: set[str], expected: str
    ) -> None:
        assert (
            resolve_typescript_specifier("./parser", "src/consumer.ts", indexed)
            == expected
        )

    def test_source_extension_wins_over_index_directory(self) -> None:
        # A file next to the consumer is a closer match than a directory
        # barrel of the same name; TS resolves the file first.
        indexed = {"src/parser.ts", "src/parser/index.ts"}
        assert (
            resolve_typescript_specifier("./parser", "src/consumer.ts", indexed)
            == "src/parser.ts"
        )

    def test_typescript_wins_over_javascript(self) -> None:
        indexed = {"src/parser.js", "src/parser.ts"}
        assert (
            resolve_typescript_specifier("./parser", "src/consumer.ts", indexed)
            == "src/parser.ts"
        )


class TestRelativePathArithmetic:
    def test_same_directory(self) -> None:
        assert (
            resolve_typescript_specifier(
                "./parser", "src/consumer.ts", {"src/parser.ts"}
            )
            == "src/parser.ts"
        )

    def test_parent_directory(self) -> None:
        assert (
            resolve_typescript_specifier(
                "../parser", "src/deep/consumer.ts", {"src/parser.ts"}
            )
            == "src/parser.ts"
        )

    def test_two_levels_up(self) -> None:
        assert (
            resolve_typescript_specifier(
                "../../parser", "src/a/b/consumer.ts", {"src/parser.ts"}
            )
            == "src/parser.ts"
        )

    def test_nested_subdirectory(self) -> None:
        assert (
            resolve_typescript_specifier(
                "./lib/parser", "src/consumer.ts", {"src/lib/parser.ts"}
            )
            == "src/lib/parser.ts"
        )

    def test_explicit_extension_in_specifier_is_honoured(self) -> None:
        # NodeNext/ESM style: './parser.js' may point at the emitted name while
        # the indexed source is parser.ts, but an exact indexed hit wins first.
        assert (
            resolve_typescript_specifier(
                "./parser.ts", "src/consumer.ts", {"src/parser.ts"}
            )
            == "src/parser.ts"
        )

    def test_consumer_at_repository_root(self) -> None:
        assert (
            resolve_typescript_specifier("./parser", "consumer.ts", {"parser.ts"})
            == "parser.ts"
        )

    def test_windows_style_consumer_path_is_normalized(self) -> None:
        assert (
            resolve_typescript_specifier(
                "./parser", "src\\consumer.ts", {"src/parser.ts"}
            )
            == "src/parser.ts"
        )


class TestNonResolvingSpecifiers:
    @pytest.mark.parametrize(
        "specifier", ["react", "@scope/pkg", "node:fs", "lodash/fp"]
    )
    def test_bare_package_specifier_never_resolves(self, specifier: str) -> None:
        # Even with a decoy file of the same name indexed, a bare specifier is
        # an external package and must not bind to a project file.
        indexed = {"react.ts", "src/react.ts", "@scope/pkg.ts", "node:fs.ts"}
        assert resolve_typescript_specifier(specifier, "src/consumer.ts", indexed) == ""

    def test_unindexed_target_returns_empty(self) -> None:
        assert (
            resolve_typescript_specifier(
                "./missing", "src/consumer.ts", {"src/other.ts"}
            )
            == ""
        )

    def test_escaping_above_the_repository_root_returns_empty(self) -> None:
        assert (
            resolve_typescript_specifier(
                "../../../outside", "src/consumer.ts", {"outside.ts"}
            )
            == ""
        )

    def test_empty_specifier_returns_empty(self) -> None:
        assert (
            resolve_typescript_specifier("", "src/consumer.ts", {"src/parser.ts"}) == ""
        )
