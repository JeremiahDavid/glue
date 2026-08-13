"""Small runtime compatibility helpers shared across deploy targets."""

from __future__ import annotations

from datetime import timezone

try:
    from datetime import UTC
except ImportError:  # Python < 3.11 (Glue Python Shell 3.9)
    UTC = timezone.utc

__all__ = ["UTC"]
