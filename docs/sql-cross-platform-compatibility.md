# SQL Cross-Platform Compatibility

Tree-sitter Analyzer provides robust SQL parsing capabilities across different operating systems (Windows, macOS, Linux) and Python versions. Due to differences in how the underlying `tree-sitter-sql` parser behaves on different platforms, we have implemented a compatibility layer to ensure consistent results.

## Supported Platforms

The following platforms are fully supported and tested:

| Platform | Python Versions | Status |
|----------|-----------------|--------|
| Windows  | 3.10 - 3.13     | ✅ Supported |
| macOS    | 3.10 - 3.13     | ✅ Supported |
| Linux    | 3.10 - 3.13     | ✅ Supported |

## How It Works

The compatibility layer works by:

1.  **Detection**: Automatically identifying your OS and Python version.
2.  **Profiling**: Loading a "Behavior Profile" that describes known parsing quirks for your platform.
3.  **Adaptation**: Applying specific rules to fix AST issues (e.g., recovering function names that are mistaken for keywords, fixing trigger names).

This process happens automatically when you use the `SQLPlugin`.

## Known Issues & Adaptations

### Windows
-   **Issue**: Function names that are also SQL keywords (e.g., `BEGIN`, `END`) might be extracted as the keyword type instead of the identifier.
-   **Fix**: The `FixFunctionNameKeywordsRule` recovers the correct name from the source code.

### macOS
-   **Issue**: Trigger names can sometimes be incorrectly extracted as "description" due to an internal parser node mismatch.
-   **Fix**: The `FixTriggerNameDescriptionRule` uses regex to find the actual trigger name.

### Linux (Ubuntu)
-   **Issue**: Phantom trigger elements may appear in the AST where they don't exist.
-   **Fix**: The `RemovePhantomTriggersRule` validates trigger elements against the source code and removes invalid ones.

## Recording Custom Profiles

If you encounter parsing issues on a specific setup, you can record a new behavior profile:

```bash
python -m tree_sitter_analyzer.platform_compat.record --output-dir my_profiles
```

This will generate a `profile.json` file that captures how the parser behaves on your machine. You can then submit this profile to the development team or use it to develop new adaptation rules.

## Troubleshooting

### Diagnostic Mode

If SQL parsing is failing or producing incorrect results, enable diagnostic mode to see what's happening:

```python
from tree_sitter_analyzer.languages.sql_plugin import SQLPlugin

plugin = SQLPlugin(diagnostic_mode=True)
# Logs will show:
# - Detected platform
# - Loaded profile
# - Applied adaptation rules
# - Before/After element snapshots
```

### Common Errors

**"No SQL behavior profile found for..."**
-   **Cause**: Your specific OS/Python combination hasn't been profiled yet.
-   **Solution**: The analyzer will use default settings. If you see issues, run the recording tool and share the profile.

**"Error during enhanced SQL extraction..."**
-   **Cause**: A critical parsing failure occurred.
-   **Solution**: The analyzer will degrade gracefully (returning partial results or skipping SQL). Check the logs for the specific error and consider filing a bug report with the code snippet that caused it.

## CLI Tools

The analyzer includes CLI tools for managing compatibility:

-   `--sql-platform-info`: Show current platform detection details.
-   `--record-sql-profile`: Record a new behavior profile.
-   `--compare-sql-profiles`: Compare two profiles to see differences.

(See `tree-sitter-analyzer --help` for usage details)

## Upgrading from Previous Versions

If you are upgrading from an older version of `tree-sitter-analyzer`:

1.  **No Action Required**: The compatibility layer is enabled by default.
2.  **Verification**: You can verify that your platform is correctly detected by running:
    ```bash
    uv run tree-sitter-analyzer --sql-platform-info
    ```
3.  **Backward Compatibility**: Existing SQL extraction logic is preserved. The new layer only intervenes when known parsing errors are detected.
