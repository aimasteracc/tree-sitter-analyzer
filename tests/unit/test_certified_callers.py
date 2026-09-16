"""认证 caller 查询的证据来源回归测试。"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool


@pytest.mark.asyncio
async def test_certified_qualified_callers_report_cache_source(tmp_path) -> None:
    """限定名走认证图路径时也必须声明缓存证据来源。"""
    (tmp_path / "sample.py").write_text(
        "class Service:\n"
        "    def target(self):\n"
        "        return 1\n\n"
        "def caller(service):\n"
        "    return service.target()\n",
        encoding="utf-8",
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    result = await CodeGraphCallersTool(str(tmp_path)).execute(
        {"function_name": "Service.target", "output_format": "json"}
    )

    assert result["data_source"] == "cache"
