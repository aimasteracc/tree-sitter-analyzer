from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.core.query_service import QueryService


@pytest.fixture
def query_service():
    return QueryService()


def test_query_service_basic(query_service):
    assert query_service is not None


@pytest.mark.asyncio
async def test_query_service_execute_empty(query_service):
    with patch.object(query_service, "_read_file_async", return_value=("", "utf-8")):
        with patch.object(query_service.parser, "parse_code") as mock_parse:
            mock_result = MagicMock()
            mock_result.tree = MagicMock()
            mock_result.tree.language = MagicMock()
            mock_result.tree.root_node = MagicMock()
            mock_parse.return_value = mock_result

            result = await query_service.execute_query(
                "test.py", "python", query_string="(module) @module"
            )
            assert isinstance(result, list)
