"""Re-export aggregator for split test modules."""
from test_java_formatter_advanced import (  # noqa: F401
    TestCompactTableMultipleClasses,
    TestEdgeCases,
    TestFormatAdvanced,
    TestFormatStructure,
    TestJavaDocHandling,
    TestPrivateMethods,
)
from test_java_formatter_basic import (  # noqa: F401
    TestFormatCompactTable,
    TestFormatFullTable,
    TestFormatSummary,
    TestFormatTable,
    TestJavaTableFormatterInstantiation,
    TestMethodFormatting,
    TestTypeShortening,
    TestVisibilityConversion,
)
