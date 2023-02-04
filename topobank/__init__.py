try:
    from importlib.metadata import version
    __version__ = version("topobank")
except PackageNotFoundError:
    from setuptools_scm import get_version
    __version__ = get_version()
