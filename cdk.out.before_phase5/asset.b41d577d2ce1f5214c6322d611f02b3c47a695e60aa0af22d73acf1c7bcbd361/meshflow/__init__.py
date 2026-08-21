"""Meshflow CLI meta-package (extends the shared ``meshflow`` namespace)."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
