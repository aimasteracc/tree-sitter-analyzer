"""Unit tests for TypeScript/JavaScript import parsing (reverse-import support).

Pulse's ``imported_by`` context was Python-only because ``parse_imports``
returned an empty list for every other language, so no ``module:`` edge was
ever written for TS/JS files. These tests lock in the ES-module forms that
carry a resolvable specifier, and — critically — the forms that must NOT
produce a row (bare package specifiers are external, not project files).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry, parse_imports


def _entry(
    module_path: str,
    local_name: str = "",
    *,
    is_relative: bool = True,
    is_star: bool = False,
    alias_of: str = "",
    language: str = "typescript",
    file_path: str = "src/consumer.ts",
    line: int = 5,
) -> ImportEntry:
    return ImportEntry(
        file_path=file_path,
        language=language,
        module_path=module_path,
        local_name=local_name,
        is_relative=is_relative,
        is_star=is_star,
        alias_of=alias_of,
        line=line,
    )


class TestNamedImports:
    def test_single_named_import(self) -> None:
        assert parse_imports(
            "import { parse } from './parser';", "typescript", "src/consumer.ts", 5
        ) == [_entry("./parser", "parse")]

    def test_multiple_named_imports_produce_one_row_each(self) -> None:
        rows = parse_imports(
            "import { parse, render } from './parser';",
            "typescript",
            "src/consumer.ts",
            5,
        )
        assert rows == [_entry("./parser", "parse"), _entry("./parser", "render")]

    def test_aliased_named_import_records_alias_of(self) -> None:
        assert parse_imports(
            "import { parse as doParse } from './parser';",
            "typescript",
            "src/consumer.ts",
            5,
        ) == [_entry("./parser", "doParse", alias_of="parse")]

    def test_type_only_named_import_is_still_an_edge(self) -> None:
        # A type-only import still creates a real file->file dependency.
        assert parse_imports(
            "import type { Node } from './ast';", "typescript", "src/consumer.ts", 5
        ) == [_entry("./ast", "Node")]


class TestDefaultAndNamespaceImports:
    def test_default_import(self) -> None:
        assert parse_imports(
            "import parser from './parser';", "typescript", "src/consumer.ts", 5
        ) == [_entry("./parser", "parser")]

    def test_namespace_import_is_star(self) -> None:
        rows = parse_imports(
            "import * as parser from './parser';", "typescript", "src/consumer.ts", 5
        )
        assert len(rows) == 1
        assert rows[0].is_star is True
        assert rows[0].local_name == "parser"
        assert rows[0].module_path == "./parser"

    def test_default_plus_named_combination(self) -> None:
        rows = parse_imports(
            "import parser, { parse } from './parser';",
            "typescript",
            "src/consumer.ts",
            5,
        )
        assert [r.local_name for r in rows] == ["parser", "parse"]
        assert {r.module_path for r in rows} == {"./parser"}

    def test_side_effect_only_import_has_no_bound_name(self) -> None:
        rows = parse_imports(
            "import './polyfills';", "typescript", "src/consumer.ts", 5
        )
        assert len(rows) == 1
        assert rows[0].module_path == "./polyfills"
        assert rows[0].local_name == ""


class TestRelativeAndAbsoluteSpecifiers:
    @pytest.mark.parametrize(
        "specifier", ["./parser", "../parser", "../../lib/parser", "./a/b/parser"]
    )
    def test_relative_specifiers_are_marked_relative(self, specifier: str) -> None:
        rows = parse_imports(
            f"import {{ x }} from '{specifier}';", "typescript", "src/consumer.ts", 5
        )
        assert rows[0].is_relative is True
        assert rows[0].module_path == specifier

    @pytest.mark.parametrize(
        "specifier", ["react", "@scope/pkg", "node:fs", "lodash/fp"]
    )
    def test_bare_package_specifiers_are_not_relative(self, specifier: str) -> None:
        # These are external packages. They must still be recorded (the import
        # exists) but must not be flagged relative, so module->file resolution
        # never mistakes them for a project file.
        rows = parse_imports(
            f"import {{ x }} from '{specifier}';", "typescript", "src/consumer.ts", 5
        )
        assert rows[0].is_relative is False
        assert rows[0].module_path == specifier


class TestQuotingAndFormatting:
    @pytest.mark.parametrize("quote", ["'", '"'])
    def test_both_quote_styles(self, quote: str) -> None:
        rows = parse_imports(
            f"import {{ x }} from {quote}./parser{quote};",
            "typescript",
            "src/consumer.ts",
            5,
        )
        assert rows[0].module_path == "./parser"

    def test_missing_semicolon_is_accepted(self) -> None:
        rows = parse_imports(
            "import { x } from './parser'", "typescript", "src/consumer.ts", 5
        )
        assert rows[0].module_path == "./parser"

    def test_multiline_named_import_block(self) -> None:
        text = "import {\n  parse,\n  render,\n} from './parser';"
        rows = parse_imports(text, "typescript", "src/consumer.ts", 5)
        assert [r.local_name for r in rows] == ["parse", "render"]

    def test_line_comment_is_stripped_before_matching(self) -> None:
        text = "import { parse } from './parser'; // keep this out"
        rows = parse_imports(text, "typescript", "src/consumer.ts", 5)
        assert rows == [_entry("./parser", "parse")]


class TestNonImportStatementsAreIgnored:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "const parser = require('./parser');",
            "export { parse } from './parser';",
            "// import { parse } from './parser';",
            "function importSomething() {}",
        ],
    )
    def test_no_rows_for_non_import_statements(self, text: str) -> None:
        assert parse_imports(text, "typescript", "src/consumer.ts", 5) == []


class TestJavaScriptDialectSharesTheParser:
    @pytest.mark.parametrize("language", ["javascript", "typescript"])
    def test_both_dialects_parse(self, language: str) -> None:
        rows = parse_imports(
            "import { parse } from './parser';", language, "src/consumer.js", 5
        )
        assert len(rows) == 1
        assert rows[0].language == language
        assert rows[0].module_path == "./parser"


class TestUnsupportedLanguagesStillReturnEmpty:
    @pytest.mark.parametrize("language", ["go", "rust", "bash", "css"])
    def test_no_regression_for_languages_without_a_parser(self, language: str) -> None:
        assert (
            parse_imports(
                "import { parse } from './parser';", language, "src/consumer.x", 5
            )
            == []
        )
