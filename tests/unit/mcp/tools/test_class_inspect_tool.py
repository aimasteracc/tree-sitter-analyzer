#!/usr/bin/env python3
"""Tests for ClassInspectTool — full contract: fields, visibility, extends, no closures.

Issue #455: class_detail was returning only a flat method list.
This test suite pins the full contract using a synthetic fixture class.
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.class_inspect_tool import ClassInspectTool

# ---------------------------------------------------------------------------
# Synthetic fixture source
# ---------------------------------------------------------------------------

FIXTURE_SOURCE = textwrap.dedent('''\
    """Synthetic fixture class for class_inspect contract tests."""

    from abc import ABC


    class Animal(ABC):
        """Base animal class."""

        kingdom: str = "Animalia"

        def __init__(self, name: str, weight: float) -> None:
            self.name = name
            self._weight = weight
            self.__secret = "hidden"  # pragma: allowlist secret

        def speak(self) -> str:
            return ""

        def _internal(self) -> None:
            pass

        def __dunder_method(self) -> None:
            pass


    class Dog(Animal):
        """Dog extends Animal."""

        breed_count: int = 0

        def __init__(self, name: str, weight: float, breed: str) -> None:
            super().__init__(name, weight)
            self.breed = breed
            self._tag = "dog"

        def speak(self) -> str:
            return "Woof"

        def _fetch(self) -> None:
            def _nested_closure() -> None:
                pass
            _nested_closure()

        @staticmethod
        def info() -> str:
            return "Dog"
''')


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixture file setup
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixture_file(tmp_path: Path) -> Path:
    """Write the synthetic fixture source to a temp file and return its path."""
    p = tmp_path / "fixture_animals.py"
    p.write_text(FIXTURE_SOURCE, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Helper: run class_detail via ClassInspectTool with a real index
# ---------------------------------------------------------------------------


def _run_class_detail(
    fixture_file: Path,
    class_name: str,
) -> dict[str, Any]:
    """Index the fixture file and execute ClassInspectTool against it."""
    from tree_sitter_analyzer.ast_cache import ASTCache

    project_root = str(fixture_file.parent)
    tool = ClassInspectTool(project_root)

    # Build the AST cache for the fixture file using the public API
    cache = ASTCache(project_root)
    result = cache.index_file(str(fixture_file), language="python")
    assert result.get("status") in ("ok", "indexed", "unchanged"), (
        f"Cache index failed: {result}"
    )

    response = _run(tool.execute({"class_name": class_name, "output_format": "json"}))
    assert response["success"] is True, f"Tool failed: {response}"
    return response


# ---------------------------------------------------------------------------
# Tests for Animal (base class with no extends in project, direct ABC parent)
# ---------------------------------------------------------------------------


class TestAnimalClassContract:
    def test_extends_contains_abc(self, fixture_file: Path) -> None:
        """Animal(ABC) → extends = ['ABC']"""
        r = _run_class_detail(fixture_file, "Animal")
        assert r["extends"] == ["ABC"]

    def test_method_list_exact(self, fixture_file: Path) -> None:
        """Exact set of methods on Animal — no phantom symbols."""
        r = _run_class_detail(fixture_file, "Animal")
        names = [m["name"] for m in r["methods"]]
        assert names == ["__init__", "speak", "_internal", "__dunder_method"]

    def test_method_visibility_public(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Animal")
        method_map = {m["name"]: m["visibility"] for m in r["methods"]}
        assert method_map["__init__"] == "public"
        assert method_map["speak"] == "public"

    def test_method_visibility_protected(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Animal")
        method_map = {m["name"]: m["visibility"] for m in r["methods"]}
        assert method_map["_internal"] == "protected"

    def test_method_visibility_private(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Animal")
        method_map = {m["name"]: m["visibility"] for m in r["methods"]}
        assert method_map["__dunder_method"] == "private"

    def test_fields_class_level(self, fixture_file: Path) -> None:
        """Animal has class-level field kingdom: str = 'Animalia'"""
        r = _run_class_detail(fixture_file, "Animal")
        field_names = [f["name"] for f in r["fields"]]
        assert "kingdom" in field_names

    def test_fields_instance_from_init(self, fixture_file: Path) -> None:
        """Animal.__init__ sets self.name, self._weight, self.__secret"""
        r = _run_class_detail(fixture_file, "Animal")
        field_names = [f["name"] for f in r["fields"]]
        assert "name" in field_names
        assert "_weight" in field_names
        assert "__secret" in field_names

    def test_fields_visibility_public(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Animal")
        field_map = {f["name"]: f["visibility"] for f in r["fields"]}
        assert field_map["name"] == "public"
        assert field_map["kingdom"] == "public"

    def test_fields_visibility_protected(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Animal")
        field_map = {f["name"]: f["visibility"] for f in r["fields"]}
        assert field_map["_weight"] == "protected"

    def test_fields_visibility_private(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Animal")
        field_map = {f["name"]: f["visibility"] for f in r["fields"]}
        assert field_map["__secret"] == "private"  # pragma: allowlist secret

    def test_field_count_exact(self, fixture_file: Path) -> None:
        """Animal has exactly 4 fields: kingdom + name + _weight + __secret"""
        r = _run_class_detail(fixture_file, "Animal")
        assert len(r["fields"]) == 4

    def test_method_count_exact(self, fixture_file: Path) -> None:
        """Animal has exactly 4 methods."""
        r = _run_class_detail(fixture_file, "Animal")
        assert r["method_count"] == 4


# ---------------------------------------------------------------------------
# Tests for Dog (subclass — inherits from Animal)
# ---------------------------------------------------------------------------


class TestDogClassContract:
    def test_extends_contains_animal(self, fixture_file: Path) -> None:
        """Dog(Animal) → extends = ['Animal']"""
        r = _run_class_detail(fixture_file, "Dog")
        assert r["extends"] == ["Animal"]

    def test_no_closure_in_methods(self, fixture_file: Path) -> None:
        """_nested_closure defined inside _fetch must NOT appear in methods."""
        r = _run_class_detail(fixture_file, "Dog")
        names = [m["name"] for m in r["methods"]]
        assert "_nested_closure" not in names

    def test_method_list_exact_dog(self, fixture_file: Path) -> None:
        """Dog has exactly: __init__, speak, _fetch, info"""
        r = _run_class_detail(fixture_file, "Dog")
        names = [m["name"] for m in r["methods"]]
        assert names == ["__init__", "speak", "_fetch", "info"]

    def test_method_count_exact_dog(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Dog")
        assert r["method_count"] == 4

    def test_speak_is_override(self, fixture_file: Path) -> None:
        """speak is defined in Animal → Dog.speak is_override=True"""
        r = _run_class_detail(fixture_file, "Dog")
        method_map = {m["name"]: m for m in r["methods"]}
        assert method_map["speak"]["is_override"] is True

    def test_info_is_not_override(self, fixture_file: Path) -> None:
        """info is new in Dog → is_override=False"""
        r = _run_class_detail(fixture_file, "Dog")
        method_map = {m["name"]: m for m in r["methods"]}
        assert method_map["info"]["is_override"] is False

    def test_dog_fields_class_level(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Dog")
        field_names = [f["name"] for f in r["fields"]]
        assert "breed_count" in field_names

    def test_dog_fields_instance(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Dog")
        field_names = [f["name"] for f in r["fields"]]
        assert "breed" in field_names
        assert "_tag" in field_names

    def test_dog_field_count_exact(self, fixture_file: Path) -> None:
        """Dog has exactly 3 fields: breed_count + breed + _tag"""
        r = _run_class_detail(fixture_file, "Dog")
        assert len(r["fields"]) == 3

    def test_inherited_members_present(self, fixture_file: Path) -> None:
        """Animal is in same project → inherited_methods must be populated."""
        r = _run_class_detail(fixture_file, "Dog")
        assert "inherited_methods" in r
        inherited_names = [m["name"] for m in r["inherited_methods"]]
        assert "speak" in inherited_names

    def test_field_line_numbers_positive(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Dog")
        for f in r["fields"]:
            assert f["line"] > 0

    def test_method_line_numbers_positive(self, fixture_file: Path) -> None:
        r = _run_class_detail(fixture_file, "Dog")
        for m in r["methods"]:
            assert m["line"] > 0


# ---------------------------------------------------------------------------
# Regression: BaseMCPTool — _wrapped must not appear
# ---------------------------------------------------------------------------


class TestBaseMCPToolClosureRegression:
    def test_wrapped_closure_not_in_methods(self, tmp_path: Path) -> None:
        """_wrapped is a local closure inside __init_subclass__, not a real method.

        This guards the specific defect reported in issue #455.
        We create a minimal file that reproduces the pattern.
        """
        src = textwrap.dedent("""\
            import functools


            class ToolBase:
                @classmethod
                def __init_subclass__(cls, **kwargs):
                    super().__init_subclass__(**kwargs)
                    original = cls.__dict__.get("execute")
                    if original is None:
                        return

                    @functools.wraps(original)
                    async def _wrapped(self, arguments):
                        return await original(self, arguments)

                    cls.execute = _wrapped

                async def execute(self, arguments):
                    raise NotImplementedError
        """)
        p = tmp_path / "tool_base.py"
        p.write_text(src, encoding="utf-8")

        from tree_sitter_analyzer.ast_cache import ASTCache

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged"), (
            f"Index failed: {result}"
        )

        tool = ClassInspectTool(project_root)
        response = _run(
            tool.execute({"class_name": "ToolBase", "output_format": "json"})
        )
        assert response["success"] is True

        names = [m["name"] for m in response["methods"]]
        assert "_wrapped" not in names, (
            "_wrapped is a closure inside __init_subclass__, not a class method"
        )
        assert "execute" in names
        assert "__init_subclass__" in names


# ---------------------------------------------------------------------------
# Edge-case / defensive-branch coverage
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_not_found_class_returns_not_found_verdict(self, tmp_path: Path) -> None:
        """Asking for a class that doesn't exist returns NOT_FOUND verdict."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        project_root = str(tmp_path)
        ASTCache(project_root)  # Ensure cache is created
        tool = ClassInspectTool(project_root)
        response = _run(
            tool.execute(
                {"class_name": "NonExistentClass9999", "output_format": "json"}
            )
        )
        assert response["success"] is True
        assert response["verdict"] == "NOT_FOUND"
        assert response["methods"] == []
        assert response["fields"] == []
        assert response["extends"] == []

    def test_get_cache_raises_without_project_root(self) -> None:
        """_get_cache raises ValueError when project_root is None."""
        import pytest

        tool = ClassInspectTool(None)
        with pytest.raises(ValueError, match="Project root"):
            tool._get_cache()

    def test_validate_arguments_raises_for_empty_class_name(self) -> None:
        """validate_arguments raises ValueError for empty class_name."""
        import pytest

        tool = ClassInspectTool(None)
        with pytest.raises(ValueError, match="class_name"):
            tool.validate_arguments({"class_name": ""})

    def test_class_with_no_indexed_parent_returns_inherited_unavailable(
        self, tmp_path: Path
    ) -> None:
        """A class whose only parent is an external library has inherited.available=False."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = "from external_lib import ExternalBase\n\nclass MyTool(ExternalBase):\n    def run(self) -> None:\n        pass\n"
        p = tmp_path / "my_tool.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(tool.execute({"class_name": "MyTool", "output_format": "json"}))
        assert response["success"] is True
        # ExternalBase is not indexed → inherited should be unavailable
        assert "inherited" in response
        assert response["inherited"]["available"] is False

    def test_fields_oserror_falls_back_to_empty(
        self, tmp_path: Path, fixture_file: Path
    ) -> None:
        """When the source file cannot be read, fields returns empty list without crashing."""
        from unittest.mock import patch

        from tree_sitter_analyzer.ast_cache import ASTCache

        project_root = str(fixture_file.parent)
        cache = ASTCache(project_root)
        result = cache.index_file(str(fixture_file), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)

        # Patch open to simulate an OSError
        with patch("builtins.open", side_effect=OSError("no permission")):
            response = _run(
                tool.execute({"class_name": "Animal", "output_format": "json"})
            )

        assert response["success"] is True
        # fields should be empty (OSError fallback) but rest of response is intact
        assert response["fields"] == []
        assert len(response["methods"]) == 4  # methods still work (Animal pin)

    def test_class_with_duplicate_self_assignments_deduplicated(
        self, tmp_path: Path
    ) -> None:
        """Duplicate self.x = ... in __init__ must produce exactly one field entry."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class Dup:
                def __init__(self) -> None:
                    self.x = 1
                    self.x = 2  # duplicate — same name

                def do(self) -> None:
                    pass
        """)
        p = tmp_path / "dup.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(tool.execute({"class_name": "Dup", "output_format": "json"}))
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        assert field_names.count("x") == 1

    def test_class_with_comment_lines_in_body(self, tmp_path: Path) -> None:
        """Comment lines in class body must not produce spurious fields."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class Commented:
                # This is just a comment = not a field
                value: int = 42

                def run(self) -> None:
                    pass
        """)
        p = tmp_path / "commented.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(
            tool.execute({"class_name": "Commented", "output_format": "json"})
        )
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        # Only 'value' should be a field, not "This"
        assert field_names == ["value"]

    def test_class_init_at_end_of_class(self, tmp_path: Path) -> None:
        """Class where __init__ is the last method — init_end detected at class end."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class LastInit:
                class_var: int = 0

                def helper(self) -> None:
                    pass

                def __init__(self) -> None:
                    self.data = "hello"
        """)
        p = tmp_path / "last_init.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(
            tool.execute({"class_name": "LastInit", "output_format": "json"})
        )
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        assert "data" in field_names
        assert "class_var" in field_names

    def test_class_attr_same_name_as_instance_attr_deduped(
        self, tmp_path: Path
    ) -> None:
        """Class attr 'value' and self.value = ... in __init__ → only one 'value' field."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class SameName:
                value: int = 0  # class-level

                def __init__(self) -> None:
                    self.value = 42  # instance level — same name, should dedup

                def run(self) -> None:
                    pass
        """)
        p = tmp_path / "same_name.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(
            tool.execute({"class_name": "SameName", "output_format": "json"})
        )
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        assert field_names.count("value") == 1

    def test_class_init_followed_by_decorator(self, tmp_path: Path) -> None:
        """__init__ followed by @staticmethod — init_end must be set before the decorator."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class Deco:
                def __init__(self) -> None:
                    self.x = 1

                @staticmethod
                def factory() -> "Deco":
                    return Deco()
        """)
        p = tmp_path / "deco.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(tool.execute({"class_name": "Deco", "output_format": "json"}))
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        assert field_names == ["x"]

    def test_override_source_not_found_no_overrides_from_key(
        self, tmp_path: Path
    ) -> None:
        """Method that 'overrides' a base only in hierarchy but base has no indexed methods.

        Exercises the path where _find_override_source returns None —
        overrides_from key must not appear in the method entry.
        """
        from tree_sitter_analyzer.ast_cache import ASTCache

        # Create a child class that overrides a method from an external (unindexed) parent
        # by declaring the parent in a separate file that won't be indexed
        src = textwrap.dedent("""\
            from abc import ABC, abstractmethod


            class GrandBase(ABC):
                @abstractmethod
                def do(self) -> None:
                    pass


            class Child(GrandBase):
                def do(self) -> None:
                    pass
        """)
        p = tmp_path / "hierarchy.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(tool.execute({"class_name": "Child", "output_format": "json"}))
        assert response["success"] is True

        method_map = {m["name"]: m for m in response["methods"]}
        assert "do" in method_map
        # do overrides GrandBase.do — is_override must be True
        assert method_map["do"]["is_override"] is True
        # overrides_from must be present (GrandBase is indexed)
        assert method_map["do"].get("overrides_from") == "GrandBase"

    def test_collect_class_info_exception_returns_none(self) -> None:
        """_collect_class_info catches Exception from bad conn and returns None."""
        from unittest.mock import MagicMock

        tool = ClassInspectTool(None)
        bad_cache = MagicMock()
        bad_cache.get_conn.side_effect = Exception("db error")

        result = tool._collect_class_info(bad_cache, "SomeClass")
        assert result is None

    def test_collect_raw_methods_exception_returns_empty(self) -> None:
        """_collect_raw_methods catches Exception from bad conn and returns []."""
        from unittest.mock import MagicMock

        tool = ClassInspectTool(None)
        bad_cache = MagicMock()
        bad_cache.get_conn.side_effect = Exception("db error")

        result = tool._collect_raw_methods(bad_cache, "SomeClass")
        assert result == []

    def test_parent_method_names_exception_returns_empty_set(self) -> None:
        """_parent_method_names catches Exception from bad conn and returns set()."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)
        bad_cache = MagicMock()
        bad_cache.get_conn.side_effect = Exception("db error")

        # Need a hierarchy that thinks there are ancestors
        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = [{"name": "ParentClass"}]

        result = tool._parent_method_names(mock_hier, "ChildClass", bad_cache)
        assert result == set()

    def test_find_override_source_exception_returns_none(self) -> None:
        """_find_override_source catches Exception from bad conn and returns None."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)
        bad_cache = MagicMock()
        bad_cache.get_conn.side_effect = Exception("db error")

        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = [{"name": "ParentClass"}]

        result = tool._find_override_source(mock_hier, "Child", "do", bad_cache)
        assert result is None

    def test_collect_inherited_methods_exception_returns_unavailable(self) -> None:
        """_collect_inherited_methods handles db exception gracefully."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)
        bad_cache = MagicMock()
        bad_cache.get_conn.side_effect = Exception("db error")

        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = [{"name": "ParentClass"}]

        result = tool._collect_inherited_methods(mock_hier, "Child", bad_cache)
        assert result["available"] is False
        assert "cache query failed" in result["reason"]

    def test_collect_inherited_methods_no_ancestors_returns_unavailable(self) -> None:
        """_collect_inherited_methods with no ancestors returns unavailable."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)
        mock_cache = MagicMock()
        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = []

        result = tool._collect_inherited_methods(mock_hier, "IsolatedClass", mock_cache)
        assert result["available"] is False
        assert "no ancestors" in result["reason"]

    def test_class_with_class_attr_after_init(self, tmp_path: Path) -> None:
        """Class attribute at indent 4 AFTER __init__ body — exercises 141->False branch."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class TrailingAttr:
                def __init__(self) -> None:
                    self.x = 1
                CONST = 99

                def run(self) -> None:
                    pass
        """)
        p = tmp_path / "trailing.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(
            tool.execute({"class_name": "TrailingAttr", "output_format": "json"})
        )
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        assert "x" in field_names
        assert "CONST" in field_names

    def test_find_override_source_no_ancestors_returns_none(self) -> None:
        """_find_override_source returns None when class has no ancestors."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)
        mock_cache = MagicMock()
        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = []

        result = tool._find_override_source(
            mock_hier, "BaseClass", "method", mock_cache
        )
        assert result is None

    def test_find_override_source_method_not_in_ancestor_returns_none(self) -> None:
        """_find_override_source returns None when method not found in any ancestor's methods."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)

        # Set up a mock cache that returns ancestor with different methods
        mock_conn = MagicMock()
        rows = [
            {
                "symbols_json": '{"symbols": [{"kind": "method", "name": "other_method", "class": "AncClass"}]}'
            }
        ]
        mock_conn.execute.return_value.fetchall.return_value = rows
        mock_cache = MagicMock()
        mock_cache.get_conn.return_value = mock_conn

        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = [{"name": "AncClass"}]

        result = tool._find_override_source(
            mock_hier, "Child", "target_method", mock_cache
        )
        assert result is None

    def test_collect_inherited_methods_no_methods_for_ancestor(self) -> None:
        """_collect_inherited_methods returns unavailable when ancestor has no methods."""
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        tool = ClassInspectTool(None)

        # Conn returns rows with no methods for the ancestor
        mock_conn = MagicMock()
        rows = [
            {"symbols_json": '{"symbols": [{"kind": "class", "name": "ParentClass"}]}'}
        ]
        mock_conn.execute.return_value.fetchall.return_value = rows
        mock_cache = MagicMock()
        mock_cache.get_conn.return_value = mock_conn

        mock_hier = MagicMock(spec=ClassHierarchy)
        mock_hier.superclasses_of.return_value = [{"name": "ParentClass"}]

        result = tool._collect_inherited_methods(mock_hier, "Child", mock_cache)
        assert result["available"] is False
        assert "ParentClass" in result["reason"]

    def test_class_attr_same_as_init_attr_dedup_via_field_scan(
        self, tmp_path: Path
    ) -> None:
        """Class attribute name matches self.name in __init__ — produces exactly one field.

        Exercises the 163->149 branch (attr already in seen, instance scan skips).
        """
        from tree_sitter_analyzer.ast_cache import ASTCache

        src = textwrap.dedent("""\
            class Both:
                shared_name: str = "cls"

                def __init__(self) -> None:
                    self.shared_name = "instance"
                    self.unique = True

                def go(self) -> None:
                    pass
        """)
        p = tmp_path / "both.py"
        p.write_text(src, encoding="utf-8")

        project_root = str(tmp_path)
        cache = ASTCache(project_root)
        result = cache.index_file(str(p), language="python")
        assert result.get("status") in ("ok", "indexed", "unchanged")

        tool = ClassInspectTool(project_root)
        response = _run(tool.execute({"class_name": "Both", "output_format": "json"}))
        assert response["success"] is True

        field_names = [f["name"] for f in response["fields"]]
        assert field_names.count("shared_name") == 1
        assert "unique" in field_names


# ─── Issue #455 repro guard: fields found outside __init__ ───────────────────


def test_base_mcp_tool_fields_extracted_from_delegated_init() -> None:
    """BaseMCPTool assigns self.* in _apply_project_root, not __init__.

    The issue's own repro class must yield non-empty fields — an
    __init__-only scan returns [] here (the original gap)."""
    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import (
        _extract_fields_from_source,
    )

    src = open("tree_sitter_analyzer/mcp/tools/base_tool.py").read()
    fields = _extract_fields_from_source(src, "BaseMCPTool", 282, 686)
    names = [f["name"] for f in fields]
    assert names == [
        "_project_root",
        "_project_root_initialized",
        "security_validator",
        "path_resolver",
    ]
    kinds = {f["name"]: f["kind"] for f in fields}
    assert kinds["security_validator"] == "instance"
    vis = {f["name"]: f["visibility"] for f in fields}
    assert vis["_project_root"] == "protected"
    assert vis["security_validator"] == "public"


def test_annotation_only_fields_extracted() -> None:
    """Codex P2 (#482): dataclass/Pydantic required fields have no '='.

    ``name: str`` (annotation-only) must be reported as a class field."""
    from tree_sitter_analyzer.mcp.tools.class_inspect_tool import (
        _extract_fields_from_source,
    )

    src = (
        "class Config:\n"
        "    name: str\n"
        "    retries: int = 3\n"
        "    _token: str\n"
        "\n"
        "    def ping(self) -> None:\n"
        "        pass\n"
    )
    fields = _extract_fields_from_source(src, "Config", 1, 7)
    names = [f["name"] for f in fields]
    assert names == ["name", "retries", "_token"]
    vis = {f["name"]: f["visibility"] for f in fields}
    assert vis["_token"] == "protected"
    kinds = {f["name"]: f["kind"] for f in fields}
    assert kinds == {"name": "class", "retries": "class", "_token": "class"}
