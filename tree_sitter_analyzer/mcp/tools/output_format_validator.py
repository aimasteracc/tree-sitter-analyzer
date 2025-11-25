#!/usr/bin/env python3
"""
Output format parameter validation for search_content tool.

Ensures mutual exclusion of output format parameters to prevent conflicts
and provides multilingual error messages with token efficiency guidance.
"""

import locale
import os
from typing import Any


class OutputFormatValidator:
    """Validator for output format parameters mutual exclusion."""

    # Output format parameters that are mutually exclusive
    OUTPUT_FORMAT_PARAMS = {
        "total_only",
        "count_only_matches",
        "summary_only",
        "group_by_file",
        "suppress_output",
    }

    # Token efficiency guidance for error messages
    FORMAT_EFFICIENCY_GUIDE = {
        "total_only": "~10 tokens (most efficient for count queries)",
        "count_only_matches": "~50-200 tokens (file distribution analysis)",
        "summary_only": "~500-2000 tokens (initial investigation)",
        "group_by_file": "~2000-10000 tokens (context-aware review)",
        "suppress_output": "0 tokens (cache only, no output)",
    }

    def _detect_language(self) -> str:
        """Detect preferred language from environment."""
        # Check environment variables for language preference
        lang = os.environ.get("LANG", "")
        if lang.startswith("ja"):
            return "ja"

        # Check locale
        try:
            current_locale = locale.getlocale()[0]
            if current_locale and current_locale.startswith("ja"):
                return "ja"
        except Exception:
            pass  # nosec

        # Default to English
        return "en"

    def _get_error_message(self, specified_formats: list[str]) -> str:
        """Generate localized error message with usage examples."""
        lang = self._detect_language()
        format_list = ", ".join(specified_formats)

        if lang == "ja":
            # Japanese error message
            base_message = (
                f"⚠️ 出力形式パラメータエラー: 相互排他的なパラメータが同時に指定されています: {format_list}\n\n"
                f"🔒 相互排他的パラメータ: {', '.join(self.OUTPUT_FORMAT_PARAMS)}\n\n"
                f"💡 トークン効率ガイド:\n"
            )

            for param, desc in self.FORMAT_EFFICIENCY_GUIDE.items():
                base_message += f"  • {param}: {desc}\n"

            base_message += (
                "\n📋 推奨使用パターン:\n"
                "  • 件数確認: total_only=true\n"
                "  • ファイル分布: count_only_matches=true\n"
                "  • 初期調査: summary_only=true\n"
                "  • 詳細レビュー: group_by_file=true\n"
                "  • キャッシュのみ: suppress_output=true\n\n"
                '❌ 間違った例: {"total_only": true, "summary_only": true}\n'
                '✅ 正しい例: {"total_only": true}'
            )
        else:
            # English error message
            base_message = (
                f"⚠️ Output Format Parameter Error: Multiple mutually exclusive formats specified: {format_list}\n\n"
                f"🔒 Mutually Exclusive Parameters: {', '.join(self.OUTPUT_FORMAT_PARAMS)}\n\n"
                f"💡 Token Efficiency Guide:\n"
            )

            for param, desc in self.FORMAT_EFFICIENCY_GUIDE.items():
                base_message += f"  • {param}: {desc}\n"

            base_message += (
                "\n📋 Recommended Usage Patterns:\n"
                "  • Count validation: total_only=true\n"
                "  • File distribution: count_only_matches=true\n"
                "  • Initial investigation: summary_only=true\n"
                "  • Detailed review: group_by_file=true\n"
                "  • Cache only: suppress_output=true\n\n"
                '❌ Incorrect: {"total_only": true, "summary_only": true}\n'
                '✅ Correct: {"total_only": true}'
            )

        return base_message

    def validate_output_format_exclusion(self, arguments: dict[str, Any]) -> None:
        """
        Validate that only one output format parameter is specified.

        Args:
            arguments: Tool arguments dictionary

        Raises:
            ValueError: If multiple output format parameters are specified
        """
        specified_formats = []

        for param in self.OUTPUT_FORMAT_PARAMS:
            if arguments.get(param, False):
                specified_formats.append(param)

        if len(specified_formats) > 1:
            error_message = self._get_error_message(specified_formats)
            raise ValueError(error_message)

    def get_active_format(self, arguments: dict[str, Any]) -> str:
        """
        Get the active output format from arguments.

        Args:
            arguments: Tool arguments dictionary

        Returns:
            Active format name or "normal" if none specified
        """
        for param in self.OUTPUT_FORMAT_PARAMS:
            if arguments.get(param, False):
                return param
        return "normal"


# Global validator instance
_default_validator: OutputFormatValidator | None = None


def get_default_validator() -> OutputFormatValidator:
    """Get the default output format validator instance."""
    global _default_validator
    if _default_validator is None:
        _default_validator = OutputFormatValidator()
    return _default_validator
