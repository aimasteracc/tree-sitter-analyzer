"""
Encoding detection and safe file reading utilities.

This module provides:
- EncodingDetector: Automatic encoding detection and safe file reading
- EncodingCache: LRU cache for encoding detection results

Supports:
- UTF-8, UTF-16, UTF-32 (with and without BOM)
- Japanese: Shift_JIS, EUC-JP
- Chinese: GBK, GB2312, Big5
- Korean: CP949
- Western European: CP1252, ISO-8859-1
"""

import threading
from collections import OrderedDict
from collections.abc import Generator
from pathlib import Path

# Try to import chardet for advanced encoding detection
try:
    import chardet

    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False


class EncodingCache:
    """
    Thread-safe LRU cache for encoding detection results.

    Cache key format: "{absolute_path}:{mtime}"
    This ensures automatic invalidation when files are modified.
    """

    def __init__(self, max_size: int = 500):
        """
        Initialize encoding cache.

        Args:
            max_size: Maximum number of entries to cache
        """
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, file_path: str | Path) -> str | None:
        """
        Get cached encoding for file.

        Returns None if:
        - File not in cache
        - File was modified (mtime changed)

        Args:
            file_path: Path to file

        Returns:
            Cached encoding name or None
        """
        with self._lock:
            try:
                cache_key = self._get_cache_key(file_path)
                if cache_key in self._cache:
                    # Move to end (most recently used)
                    encoding = self._cache.pop(cache_key)
                    self._cache[cache_key] = encoding
                    return encoding
            except (OSError, FileNotFoundError):
                # File doesn't exist or can't be accessed
                pass
            return None

    def set(self, file_path: str | Path, encoding: str) -> None:
        """
        Cache encoding for file.

        Implements LRU eviction when cache is full.

        Args:
            file_path: Path to file
            encoding: Encoding name to cache
        """
        with self._lock:
            try:
                cache_key = self._get_cache_key(file_path)

                # Remove if already exists (will re-add at end)
                if cache_key in self._cache:
                    self._cache.pop(cache_key)

                # Add to end (most recently used)
                self._cache[cache_key] = encoding

                # Evict oldest if over max size
                if len(self._cache) > self._max_size:
                    self._cache.popitem(last=False)  # Remove oldest (first item)
            except (OSError, FileNotFoundError):
                # Can't cache if file doesn't exist
                pass

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def _get_cache_key(self, file_path: str | Path) -> str:
        """
        Generate cache key: "{path}:{mtime}".

        Args:
            file_path: Path to file

        Returns:
            Cache key string
        """
        path = Path(file_path).resolve()
        mtime = path.stat().st_mtime
        return f"{path}:{mtime}"


class EncodingDetector:
    """
    Detect file encoding and provide safe file reading.

    Detection strategy:
    1. Check cache (if enabled)
    2. Detect BOM (Byte Order Mark)
    3. Try UTF-8 decode
    4. Use chardet library (if available)
    5. Fallback to encoding list

    Always returns a valid encoding - never raises exceptions.
    """

    # Class-level cache (shared across instances)
    _cache: EncodingCache | None = None

    # Fallback encodings in priority order
    FALLBACK_ENCODINGS = [
        "utf-8",
        "shift_jis",  # Japanese
        "euc-jp",  # Japanese
        "gbk",  # Chinese (Simplified)
        "gb2312",  # Chinese (older)
        "big5",  # Chinese (Traditional)
        "cp1252",  # Windows Western European
        "iso-8859-1",  # Latin-1
        "cp949",  # Korean
        "utf-16",
        "utf-16-le",
        "utf-16-be",
    ]

    # BOM (Byte Order Mark) signatures
    BOM_SIGNATURES = {
        b"\xef\xbb\xbf": "utf-8",
        b"\xff\xfe\x00\x00": "utf-32-le",
        b"\x00\x00\xfe\xff": "utf-32-be",
        b"\xff\xfe": "utf-16-le",
        b"\xfe\xff": "utf-16-be",
    }

    def __init__(self, enable_cache: bool = True):
        """
        Initialize encoding detector.

        Args:
            enable_cache: Whether to enable encoding cache
        """
        if enable_cache and EncodingDetector._cache is None:
            EncodingDetector._cache = EncodingCache(max_size=500)
        self._enable_cache = enable_cache

    def detect_encoding(
        self,
        file_path: str | Path,
        sample_size: int = 32768,  # 32KB sample
    ) -> str:
        """
        Detect file encoding.

        Always returns a valid encoding name, never raises exceptions.

        Args:
            file_path: Path to file
            sample_size: Number of bytes to read for detection

        Returns:
            Encoding name (e.g., 'utf-8', 'shift_jis')
        """
        file_path = Path(file_path)

        # Check cache first
        if self._enable_cache and self._cache:
            cached = self._cache.get(file_path)
            if cached:
                return cached

        try:
            # Read sample
            with open(file_path, "rb") as f:
                sample = f.read(sample_size)

            if not sample:
                # Empty file - default to UTF-8
                encoding = "utf-8"
            else:
                # Try detection strategies
                encoding = (
                    self._detect_bom(sample)
                    or self._try_utf8(sample)
                    or self._use_chardet(sample)
                    or self._try_fallbacks(sample)
                    or "utf-8"  # Last resort
                )

            # Cache result
            if self._enable_cache and self._cache:
                self._cache.set(file_path, encoding)

            return encoding

        except Exception:
            # If anything goes wrong, default to UTF-8
            return "utf-8"

    def read_file_safe(
        self, file_path: str | Path, fallback_encoding: str = "utf-8", errors: str = "replace"
    ) -> str:
        """
        Read entire file with automatic encoding detection.

        For files < 10MB. For larger files, use read_file_streaming().

        Args:
            file_path: Path to file
            fallback_encoding: Encoding to use if detection fails
            errors: How to handle encoding errors ('replace', 'ignore', 'strict')

        Returns:
            File content as string
        """
        file_path = Path(file_path)

        # Detect encoding
        try:
            encoding = self.detect_encoding(file_path)
        except Exception:
            encoding = fallback_encoding

        # Read file with detected encoding
        try:
            with open(file_path, encoding=encoding, errors=errors) as f:
                return f.read()
        except Exception:
            # Fallback to specified encoding
            with open(file_path, encoding=fallback_encoding, errors=errors) as f:
                return f.read()

    def read_file_streaming(
        self, file_path: str | Path, chunk_size: int = 8192
    ) -> Generator[str, None, None]:
        """
        Stream file content line by line (memory-efficient).

        For files > 10MB. Memory usage: O(1) regardless of file size.

        Args:
            file_path: Path to file
            chunk_size: Size of chunks to read (not used for line iteration)

        Yields:
            Lines from file
        """
        file_path = Path(file_path)

        # Detect encoding from small sample
        encoding = self.detect_encoding(file_path)

        # Open file and yield lines
        try:
            with open(file_path, encoding=encoding, errors="replace") as f:
                yield from f
        except Exception:
            # Fallback to UTF-8
            with open(file_path, encoding="utf-8", errors="replace") as f:
                yield from f

    def _detect_bom(self, data: bytes) -> str | None:
        """
        Detect BOM (Byte Order Mark) signature.

        Args:
            data: File sample bytes

        Returns:
            Encoding name if BOM detected, None otherwise
        """
        # Check BOMs in order of longest to shortest
        for bom, encoding in sorted(
            self.BOM_SIGNATURES.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if data.startswith(bom):
                return encoding
        return None

    def _try_utf8(self, data: bytes) -> str | None:
        """
        Try to decode as UTF-8.

        Args:
            data: File sample bytes

        Returns:
            'utf-8' if successful, None otherwise
        """
        try:
            data.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            return None

    def _use_chardet(self, data: bytes) -> str | None:
        """
        Use chardet library for detection (if available).

        Args:
            data: File sample bytes

        Returns:
            Detected encoding if confidence > 0.7, None otherwise
        """
        if not HAS_CHARDET:
            return None

        try:
            result = chardet.detect(data)
            if result and result.get("confidence", 0) > 0.7:
                encoding = result.get("encoding")
                if encoding:
                    return encoding.lower()
        except Exception:
            pass

        return None

    def _try_fallbacks(self, data: bytes) -> str | None:
        """
        Try fallback encodings in priority order.

        Args:
            data: File sample bytes

        Returns:
            First successful encoding or None
        """
        for encoding in self.FALLBACK_ENCODINGS:
            try:
                data.decode(encoding)
                return encoding
            except (UnicodeDecodeError, LookupError):
                continue
        return None
