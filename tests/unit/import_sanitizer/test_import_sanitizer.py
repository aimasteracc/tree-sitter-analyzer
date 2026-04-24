"""Tests for import sanitizer analysis engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.import_sanitizer import (
    CircularImport,
    FileAnalysis,
    ImportInfo,
    ImportSanitizer,
    analyze_imports,
)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def sanitizer(tmp_project: Path) -> ImportSanitizer:
    return ImportSanitizer(project_root=tmp_project)


# ---- Python Import Detection ----


class TestPythonImportDetection:
    def test_simple_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 1
        assert result.imports[0].import_name == "os"
        assert result.imports[0].module == "os"

    def test_dotted_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os.path\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 1
        assert result.imports[0].import_name == "os.path"

    def test_from_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("from os.path import join\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 1
        assert result.imports[0].import_name == "join"
        assert result.imports[0].module == "os.path"

    def test_from_import_alias(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("from os.path import join as j\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 1
        assert result.imports[0].import_name == "join"
        assert result.imports[0].alias == "j"

    def test_star_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("from os import *\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 1
        assert result.imports[0].is_star is True
        assert result.imports[0].import_name == "*"

    def test_multiple_imports(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nimport sys\nimport json\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 3
        names = [i.import_name for i in result.imports]
        assert "os" in names
        assert "sys" in names
        assert "json" in names

    def test_mixed_imports(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text(
            "import os\nfrom pathlib import Path\nfrom collections import defaultdict as dd\n"
        )
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 3


# ---- Unused Import Detection ----


class TestUnusedImportDetection:
    def test_used_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nos.getcwd()\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.unused_imports) == 0

    def test_unused_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nimport sys\nprint('hello')\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.unused_imports) >= 1
        unused_names = [i.import_name for i in result.unused_imports]
        assert "os" in unused_names or "sys" in unused_names

    def test_used_via_alias(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("from pathlib import Path as P\nP('/tmp')\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.unused_imports) == 0

    def test_unused_via_alias(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("from pathlib import Path as P\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.unused_imports) == 1
        assert result.unused_imports[0].alias == "P"

    def test_star_import_not_flagged(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("from os import *\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.unused_imports) == 0

    def test_side_effect_import_not_flagged(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\n")
        result = sanitizer.analyze_file(py_file)
        for imp in result.imports:
            assert imp.is_side_effect is False


# ---- JavaScript/TypeScript Import Detection ----


class TestJavaScriptImportDetection:
    def test_named_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        js_file = tmp_project / "test.js"
        js_file.write_text('import { useState } from "react";\n')
        result = sanitizer.analyze_file(js_file)
        assert len(result.imports) >= 1
        names = [i.import_name for i in result.imports]
        assert "useState" in names

    def test_default_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        js_file = tmp_project / "test.js"
        js_file.write_text('import React from "react";\n')
        result = sanitizer.analyze_file(js_file)
        assert len(result.imports) >= 1
        names = [i.import_name for i in result.imports]
        assert "React" in names

    def test_side_effect_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        js_file = tmp_project / "test.js"
        js_file.write_text('import "./styles.css";\n')
        result = sanitizer.analyze_file(js_file)
        assert len(result.imports) >= 1
        assert any(i.is_side_effect for i in result.imports)

    def test_unused_js_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        js_file = tmp_project / "test.js"
        js_file.write_text('import { useState } from "react";\nconsole.log("hi");\n')
        result = sanitizer.analyze_file(js_file)
        assert len(result.unused_imports) >= 1


class TestTypeScriptImportDetection:
    def test_ts_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        ts_file = tmp_project / "test.ts"
        ts_file.write_text('import { useState } from "react";\n')
        result = sanitizer.analyze_file(ts_file)
        assert len(result.imports) >= 1


# ---- Java Import Detection ----


class TestJavaImportDetection:
    def test_java_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        java_file = tmp_project / "Test.java"
        java_file.write_text(
            "import java.util.List;\npublic class Test {}\n"
        )
        result = sanitizer.analyze_file(java_file)
        assert len(result.imports) >= 1
        names = [i.import_name for i in result.imports]
        assert "List" in names

    def test_unused_java_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        java_file = tmp_project / "Test.java"
        java_file.write_text(
            "import java.util.List;\npublic class Test {}\n"
        )
        result = sanitizer.analyze_file(java_file)
        assert len(result.unused_imports) >= 1

    def test_used_java_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        java_file = tmp_project / "Test.java"
        java_file.write_text(
            "import java.util.List;\npublic class Test { List<String> items; }\n"
        )
        result = sanitizer.analyze_file(java_file)
        used_names = [i.import_name for i in result.imports if i not in result.unused_imports]
        assert "List" in used_names


# ---- Go Import Detection ----


class TestGoImportDetection:
    def test_go_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        go_file = tmp_project / "main.go"
        go_file.write_text(
            'package main\n\nimport "fmt"\n\nfunc main() {}\n'
        )
        result = sanitizer.analyze_file(go_file)
        assert len(result.imports) >= 1
        names = [i.import_name for i in result.imports]
        assert "fmt" in names

    def test_unused_go_import(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        go_file = tmp_project / "main.go"
        go_file.write_text(
            'package main\n\nimport "fmt"\n\nfunc main() {}\n'
        )
        result = sanitizer.analyze_file(go_file)
        assert len(result.unused_imports) >= 1


# ---- Directory Analysis ----


class TestDirectoryAnalysis:
    def test_analyze_directory(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        (tmp_project / "a.py").write_text("import os\nos.getcwd()\n")
        (tmp_project / "b.py").write_text("import sys\n")
        result = sanitizer.analyze_directory(tmp_project)
        assert result.total_imports >= 2
        assert len(result.files) >= 2

    def test_unsupported_file_skipped(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        (tmp_project / "data.txt").write_text("import os\n")
        (tmp_project / "code.py").write_text("import os\n")
        result = sanitizer.analyze_directory(tmp_project)
        assert len(result.files) == 1

    def test_result_serialization(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        (tmp_project / "test.py").write_text("import os\n")
        result = sanitizer.analyze_directory(tmp_project)
        d = result.to_dict()
        assert "total_imports" in d
        assert "files" in d
        assert isinstance(d["files"], list)


# ---- Sort Compliance ----


class TestSortCompliance:
    def test_properly_sorted(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import os\nimport sys\n\nimport requests\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.sort_violations) == 0

    def test_badly_sorted(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import requests\nimport os\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.sort_violations) >= 1

    def test_local_after_third_party(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "test.py"
        py_file.write_text("import requests\n\nfrom . import utils\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.sort_violations) == 0


# ---- Edge Cases ----


class TestEdgeCases:
    def test_empty_file(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        py_file = tmp_project / "empty.py"
        py_file.write_text("")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 0
        assert len(result.unused_imports) == 0

    def test_file_with_only_comments(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        py_file = tmp_project / "comments.py"
        py_file.write_text("# This is a comment\n# Another comment\n")
        result = sanitizer.analyze_file(py_file)
        assert len(result.imports) == 0

    def test_nonexistent_file(self, sanitizer: ImportSanitizer, tmp_project: Path) -> None:
        result = sanitizer.analyze_file(tmp_project / "nonexistent.py")
        assert len(result.errors) > 0

    def test_unsupported_extension(
        self, sanitizer: ImportSanitizer, tmp_project: Path,
    ) -> None:
        result = sanitizer.analyze_file(tmp_project / "test.rb")
        assert len(result.errors) > 0

    def test_import_info_display_name(self) -> None:
        info = ImportInfo(import_name="join", module="os.path", line=1, column=0)
        assert info.display_name == "join"

        info_alias = ImportInfo(
            import_name="join", module="os.path", line=1, column=0, alias="j",
        )
        assert info_alias.display_name == "join as j"

    def test_circular_import_display(self) -> None:
        ci = CircularImport(cycle=("a.py", "b.py", "a.py"))
        assert ci.display == "a.py -> b.py -> a.py"

    def test_convenience_function(self, tmp_path: Path) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("import os\n")
        result = analyze_imports(py_file)
        assert isinstance(result, FileAnalysis)
        assert len(result.imports) >= 1
