"""
physcheck package root.

This module exposes the high-level API surface for URDF analysis tooling.
"""

from importlib.metadata import version, PackageNotFoundError


def __getattr__(name: str) -> str:
    if name == "__version__":
        try:
            return version("physcheck")
        except PackageNotFoundError:
            return "0.0.0"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["__version__"]
