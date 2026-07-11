"""Regression tests for star-import expansion in _build_import_maps.

Verifies that ``from M import *`` entries are expanded into per-name
name_to_source entries when file_symbols is supplied, and that external
modules are silently skipped (REQ-N-013).
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver._context import _build_import_maps
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_star_entry(
    caller: str,
    module_path: str,
    *,
    is_relative: bool = False,
) -> ImportEntry:
    return ImportEntry(
        file_path=caller,
        language="python",
        module_path=module_path,
        local_name="",
        is_relative=is_relative,
        is_star=True,
        alias_of="",
        line=1,
    )


# ---------------------------------------------------------------------------
# Test 1: star import from a project-local sibling resolves exported names
# ---------------------------------------------------------------------------


class TestStarImportResolvesExportedNameToProject:
    """``from .sibling import *`` maps each exported name to sibling.py."""

    def test_exported_function_in_name_to_source(self) -> None:
        # pkg/sibling.py exports helper()
        file_symbols = {
            "pkg/sibling.py": [("helper", "function", 10)],
        }
        imports_by_file = {
            "pkg/caller.py": [
                _make_star_entry("pkg/caller.py", ".sibling", is_relative=True),
            ],
        }
        # module_to_file maps the file path to itself (path-keyed)
        module_to_file: dict[str, str] = {"pkg/sibling.py": "pkg/sibling.py"}

        name_to_source, _alias = _build_import_maps(
            imports_by_file, module_to_file, file_symbols
        )

        assert "pkg/caller.py" in name_to_source
        assert name_to_source["pkg/caller.py"]["helper"] == "pkg/sibling.py"

    def test_multiple_exported_names_all_mapped(self) -> None:
        file_symbols = {
            "pkg/sibling.py": [
                ("func_a", "function", 5),
                ("MyClass", "class", 20),
            ],
        }
        imports_by_file = {
            "pkg/caller.py": [
                _make_star_entry("pkg/caller.py", ".sibling", is_relative=True),
            ],
        }
        module_to_file = {"pkg/sibling.py": "pkg/sibling.py"}

        name_to_source, _ = _build_import_maps(
            imports_by_file, module_to_file, file_symbols
        )

        assert name_to_source["pkg/caller.py"]["func_a"] == "pkg/sibling.py"
        assert name_to_source["pkg/caller.py"]["MyClass"] == "pkg/sibling.py"


# ---------------------------------------------------------------------------
# Test 2: name not exported by starred module is not in name_to_source
# ---------------------------------------------------------------------------


class TestStarImportNonExportedNameStaysUnknown:
    """Names absent from the starred module's file_symbols are not injected."""

    def test_unknown_name_not_in_name_to_source(self) -> None:
        # sibling.py only exports "helper"; "secret" is not exported
        file_symbols = {
            "pkg/sibling.py": [("helper", "function", 10)],
        }
        imports_by_file = {
            "pkg/caller.py": [
                _make_star_entry("pkg/caller.py", ".sibling", is_relative=True),
            ],
        }
        module_to_file = {"pkg/sibling.py": "pkg/sibling.py"}

        name_to_source, _ = _build_import_maps(
            imports_by_file, module_to_file, file_symbols
        )

        caller_map = name_to_source.get("pkg/caller.py", {})
        assert "secret" not in caller_map

    def test_no_symbols_in_starred_module_produces_no_entry(self) -> None:
        # sibling.py is in file_symbols but has no symbols (empty list)
        file_symbols: dict[str, list[tuple[str, str, int]]] = {
            "pkg/sibling.py": [],
        }
        imports_by_file = {
            "pkg/caller.py": [
                _make_star_entry("pkg/caller.py", ".sibling", is_relative=True),
            ],
        }
        module_to_file = {"pkg/sibling.py": "pkg/sibling.py"}

        name_to_source, _ = _build_import_maps(
            imports_by_file, module_to_file, file_symbols
        )

        # No symbols to inject — caller should have no entry
        assert "pkg/caller.py" not in name_to_source


# ---------------------------------------------------------------------------
# Test 3: star import from an external module produces no name_to_source entry
# ---------------------------------------------------------------------------


class TestStarImportExternalModuleSkipped:
    """``from os import *`` produces no name_to_source entries (REQ-N-013)."""

    def test_external_module_not_in_module_to_file(self) -> None:
        file_symbols: dict[str, list[tuple[str, str, int]]] = {}
        imports_by_file = {
            "myapp/main.py": [
                _make_star_entry("myapp/main.py", "os", is_relative=False),
            ],
        }
        # "os" is not in module_to_file (it is a stdlib/external module)
        module_to_file: dict[str, str] = {}

        name_to_source, alias_target = _build_import_maps(
            imports_by_file, module_to_file, file_symbols
        )

        assert "myapp/main.py" not in name_to_source
        assert "myapp/main.py" not in alias_target

    def test_external_star_does_not_pollute_other_caller_entries(self) -> None:
        # caller.py has a normal import AND an external star import
        file_symbols = {
            "pkg/util.py": [("helper", "function", 3)],
        }
        imports_by_file = {
            "pkg/caller.py": [
                ImportEntry(
                    file_path="pkg/caller.py",
                    language="python",
                    module_path=".util",
                    local_name="helper",
                    is_relative=True,
                    is_star=False,
                    alias_of="",
                    line=1,
                ),
                _make_star_entry("pkg/caller.py", "os", is_relative=False),
            ],
        }
        module_to_file = {"pkg/util.py": "pkg/util.py"}

        name_to_source, _ = _build_import_maps(
            imports_by_file, module_to_file, file_symbols
        )

        # The normal import is still resolved correctly
        assert name_to_source["pkg/caller.py"]["helper"] == "pkg/util.py"
        # External star import added no extra keys
        assert len(name_to_source["pkg/caller.py"]) == 1


# ---------------------------------------------------------------------------
# Test 4: backward-compat — when file_symbols is None, star imports are skipped
# ---------------------------------------------------------------------------


class TestStarImportBackwardCompatNoneFileSymbols:
    """Passing file_symbols=None (default) preserves old behaviour: skip stars."""

    def test_star_import_skipped_when_file_symbols_none(self) -> None:
        imports_by_file = {
            "pkg/caller.py": [
                _make_star_entry("pkg/caller.py", ".sibling", is_relative=True),
            ],
        }
        module_to_file = {"pkg/sibling.py": "pkg/sibling.py"}

        # No file_symbols supplied — default None
        name_to_source, _ = _build_import_maps(imports_by_file, module_to_file)

        assert "pkg/caller.py" not in name_to_source
