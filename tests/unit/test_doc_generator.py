"""
Tests for features/doc_generator.py module.

TDD: Testing documentation generation from code.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.doc_generator import (
    FunctionDoc,
    ClassDoc,
    ModuleDoc,
    DocumentationGenerator,
    generate_docs,
)


class TestFunctionDoc:
    """Test FunctionDoc dataclass."""

    def test_basic_creation(self) -> None:
        """Should create FunctionDoc."""
        doc = FunctionDoc(name="test", docstring="Test function")
        assert doc.name == "test"
        assert doc.docstring == "Test function"
        assert doc.parameters == []

    def test_with_parameters(self) -> None:
        """Should store parameters."""
        doc = FunctionDoc(name="func", docstring=None, parameters=["a", "b"])
        assert doc.parameters == ["a", "b"]


class TestClassDoc:
    """Test ClassDoc dataclass."""

    def test_basic_creation(self) -> None:
        """Should create ClassDoc."""
        doc = ClassDoc(name="MyClass", docstring="A class")
        assert doc.name == "MyClass"
        assert doc.methods == []

    def test_with_methods(self) -> None:
        """Should store methods."""
        method = FunctionDoc(name="method1", docstring="")
        doc = ClassDoc(name="MyClass", docstring="", methods=[method])
        assert len(doc.methods) == 1


class TestModuleDoc:
    """Test ModuleDoc dataclass."""

    def test_basic_creation(self) -> None:
        """Should create ModuleDoc."""
        doc = ModuleDoc(name="module", file_path="test.py", docstring="Module doc")
        assert doc.name == "module"
        assert doc.classes == []
        assert doc.functions == []


class TestDocumentationGenerator:
    """Test DocumentationGenerator class."""

    def test_extract_from_file_basic(self) -> None:
        """Should extract documentation from file."""
        generator = DocumentationGenerator()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('"""Module docstring."""\n\ndef hello():\n    """Hello function."""\n    pass\n')
            f.flush()
            file_path = Path(f.name)
        
        try:
            doc = generator.extract_from_file(file_path)
            
            assert doc.name == file_path.stem
            assert doc.docstring == "Module docstring."
            assert len(doc.functions) >= 1
        finally:
            file_path.unlink()

    def test_extract_classes(self) -> None:
        """Should extract class documentation."""
        generator = DocumentationGenerator()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''
class MyClass:
    """A sample class."""
    
    def method(self, x):
        """A method."""
        pass
''')
            f.flush()
            file_path = Path(f.name)
        
        try:
            doc = generator.extract_from_file(file_path)
            
            assert len(doc.classes) >= 1
            cls = doc.classes[0]
            assert cls.name == "MyClass"
            assert cls.docstring == "A sample class."
            assert len(cls.methods) >= 1
        finally:
            file_path.unlink()

    def test_extract_function_parameters(self) -> None:
        """Should extract function parameters."""
        generator = DocumentationGenerator()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('def process(a, b, c):\n    pass\n')
            f.flush()
            file_path = Path(f.name)
        
        try:
            doc = generator.extract_from_file(file_path)
            
            func = doc.functions[0]
            assert "a" in func.parameters
            assert "b" in func.parameters
            assert "c" in func.parameters
        finally:
            file_path.unlink()

    def test_handle_syntax_error(self) -> None:
        """Should handle files with syntax errors."""
        generator = DocumentationGenerator()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("{{{ invalid python")
            f.flush()
            file_path = Path(f.name)
        
        try:
            doc = generator.extract_from_file(file_path)
            
            assert doc.name == file_path.stem
            assert doc.docstring is None
        finally:
            file_path.unlink()

    def test_generate_markdown_basic(self) -> None:
        """Should generate basic markdown."""
        generator = DocumentationGenerator()
        
        module_doc = ModuleDoc(
            name="test_module",
            file_path="test_module.py",
            docstring="Module description"
        )
        
        markdown = generator.generate_markdown(module_doc)
        
        assert "# test_module" in markdown
        assert "Module description" in markdown
        assert "`test_module.py`" in markdown

    def test_generate_markdown_with_classes(self) -> None:
        """Should include classes in markdown."""
        generator = DocumentationGenerator()
        
        method = FunctionDoc(name="method1", docstring="Method doc", parameters=["self"])
        cls = ClassDoc(name="MyClass", docstring="Class doc", methods=[method])
        module_doc = ModuleDoc(
            name="module",
            file_path="module.py",
            docstring=None,
            classes=[cls]
        )
        
        markdown = generator.generate_markdown(module_doc)
        
        assert "## Classes" in markdown
        assert "### MyClass" in markdown
        assert "Class doc" in markdown
        assert "method1" in markdown

    def test_generate_markdown_with_functions(self) -> None:
        """Should include functions in markdown."""
        generator = DocumentationGenerator()
        
        func = FunctionDoc(name="process", docstring="Process data", parameters=["x", "y"])
        module_doc = ModuleDoc(
            name="utils",
            file_path="utils.py",
            docstring=None,
            functions=[func]
        )
        
        markdown = generator.generate_markdown(module_doc)
        
        assert "## Functions" in markdown
        assert "`process(x, y)`" in markdown
        assert "Process data" in markdown

    def test_generate_markdown_no_docstring(self) -> None:
        """Should handle missing docstrings."""
        generator = DocumentationGenerator()
        
        func = FunctionDoc(name="nodoc", docstring=None, parameters=[])
        module_doc = ModuleDoc(
            name="mod",
            file_path="mod.py",
            docstring=None,
            functions=[func]
        )
        
        markdown = generator.generate_markdown(module_doc)
        
        assert "No documentation available" in markdown

    def test_generate_directory_docs(self) -> None:
        """Should generate docs for directory."""
        generator = DocumentationGenerator()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            
            (src_dir / "module1.py").write_text('"""Module 1."""\ndef func(): pass\n')
            (src_dir / "module2.py").write_text('"""Module 2."""\nclass C: pass\n')
            
            output_dir = Path(tmpdir) / "docs"
            generator.generate_directory_docs(src_dir, output_dir)
            
            assert output_dir.exists()
            assert (output_dir / "module1.md").exists()
            assert (output_dir / "module2.md").exists()


class TestGenerateDocs:
    """Test generate_docs convenience function."""

    def test_generate_for_file(self) -> None:
        """Should generate docs for single file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "source.py"
            src_file.write_text('"""Source module."""\ndef main(): pass\n')
            
            output_dir = Path(tmpdir) / "output"
            result = generate_docs(src_file, output_dir)
            
            assert result["success"] is True
            assert result["files_generated"] == 1
            assert Path(result["output_file"]).exists()

    def test_generate_for_directory(self) -> None:
        """Should generate docs for directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "a.py").write_text("x = 1\n")
            (src_dir / "b.py").write_text("y = 2\n")
            
            output_dir = Path(tmpdir) / "docs"
            result = generate_docs(src_dir, output_dir)
            
            assert result["success"] is True
            assert result["files_generated"] >= 2

    def test_generate_nonexistent_path(self) -> None:
        """Should return error for non-existent path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_docs(Path("/nonexistent"), Path(tmpdir))
            
            assert result["success"] is False
            assert "error" in result
