"""Silver layer: consolidate append-only bronze runs into single entity tables."""

from hiveflow.silver.consolidate import consolidate_source

__all__ = ["consolidate_source"]
