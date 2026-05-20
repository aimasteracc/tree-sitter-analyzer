#!/usr/bin/env python3
"""Re-export aggregator for CLI comprehensive tests (split into 3 focused modules)."""

from tests.integration.cli.test_cli_advanced_summary_structure import (
    TestCLIAdvancedOptions,
    TestCLIStructureOption,
    TestCLISummaryOption,
)
from tests.integration.cli.test_cli_query_exec_coverage import (
    TestCLIAdditionalCoverage,
    TestCLILoggingConfiguration,
    TestCLIQueryExecution,
)
from tests.integration.cli.test_cli_table_partial_query import (
    TestCLILanguageHandling,
    TestCLIPartialReadOption,
    TestCLIQueryHandling,
    TestCLITableOption,
)

__all__ = [
    "TestCLIAdvancedOptions",
    "TestCLISummaryOption",
    "TestCLIStructureOption",
    "TestCLITableOption",
    "TestCLIPartialReadOption",
    "TestCLIQueryHandling",
    "TestCLILanguageHandling",
    "TestCLIQueryExecution",
    "TestCLILoggingConfiguration",
    "TestCLIAdditionalCoverage",
]
