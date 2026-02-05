"""
Unit tests for ImportResolver (E3 enhancement).

Tests import parsing and resolution for cross-file call tracking.
"""

from pathlib import Path

from tree_sitter_analyzer_v2.graph.imports import Import, ImportResolver


class TestImportParsing:
    """Tests for parsing import statements from Python files."""

    def test_parse_simple_import(self, tmp_path: Path):
        """Test parsing simple import statement: import os."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\n")

        # Parse imports
        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        # Verify
        assert len(imports) == 1
        assert imports[0].module == "os"
        assert imports[0].names == []
        assert imports[0].alias is None
        assert imports[0].import_type == "absolute"
        assert imports[0].level == 0
        assert imports[0].wildcard is False

    def test_parse_import_with_alias(self, tmp_path: Path):
        """Test parsing import with alias: import numpy as np."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import numpy as np\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module == "numpy"
        assert imports[0].alias == {"numpy": "np"}
        assert imports[0].import_type == "absolute"

    def test_parse_from_import(self, tmp_path: Path):
        """Test parsing from-import: from utils import helper."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from utils import helper\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module == "utils"
        assert imports[0].names == ["helper"]
        assert imports[0].import_type == "absolute"

    def test_parse_from_import_multiple(self, tmp_path: Path):
        """Test parsing from-import with multiple names."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from utils import helper, validator\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module == "utils"
        assert set(imports[0].names) == {"helper", "validator"}

    def test_parse_from_import_with_alias(self, tmp_path: Path):
        """Test parsing from-import with alias: from x import y as z."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from utils import helper as h\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module == "utils"
        assert imports[0].names == ["helper"]
        assert imports[0].alias == {"helper": "h"}

    def test_parse_relative_import_sibling(self, tmp_path: Path):
        """Test parsing relative import: from . import sibling."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from . import sibling\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].import_type == "relative"
        assert imports[0].level == 1
        assert imports[0].names == ["sibling"]

    def test_parse_relative_import_parent(self, tmp_path: Path):
        """Test parsing relative import from parent: from .. import parent."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from .. import parent\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].import_type == "relative"
        assert imports[0].level == 2

    def test_parse_relative_import_with_module(self, tmp_path: Path):
        """Test parsing relative import with module: from ..utils import helper."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from ..utils import helper\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].import_type == "relative"
        assert imports[0].level == 2
        assert imports[0].module == "utils"
        assert imports[0].names == ["helper"]

    def test_parse_wildcard_import(self, tmp_path: Path):
        """Test parsing wildcard import: from utils import *."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from utils import *\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module == "utils"
        assert imports[0].wildcard is True
        assert imports[0].names == ["*"]

    def test_parse_multiple_imports(self, tmp_path: Path):
        """Test parsing file with multiple import statements."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import os
import sys
from utils import helper
from . import sibling
"""
        )

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 4
        modules = [imp.module for imp in imports]
        assert "os" in modules
        assert "sys" in modules
        assert "utils" in modules

    def test_parse_dotted_module_name(self, tmp_path: Path):
        """Test parsing dotted module name: from package.subpackage import module."""
        test_file = tmp_path / "test.py"
        test_file.write_text("from package.subpackage.module import func\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module == "package.subpackage.module"
        assert imports[0].names == ["func"]

    def test_parse_empty_file(self, tmp_path: Path):
        """Test parsing file with no imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# Just a comment\nx = 42\n")

        resolver = ImportResolver(tmp_path)
        imports = resolver.parse_imports(test_file)

        assert len(imports) == 0

    def test_parse_file_with_syntax_error(self, tmp_path: Path):
        """Test parsing file with syntax errors (should handle gracefully)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nthis is invalid syntax\n")

        resolver = ImportResolver(tmp_path)
        # Should not crash, may return partial results
        imports = resolver.parse_imports(test_file)
        # At minimum, should find the valid import
        assert any(imp.module == "os" for imp in imports)


class TestAbsoluteImportResolution:
    """Tests for resolving absolute imports to file paths."""

    def test_resolve_absolute_simple_module(self, tmp_path: Path):
        """Test resolving simple module: from utils import helper -> utils.py."""
        # Create project structure
        (tmp_path / "utils.py").write_text("def helper(): pass\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="utils",
            names=["helper"],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is not None
        assert result == tmp_path / "utils.py"

    def test_resolve_absolute_nested_module(self, tmp_path: Path):
        """Test resolving nested module: from package.module import func."""
        # Create project structure
        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "module.py").write_text("def func(): pass\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="package.module",
            names=["func"],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is not None
        assert result == package_dir / "module.py"

    def test_resolve_absolute_package_init(self, tmp_path: Path):
        """Test resolving package to __init__.py: from package import x."""
        # Create package with __init__.py
        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("def x(): pass\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="package",
            names=["x"],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is not None
        assert result == package_dir / "__init__.py"

    def test_resolve_absolute_external_module(self, tmp_path: Path):
        """Test resolving external module returns None: import os."""
        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="os",
            names=[],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is None  # External module, not in project

    def test_resolve_absolute_nonexistent_module(self, tmp_path: Path):
        """Test resolving non-existent module returns None."""
        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="nonexistent",
            names=[],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is None

    def test_resolve_absolute_deep_nesting(self, tmp_path: Path):
        """Test resolving deeply nested module: a.b.c.d."""
        # Create deep structure
        path = tmp_path / "a" / "b" / "c"
        path.mkdir(parents=True)
        (path / "d.py").write_text("def func(): pass\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="a.b.c.d",
            names=["func"],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is not None
        assert result == path / "d.py"

    def test_resolve_absolute_prefer_py_over_init(self, tmp_path: Path):
        """Test that module.py is preferred over module/__init__.py."""
        # Create both module.py and module/__init__.py
        (tmp_path / "module.py").write_text("# module.py\n")
        module_dir = tmp_path / "module"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("# __init__.py\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="module",
            names=[],
            alias=None,
            import_type="absolute",
            level=0,
            wildcard=False,
        )

        result = resolver._resolve_absolute(imp)
        assert result is not None
        # Should prefer module.py
        assert result == tmp_path / "module.py"


class TestRelativeImportResolution:
    """Tests for resolving relative imports to file paths."""

    def test_resolve_relative_sibling(self, tmp_path: Path):
        """Test resolving sibling import: from . import sibling."""
        # Create project structure
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "main.py").write_text("# main\n")
        (app_dir / "sibling.py").write_text("# sibling\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="",
            names=["sibling"],
            alias=None,
            import_type="relative",
            level=1,
            wildcard=False,
        )

        result = resolver._resolve_relative(imp, app_dir / "main.py")
        assert result is not None
        assert result == app_dir / "sibling.py"

    def test_resolve_relative_parent(self, tmp_path: Path):
        """Test resolving parent import: from .. import parent."""
        # Create nested structure
        app_dir = tmp_path / "app"
        sub_dir = app_dir / "sub"
        sub_dir.mkdir(parents=True)
        (sub_dir / "child.py").write_text("# child\n")
        (app_dir / "parent.py").write_text("# parent\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="",
            names=["parent"],
            alias=None,
            import_type="relative",
            level=2,
            wildcard=False,
        )

        result = resolver._resolve_relative(imp, sub_dir / "child.py")
        assert result is not None
        assert result == app_dir / "parent.py"

    def test_resolve_relative_with_module(self, tmp_path: Path):
        """Test resolving relative import with module: from ..utils import helper."""
        # Create structure
        app_dir = tmp_path / "app"
        sub_dir = app_dir / "sub"
        utils_dir = app_dir / "utils"
        sub_dir.mkdir(parents=True)
        utils_dir.mkdir()
        (sub_dir / "main.py").write_text("# main\n")
        (utils_dir / "helper.py").write_text("# helper\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="utils",
            names=["helper"],
            alias=None,
            import_type="relative",
            level=2,
            wildcard=False,
        )

        result = resolver._resolve_relative(imp, sub_dir / "main.py")
        assert result is not None
        assert result == utils_dir / "helper.py"

    def test_resolve_relative_to_package_init(self, tmp_path: Path):
        """Test resolving relative import to package __init__.py."""
        # Create package structure
        app_dir = tmp_path / "app"
        pkg_dir = app_dir / "pkg"
        pkg_dir.mkdir(parents=True)
        (app_dir / "main.py").write_text("# main\n")
        (pkg_dir / "__init__.py").write_text("# pkg init\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="pkg",
            names=[],
            alias=None,
            import_type="relative",
            level=1,
            wildcard=False,
        )

        result = resolver._resolve_relative(imp, app_dir / "main.py")
        assert result is not None
        assert result == pkg_dir / "__init__.py"

    def test_resolve_relative_invalid_level(self, tmp_path: Path):
        """Test resolving relative import with too many levels returns None."""
        # Only one level of directories
        (tmp_path / "main.py").write_text("# main\n")

        resolver = ImportResolver(tmp_path)
        imp = Import(
            module="",
            names=["something"],
            alias=None,
            import_type="relative",
            level=3,  # Too many levels
            wildcard=False,
        )

        result = resolver._resolve_relative(imp, tmp_path / "main.py")
        # Should return None (goes above project root)
        assert result is None

    def test_resolve_relative_deep_nesting(self, tmp_path: Path):
        """Test resolving relative import with deep nesting: from .....x import y."""
        # Create deep structure
        # tmp_path/a/b/c/d/deep.py
        a = tmp_path / "a"
        b = a / "b"
        c = b / "c"
        d = c / "d"
        d.mkdir(parents=True)
        (d / "deep.py").write_text("# deep\n")
        (tmp_path / "top.py").write_text("# top\n")

        resolver = ImportResolver(tmp_path)
        # Level 5 means ..... (5 dots) = go up 4 levels from d/ to tmp_path/
        imp = Import(
            module="",
            names=["top"],
            alias=None,
            import_type="relative",
            level=5,  # Changed from 4 to 5
            wildcard=False,
        )

        result = resolver._resolve_relative(imp, d / "deep.py")
        assert result is not None
        assert result == tmp_path / "top.py"


class TestImportGraphConstruction:
    """Tests for building import dependency graph."""

    def test_build_import_graph_simple(self, tmp_path: Path):
        """Test building graph with simple import relationship."""
        # Create files
        (tmp_path / "main.py").write_text("from utils import helper\n")
        (tmp_path / "utils.py").write_text("def helper(): pass\n")

        resolver = ImportResolver(tmp_path)
        files = [tmp_path / "main.py", tmp_path / "utils.py"]
        graph = resolver.build_import_graph(files)

        # Check edge exists
        assert graph.has_edge(str(tmp_path / "main.py"), str(tmp_path / "utils.py"))

        # Check edge data
        edge_data = graph[str(tmp_path / "main.py")][str(tmp_path / "utils.py")]
        assert edge_data["type"] == "IMPORTS"
        assert edge_data["imported_names"] == ["helper"]

    def test_build_import_graph_no_imports(self, tmp_path: Path):
        """Test building graph with file that has no imports."""
        (tmp_path / "standalone.py").write_text("x = 42\n")

        resolver = ImportResolver(tmp_path)
        graph = resolver.build_import_graph([tmp_path / "standalone.py"])

        # Graph should have node but no edges
        assert graph.number_of_nodes() == 1
        assert graph.number_of_edges() == 0

    def test_build_import_graph_circular(self, tmp_path: Path):
        """Test building graph with circular imports."""
        (tmp_path / "a.py").write_text("from b import func_b\n")
        (tmp_path / "b.py").write_text("from a import func_a\n")

        resolver = ImportResolver(tmp_path)
        files = [tmp_path / "a.py", tmp_path / "b.py"]
        graph = resolver.build_import_graph(files)

        # Both edges should exist
        assert graph.has_edge(str(tmp_path / "a.py"), str(tmp_path / "b.py"))
        assert graph.has_edge(str(tmp_path / "b.py"), str(tmp_path / "a.py"))

    def test_build_import_graph_with_aliases(self, tmp_path: Path):
        """Test building graph with import aliases."""
        (tmp_path / "main.py").write_text("from utils import helper as h\n")
        (tmp_path / "utils.py").write_text("def helper(): pass\n")

        resolver = ImportResolver(tmp_path)
        files = [tmp_path / "main.py", tmp_path / "utils.py"]
        graph = resolver.build_import_graph(files)

        # Check edge data includes aliases
        edge_data = graph[str(tmp_path / "main.py")][str(tmp_path / "utils.py")]
        assert "aliases" in edge_data
        assert edge_data["aliases"] == {"helper": "h"}

    def test_build_import_graph_external_imports_ignored(self, tmp_path: Path):
        """Test that external imports don't create edges."""
        (tmp_path / "main.py").write_text("import os\nimport sys\n")

        resolver = ImportResolver(tmp_path)
        graph = resolver.build_import_graph([tmp_path / "main.py"])

        # No edges to external modules
        assert graph.number_of_edges() == 0

    def test_build_import_graph_relative_imports(self, tmp_path: Path):
        """Test building graph with relative imports."""
        # Create package structure
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "main.py").write_text("from . import utils\n")
        (pkg_dir / "utils.py").write_text("def helper(): pass\n")

        resolver = ImportResolver(tmp_path)
        files = [pkg_dir / "main.py", pkg_dir / "utils.py"]
        graph = resolver.build_import_graph(files)

        # Check edge exists
        assert graph.has_edge(str(pkg_dir / "main.py"), str(pkg_dir / "utils.py"))
