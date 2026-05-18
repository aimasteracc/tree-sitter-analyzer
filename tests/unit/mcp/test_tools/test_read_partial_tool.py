#!/usr/bin/env python3
"""
Unit tests for read_partial_tool.py

Tests for ReadPartialTool MCP tool which provides partial file reading functionality.
"""

from tests.unit.mcp.test_tools._test_read_partial_tool_batch_core_mixins import (
    ReadPartialToolExecuteBatchProcessingMixin,
    ReadPartialToolExecuteBatchValidationMixin,
)
from tests.unit.mcp.test_tools._test_read_partial_tool_batch_extra_mixins import (
    ReadPartialToolBatchExtraFileErrorMixin,
    ReadPartialToolBatchExtraLimitMixin,
    ReadPartialToolBatchExtraValidationMixin,
)
from tests.unit.mcp.test_tools._test_read_partial_tool_coverage_mixins import (
    ReadPartialToolCoverageBatchMixin,
    ReadPartialToolCoverageExecuteMixin,
    ReadPartialToolCoverageValidateMixin,
)
from tests.unit.mcp.test_tools._test_read_partial_tool_execute_core_mixins import (
    ReadPartialToolExecuteMixin,
    ReadPartialToolReadFilePartialMixin,
)
from tests.unit.mcp.test_tools._test_read_partial_tool_execute_extra_mixins import (
    ReadPartialToolExecuteExtraContinuedMixin,
    ReadPartialToolExecuteExtraMixin,
)
from tests.unit.mcp.test_tools._test_read_partial_tool_schema_mixins import (
    ReadPartialToolGetToolDefinitionMixin,
    ReadPartialToolGetToolSchemaMixin,
    ReadPartialToolInitMixin,
    ReadPartialToolValidateArgumentsMixin,
    ReadPartialToolValidateExtraMixin,
)


class TestReadPartialToolInit(ReadPartialToolInitMixin):
    """Tests for ReadPartialTool initialization."""

    __test__ = True


class TestReadPartialToolGetToolSchema(ReadPartialToolGetToolSchemaMixin):
    """Tests for get_tool_schema method."""

    __test__ = True


class TestReadPartialToolGetToolDefinition(ReadPartialToolGetToolDefinitionMixin):
    """Tests for get_tool_definition method."""

    __test__ = True


class TestReadPartialToolValidateArguments(ReadPartialToolValidateArgumentsMixin):
    """Tests for validate_arguments method."""

    __test__ = True


class TestReadPartialToolExecute(ReadPartialToolExecuteMixin):
    """Tests for execute method (single mode)."""

    __test__ = True


class TestReadPartialToolExecuteBatch(
    ReadPartialToolExecuteBatchValidationMixin,
    ReadPartialToolExecuteBatchProcessingMixin,
):
    """Tests for _execute_batch method (batch mode)."""

    __test__ = True


class TestReadPartialToolReadFilePartial(ReadPartialToolReadFilePartialMixin):
    """Tests for _read_file_partial method."""

    __test__ = True


class TestReadPartialToolExecuteExtra(ReadPartialToolExecuteExtraMixin):
    """Additional tests for uncovered execute() paths."""

    __test__ = True


class TestReadPartialToolExecuteExtraContinued(
    ReadPartialToolExecuteExtraContinuedMixin
):
    """Additional read_partial execute and agent summary tests."""

    __test__ = True


class TestReadPartialToolBatchExtra(
    ReadPartialToolBatchExtraFileErrorMixin,
    ReadPartialToolBatchExtraLimitMixin,
    ReadPartialToolBatchExtraValidationMixin,
):
    """Additional tests for uncovered _execute_batch() paths."""

    __test__ = True


class TestReadPartialToolValidateExtra(ReadPartialToolValidateExtraMixin):
    """Additional tests for uncovered validate_arguments paths."""

    __test__ = True


class TestReadPartialToolCoverageGaps(
    ReadPartialToolCoverageExecuteMixin,
    ReadPartialToolCoverageBatchMixin,
    ReadPartialToolCoverageValidateMixin,
):
    """Tests targeting specific uncovered lines in read_partial_tool.py."""

    __test__ = True
