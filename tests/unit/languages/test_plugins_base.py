"""Re-export aggregator for split plugins_base test modules.

Originally a single 845-line file, now split into:
- test_plugins_base_core.py: TestLanguagePlugin, TestElementExtractor, TestDefaultExtractorTraversalDirect, TestDefaultExtractorIntegration
- test_plugins_base_advanced.py: TestLanguagePluginIntegration, TestEdgeCases, TestDefaultExtractorTraversal, TestDefaultExtractorErrorPaths
"""

from tests.unit.languages.test_plugins_base_advanced import *  # noqa: F401,F403
from tests.unit.languages.test_plugins_base_core import *  # noqa: F401,F403
