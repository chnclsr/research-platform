"""Runtime version sourced from the installed package metadata."""

from importlib.metadata import PackageNotFoundError, version

_DISTRIBUTION = "research-platform"

try:
    VERSION = version(_DISTRIBUTION)
except PackageNotFoundError:  # pragma: no cover - only an unpackaged source tree
    VERSION = "0+unknown"

__version__ = VERSION
