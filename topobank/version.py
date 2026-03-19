from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("topobank")
except PackageNotFoundError:
    __version__ = "unknown"
