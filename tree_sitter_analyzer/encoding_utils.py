#!/usr/bin/env python3
"""
Optimized Encoding Utilities Module

This module provides unified encoding/decoding functionality with performance
optimizations including file-based encoding caching to reduce redundant
chardet.detect() calls.
"""

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


# Set up encoding environment early
def _setup_encoding_environment() -> None:
    """Set up proper encoding environment"""
    try:
        os.environ["PYTHONIOENCODING"] = "utf-8"
        os.environ["PYTHONUTF8"] = "1"

        # Ensure proper stdout/stderr encoding if possible
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as e:
        # Ignore setup errors, use defaults; log at debug when possible
        msg = f"[encoding_setup] non-fatal setup error: {e}\n"
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            try:
                sys.stderr.write(msg)
            except Exception:
                # Swallow secondary I/O errors intentionally
                ...


# Set up environment when module is imported
_setup_encoding_environment()

# Try to import chardet with fallback
try:
    import chardet

    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False

# Import utilities with fallback
try:
    from .utils import log_debug, log_warning
except ImportError:
    # Fallback logging functions with compatible signatures
    def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
        print(f"DEBUG: {message}")

    def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
        print(f"WARNING: {message}")


class EncodingCache:
    """Thread-safe encoding cache for file-based encoding detection optimization"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize encoding cache

        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self._cache: dict[
            str, tuple[str, float]
        ] = {}  # file_path -> (encoding, timestamp)
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def get(self, file_path: str) -> str | None:
        """
        Get cached encoding for file path

        Args:
            file_path: Path to the file

        Returns:
            Cached encoding or None if not found/expired
        """
        with self._lock:
            if file_path not in self._cache:
                return None

            encoding, timestamp = self._cache[file_path]
            current_time = time.time()

            # Check if entry has expired
            if current_time - timestamp > self._ttl_seconds:
                del self._cache[file_path]
                return None

            return encoding

    def set(self, file_path: str, encoding: str) -> None:
        """
        Cache encoding for file path

        Args:
            file_path: Path to the file
            encoding: Detected encoding
        """
        with self._lock:
            current_time = time.time()

            # Clean up expired entries if cache is getting full
            if len(self._cache) >= self._max_size:
                self._cleanup_expired()

            # If still full after cleanup, remove oldest entry
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            self._cache[file_path] = (encoding, current_time)

    def _cleanup_expired(self) -> None:
        """Remove expired entries from cache"""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if current_time - timestamp > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cached entries"""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Get current cache size"""
        with self._lock:
            return len(self._cache)


# Global encoding cache instance
_encoding_cache = EncodingCache()


class EncodingManager:
    """Centralized encoding management for consistent text processing"""

    DEFAULT_ENCODING = "utf-8"
    FALLBACK_ENCODINGS = ["utf-8", "cp1252", "iso-8859-1", "shift_jis", "gbk"]

    @classmethod
    def safe_encode(cls, text: str | None, encoding: str | None = None) -> bytes:
        """
        Safely encode text to bytes with fallback handling

        Args:
            text: Text to encode (can be None)
            encoding: Target encoding (defaults to UTF-8)

        Returns:
            Encoded bytes
        """
        # Handle None input
        if text is None:
            return b""

        target_encoding = encoding or cls.DEFAULT_ENCODING

        try:
            return text.encode(target_encoding)
        except UnicodeEncodeError as e:
            log_debug(f"Failed to encode with {target_encoding}, trying fallbacks: {e}")

            # Try fallback encodings
            for fallback in cls.FALLBACK_ENCODINGS:
                if fallback != target_encoding:
                    try:
                        return text.encode(fallback, errors="replace")
                    except UnicodeEncodeError:
                        continue

            # Last resort: encode with error replacement
            log_warning(f"Using error replacement for encoding: {text[:50]}...")
            return text.encode(cls.DEFAULT_ENCODING, errors="replace")

    @classmethod
    def safe_decode(cls, data: bytes, encoding: str | None = None) -> str:
        """
        Safely decode bytes to text with fallback handling

        Args:
            data: Bytes to decode
            encoding: Source encoding (auto-detected if None)

        Returns:
            Decoded text
        """
        if data is None or len(data) == 0:
            return ""

        # Use provided encoding or detect
        target_encoding = encoding
        if not target_encoding:
            target_encoding = cls.detect_encoding(data)

        try:
            return data.decode(target_encoding)
        except UnicodeDecodeError as e:
            log_debug(f"Failed to decode with {target_encoding}, trying fallbacks: {e}")

            # Try fallback encodings
            for fallback in cls.FALLBACK_ENCODINGS:
                if fallback != target_encoding:
                    try:
                        return data.decode(fallback, errors="replace")
                    except UnicodeDecodeError:
                        continue

            # Last resort: decode with error replacement
            log_warning(
                f"Using error replacement for decoding data (length: {len(data)})"
            )
            return data.decode(cls.DEFAULT_ENCODING, errors="replace")

    @classmethod
    def detect_encoding(cls, data: bytes, file_path: str | None = None) -> str:
        """
        Detect encoding of byte data with optional file-based caching

        Args:
            data: Bytes to analyze
            file_path: Optional file path for caching (improves performance)

        Returns:
            Detected encoding name
        """
        if not data:
            return cls.DEFAULT_ENCODING

        # Check cache first if file_path is provided
        if file_path:
            cached_encoding = _encoding_cache.get(file_path)
            if cached_encoding:
                log_debug(f"Using cached encoding for {file_path}: {cached_encoding}")
                return cached_encoding

        detected_encoding = cls.DEFAULT_ENCODING

        # If chardet is not available, use simple heuristics
        if not CHARDET_AVAILABLE:
            try:
                # Try UTF-8 first
                data.decode("utf-8")
                detected_encoding = "utf-8"
            except UnicodeDecodeError:
                # Check for BOM
                if data.startswith(b"\xff\xfe"):
                    detected_encoding = "utf-16-le"
                elif data.startswith(b"\xfe\xff"):
                    detected_encoding = "utf-16-be"
                elif data.startswith(b"\xef\xbb\xbf"):
                    detected_encoding = "utf-8-sig"
                else:
                    detected_encoding = cls.DEFAULT_ENCODING
        else:
            try:
                # Use chardet for detection
                detection = chardet.detect(data)
                if detection and detection["encoding"]:
                    confidence = detection.get("confidence", 0)
                    detected_encoding = detection["encoding"].lower()

                    # Only trust high-confidence detections
                    if confidence > 0.7:
                        log_debug(
                            f"Detected encoding: {detected_encoding} (confidence: {confidence:.2f})"
                        )
                    else:
                        log_debug(
                            f"Low confidence encoding detection: {detected_encoding} (confidence: {confidence:.2f}), using default"
                        )
                        detected_encoding = cls.DEFAULT_ENCODING

            except Exception as e:
                log_debug(f"Encoding detection failed: {e}")
                detected_encoding = cls.DEFAULT_ENCODING

        # Cache the result if file_path is provided
        if file_path and detected_encoding:
            _encoding_cache.set(file_path, detected_encoding)
            log_debug(f"Cached encoding for {file_path}: {detected_encoding}")

        return detected_encoding

    @classmethod
    def read_file_safe(cls, file_path: str | Path) -> tuple[str, str]:
        """
        Safely read a file with automatic encoding detection and caching

        Args:
            file_path: Path to the file

        Returns:
            Tuple of (content, detected_encoding)
        """
        file_path = Path(file_path)

        try:
            # Read raw bytes first
            with open(file_path, "rb") as f:
                raw_data = f.read()

            if not raw_data:
                return "", cls.DEFAULT_ENCODING

            # Detect and decode with file path for caching
            detected_encoding = cls.detect_encoding(raw_data, str(file_path))
            content = cls.safe_decode(raw_data, detected_encoding)

            # Normalize line endings for consistency
            content = cls.normalize_line_endings(content)

            return content, detected_encoding

        except OSError as e:
            log_warning(f"Failed to read file {file_path}: {e}")
            raise e

    @classmethod
    def write_file_safe(
        cls, file_path: str | Path, content: str, encoding: str | None = None
    ) -> bool:
        """
        Safely write content to a file

        Args:
            file_path: Path to the file
            content: Content to write
            encoding: Target encoding (defaults to UTF-8)

        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)
        target_encoding = encoding or cls.DEFAULT_ENCODING

        try:
            encoded_content = cls.safe_encode(content, target_encoding)

            with open(file_path, "wb") as f:
                f.write(encoded_content)

            return True

        except OSError as e:
            log_warning(f"Failed to write file {file_path}: {e}")
            return False

    @classmethod
    def normalize_line_endings(cls, text: str) -> str:
        """
        Normalize line endings to Unix style (\n)

        Args:
            text: Text to normalize

        Returns:
            Text with normalized line endings
        """
        if not text:
            return text

        # Replace Windows (\r\n) and Mac (\r) line endings with Unix (\n)
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @classmethod
    def extract_text_slice(
        cls,
        content_bytes: bytes,
        start_byte: int,
        end_byte: int,
        encoding: str | None = None,
    ) -> str:
        """
        Extract a slice of text from bytes with proper encoding handling

        Args:
            content_bytes: Source bytes
            start_byte: Start position
            end_byte: End position
            encoding: Encoding to use (auto-detected if None)

        Returns:
            Extracted text slice
        """
        if not content_bytes or start_byte >= len(content_bytes):
            return ""

        # Ensure bounds are valid
        start_byte = max(0, start_byte)
        end_byte = min(len(content_bytes), end_byte)

        if start_byte >= end_byte:
            return ""

        # Extract byte slice
        byte_slice = content_bytes[start_byte:end_byte]

        # Decode the slice
        return cls.safe_decode(byte_slice, encoding)


# Convenience functions for backward compatibility
def safe_encode(text: str, encoding: str | None = None) -> bytes:
    """Convenience function for safe encoding"""
    return EncodingManager.safe_encode(text, encoding)


def safe_decode(data: bytes, encoding: str | None = None) -> str:
    """Convenience function for safe decoding"""
    return EncodingManager.safe_decode(data, encoding)


def detect_encoding(data: bytes, file_path: str | None = None) -> str:
    """Convenience function for encoding detection with optional caching"""
    return EncodingManager.detect_encoding(data, file_path)


def read_file_safe(file_path: str | Path) -> tuple[str, str]:
    """Convenience function for safe file reading"""
    return EncodingManager.read_file_safe(file_path)


def write_file_safe(
    file_path: str | Path, content: str, encoding: str | None = None
) -> bool:
    """Convenience function for safe file writing"""
    return EncodingManager.write_file_safe(file_path, content, encoding)


def extract_text_slice(
    content_bytes: bytes, start_byte: int, end_byte: int, encoding: str | None = None
) -> str:
    """Convenience function for text slice extraction"""
    return EncodingManager.extract_text_slice(
        content_bytes, start_byte, end_byte, encoding
    )


def clear_encoding_cache() -> None:
    """Clear the global encoding cache"""
    _encoding_cache.clear()


def get_encoding_cache_size() -> int:
    """Get the current size of the encoding cache"""
    return _encoding_cache.size()
