"""Tests for Import Shadowing Detector."""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.import_shadowing import (
    ISSUE_SHADOWED_FROM_IMPORT,
    ISSUE_SHADOWED_IMPORT,
    ImportShadowingAnalyzer,
)


def _write(tmp: Path, name: str, code: str) -> Path:
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    return p


# ── Import statement shadowing ────────────────────────────────


class TestImportShadowing:
    def test_import_then_assign(self, tmp_path: Path) -> None:
        code = "import os\nos = 'linux'\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_IMPORT

    def test_import_not_shadowed(self, tmp_path: Path) -> None:
        code = "import os\nprint(os.path)\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_aliased_import_shadowed(self, tmp_path: Path) -> None:
        code = "import numpy as np\nnp = [1, 2, 3]\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_import_different_name(self, tmp_path: Path) -> None:
        code = "import os\npath = '/tmp'\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── From-import shadowing ─────────────────────────────────────


class TestFromImportShadowing:
    def test_from_import_shadowed(self, tmp_path: Path) -> None:
        code = "from typing import Optional\nOptional = None\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_SHADOWED_FROM_IMPORT

    def test_from_import_not_shadowed(self, tmp_path: Path) -> None:
        code = "from typing import Optional\nx: Optional[str] = None\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_from_import_aliased_shadowed(self, tmp_path: Path) -> None:
        code = "from typing import Optional as Opt\nOpt = str\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 1


# ── For-loop target shadowing ─────────────────────────────────


class TestForLoopShadowing:
    def test_for_loop_shadowing_import(self, tmp_path: Path) -> None:
        code = "import x\nfor x in [1, 2, 3]:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 1

    def test_for_loop_no_shadow(self, tmp_path: Path) -> None:
        code = "import os\nfor path in ['/tmp']:\n    pass\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0


# ── Edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.py", "")
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        r = ImportShadowingAnalyzer().analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "a.js", "import os from 'os';\nos = 'x';\n")
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_to_dict(self, tmp_path: Path) -> None:
        code = "import os\nos = 'linux'\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        d = r.to_dict()
        assert "issues" in d
        assert d["issue_count"] == 1
        assert "import_line" in d["issues"][0]

    def test_import_after_assign_not_flagged(self, tmp_path: Path) -> None:
        code = "x = 1\nimport x\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 0

    def test_line_numbers_correct(self, tmp_path: Path) -> None:
        code = "import os\nos = 'linux'\n"
        p = _write(tmp_path, "a.py", code)
        r = ImportShadowingAnalyzer().analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].line == 2
        assert r.issues[0].import_line == 1
