"""#1643：未改名的 ``from m import name`` 绑定不计为非调用引用。"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_import_bindings import mask_import_bindings


@pytest.mark.parametrize(
    "source",
    [
        "from mod import lonely\n",
        "from pkg.mod import reader, lonely\n",
        "from . import lonely\n",
        "from .mod import (\n    reader,\n    lonely,\n)\n",
        "from mod import reader, \\\n    lonely\n",
        "    from mod import lonely  \n",
    ],
)
def test_plain_import_binding_is_masked(source: str) -> None:
    # #1643：导入方的后续使用仍由同一扫描逐一检查，导入行本身不是引用。
    masked = mask_import_bindings(source, "lonely")

    assert "lonely" not in masked
    assert (len(masked), masked.count("\n")) == (len(source), source.count("\n"))


@pytest.mark.parametrize(
    "source",
    [
        # 改名导入：之后的 `lo()` 名字不同，导入行就是引用。
        "from mod import lonely as lo\n",
        "from mod import (\n    lonely as lo,\n)\n",
        # 本地 `lonely` 指向别处：保守保留。
        "from mod import other as lonely\n",
        # 模块名而非导入的名字。
        "import lonely\n",
        "from lonely import x\n",
        # 导入语句之外的使用。
        "from mod import reader\nhandler = lonely\n",
    ],
)
def test_other_occurrences_are_kept(source: str) -> None:
    # #1643 负对照：除未改名的导入名外，任何同名出现都原样保留。
    assert mask_import_bindings(source, "lonely") == source


def test_only_the_binding_is_masked_on_a_mixed_line() -> None:
    # #1643：同一文件中导入行之后的引用仍可见。
    source = "from mod import lonely\nCALLBACKS = [lonely]\n"

    masked = mask_import_bindings(source, "lonely")

    assert masked.splitlines() == ["from mod import       ", "CALLBACKS = [lonely]"]
