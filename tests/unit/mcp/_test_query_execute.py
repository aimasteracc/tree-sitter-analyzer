"""Mixins for query tool: execute tests."""

from unittest.mock import AsyncMock, patch

import pytest


class TestExecuteTestMixin:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_empty_arguments(self, tool):
        with pytest.raises(Exception, match="file_path or symbol is required"):
            await tool.execute({})

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self, tool):
        arguments = {"query_key": "methods"}
        with pytest.raises(Exception, match="file_path or symbol is required"):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_missing_both_query_params(self, tool):
        arguments = {"file_path": "test.py"}
        with pytest.raises(
            Exception, match="Either query_key or query_string must be provided"
        ):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_both_query_params_provided(self, tool, sample_python_file):
        arguments = {
            "file_path": str(sample_python_file),
            "query_key": "methods",
            "query_string": "(function_definition) @func",
        }
        result = await tool.execute(arguments)
        assert result["success"] is False
        assert "Cannot provide both" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_language_detection_fails(self, tool, sample_python_file):
        with patch(
            "tree_sitter_analyzer.mcp.tools.query_tool.detect_language_from_file",
            return_value=None,
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
            }
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "Could not detect language" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_success_with_query_key(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["count"] == len(mock_query_results)
            assert "toon_content" in result
            assert result["file_path"] == str(sample_python_file)
            assert result["language"] == "python"
            assert result["query"] == "methods"

    @pytest.mark.asyncio
    async def test_execute_success_with_query_string(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_string": "(function_definition) @func",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["query"] == "(function_definition) @func"

    @pytest.mark.asyncio
    async def test_execute_no_results(self, tool, sample_python_file):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = []

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["count"] == 0
            assert "No results" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_summary_format(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "result_format": "summary",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert "query_type" in result
            assert "captures" in result
            assert "total_count" in result

    @pytest.mark.asyncio
    async def test_execute_with_file_output(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/query_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert "output_file_path" in result
                assert result["output_file_path"] == "/output/query_results.json"
                assert result["file_saved"] is True

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/query_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert "output_file_path" in result
                assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_with_toon_format(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch(
                "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response"
            ) as mock_toon:
                mock_toon.return_value = {"toon": "formatted"}

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_format": "toon",
                }

                result = await tool.execute(arguments)

                assert mock_toon.called
                assert result == {"toon": "formatted"}

    @pytest.mark.asyncio
    async def test_execute_exception_handling(self, tool, sample_python_file):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.side_effect = Exception("Unexpected error")

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_file_save_error(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("Save failed")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_execute_auto_language_detection(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.query_tool.detect_language_from_file",
            return_value="python",
        ):
            with patch.object(
                tool.query_service, "execute_query", new_callable=AsyncMock
            ) as mock_query:
                mock_query.return_value = mock_query_results

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_file_save_error(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("Disk full")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_execute_with_empty_output_file_string(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/sample_query_methods.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "   ",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is True
                mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_query_string_and_file_output(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/custom_query.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_string": "(function_definition) @func",
                    "language": "python",
                    "output_file": "   ",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is True


class TestExecuteAdditionalCoverageTestMixin:
    """Additional tests targeting uncovered branches in execute."""

    @pytest.mark.asyncio
    async def test_execute_none_arguments(self, tool):
        with pytest.raises(Exception, match="file_path or symbol is required"):
            await tool.execute(None)

    @pytest.mark.asyncio
    async def test_execute_summary_format_with_file_output(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/summary_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "result_format": "summary",
                    "output_file": "summary_results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["output_file_path"] == "/output/summary_results.json"
                assert result["file_saved"] is True

    @pytest.mark.asyncio
    async def test_execute_summary_format_file_save_error(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = OSError("Permission denied")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "result_format": "summary",
                    "output_file": "results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_file_save_info(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/suppressed_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["output_file_path"] == "/output/suppressed_results.json"
                assert result["file_saved"] is True
                assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_save_error_info(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("No space left")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result
                assert "No space left" in result["file_save_error"]

    @pytest.mark.asyncio
    async def test_execute_analysis_error_reraise(self, tool, sample_python_file):
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=AnalysisError("bad file", operation="query_code"),
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
            }
            with pytest.raises(AnalysisError, match="bad file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_with_output_format_json(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "output_format": "json",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["count"] == len(mock_query_results)
            assert "results" in result

    @pytest.mark.asyncio
    async def test_execute_no_language_provided_auto_detect(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.query_tool.detect_language_from_file",
            return_value="python",
        ):
            with patch.object(
                tool.query_service, "execute_query", new_callable=AsyncMock
            ) as mock_query:
                mock_query.return_value = mock_query_results

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "output_format": "json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["language"] == "python"


class TestExecuteCoverageBoostTestMixin:
    """Tests targeting specific uncovered lines in execute()."""

    @pytest.mark.asyncio
    async def test_execute_generic_exception_returns_error(
        self, tool, sample_python_file
    ):
        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=RuntimeError("file resolve boom"),
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "file resolve boom" in result["error"]
            assert result["file_path"] == str(sample_python_file)
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_suppress_output_without_file_save(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "output_file": "results.json",
                "suppress_output": True,
            }

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/results.json"

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["output_file_path"] == "/output/results.json"
                assert result["file_saved"] is True
                assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_file_output_with_toon_format(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/toon_results.txt"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "toon_results",
                    "output_format": "toon",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is True
                assert result["output_file_path"] == "/output/toon_results.txt"

    @pytest.mark.asyncio
    async def test_execute_empty_arguments_dict_triggers_error(self, tool):
        with pytest.raises(Exception, match="file_path or symbol is required"):
            await tool.execute({})

    @pytest.mark.asyncio
    async def test_execute_none_file_path_triggers_error(self, tool):
        with pytest.raises(Exception, match="file_path or symbol is required"):
            await tool.execute({"file_path": None})


class TestExecuteInvalidQueryKeyTestMixin:
    """Tests for execute with invalid query_key."""

    @pytest.mark.asyncio
    async def test_execute_invalid_query_key_returns_suggestions(
        self, tool, sample_python_file
    ):
        with patch.object(
            tool.query_service,
            "get_available_queries",
            return_value=["methods", "classes"],
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "nonexistent",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "not found" in result["error"]
            assert "available_queries" in result
            assert result["language"] == "python"
            assert "hint" in result

    @pytest.mark.asyncio
    async def test_execute_no_results_with_productive_queries(
        self, tool, sample_python_file
    ):
        call_count = 0

        async def mock_execute_query(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            query_key = args[3] if len(args) > 3 else kwargs.get("query_key")
            if query_key == "classes":
                return [
                    {
                        "capture_name": "class",
                        "content": "class Foo",
                        "start_line": 1,
                        "end_line": 1,
                        "node_type": "class",
                    }
                ]
            return []

        with patch.object(
            tool.query_service,
            "execute_query",
            side_effect=mock_execute_query,
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["count"] == 0
            assert "productive_queries" in result
            assert "classes" in result["productive_queries"]

    @pytest.mark.asyncio
    async def test_execute_no_results_productive_queries_exception(
        self, tool, sample_python_file
    ):
        call_count = 0

        async def mock_execute_query(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []
            raise RuntimeError("probe failed")

        with patch.object(
            tool.query_service,
            "execute_query",
            side_effect=mock_execute_query,
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["count"] == 0
            assert "productive_queries" not in result

    @pytest.mark.asyncio
    async def test_execute_no_results_with_query_string(self, tool, sample_python_file):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = []

            arguments = {
                "file_path": str(sample_python_file),
                "query_string": "(method_declaration) @m",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["count"] == 0
            assert "custom" in result.get(
                "message", ""
            ) or "(method_declaration) @m" in result.get(
                "message",
                "",
            )

    @pytest.mark.asyncio
    async def test_execute_suppress_output_without_output_file(
        self, tool, sample_python_file, mock_query_results
    ):
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "suppress_output": True,
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
