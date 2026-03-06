#!/usr/bin/env python3
"""
Large File Handler

Provides memory-efficient processing for large files (>100MB) through:
- Chunked file reading
- Streaming parsing
- Memory-bounded operations

Phase 3 Performance Enhancement.
"""

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generator, Optional

from ..utils import log_debug, log_info, log_warning


# Default chunk size: 10MB
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024

# Large file threshold: 100MB
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024


@dataclass
class ChunkInfo:
    """Information about a file chunk."""
    chunk_index: int
    start_byte: int
    end_byte: int
    size_bytes: int
    is_last: bool = False


@dataclass
class ChunkingStats:
    """Statistics for chunking operations."""
    files_chunked: int = 0
    total_chunks_processed: int = 0
    total_bytes_processed: int = 0
    memory_saved_mb: float = 0.0
    chunking_errors: int = 0


class LargeFileHandler:
    """
    Memory-efficient handler for large files.
    
    Provides chunked reading and processing to handle files that would
    otherwise exceed memory limits.
    
    Attributes:
        _chunk_size: Size of each chunk in bytes
        _threshold: File size threshold for chunking
        _stats: Chunking statistics
        _lock: Thread lock for statistics
    """
    
    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        large_file_threshold: int = LARGE_FILE_THRESHOLD,
    ) -> None:
        """
        Initialize large file handler.
        
        Args:
            chunk_size: Size of each chunk in bytes
            large_file_threshold: Threshold for chunking in bytes
        """
        self._chunk_size = chunk_size
        self._threshold = large_file_threshold
        self._stats = ChunkingStats()
        self._lock = threading.Lock()
        
        log_debug(
            f"LargeFileHandler initialized: chunk_size={chunk_size / 1024 / 1024:.1f}MB, "
            f"threshold={large_file_threshold / 1024 / 1024:.1f}MB"
        )
    
    def should_chunk(self, file_path: str | Path) -> bool:
        """
        Check if a file should be chunked.
        
        Args:
            file_path: Path to file
        
        Returns:
            True if file should be chunked
        """
        try:
            size = os.path.getsize(file_path)
            return size >= self._threshold
        except OSError:
            return False
    
    def get_file_size(self, file_path: str | Path) -> int:
        """
        Get file size in bytes.
        
        Args:
            file_path: Path to file
        
        Returns:
            File size in bytes
        """
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0
    
    def get_chunk_count(self, file_path: str | Path) -> int:
        """
        Calculate number of chunks for a file.
        
        Args:
            file_path: Path to file
        
        Returns:
            Number of chunks
        """
        size = self.get_file_size(file_path)
        if size == 0:
            return 0
        return (size + self._chunk_size - 1) // self._chunk_size
    
    def get_chunk_info(self, file_path: str | Path) -> list[ChunkInfo]:
        """
        Get information about all chunks for a file.
        
        Args:
            file_path: Path to file
        
        Returns:
            List of ChunkInfo objects
        """
        size = self.get_file_size(file_path)
        chunks: list[ChunkInfo] = []
        
        if size == 0:
            return chunks
        
        chunk_count = self.get_chunk_count(file_path)
        
        for i in range(chunk_count):
            start = i * self._chunk_size
            end = min((i + 1) * self._chunk_size, size)
            
            chunks.append(ChunkInfo(
                chunk_index=i,
                start_byte=start,
                end_byte=end,
                size_bytes=end - start,
                is_last=(i == chunk_count - 1),
            ))
        
        return chunks
    
    def read_chunk(
        self,
        file_path: str | Path,
        chunk_info: ChunkInfo,
        encoding: str = "utf-8",
    ) -> str:
        """
        Read a specific chunk from a file.
        
        Args:
            file_path: Path to file
            chunk_info: Chunk information
            encoding: File encoding
        
        Returns:
            Chunk content as string
        """
        try:
            with open(file_path, "rb") as f:
                f.seek(chunk_info.start_byte)
                data = f.read(chunk_info.size_bytes)
                
                with self._lock:
                    self._stats.total_chunks_processed += 1
                    self._stats.total_bytes_processed += len(data)
                
                return data.decode(encoding, errors="replace")
        except Exception as e:
            log_warning(f"Error reading chunk {chunk_info.chunk_index}: {e}")
            with self._lock:
                self._stats.chunking_errors += 1
            return ""
    
    def read_chunks(
        self,
        file_path: str | Path,
        encoding: str = "utf-8",
    ) -> Generator[tuple[ChunkInfo, str], None, None]:
        """
        Generator that yields chunks of a file.
        
        Args:
            file_path: Path to file
            encoding: File encoding
        
        Yields:
            Tuples of (ChunkInfo, chunk_content)
        """
        file_path = Path(file_path)
        
        if not self.should_chunk(file_path):
            # Small file - read all at once
            try:
                content = file_path.read_text(encoding=encoding)
                yield ChunkInfo(
                    chunk_index=0,
                    start_byte=0,
                    end_byte=len(content.encode(encoding)),
                    size_bytes=len(content.encode(encoding)),
                    is_last=True,
                ), content
            except Exception as e:
                log_warning(f"Error reading file: {e}")
            return
        
        # Large file - read in chunks
        with self._lock:
            self._stats.files_chunked += 1
        
        for chunk_info in self.get_chunk_info(file_path):
            content = self.read_chunk(file_path, chunk_info, encoding)
            yield chunk_info, content
    
    def process_chunked(
        self,
        file_path: str | Path,
        processor: Callable[[str, ChunkInfo], Any],
        encoding: str = "utf-8",
    ) -> list[Any]:
        """
        Process a file chunk-by-chunk.
        
        Args:
            file_path: Path to file
            processor: Function(chunk_content, chunk_info) -> result
            encoding: File encoding
        
        Returns:
            List of processor results for each chunk
        """
        results: list[Any] = []
        
        for chunk_info, content in self.read_chunks(file_path, encoding):
            try:
                result = processor(content, chunk_info)
                results.append(result)
            except Exception as e:
                log_warning(
                    f"Error processing chunk {chunk_info.chunk_index}: {e}"
                )
                results.append(None)
        
        return results
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get chunking statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "files_chunked": self._stats.files_chunked,
                "total_chunks_processed": self._stats.total_chunks_processed,
                "total_bytes_processed": self._stats.total_bytes_processed,
                "total_mb_processed": self._stats.total_bytes_processed / (1024 * 1024),
                "memory_saved_mb": self._stats.memory_saved_mb,
                "chunking_errors": self._stats.chunking_errors,
                "chunk_size_mb": self._chunk_size / (1024 * 1024),
                "threshold_mb": self._threshold / (1024 * 1024),
            }
    
    def estimate_memory_saved(self, file_path: str | Path) -> float:
        """
        Estimate memory saved by chunking a file.
        
        Args:
            file_path: Path to file
        
        Returns:
            Estimated memory saved in MB
        """
        size = self.get_file_size(file_path)
        
        if size < self._threshold:
            return 0.0
        
        # Without chunking: need to load entire file
        # With chunking: only need one chunk at a time
        saved = (size - self._chunk_size) / (1024 * 1024)
        
        with self._lock:
            self._stats.memory_saved_mb += saved
        
        return saved


# Singleton instance
_handler: Optional[LargeFileHandler] = None
_handler_lock = threading.Lock()


def get_large_file_handler(
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    threshold: int = LARGE_FILE_THRESHOLD,
) -> LargeFileHandler:
    """
    Get or create large file handler singleton.
    
    Args:
        chunk_size: Size of each chunk
        threshold: File size threshold
    
    Returns:
        LargeFileHandler instance
    """
    global _handler
    
    with _handler_lock:
        if _handler is None:
            _handler = LargeFileHandler(
                chunk_size=chunk_size,
                large_file_threshold=threshold,
            )
        return _handler
