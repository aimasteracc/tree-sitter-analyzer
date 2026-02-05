"""
Language detection from file paths and content.

This module provides language detection capabilities using multiple signals:
- File extension
- Shebang line
- Content patterns

Confidence scores indicate detection certainty.
"""

import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.types import SupportedLanguage


class LanguageDetector:
    """
    Detect programming language from file path and content.

    Uses multiple detection strategies with confidence scoring:
    - Extension matching (highest confidence)
    - Shebang detection (medium confidence)
    - Content pattern matching (lower confidence)
    """

    # Shebang patterns for language detection
    SHEBANG_PATTERNS = {
        "python": [
            r"#!/usr/bin/env python",
            r"#!/usr/bin/python",
            r"#!/usr/local/bin/python",
        ],
        "javascript": [
            r"#!/usr/bin/env node",
            r"#!/usr/bin/node",
        ],
    }

    # Content patterns for language detection
    CONTENT_PATTERNS = {
        "python": [
            r"^import\s+\w+",
            r"^from\s+\w+\s+import",
            r"^def\s+\w+\s*\(",
            r"^class\s+\w+",
        ],
        "java": [
            r"^public\s+class\s+\w+",
            r"^class\s+\w+",
            r"^public\s+static\s+void\s+main",
            r"System\.out\.println",
        ],
        "typescript": [
            r"^interface\s+\w+",
            r":\s*(string|number|boolean)",
            r"^type\s+\w+\s*=",
            r"^export\s+(interface|type|class)",
        ],
        "javascript": [
            r"^const\s+\w+\s*=",
            r"^let\s+\w+\s*=",
            r"^function\s+\w+\s*\(",
            r"console\.log",
        ],
    }

    def detect_from_path(self, file_path: str) -> dict[str, Any] | None:
        """
        Detect language from file path (extension only).

        Args:
            file_path: Path to file (can be relative or absolute)

        Returns:
            Dict with language, confidence, method, or None if unknown
        """
        # Extract extension
        path = Path(file_path)
        extension = path.suffix

        if not extension:
            return None

        # Try to match extension
        lang = SupportedLanguage.from_extension(extension)
        if lang:
            return {
                "language": lang.name,
                "confidence": 0.9,
                "method": "extension",
            }

        return None

    def detect_from_content(
        self,
        content: str,
        filename: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Detect language from file content.

        Uses multiple signals: extension, shebang, content patterns.

        Args:
            content: File content
            filename: Optional filename for extension detection

        Returns:
            Dict with language, confidence, method, or None if unknown
        """
        signals: list[tuple[str, str, float]] = []  # (language, method, confidence)

        # 1. Try extension if filename provided
        extension_lang = None
        if filename:
            result = self.detect_from_path(filename)
            if result:
                extension_lang = result["language"]
                signals.append((extension_lang, "extension", 0.9))

        # 2. Try shebang detection (first line)
        if content:
            first_line = content.split("\n")[0] if content else ""
            shebang_lang = self._detect_shebang(first_line)
            if shebang_lang:
                signals.append((shebang_lang, "shebang", 0.8))

        # 3. Try content pattern matching
        if content:
            content_lang = self._detect_content_patterns(content)
            if content_lang:
                signals.append((content_lang, "content", 0.6))

        # No signals found
        if not signals:
            return None

        # Combine signals
        return self._combine_signals(signals)

    def _detect_shebang(self, first_line: str) -> str | None:
        """
        Detect language from shebang line.

        Args:
            first_line: First line of file

        Returns:
            Language name or None
        """
        if not first_line.startswith("#!"):
            return None

        # Check each language's shebang patterns
        for language, patterns in self.SHEBANG_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, first_line):
                    return language

        return None

    def _detect_content_patterns(self, content: str) -> str | None:
        """
        Detect language from content patterns.

        Args:
            content: File content

        Returns:
            Language name or None
        """
        # Score each language based on pattern matches
        scores: dict[str, int] = {}

        for language, patterns in self.CONTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                # Use MULTILINE to match patterns at line start
                if re.search(pattern, content, re.MULTILINE):
                    score += 1

            if score > 0:
                scores[language] = score

        # No matches
        if not scores:
            return None

        # Return language with highest score
        best_language = max(scores.items(), key=lambda x: x[1])
        return best_language[0]

    def _combine_signals(self, signals: list[tuple[str, str, float]]) -> dict[str, Any]:
        """
        Combine multiple detection signals into final result.

        Args:
            signals: List of (language, method, confidence) tuples

        Returns:
            Detection result dict
        """
        # If only one signal, return it
        if len(signals) == 1:
            lang, method, conf = signals[0]
            return {
                "language": lang,
                "confidence": conf,
                "method": method,
            }

        # Multiple signals - prefer extension if present
        extension_signal = None
        shebang_signal = None
        content_signal = None

        for lang, method, conf in signals:
            if method == "extension":
                extension_signal = (lang, method, conf)
            elif method == "shebang":
                shebang_signal = (lang, method, conf)
            elif method == "content":
                content_signal = (lang, method, conf)

        # Extension takes priority
        if extension_signal:
            lang, _, _ = extension_signal

            # Check if other signals agree
            agreement_count = 1  # Extension itself
            if shebang_signal and shebang_signal[0] == lang:
                agreement_count += 1
            if content_signal and content_signal[0] == lang:
                agreement_count += 1

            # More agreement = higher confidence
            if agreement_count == 3:
                confidence = 0.98
            elif agreement_count == 2:
                confidence = 0.95
            else:
                confidence = 0.9

            return {
                "language": lang,
                "confidence": confidence,
                "method": "combined" if agreement_count > 1 else "extension",
            }

        # No extension - use shebang if available
        if shebang_signal:
            lang, method, conf = shebang_signal

            # Check if content agrees
            if content_signal and content_signal[0] == lang:
                return {
                    "language": lang,
                    "confidence": 0.85,
                    "method": "combined",
                }

            return {
                "language": lang,
                "confidence": conf,
                "method": method,
            }

        # Only content signal
        if content_signal:
            lang, method, conf = content_signal
            return {
                "language": lang,
                "confidence": conf,
                "method": method,
            }

        # Shouldn't reach here, but return first signal as fallback
        lang, method, conf = signals[0]
        return {
            "language": lang,
            "confidence": conf,
            "method": method,
        }
