"""
helpers.py — Small presentation-agnostic formatting helpers.

Used by the progress panel (speed / elapsed / remaining time), the
history window, and log messages. Pure functions, fully unit-testable.
"""

from __future__ import annotations

from datetime import datetime

from utils.file_utils import human_readable_size


def format_duration(seconds: float) -> str:
    """Format seconds for display: 5 -> '5s', 65 -> '1m 05s', 3665 -> '1h 01m'."""
    if seconds < 0:
        raise ValueError("Duration cannot be negative")
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_speed(bytes_per_second: float) -> str:
    """Format a throughput value: 12582912 -> '12.0 MB/s'."""
    if bytes_per_second < 0:
        raise ValueError("Speed cannot be negative")
    return f"{human_readable_size(bytes_per_second)}/s"


def estimate_remaining(done_bytes: int, total_bytes: int, elapsed: float) -> float:
    """Estimate remaining seconds from progress so far (0.0 if unknowable)."""
    if done_bytes <= 0 or elapsed <= 0 or total_bytes <= done_bytes:
        return 0.0
    speed = done_bytes / elapsed
    return (total_bytes - done_bytes) / speed


def now_timestamp() -> str:
    """Current local time as 'YYYY-MM-DD HH:MM:SS' (history table format)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def truncate_middle(text: str, max_length: int = 60) -> str:
    """Shorten long paths for display: keep both ends, ellipsis in middle."""
    if max_length < 5:
        raise ValueError("max_length must be at least 5")
    if len(text) <= max_length:
        return text
    keep = max_length - 1
    head = (keep + 1) // 2
    tail = keep - head
    return f"{text[:head]}…{text[-tail:]}" if tail else f"{text[:head]}…"
