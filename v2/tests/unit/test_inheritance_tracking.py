"""
Unit tests for class inheritance chain tracking.

Sprint 4: trace_inheritance() and find_implementations().
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import ProjectCodeMap


@pytest.fixture
def cross_file_project():
    """Return path to cross-file test project with inheritance fixture."""
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def result(cross_file_project):
    """Pre-scanned result for the cross-file project."""
    mapper = ProjectCodeMap()
    return mapper.scan(str(cross_file_project), extensions=[".py"])


class TestSymbolInfoBases:
    """Test that SymbolInfo includes base class information."""

    def test_class_with_bases_has_bases_field(self, result):
        """A class with parent classes should have bases populated."""
        dog = next((s for s in result.symbols if s.name == "Dog" and s.kind == "class"), None)
        assert dog is not None, "Dog class not found in symbols"
        assert hasattr(dog, "bases"), "SymbolInfo must have 'bases' attribute"
        assert "Mammal" in dog.bases, f"Dog.bases should contain 'Mammal', got {dog.bases}"

    def test_class_without_bases_has_empty_bases(self, result):
        """A class with no parent should have empty bases."""
        serializable = next(
            (s for s in result.symbols if s.name == "Serializable" and s.kind == "class"), None
        )
        assert serializable is not None
        assert serializable.bases == [] or serializable.bases == ()

    def test_multiple_bases(self, result):
        """A class with multiple parents should list all."""
        pdog = next(
            (s for s in result.symbols if s.name == "PersistentDog" and s.kind == "class"), None
        )
        assert pdog is not None
        assert "Dog" in pdog.bases
        assert "Serializable" in pdog.bases
        assert "Persistable" in pdog.bases

    def test_abc_base(self, result):
        """ABC base class should be captured."""
        animal = next(
            (s for s in result.symbols if s.name == "Animal" and s.kind == "class"), None
        )
        assert animal is not None
        assert "ABC" in animal.bases


class TestTraceInheritance:
    """Test trace_inheritance() method on CodeMapResult."""

    def test_trace_inheritance_returns_chain(self, result):
        """trace_inheritance should return the full inheritance chain."""
        chain = result.trace_inheritance("Dog")
        assert chain is not None
        assert hasattr(chain, "target")
        assert chain.target is not None
        assert chain.target.name == "Dog"

    def test_trace_inheritance_includes_parents(self, result):
        """Chain should include direct and transitive parents."""
        chain = result.trace_inheritance("Dog")
        parent_names = [s.name for s in chain.ancestors]
        assert "Mammal" in parent_names
        assert "Animal" in parent_names

    def test_trace_inheritance_deep_chain(self, result):
        """StrayDog -> Dog -> Mammal -> Animal."""
        chain = result.trace_inheritance("StrayDog")
        parent_names = [s.name for s in chain.ancestors]
        assert "Dog" in parent_names
        assert "Mammal" in parent_names
        assert "Animal" in parent_names

    def test_trace_inheritance_multiple_parents(self, result):
        """PersistentDog -> Dog + Serializable + Persistable."""
        chain = result.trace_inheritance("PersistentDog")
        parent_names = [s.name for s in chain.ancestors]
        assert "Dog" in parent_names
        assert "Serializable" in parent_names

    def test_trace_inheritance_not_found(self, result):
        """Nonexistent class returns empty chain."""
        chain = result.trace_inheritance("NoSuchClass")
        assert chain.target is None

    def test_trace_inheritance_has_children(self, result):
        """Mammal should have Dog and Cat as children."""
        chain = result.trace_inheritance("Mammal")
        child_names = [s.name for s in chain.descendants]
        assert "Dog" in child_names
        assert "Cat" in child_names

    def test_trace_inheritance_toon_output(self, result):
        """Chain should produce TOON output."""
        chain = result.trace_inheritance("Dog")
        toon = chain.to_toon()
        assert "Dog" in toon
        assert "Mammal" in toon


class TestFindImplementations:
    """Test find_implementations() method."""

    def test_find_implementations_of_animal(self, result):
        """All classes inheriting from Animal should be found."""
        impls = result.find_implementations("Animal")
        impl_names = {s.name for s in impls}
        assert "Mammal" in impl_names
        assert "Dog" in impl_names
        assert "Cat" in impl_names

    def test_find_implementations_of_serializable(self, result):
        """PersistentDog implements Serializable."""
        impls = result.find_implementations("Serializable")
        impl_names = {s.name for s in impls}
        assert "PersistentDog" in impl_names

    def test_find_implementations_no_children(self, result):
        """StrayDog has no children."""
        impls = result.find_implementations("StrayDog")
        assert len(impls) == 0

    def test_find_implementations_not_found(self, result):
        """Nonexistent class returns empty."""
        impls = result.find_implementations("NoSuchClass")
        assert len(impls) == 0
