"""#1765：JS/TS 相对导入的本地名 -> 目标文件映射（沿 extends 链定位基类用）。"""

from __future__ import annotations

from tree_sitter_analyzer.jsts_import_targets import jsts_import_map

_FILES = {
    "src/a.ts",
    "src/b/index.ts",
    "src/c.tsx",
    "src/user.ts",
    "src/types.ts",
    "lib/z.py",
}


def test_relative_imports_map_local_names_to_files() -> None:
    imports = {
        "src/user.ts": [
            "import Base, { Mixin, Other as Renamed } from './a'",
            {"text": "import type { Shape, type Kind } from './b'"},
            "import * as ns from './c'",
            "import { View } from './c.js'",
            "import { external } from 'react'",
            "import { Missing } from './nowhere'",
            "const x = require('./a')",
        ],
        "lib/z.py": ["from a import b"],
    }

    assert jsts_import_map(imports, _FILES) == {
        "src/user.ts": {
            "Base": "src/a.ts",
            "Mixin": "src/a.ts",
            "Renamed": "src/a.ts",
            "Shape": "src/b/index.ts",
            "Kind": "src/b/index.ts",
            "View": "src/c.tsx",
        }
    }


def test_file_without_resolvable_imports_is_absent() -> None:
    assert jsts_import_map({"src/a.ts": ["import { x } from 'pkg'"]}, _FILES) == {}
