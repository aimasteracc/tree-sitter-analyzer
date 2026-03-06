#!/usr/bin/env python3
"""
Progress Indicator System

Provides progress reporting with:
- Multiple indicator styles (bar, spinner, percent)
- Thread-safe updates
- Callback support
- ETA calculation

Phase 4 User Experience Enhancement.
"""

import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional


class ProgressStyle(Enum):
    """Progress indicator styles."""
    BAR = "bar"
    SPINNER = "spinner"
    PERCENT = "percent"
    DOTS = "dots"


@dataclass
class ProgressState:
    """Current state of progress."""
    current: int = 0
    total: int = 0
    message: str = ""
    start_time: Optional[float] = None
    last_update: Optional[float] = None


@dataclass
class ProgressStats:
    """Statistics for progress tracking."""
    items_processed: int = 0
    total_items: int = 0
    bytes_processed: int = 0
    total_bytes: int = 0
    errors: int = 0
    skipped: int = 0
    start_time: Optional[datetime] = None


class ProgressIndicator:
    """
    Thread-safe progress indicator.
    
    Provides visual feedback during long-running operations.
    
    Attributes:
        _style: Progress display style
        _state: Current progress state
        _lock: Thread lock
        _callback: Optional callback for progress updates
        _enabled: Whether output is enabled
    """
    
    # Spinner characters
    SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    
    # Bar characters
    BAR_FILL = "█"
    BAR_EMPTY = "░"
    BAR_WIDTH = 30
    
    def __init__(
        self,
        style: ProgressStyle = ProgressStyle.BAR,
        enabled: bool = True,
        callback: Optional[Callable[[int, int, str], None]] = None,
        update_interval: float = 0.1,
    ) -> None:
        """
        Initialize progress indicator.
        
        Args:
            style: Display style
            enabled: Whether to show progress
            callback: Callback(current, total, message)
            update_interval: Minimum interval between updates
        """
        self._style = style
        self._state = ProgressState()
        self._lock = threading.Lock()
        self._callback = callback
        self._enabled = enabled and sys.stdout.isatty()
        self._update_interval = update_interval
        self._spinner_index = 0
        self._stats = ProgressStats()
    
    def start(
        self,
        total: int,
        message: str = "Processing",
    ) -> None:
        """
        Start progress tracking.
        
        Args:
            total: Total items to process
            message: Initial message
        """
        with self._lock:
            self._state = ProgressState(
                current=0,
                total=total,
                message=message,
                start_time=time.time(),
                last_update=0,
            )
            self._stats = ProgressStats(
                start_time=datetime.now(),
                total_items=total,
            )
            self._spinner_index = 0
        
        self._display()
    
    def update(
        self,
        current: int,
        message: Optional[str] = None,
        increment: int = 1,
    ) -> None:
        """
        Update progress.
        
        Args:
            current: Current item count
            message: Optional message update
            increment: Items processed in this update
        """
        should_display = False
        
        with self._lock:
            self._state.current = current
            
            if message:
                self._state.message = message
            
            # Check if we should update display
            now = time.time()
            if (self._state.last_update is None or 
                now - self._state.last_update >= self._update_interval or
                current == self._state.total):
                self._state.last_update = now
                should_display = True
            
            self._stats.items_processed = current
        
        if should_display:
            self._display()
        
        if self._callback:
            self._callback(
                self._state.current,
                self._state.total,
                self._state.message,
            )
    
    def increment(self, message: Optional[str] = None) -> None:
        """
        Increment progress by 1.
        
        Args:
            message: Optional message update
        """
        with self._lock:
            new_current = self._state.current + 1
        
        self.update(new_current, message)
    
    def complete(self, message: str = "Complete") -> None:
        """
        Mark progress as complete.
        
        Args:
            message: Completion message
        """
        with self._lock:
            self._state.current = self._state.total
            self._state.message = message
        
        self._display()
        
        if self._enabled:
            # Print newline after progress
            print()
    
    def error(self, error_message: str) -> None:
        """
        Record an error.
        
        Args:
            error_message: Error description
        """
        with self._lock:
            self._stats.errors += 1
        
        self.update(self._state.current, f"Error: {error_message}")
    
    def skip(self, reason: str = "") -> None:
        """
        Record a skipped item.
        
        Args:
            reason: Reason for skipping
        """
        with self._lock:
            self._stats.skipped += 1
        
        self.increment(f"Skipped: {reason}" if reason else None)
    
    def _display(self) -> None:
        """Display current progress."""
        if not self._enabled:
            return
        
        with self._lock:
            state = ProgressState(
                current=self._state.current,
                total=self._state.total,
                message=self._state.message,
                start_time=self._state.start_time,
                last_update=self._state.last_update,
            )
        
        # Build progress string based on style
        if self._style == ProgressStyle.BAR:
            progress_str = self._format_bar(state)
        elif self._style == ProgressStyle.SPINNER:
            progress_str = self._format_spinner(state)
        elif self._style == ProgressStyle.PERCENT:
            progress_str = self._format_percent(state)
        else:
            progress_str = self._format_dots(state)
        
        # Add ETA if available
        eta_str = self._format_eta(state)
        if eta_str:
            progress_str = f"{progress_str} {eta_str}"
        
        # Clear line and print
        print(f"\r{progress_str}", end="", flush=True)
    
    def _format_bar(self, state: ProgressState) -> str:
        """Format progress bar."""
        if state.total == 0:
            percent = 0
        else:
            percent = state.current / state.total
        
        filled = int(self.BAR_WIDTH * percent)
        empty = self.BAR_WIDTH - filled
        
        bar = self.BAR_FILL * filled + self.BAR_EMPTY * empty
        percent_str = f"{percent * 100:5.1f}%"
        
        return f"{state.message}: [{bar}] {percent_str} ({state.current}/{state.total})"
    
    def _format_spinner(self, state: ProgressState) -> str:
        """Format spinner indicator."""
        char = self.SPINNER_CHARS[self._spinner_index % len(self.SPINNER_CHARS)]
        self._spinner_index += 1
        
        if state.total > 0:
            return f"{char} {state.message} ({state.current}/{state.total})"
        return f"{char} {state.message}"
    
    def _format_percent(self, state: ProgressState) -> str:
        """Format percentage indicator."""
        if state.total == 0:
            percent = 0
        else:
            percent = (state.current / state.total) * 100
        
        return f"{state.message}: {percent:5.1f}% ({state.current}/{state.total})"
    
    def _format_dots(self, state: ProgressState) -> str:
        """Format dots indicator."""
        dots = "." * (self._spinner_index % 4)
        self._spinner_index += 1
        
        if state.total > 0:
            return f"{state.message}{dots} ({state.current}/{state.total})"
        return f"{state.message}{dots}"
    
    def _format_eta(self, state: ProgressState) -> str:
        """Format estimated time remaining."""
        if state.start_time is None or state.current == 0:
            return ""
        
        if state.total == 0:
            return ""
        
        elapsed = time.time() - state.start_time
        if elapsed < 1:
            return ""
        
        rate = state.current / elapsed
        if rate < 0.001:
            return ""
        
        remaining = state.total - state.current
        eta_seconds = remaining / rate
        
        if eta_seconds < 60:
            return f"ETA: {eta_seconds:.0f}s"
        elif eta_seconds < 3600:
            return f"ETA: {eta_seconds / 60:.0f}m"
        else:
            return f"ETA: {eta_seconds / 3600:.1f}h"
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get progress statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            elapsed = 0.0
            if self._stats.start_time:
                elapsed = (datetime.now() - self._stats.start_time).total_seconds()
            
            return {
                "items_processed": self._stats.items_processed,
                "total_items": self._stats.total_items,
                "bytes_processed": self._stats.bytes_processed,
                "total_bytes": self._stats.total_bytes,
                "errors": self._stats.errors,
                "skipped": self._stats.skipped,
                "elapsed_seconds": elapsed,
                "items_per_second": (
                    self._stats.items_processed / elapsed if elapsed > 0 else 0
                ),
                "completion_percent": (
                    (self._stats.items_processed / self._stats.total_items * 100)
                    if self._stats.total_items > 0 else 0
                ),
            }


class BatchProgress:
    """
    Progress tracker for batch operations.
    
    Manages multiple sub-operations within a larger batch.
    
    Attributes:
        _indicator: Main progress indicator
        _operations: Dictionary of operation states
        _lock: Thread lock
    """
    
    def __init__(
        self,
        total_operations: int,
        style: ProgressStyle = ProgressStyle.BAR,
    ) -> None:
        """
        Initialize batch progress.
        
        Args:
            total_operations: Total operations in batch
            style: Progress display style
        """
        self._indicator = ProgressIndicator(style=style)
        self._operations: dict[str, ProgressState] = {}
        self._lock = threading.Lock()
        
        self._indicator.start(total_operations, "Batch processing")
    
    def start_operation(
        self,
        operation_id: str,
        total: int,
        message: str = "",
    ) -> None:
        """
        Start a sub-operation.
        
        Args:
            operation_id: Unique operation identifier
            total: Total items in operation
            message: Operation message
        """
        with self._lock:
            self._operations[operation_id] = ProgressState(
                current=0,
                total=total,
                message=message,
                start_time=time.time(),
            )
    
    def update_operation(
        self,
        operation_id: str,
        current: int,
        message: Optional[str] = None,
    ) -> None:
        """
        Update sub-operation progress.
        
        Args:
            operation_id: Operation identifier
            current: Current progress
            message: Optional message update
        """
        with self._lock:
            if operation_id in self._operations:
                self._operations[operation_id].current = current
                if message:
                    self._operations[operation_id].message = message
        
        # Update main progress
        total_current = sum(op.current for op in self._operations.values())
        self._indicator.update(total_current, message)
    
    def complete_operation(self, operation_id: str) -> None:
        """
        Complete a sub-operation.
        
        Args:
            operation_id: Operation identifier
        """
        with self._lock:
            if operation_id in self._operations:
                self._operations[operation_id].current = (
                    self._operations[operation_id].total
                )
        
        # Update main progress
        total_current = sum(op.current for op in self._operations.values())
        self._indicator.update(total_current)
    
    def complete_all(self, message: str = "Batch complete") -> None:
        """
        Complete all operations.
        
        Args:
            message: Completion message
        """
        self._indicator.complete(message)
    
    def get_operation_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get statistics for all operations.
        
        Returns:
            Dictionary of operation statistics
        """
        with self._lock:
            return {
                op_id: {
                    "current": op.current,
                    "total": op.total,
                    "percent": (op.current / op.total * 100) if op.total > 0 else 0,
                    "message": op.message,
                }
                for op_id, op in self._operations.items()
            }
