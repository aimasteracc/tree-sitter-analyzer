"""Regression tests for Python import rendering with multi-byte source bytes.

Tree-sitter reports node spans in UTF-8 byte offsets, but the Python plugin's
import helpers used to slice the Python ``str`` directly with those byte
offsets. Any multi-byte character upstream of an import (e.g. an em-dash in a
module docstring) silently shifted every downstream import literal, producing
mangled ``table_output`` lines like ``import port json`` instead of
``import json``. See the ``_import_package_mixin._extract_import_info`` and
``_import.import_node_context`` byte-aware fix.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)

# Source intentionally contains an em-dash (a 3-byte UTF-8 character) in the
# module docstring so that every byte offset after the docstring is shifted
# relative to the corresponding Python ``str`` index.
_MULTIBYTE_PY_SOURCE = (
    "#!/usr/bin/env python3\n"
    '"""Module — uses an em-dash before any imports.\n'
    "\n"
    "The em-dash above is a multi-byte UTF-8 character. Any naive byte->char\n"
    "slicing of the source string will be off-by-N for every import below.\n"
    '"""\n'
    "\n"
    "import json\n"
    "import logging\n"
    "from dataclasses import asdict, dataclass\n"
    "from pathlib import Path\n"
)


def _table_output(tmp_path: Path) -> str:
    src = tmp_path / "multibyte_imports.py"
    src.write_text(_MULTIBYTE_PY_SOURCE, encoding="utf-8")

    tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
    result = asyncio.run(tool.execute({"file_path": src.name, "output_format": "json"}))
    return result.get("table_output", "")


def _extract_import_block(output: str) -> list[str]:
    lines = output.splitlines()
    in_imports = False
    in_fence = False
    import_lines: list[str] = []
    for line in lines:
        if line == "## Imports":
            in_imports = True
            continue
        if in_imports and line.startswith("```python"):
            in_fence = True
            continue
        if in_imports and in_fence and line == "```":
            break
        if in_imports and in_fence:
            import_lines.append(line)
    return import_lines


def test_imports_section_renders_clean_after_multibyte_docstring(
    tmp_path: Path,
) -> None:
    """Regression: em-dash in docstring must not corrupt downstream imports."""
    output = _table_output(tmp_path)
    import_lines = _extract_import_block(output)

    assert import_lines, "Imports section was not produced. Full output:\n" + output

    # No mangled tokens leaking the byte/char offset bug.
    for literal in import_lines:
        assert "import port " not in literal, literal
        assert "import om " not in literal, literal
        # No truncated leading bytes; every line must begin with ``import``
        # or ``from``. The lone-letter artefacts (``i`` / ``f``) from the old
        # bug would fail this check.
        assert literal.startswith("import ") or literal.startswith("from "), literal

    rendered = "\n".join(import_lines)
    assert "import json" in rendered
    assert "import logging" in rendered
    assert "from dataclasses import asdict, dataclass" in rendered
    assert "from pathlib import Path" in rendered


def test_imports_section_renders_clean_without_multibyte(tmp_path: Path) -> None:
    """Sanity: pure-ASCII source still produces clean imports (no regression)."""
    src = tmp_path / "ascii_imports.py"
    src.write_text(
        (
            "#!/usr/bin/env python3\n"
            '"""Pure ASCII module docstring."""\n'
            "\n"
            "import os\n"
            "from pathlib import Path\n"
        ),
        encoding="utf-8",
    )

    tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
    result = asyncio.run(tool.execute({"file_path": src.name, "output_format": "json"}))
    import_lines = _extract_import_block(result.get("table_output", ""))

    assert "import os" in import_lines
    assert "from pathlib import Path" in import_lines
